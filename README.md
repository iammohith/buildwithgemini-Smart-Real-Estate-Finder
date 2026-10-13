# Smart Real Estate Finder 🏡

> *This project was developed during the Build with Gemini session held in Hyderabad on 13 October 2026.*

A conversational real estate advisory agent built with Google's **Agent Development Kit (ADK)**, powered by Google's flagship **Gemini 3.8 Flash** (`gemini-3.8-flash`) model, and deployed on **Google Cloud Agent Platform**. 

Smart Real Estate Finder helps home seekers discover, evaluate, visualize, and tour properties from a curated catalog. It combines **Gemini 3.8 Flash** for intelligent conversational reasoning and tool calling with cross-session memory, safe Python sandbox financial calculations, multimodal image and video generation, Google Maps location intelligence, and rich agent-driven UI (A2UI) cards.

---

## 🌟 Key Capabilities & Features

Based directly on the implementation in `app/agent.py` and `agents-cli-manifest.yaml`, the agent provides the following capabilities:

### 0. Intelligent Agent Foundation (Gemini 3.8 Flash)
- **Primary Reasoning Model (`gemini-3.8-flash`)**: Drives the multi-turn conversational advisory loop, tool selection, parameter extraction, and context-aware responses with state-of-the-art speed and reasoning fidelity.
- **Robust Tool Orchestration**: Intelligently coordinates between 14 domain tools across Firestore, Maps, Sandbox Code Execution, and Multimodal GenAI models.

### 1. Curated Property Search & Management (Cloud Firestore)
- **Catalog Search (`search_properties`)**: Queries Firestore for properties filtered by city, price range, bedrooms, bathrooms, property type (Single Family, Condo, Townhouse), and pet-friendliness.
- **Detailed Property Breakdown (`get_property_details`)**: Retrieves complete listing information including square footage, HOA fees, year built, amenities, heating/cooling, and parking specs.
- **Amenities & Features (`get_property_amenities`)**: Retrieves a targeted list of appliances, luxury features, and fixtures for a specific listing ID.
- **Listing Ingestion (`add_property_listing`)**: Dynamically adds or updates property listings in Firestore with custom metadata.
- **Tour Scheduling (`schedule_property_tour`)**: Books private showings and walkthrough appointments with buyer contact info, storing reservations in Firestore.

### 2. Cross-Session Long-Term Memory (Vertex AI Memory Bank)
- **PreloadMemoryTool & Memory Callback**: Connects to a managed Vertex AI Memory Bank (`agentengine://...`) using `PreloadMemoryTool` and an automated memory generation callback (`generate_memories_callback`).
- **Personalized Recommendations**: Automatically remembers buyer preferences, target neighborhoods, maximum budget, desired home features, and past feedback across separate chat sessions without requiring re-entry.

### 3. Financial Modeling & Code Execution (Agent Engine Sandbox)
- **Mortgage Calculator (`calculate_mortgage_payment`)**: Computes estimated monthly principal & interest (P&I), property taxes, homeowner insurance, and total PITI payments.
- **Code Execution (`AgentEngineSandboxCodeExecutor`)**: Executes generated Python code inside an isolated Google Cloud Agent Engine Sandbox for complex financial comparisons, loan amortization schedules, investment ROI models, and price-per-square-foot metrics.

### 4. Multimodal Media Generation (Vertex AI & Cloud Storage)
- **Interior Staging & Rendering (`generate_property_rendering`)**: Uses Google's `gemini-3.1-flash-lite-image` model in the `global` region to generate architectural renderings, room remodeling concepts, and interior staging visualizations tailored to specific properties.
- **Property Walkthrough Videos (`generate_property_video`)**: Uses Google's Omni model (`gemini-omni-flash-preview`) in the `global` region via the Google GenAI SDK interactions API to produce short cinematic walkthroughs and aerial drone flyover video clips.
- **In-Memory Cloud Storage Uploads**: Generated image and video bytes are saved to session artifacts via `tool_context.save_artifact` (for Playground inspection) and uploaded directly to a public Cloud Storage bucket in memory without writing temporary files to local disk.

