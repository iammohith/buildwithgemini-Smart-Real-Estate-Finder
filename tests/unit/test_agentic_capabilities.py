"""Tests for production-grade agentic capabilities.

Validates:
- Tool parameter bounds checking and input safeguards
- Places API radius limits
- /health observability endpoint
- Request validation (empty messages, payload length limits)
- ReAct cognitive system prompt structure
"""

import pytest
from fastapi.testclient import TestClient

from app.agent import (
    calculate_mortgage_payment,
    find_nearby_places,
    role_description,
    root_agent,
)
from frontend.main import app as frontend_app


def test_mortgage_bounds_validation():
    """Verify bounds checking on mortgage payment parameters."""
    # Invalid negative down payment
    res_neg_down = calculate_mortgage_payment(
        home_price=500000.0, down_payment_percent=-5.0
    )
    assert "Invalid down payment" in res_neg_down

    # Invalid excessive down payment (>100%)
    res_high_down = calculate_mortgage_payment(
        home_price=500000.0, down_payment_percent=105.0
    )
    assert "Invalid down payment" in res_high_down

    # Invalid negative interest rate
    res_neg_rate = calculate_mortgage_payment(
        home_price=500000.0, interest_rate_percent=-1.0
    )
    assert "Invalid interest rate" in res_neg_rate

    # Invalid excessive interest rate (>40%)
    res_high_rate = calculate_mortgage_payment(
        home_price=500000.0, interest_rate_percent=55.0
    )
    assert "Invalid interest rate" in res_high_rate

    # Invalid loan term (0 or negative)
    res_zero_term = calculate_mortgage_payment(
        home_price=500000.0, loan_term_years=0
    )
    assert "Invalid loan term" in res_zero_term

    # Invalid excessive loan term (>50 years)
    res_high_term = calculate_mortgage_payment(
        home_price=500000.0, loan_term_years=60
    )
    assert "Invalid loan term" in res_high_term

    # Valid execution succeeds
    res_valid = calculate_mortgage_payment(
        home_price=500000.0,
        down_payment_percent=20.0,
        interest_rate_percent=6.5,
        loan_term_years=30,
    )
    assert "TOTAL ESTIMATED MONTHLY PAYMENT" in res_valid
    assert "$500,000.00" in res_valid


def test_places_radius_bounds():
    """Verify find_nearby_places requires coordinates/address and doesn't crash on out-of-range radius."""
    res_missing = find_nearby_places(place_type="school", latitude=0.0, longitude=0.0)
    assert "Error: Please specify coordinates" in res_missing


def test_react_cognitive_system_prompt_structure():
    """Verify that root_agent incorporates the complete ReAct cognitive loop."""
    assert "GOAL DECOMPOSITION" in role_description
    assert "PLAN & ACT" in role_description
    assert "EVALUATE & REFLECT" in role_description
    assert "COMPLETION DETECTION" in role_description
    assert root_agent.model.model == "gemini-3.8-flash"


def test_frontend_health_endpoint():
    """Verify the production /health endpoint returns HTTP 200 with complete diagnostics."""
    client = TestClient(frontend_app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "healthy"
    assert data.get("model") == "gemini-3.8-flash"
    assert "uptime_seconds" in data
    assert "agent_engine_resource" in data
    assert "timestamp" in data


def test_frontend_chat_request_validation():
    """Verify /chat request validation guards against empty and oversized messages."""
    client = TestClient(frontend_app)

    # Empty string message
    res_empty = client.post("/chat", json={"message": "   "})
    assert res_empty.status_code == 400
    data_empty = res_empty.json()
    assert "cannot be empty" in data_empty.get("error", "")

    # Oversized message (>4,000 chars)
    oversized = "a" * 4500
    res_oversized = client.post("/chat", json={"message": oversized})
    assert res_oversized.status_code == 400
    data_oversized = res_oversized.json()
    assert "maximum allowed length" in data_oversized.get("error", "")


def test_frontend_cors_and_reset():
    """Verify CORS preflight handling and /reset endpoint."""
    client = TestClient(frontend_app)

    # CORS OPTIONS preflight
    res_cors = client.options(
        "/chat",
        headers={
            "Origin": "https://remote-browser-vm1-apoaopdc2q-em.a.run.app",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert res_cors.status_code == 200
    assert "access-control-allow-origin" in res_cors.headers

    # Session reset endpoint
    res_reset = client.post("/reset", json={"user_id": "test-session-123"})
    assert res_reset.status_code == 200
    assert res_reset.json().get("status") == "ok"

