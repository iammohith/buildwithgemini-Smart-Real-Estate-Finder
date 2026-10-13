"""Comprehensive unit tests for Smart Real Estate Finder tools and A2UI logic."""

import pytest
from app import agent
from app.a2ui_utils import (
    _extract_a2ui_messages,
    _extract_text_summary,
    _surface_is_renderable,
    _wrap_a2ui_part,
)


def test_calculate_mortgage_payment_by_id():
    result = agent.calculate_mortgage_payment(property_id="prop-101", down_payment_percent=20)
    assert "Monthly Mortgage Breakdown" in result
    assert "Home Price: $650,000" in result
    assert "TOTAL ESTIMATED MONTHLY PAYMENT" in result


def test_calculate_mortgage_payment_custom_price():
    result = agent.calculate_mortgage_payment(home_price=500000, down_payment_percent=10, interest_rate_percent=6.5)
    assert "Monthly Mortgage Breakdown" in result
    assert "Home Price: $500,000" in result
    assert "Loan Amount: $450,000" in result


def test_calculate_mortgage_payment_missing():
    result = agent.calculate_mortgage_payment(property_id="nonexistent-prop-999")
    assert "Please provide a valid home price" in result


def test_search_properties():
    result = agent.search_properties(city="Austin")
    assert "Found" in result or "No properties found" in result
    if "Found" in result:
        assert "prop-101" in result or "prop-102" in result


def test_get_property_details():
    result = agent.get_property_details("prop-101")
    assert "Property Details for Modern Craftsman in South Congress" in result
    assert "$650,000" in result
    assert "prop-101" in result


def test_get_property_details_not_found():
    result = agent.get_property_details("invalid-id-xyz")
    assert "was not found in the database" in result


def test_get_property_amenities():
    result = agent.get_property_amenities("prop-101")
    assert "Amenities and Features for Modern Craftsman in South Congress" in result
    assert "hardwood floors" in result


def test_get_property_amenities_not_found():
    result = agent.get_property_amenities("invalid-id-xyz")
    assert "was not found in the database" in result


def test_get_weather():
    result = agent.get_weather("Austin")
    assert "Austin" in result
    assert "temperature" in result or "weather" in result


def test_get_current_time():
    result = agent.get_current_time("Austin")
    assert "Austin" in result
    assert "202" in result  # Contains year


def test_geocode_address():
    result = agent.geocode_address("1204 South Congress Ave, Austin, TX")
    assert "1204" in result or "Congress" in result or "Austin" in result


def test_find_nearby_places():
    result = agent.find_nearby_places("school", "1204 South Congress Ave, Austin, TX")
    assert "school" in result.lower()


def test_schedule_property_tour():
    result = agent.schedule_property_tour(
        property_id="prop-101",
        client_name="Unit Test Buyer",
        tour_date="2026-11-01",
        tour_time="2:00 PM",
        notes="First-time buyer inspection",
    )
    assert "Tour confirmed!" in result
    assert "Unit Test Buyer" in result
    assert "2026-11-01" in result


def test_a2ui_extraction_and_summary():
    raw_payload = """[
        {"beginRendering": {"surfaceId": "test-surface", "root": "card-1"}},
        {"surfaceUpdate": {"surfaceId": "test-surface", "components": [
            {"id": "card-1", "component": {"Card": {"child": "col-1"}}},
            {"id": "col-1", "component": {"Column": {"children": {"explicitList": ["t1", "t2"]}}}},
            {"id": "t1", "component": {"Text": {"text": {"literalString": "Austin Modern Loft"}, "usageHint": "h1"}}},
            {"id": "t2", "component": {"Text": {"text": {"literalString": "Stunning downtown views."}}, "usageHint": "body"}}
        ]}}
    ]"""
    messages = _extract_a2ui_messages(raw_payload)
    assert len(messages) == 2
    assert _surface_is_renderable(messages) is True

    summary = _extract_text_summary(messages)
    assert "Austin Modern Loft" in summary
    assert "Stunning downtown views." in summary

    part = _wrap_a2ui_part(messages[0])
    assert part.inline_data is not None
    assert part.inline_data.mime_type == "text/plain"