### 5. Neighborhood Intelligence (Google Maps Platform APIs)
- **Nearby Places & Amenities (`find_nearby_places`)**: Uses Google Maps Places API (`places.googleapis.com/v1/places:searchText`) to find schools, transit stations, parks, grocery stores, and restaurants within range of an address.
- **Address Geocoding (`geocode_address`)**: Resolves human-readable addresses to exact geographic coordinates using Google Maps Geocoding API.
- **Environmental & Air Quality (`get_neighborhood_air_quality`)**: Queries Google Maps Air Quality API for real-time Air Quality Index (AQI) readings, dominant pollutants, and health recommendations.
- **Local Weather Conditions (`get_weather`)**: Fetches current temperature and weather conditions via Open-Meteo.
- **Local Time (`get_current_time`)**: Resolves current local time and time zone for any city.

### 6. Agent-Driven UI (A2UI)
- **Basic Catalog (v0.8)**: Implements `A2uiSchemaManager` with the Basic Catalog (`Card`, `Column`, `Row`, `Text`, and `Image` components).
- **Rich Display Formatting**: Returns structured visual cards containing property highlights, pricing, specs, and generated rendering imagery instead of plain text blocks.
- **Response Validation**: Uses `a2ui_callback` to ensure A2UI component payloads adhere to specification and provides synchronized text summaries.

### 7. Custom Web Frontend (FastAPI & A2A Protocol)
- **A2A Client**: Minimal FastAPI backend in `frontend/` acting as an authenticated proxy to the deployed Agent Engine over the Agent-to-Agent (A2A) protocol.
- **Single-Page Chat Interface**: Branded responsive UI in `frontend/static/index.html` featuring interactive example prompt chips, typing indicators, and a built-in A2UI card renderer.

---

## 🏗️ Architecture & Wired Services

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Agent Core** | Google ADK + `gemini-3.8-flash` | Reasoning loop and tool orchestration |
| **Long-Term Memory** | Vertex AI Memory Bank | Cross-session preference retention |
| **Database** | Google Cloud Firestore | Listings catalog (`properties`) & tours (`tours`) |
| **Code Sandbox** | Agent Engine Sandbox Code Executor | Safe Python execution for financial math |
| **Image Generation** | `gemini-3.1-flash-lite-image` (`global`) | Architectural and interior staging images |
| **Video Generation** | `gemini-omni-flash-preview` (`global`) | Drone flythrough and walkthrough video clips |
| **Asset Storage** | Google Cloud Storage | Public hosting for generated media |
| **Location Services**| Google Maps Platform (Places, Geocoding, AQI) | Neighborhood amenities and air quality data |
| **UI Rendering** | A2UI (Agent-to-User Interface) v0.8 | Structured cards, rows, columns, and media |
| **Web Frontend** | FastAPI + Cloud Run | A2A proxy and chat UI |

### Feature Status & Implementation Notes
- **Implemented & Wired**: Firestore, Vertex AI Memory Bank, Cloud Storage media upload, `gemini-3.1-flash-lite-image`, `gemini-omni-flash-preview`, Agent Engine Code Sandbox, Google Maps Places / Geocode / Air Quality APIs, A2UI v0.8, FastAPI A2A frontend, full unit and integration test suite (20 tests passing).
- **Planned / Not Yet Implemented**: OpenTelemetry custom distributed tracing exporter for Cloud Trace.

---

## 📁 Repository Structure

