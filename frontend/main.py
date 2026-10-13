"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Why A2A: agents-cli 1.1.0 (GA) deploys ADK agents to Agent Runtime as A2A agents
and no longer registers the reasoning-engine operation schema the old
`agent_engines.get(...).stream_query()` path relied on (operation_schemas() comes
back empty). The container serves the A2A protocol over the Agent Engine HTTP
passthrough, so this proxy fetches the agent's card and sends messages with the
a2a-sdk client (the same path `agents-cli run --mode a2a` uses). This works for
both A2A and plain ADK 1.1.0 deployments (the container serves A2A either way).

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

import datetime
import logging
import os
import time
import uuid

import google.auth
import google.auth.transport.requests
import httpx

try:
    from a2a.client import ClientConfig, ClientFactory
except ImportError:
    ClientConfig, ClientFactory = None, None

try:
    from a2a.types import (
        AgentCard,
        FilePart,
        Message,
        Part,
        Role,
        TaskArtifactUpdateEvent,
        TextPart,
        TransportProtocol,
    )
except ImportError:
    from a2a.types import AgentCard, Message, Part, Role, TaskArtifactUpdateEvent
    FilePart = None
    TextPart = None
    TransportProtocol = None

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ.get(
    "AGENT_ENGINE_RESOURCE_NAME",
    "projects/257485218858/locations/us-east1/reasoningEngines/4938809419388420096",
)
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}],
            "metadata": {"status": "error", "error": str(exc)},
        },
    )


_STARTUP_TIME = time.time()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smart_real_estate_proxy")


@app.post("/reset")
async def reset_session(req: Request):
    """Explicitly reset a conversation context for a given user or session ID."""
    try:
        body = await req.json()
        user_id = (body.get("user_id") or "web-user").strip()
    except Exception:
        user_id = "web-user"
    if user_id in _contexts:
        del _contexts[user_id]
    return JSONResponse({"status": "ok", "message": "Context reset successfully"})


@app.get("/health")
async def health():
    """Liveness and readiness check for Cloud Run and monitoring systems."""
    uptime_seconds = int(time.time() - _STARTUP_TIME)
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "model": "gemini-3.8-flash",
            "uptime_seconds": uptime_seconds,
            "agent_engine_resource": RESOURCE,
            "agent_directory": AGENT_DIRECTORY,
            "active_contexts": len(_contexts),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = AgentCard(**resp.json())
        # Agent Runtime does not serve a public card URL, so point the client at
        # the passthrough base for message sends.
        card.url = A2A_BASE
        _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI.

    Text parts pass through as {"kind": "text"}. A2UI data parts (tagged
    application/json+a2ui) become {"kind": "a2ui", "data": <message>} so the UI
    renders the card; each data part is one A2UI message (beginRendering or
    surfaceUpdate).
    """
    out: list[dict] = []
    for p in parts:
        root = getattr(p, "root", p)
        if (isinstance(root, TextPart) or hasattr(root, "text")) and getattr(root, "text", None):
            out.append({"kind": "text", "text": root.text})
        elif getattr(root, "data", None) is not None:
            data_payload = root.data
            if isinstance(data_payload, dict):
                inner_meta = data_payload.get("metadata") or {}
                inner_mime = (
                    inner_meta.get("mimeType") if isinstance(inner_meta, dict) else None
                )
                if inner_mime == _A2UI_MIME:
                    inner_data = data_payload.get("data", data_payload)
                    out.append({"kind": "a2ui", "data": inner_data})
                    continue
                if any(
                    k in data_payload
                    for k in ("beginRendering", "surfaceUpdate", "dataModelUpdate")
                ):
                    out.append({"kind": "a2ui", "data": data_payload})
                    continue

            meta = getattr(root, "metadata", None) or {}
            mime = meta.get("mimeType") if isinstance(meta, dict) else None
            if mime == _A2UI_MIME:
                out.append({"kind": "a2ui", "data": root.data})
        elif isinstance(root, FilePart):
            uri = getattr(getattr(root, "file", None), "uri", None)
            if uri:
                out.append({"kind": "text", "text": uri})
    return out


@app.post("/chat")
async def chat(req: Request):
    start_ts = time.time()
    task_id = f"task_{uuid.uuid4().hex[:8]}"

    try:
        body = await req.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body", "task_id": task_id, "parts": []},
        )

    message = (body.get("message") or "").strip()
    user_id = (body.get("user_id") or "web-user").strip()

    if not message:
        return JSONResponse(
            status_code=400,
            content={"error": "Message cannot be empty", "task_id": task_id, "parts": []},
        )

    if len(message) > 4000:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Message exceeds maximum allowed length of 4,000 characters.",
                "task_id": task_id,
                "parts": [],
            },
        )

    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(
            ClientConfig(
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
                httpx_client=client,
            )
        )
        a2a_client = factory.create(card)

        async def _send_and_collect(ctx_id: str | None):
            art_parts: list[dict] = []
            stat_parts: list[dict] = []
            lt = None
            m = Message(
                message_id=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=message))],
                context_id=ctx_id,
            )
            async for event in a2a_client.send_message(m):
                if not isinstance(event, tuple):
                    continue
                t, u = event
                if t is not None:
                    lt = t
                    if getattr(t, "context_id", None):
                        _contexts[user_id] = t.context_id
                if isinstance(u, TaskArtifactUpdateEvent):
                    art_parts.extend(_extract_parts(u.artifact.parts))
                elif getattr(u, "status", None) and getattr(u.status, "message", None):
                    msg_obj = u.status.message
                    if getattr(msg_obj, "parts", None):
                        stat_parts.extend(_extract_parts(msg_obj.parts))
            return art_parts, stat_parts, lt

        try:
            artifact_parts, status_parts, last_task = await _send_and_collect(_contexts.get(user_id))
        except Exception as e:
            logger.warning(
                f"Error sending message with context {_contexts.get(user_id)}: {e}. Retrying with fresh context."
            )
            if user_id in _contexts:
                del _contexts[user_id]
            artifact_parts, status_parts, last_task = await _send_and_collect(None)

        # Collect text parts first, followed by A2UI card parts, avoiding duplicates
        for sp in status_parts:
            if sp not in parts:
                parts.append(sp)
        if artifact_parts:
            for ap in artifact_parts:
                if ap not in parts:
                    parts.append(ap)

        # Non-streaming fallback: pull parts from the final task's artifacts or history if still empty
        if not parts and last_task is not None:
            for artifact in getattr(last_task, "artifacts", None) or []:
                parts.extend(_extract_parts(artifact.parts))
            if not parts:
                for hist_msg in reversed(getattr(last_task, "history", None) or []):
                    if getattr(hist_msg, "role", None) == Role.agent and getattr(hist_msg, "parts", None):
                        parts.extend(_extract_parts(hist_msg.parts))
                        if parts:
                            break

    if not parts:
        # The turn produced no text or UI (e.g. the agent only ran tools, or a
        # tool stalled). Be honest rather than silent.
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]

    execution_time_ms = int((time.time() - start_ts) * 1000)
    return JSONResponse(
        {
            "parts": parts,
            "metadata": {
                "task_id": task_id,
                "execution_time_ms": execution_time_ms,
                "status": "complete",
                "model": "gemini-3.8-flash",
            },
        }
    )


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.get("/")
async def root():
    return FileResponse(
        os.path.join(STATIC_DIR, "index.html"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# Serve the chat UI (keep this mount last so /chat and / win).
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