```
smart-real-estate-finder/
├── app/
│   ├── agent.py              # Agent definition, system instructions, tools, and callbacks
│   ├── a2ui_utils.py         # A2UI after_model_callback handler
│   ├── fast_api_app.py       # Local development FastAPI app entrypoint
│   └── app_utils/            # Helper utilities
├── frontend/
│   ├── main.py               # FastAPI proxy communicating via A2A protocol
│   ├── requirements.txt      # Frontend Python dependencies
│   ├── Dockerfile            # Container image definition for Cloud Run
│   └── static/
│       └── index.html        # Branded chat UI with A2UI card renderer
├── tests/
│   ├── unit/                 # Unit test suite
│   ├── integration/          # Integration tests
│   └── eval/                 # Evaluation datasets
├── agents-cli-manifest.yaml  # agents-cli deployment configuration
├── seed_firestore.py         # Catalog population script for Firestore
├── pyproject.toml            # Project dependencies and tool configurations
└── README.md
```

---

## 🚀 Setup & Local Execution

### Prerequisites

1. **Python 3.11+** and **uv** (recommended package manager):
   ```bash
   pip install uv
   ```
2. **Google Cloud SDK (`gcloud`)**:
   Authenticate and set your Google Cloud project:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project <YOUR_PROJECT_ID>
   ```
3. **Google Maps API Key**:
   Enable the Places API, Geocoding API, and Air Quality API in your Google Cloud Console and obtain an API key.

### Configuration

Create a `.env` file in the project directory:

```bash
PROJECT_ID="<YOUR_PROJECT_ID>"
GOOGLE_CLOUD_PROJECT="<YOUR_PROJECT_ID>"
GOOGLE_CLOUD_LOCATION="us-east1"
GOOGLE_MAPS_API_KEY="<YOUR_GOOGLE_MAPS_API_KEY>"
GCS_BUCKET_NAME="<YOUR_PUBLIC_STORAGE_BUCKET>"
SANDBOX_RESOURCE_NAME="projects/<PROJECT_NUMBER>/locations/us-east1/reasoningEngines/<SANDBOX_ID>"
```

### 1. Seed the Firestore Catalog

Populate the Firestore database with initial curated property listings:

```bash
uv run python seed_firestore.py
```

### 2. Run the Agent Locally (ADK Playground)

Launch the interactive ADK development UI with Memory Bank support:

```bash
uv run adk web . --port 8080 --reload_agents --memory_service_uri=agentengine://<YOUR_AGENT_ENGINE_ID>
```

Open your browser to the local ADK interface to interact with the agent, view execution logs, inspect tool calls, and examine saved artifacts.

### 3. Run the Custom Web Frontend Locally

The custom frontend in `frontend/` connects to a deployed Agent Engine instance over the A2A protocol:

```bash
cd frontend
uv pip install -r requirements.txt

export AGENT_ENGINE_RESOURCE_NAME="projects/<PROJECT_NUMBER>/locations/us-east1/reasoningEngines/<ENGINE_ID>"
export AGENT_DIRECTORY="app"

python main.py
```

---

## ☁️ Deployment

### Deploying the Agent to Agent Platform

Deploy the agent logic, tools, and sandbox configuration to Google Cloud Agent Runtime:

```bash
agents-cli deploy --update-env-vars GOOGLE_MAPS_API_KEY="<YOUR_KEY>"
```

Ensure the deployment service account has the following IAM roles:
- `roles/datastore.user` (Firestore read/write)
- `roles/storage.objectAdmin` (Cloud Storage media upload)
- `roles/aiplatform.user` (Vertex AI models & sandbox)

### Deploying the Frontend to Cloud Run

Build and deploy the custom A2A chat frontend container to Cloud Run:

```bash
gcloud run deploy smart-real-estate-finder-frontend \
  --source ./frontend \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars AGENT_ENGINE_RESOURCE_NAME="projects/<PROJECT_NUMBER>/locations/us-east1/reasoningEngines/<ENGINE_ID>",AGENT_DIRECTORY="app"
```

Grant the Cloud Run service account `roles/aiplatform.user` so it can invoke the deployed agent engine.

---

## 🧪 Testing & Evaluation

Run unit and integration tests:

```bash
uv run pytest tests/unit tests/integration
```

Run agent evaluation with `agents-cli`:

```bash
agents-cli eval run
```
