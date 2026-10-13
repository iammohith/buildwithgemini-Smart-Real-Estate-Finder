# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo
import uuid
import os
import inspect
from dotenv import load_dotenv

load_dotenv()

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
try:
    from .a2ui_utils import a2ui_callback
except ImportError:
    from app.a2ui_utils import a2ui_callback


MODEL = "gemini-3.8-flash"


WMO_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow fall",
    73: "moderate snow fall",
    75: "heavy snow fall",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
}


def get_weather(query: str) -> str:
    """Fetches real-time current weather for a city or location.

    Args:
        query: The name of the city or location (e.g., 'Hyderabad', 'San Francisco', 'New York').

    Returns:
        A string with the current weather condition, temperature, and humidity.
    """
    try:
        clean_query = query.strip()
        encoded = urllib.parse.quote(clean_query)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=1&language=en&format=json"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "BuildWithGemini/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        if not data.get("results"):
            return f"Could not find location coordinates for {query}."

        result = data["results"][0]
        lat, lon = result["latitude"], result["longitude"]
        city_name = result.get("name", query)
        country = result.get("country", "")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code"
        req_w = urllib.request.Request(weather_url, headers={"User-Agent": "BuildWithGemini/1.0"})
        with urllib.request.urlopen(req_w, timeout=5) as resp_w:
            wdata = json.loads(resp_w.read().decode())

        current = wdata.get("current", {})
        temp_c = current.get("temperature_2m")
        temp_f = round(temp_c * 9 / 5 + 32, 1) if temp_c is not None else None
        code = current.get("weather_code", 0)
        condition = WMO_CODES.get(code, "clear sky")
        humidity = current.get("relative_humidity_2m")

        location_str = f"{city_name}, {country}" if country else city_name
        return f"The current weather in {location_str} is {condition} with a temperature of {temp_c}°C ({temp_f}°F) and {humidity}% humidity."
    except Exception as e:
        return f"Error fetching weather for {query}: {e}"


def get_current_time(query: str) -> str:
    """Gets the current time for a city or location.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time and timezone information.
    """
    try:
        clean_query = query.strip()
        encoded = urllib.parse.quote(clean_query)
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=1&language=en&format=json"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "BuildWithGemini/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        tz_identifier = None
        city_name = query
        if data.get("results"):
            tz_identifier = data["results"][0].get("timezone")
            city_name = data["results"][0].get("name", query)

        if not tz_identifier:
            if "sf" in query.lower() or "san francisco" in query.lower():
                tz_identifier = "America/Los_Angeles"
            elif "hyd" in query.lower() or "hyderabad" in query.lower():
                tz_identifier = "Asia/Kolkata"
            elif "ny" in query.lower() or "new york" in query.lower():
                tz_identifier = "America/New_York"
            else:
                return f"Sorry, I don't have timezone information for query: {query}."

        tz = ZoneInfo(tz_identifier)
        now = datetime.datetime.now(tz)
        return f"The current time in {city_name} is {now.strftime('%Y-%m-%d %H:%M:%S %Z')} ({tz_identifier})"
    except Exception as e:
        return f"Error getting time for {query}: {e}"


# Hardcode GCP Project ID, Cloud Storage Bucket name, and Sandbox Resource Name as requested
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-04-b4fbcb7610df"
GCS_BUCKET_NAME = "smart-real-estate-finder-qwiklabs-gcp-04-b4fbcb7610df"
AGENT_ENGINE_RESOURCE_NAME = "projects/257485218858/locations/us-east1/reasoningEngines/8950672262445400064"
SANDBOX_RESOURCE_NAME = "projects/257485218858/locations/us-east1/reasoningEngines/8950672262445400064/sandboxEnvironments/9754867161628672"
MEMORY_BANK_ID = "8950672262445400064"


def memory_bank_service_builder():
    """Builds VertexAiMemoryBankService reusing the deployed Agent Engine."""
    from google.adk.memory import VertexAiMemoryBankService

    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT_ID,
        location="us-east1",
        agent_engine_id=MEMORY_BANK_ID,
    )


async def generate_memories_callback(callback_context: CallbackContext):
    """Save conversation events to Memory Bank after each turn so all user queries are remembered."""
    if getattr(callback_context._invocation_context, "memory_service", None):
        await callback_context.add_session_to_memory()
    return None


_firestore_client = None


def get_firestore_client():
    global _firestore_client
    if _firestore_client is None:
        from google.cloud import firestore
        _firestore_client = firestore.Client(project=FIRESTORE_PROJECT_ID)
    return _firestore_client


def search_properties(
    city: str = "",
    max_price: float = 0.0,
    min_beds: int = 0,
    property_type: str = "",
) -> str:
    """Searches the Firestore database for real estate properties matching criteria.

    Args:
        city: City to search in (e.g. 'Austin', 'Seattle', 'Denver'). Case-insensitive. Optional.
        max_price: Maximum listing price in USD. Optional (0 means no limit).
        min_beds: Minimum number of bedrooms required. Optional (0 means no limit).
        property_type: Type of property ('Single Family', 'Condo', 'Townhouse'). Optional.

    Returns:
        A formatted list of matching properties with id, title, price, beds, baths, sqft, and neighborhood.
    """
    try:
        db = get_firestore_client()
        docs = db.collection("properties").stream()
        results = []

        for doc in docs:
            item = doc.to_dict()
            if city and city.lower() not in item.get("city", "").lower():
                continue
            if max_price > 0 and float(item.get("price", 0)) > max_price:
                continue
            if min_beds > 0 and int(item.get("bedrooms", 0)) < min_beds:
                continue
            if property_type and property_type.lower() not in item.get("property_type", "").lower():
                continue
            results.append(item)

        if not results:
            return "No properties found matching your search criteria."

        output_lines = [f"Found {len(results)} matching properties:"]
        for p in results:
            price_formatted = f"${p.get('price', 0):,}"
            output_lines.append(
                f"- [{p.get('id')}] {p.get('title')}: {price_formatted} | "
                f"{p.get('bedrooms')} bed, {p.get('bathrooms')} bath | "
                f"{p.get('sqft')} sqft | {p.get('property_type')} in {p.get('neighborhood')}, {p.get('city')}"
            )
        return "\n".join(output_lines)
    except Exception as e:
        return f"Error querying properties from Firestore: {e}"


def get_property_details(property_id: str) -> str:
    """Retrieves full details for a specific property by its property ID.

    Args:
        property_id: The ID of the property (e.g. 'prop-101', 'prop-102').

    Returns:
        A detailed description of the property including all specs, features, and status.
    """
    try:
        db = get_firestore_client()
        doc = db.collection("properties").document(property_id.strip()).get()
        if not doc.exists:
            return f"Property with ID '{property_id}' was not found in the database."

        data = doc.to_dict()
        features_str = ", ".join(data.get("features", []))
        return (
            f"Property Details for {data.get('title')} (ID: {data.get('id')}):\n"
            f"- Price: ${data.get('price', 0):,}\n"
            f"- Location: {data.get('neighborhood')}, {data.get('city')}\n"
            f"- Specs: {data.get('bedrooms')} Beds, {data.get('bathrooms')} Baths, {data.get('sqft')} SqFt\n"
            f"- Property Type: {data.get('property_type')}\n"
            f"- Status: {data.get('status', 'Available')}\n"
            f"- Year Built: {data.get('year_built', 'N/A')}\n"
            f"- Key Features: {features_str}\n"
            f"- Description: {data.get('description', '')}"
        )
    except Exception as e:
        return f"Error retrieving property details for {property_id}: {e}"


def get_property_amenities(property_id: str) -> str:
    """Retrieves the list of amenities, appliances, and special features for a property.

    Args:
        property_id: The ID of the property (e.g. 'prop-101', 'prop-102').

    Returns:
        A list of key amenities and features for the property.
    """
    try:
        db = get_firestore_client()
        doc = db.collection("properties").document(property_id.strip()).get()
        if not doc.exists:
            return f"Property with ID '{property_id}' was not found in the database."

        data = doc.to_dict()
        title = data.get("title", property_id)
        features = data.get("features", [])
        if not features:
            return f"No specific amenities listed for {title} (ID: {property_id})."

        amenity_list = "\n".join(f"- {f}" for f in features)
        return f"Amenities and Features for {title} (ID: {property_id}):\n{amenity_list}"
    except Exception as e:
        return f"Error retrieving amenities for {property_id}: {e}"


def add_property_listing(
    title: str,
    price: float,
    city: str,
    neighborhood: str,
    bedrooms: int,
    bathrooms: float,
    sqft: int,
    property_type: str,
    description: str,
    features: list[str],
) -> str:
    """Adds a new property listing to the Firestore database.

    Args:
        title: Title/headline for the listing (e.g., 'Modern Bungalow with Pool').
        price: Listing price in USD.
        city: City where the home is located (e.g., 'Austin').
        neighborhood: Neighborhood name (e.g., 'Zilker').
        bedrooms: Number of bedrooms.
        bathrooms: Number of bathrooms.
        sqft: Square footage of the home.
        property_type: Type of home ('Single Family', 'Condo', 'Townhouse').
        description: Detailed summary describing the home.
        features: List of amenities or key features (e.g., ['swimming pool', 'hardwood floors']).

    Returns:
        A confirmation message with the newly assigned property ID.
    """
    try:
        db = get_firestore_client()
        prop_id = f"prop-{uuid.uuid4().hex[:6]}"
        record = {
            "id": prop_id,
            "title": title.strip(),
            "price": float(price),
            "city": city.strip(),
            "neighborhood": neighborhood.strip(),
            "bedrooms": int(bedrooms),
            "bathrooms": float(bathrooms),
            "sqft": int(sqft),
            "property_type": property_type.strip(),
            "status": "Available",
            "description": description.strip(),
            "features": features,
        }
        db.collection("properties").document(prop_id).set(record)
        return (
            f"Successfully added new listing '{title}' with ID {prop_id} to Firestore! "
            f"Listed at ${float(price):,} in {neighborhood}, {city}."
        )
    except Exception as e:
        return f"Error adding property listing to Firestore: {e}"


def schedule_property_tour(
    property_id: str,
    client_name: str,
    tour_date: str,
    tour_time: str,
    tour_type: str = "in-person",
    notes: str = "",
) -> str:
    """Schedules a property showing or tour and records it in Firestore.

    Args:
        property_id: The ID of the property to tour (e.g., 'prop-101').
        client_name: Name of the person booking the tour.
        tour_date: Requested date for the tour (e.g., '2026-10-15').
        tour_time: Requested time slot (e.g., '2:00 PM').
        tour_type: 'in-person' or 'virtual' (video call).
        notes: Any specific requests or notes for the tour.

    Returns:
        Confirmation message with tour booking details and booking ID.
    """
    try:
        db = get_firestore_client()
        p_doc = db.collection("properties").document(property_id.strip()).get()
        p_title = p_doc.to_dict().get("title", property_id) if p_doc.exists else property_id

        tour_id = f"tour-{uuid.uuid4().hex[:6]}"
        record = {
            "tour_id": tour_id,
            "property_id": property_id.strip(),
            "property_title": p_title,
            "client_name": client_name.strip(),
            "tour_date": tour_date.strip(),
            "tour_time": tour_time.strip(),
            "tour_type": tour_type,
            "notes": notes.strip(),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": "Confirmed",
        }
        db.collection("tours").document(tour_id).set(record)
        return (
            f"Tour confirmed! Booking ID: {tour_id}. "
            f"{client_name} is scheduled for an {tour_type} showing of '{p_title}' (ID: {property_id}) "
            f"on {tour_date} at {tour_time}."
        )
    except Exception as e:
        return f"Error scheduling property tour in Firestore: {e}"


def calculate_mortgage_payment(
    home_price: float = 0.0,
    property_id: str = "",
    down_payment_percent: float = 20.0,
    interest_rate_percent: float = 6.5,
    loan_term_years: int = 30,
) -> str:
    """Calculates estimated monthly mortgage payment (PITI: Principal, Interest, Taxes, Insurance).

    Args:
        home_price: Price of the home in USD (optional if property_id is provided).
        property_id: Property ID (e.g. 'prop-101') to look up price automatically from Firestore.
        down_payment_percent: Down payment percentage (default 20%).
        interest_rate_percent: Annual mortgage interest rate percentage (default 6.5%).
        loan_term_years: Loan duration in years (default 30).

    Returns:
        A breakdown of monthly principal & interest, taxes, insurance, and total monthly payment.
    """
    try:
        title = "Custom Estimate"
        if property_id:
            db = get_firestore_client()
            doc = db.collection("properties").document(property_id.strip()).get()
            if doc.exists:
                data = doc.to_dict()
                home_price = float(data.get("price", home_price))
                title = data.get("title", property_id)

        if home_price <= 0:
            return "Please provide a valid home price or a valid property ID to calculate payments."

        if down_payment_percent < 0 or down_payment_percent > 100:
            return "Invalid down payment percentage: must be between 0% and 100%."
        if interest_rate_percent < 0 or interest_rate_percent > 40:
            return "Invalid interest rate: must be between 0% and 40%."
        if loan_term_years <= 0 or loan_term_years > 50:
            return "Invalid loan term: must be between 1 and 50 years."

        down_payment = home_price * (down_payment_percent / 100.0)
        loan_amount = home_price - down_payment
        monthly_rate = (interest_rate_percent / 100.0) / 12.0
        num_payments = loan_term_years * 12

        if monthly_rate > 0:
            factor = (1 + monthly_rate) ** num_payments
            monthly_pi = loan_amount * (monthly_rate * factor) / (factor - 1)
        else:
            monthly_pi = loan_amount / num_payments

        # Estimated property taxes (~1.2% annual) and insurance (~$1,500/year)
        monthly_tax = (home_price * 0.012) / 12.0
        monthly_insurance = 1500.0 / 12.0
        total_monthly = monthly_pi + monthly_tax + monthly_insurance

        return (
            f"Monthly Mortgage Breakdown for {title}:\n"
            f"- Home Price: ${home_price:,.2f}\n"
            f"- Down Payment ({down_payment_percent}%): ${down_payment:,.2f}\n"
            f"- Loan Amount: ${loan_amount:,.2f}\n"
            f"- Interest Rate: {interest_rate_percent}% ({loan_term_years}-year fixed)\n"
            f"-----------------------------------------\n"
            f"- Principal & Interest: ${monthly_pi:,.2f}/mo\n"
            f"- Est. Property Taxes (1.2%): ${monthly_tax:,.2f}/mo\n"
            f"- Est. Home Insurance: ${monthly_insurance:,.2f}/mo\n"
            f"=========================================\n"
            f"TOTAL ESTIMATED MONTHLY PAYMENT: ${total_monthly:,.2f}/mo"
        )
    except Exception as e:
        return f"Error calculating mortgage payment: {e}"


def get_neighborhood_air_quality(location: str = "", property_id: str = "") -> str:
    """Fetches real-time environmental air quality (US EPA AQI, PM2.5, PM10) for a neighborhood or property.

    Uses Open-Meteo Air Quality and OpenStreetMap Nominatim public APIs.

    Args:
        location: Name of the neighborhood or city (e.g. 'South Congress, Austin', 'Ballard, Seattle').
        property_id: Optional property ID (e.g. 'prop-101') to look up its location automatically.

    Returns:
        Environmental air quality score, particulate levels, and EPA health category.
    """
    try:
        loc_query = location.strip()
        if property_id:
            db = get_firestore_client()
            doc = db.collection("properties").document(property_id.strip()).get()
            if doc.exists:
                d = doc.to_dict()
                loc_query = f"{d.get('neighborhood', '')}, {d.get('city', '')}".strip(", ")

        if not loc_query:
            return "Please provide a location, neighborhood name, or a property ID."

        # Forward geocoding with OpenStreetMap Nominatim
        nom_url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(loc_query)}&format=json&limit=1"
        req_nom = urllib.request.Request(nom_url, headers={"User-Agent": "BuildWithGemini-RealEstate/1.0"})
        with urllib.request.urlopen(req_nom, timeout=5) as resp:
            nom_data = json.loads(resp.read().decode())

        if not nom_data:
            return f"Could not determine geographical coordinates for '{loc_query}'."

        lat = nom_data[0]["lat"]
        lon = nom_data[0]["lon"]
        display_name = nom_data[0].get("display_name", loc_query)

        # Open-Meteo Air Quality API (public-apis directory)
        api_key = os.environ.get("OPEN_METEO_API_KEY", "")
        key_param = f"&apikey={api_key}" if api_key else ""
        aq_url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=us_aqi,pm2_5,pm10{key_param}"
        req_aq = urllib.request.Request(aq_url, headers={"User-Agent": "BuildWithGemini-RealEstate/1.0"})
        with urllib.request.urlopen(req_aq, timeout=5) as resp_aq:
            aq_data = json.loads(resp_aq.read().decode())

        curr = aq_data.get("current", {})
        aqi = curr.get("us_aqi", "N/A")
        pm25 = curr.get("pm2_5", "N/A")
        pm10 = curr.get("pm10", "N/A")

        category = "Unknown"
        if isinstance(aqi, (int, float)):
            if aqi <= 50:
                category = "Good (Little to no health risk; ideal for outdoor living)"
            elif aqi <= 100:
                category = "Moderate (Acceptable; sensitive individuals should take precautions)"
            elif aqi <= 150:
                category = "Unhealthy for Sensitive Groups"
            elif aqi <= 200:
                category = "Unhealthy"
            else:
                category = "Very Unhealthy / Hazardous"

        return (
            f"Environmental & Air Quality Report for {loc_query}:\n"
            f"- Specific Area: {display_name}\n"
            f"- US EPA Air Quality Index (AQI): {aqi} ({category})\n"
            f"- Particulate Matter: PM2.5 = {pm25} µg/m³, PM10 = {pm10} µg/m³\n"
            f"- Coordinates: {lat}, {lon}"
        )
    except Exception as e:
        return f"Error retrieving neighborhood air quality for {location}: {e}"


def geocode_address(address: str) -> str:
    """Uses Google Maps Geocoding API to turn a street address or location into coordinates.

    Args:
        address: The street address, neighborhood, or city name to geocode.

    Returns:
        Formatted address and location coordinates (latitude, longitude).
    """
    try:
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

        encoded = urllib.parse.quote(address.strip())
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded}&key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "BuildWithGemini-RealEstate/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") != "OK" or not data.get("results"):
            return f"Could not geocode address '{address}'. Status: {data.get('status', 'ZERO_RESULTS')}."

        first = data["results"][0]
        formatted_address = first.get("formatted_address", address)
        loc = first.get("geometry", {}).get("location", {})
        lat = loc.get("lat")
        lng = loc.get("lng")

        return (
            f"Geocoding result for '{address}':\n"
            f"- Formatted Address: {formatted_address}\n"
            f"- Location Coordinates: latitude {lat}, longitude {lng}"
        )
    except Exception as e:
        return f"Error calling Google Geocoding API: {e}"


def find_nearby_places(
    place_type: str,
    address: str = "",
    latitude: float = 0.0,
    longitude: float = 0.0,
    radius_meters: float = 2000.0,
) -> str:
    """Uses Google Places API (New) nearby search to find nearby places of a given type.

    Args:
        place_type: Type of place to search for (e.g., 'school', 'park', 'supermarket', 'transit_station', 'restaurant', 'cafe', 'hospital', 'gym').
        address: Optional address or neighborhood to search around (e.g. 'South Congress, Austin, TX' or 'prop-101'). If coordinates are not given, this will be geocoded first.
        latitude: Latitude coordinate for search center (optional if address is given).
        longitude: Longitude coordinate for search center (optional if address is given).
        radius_meters: Search radius in meters (default 2000m / ~1.2 miles).

    Returns:
        Key fields of found places: name, address, and location coordinates.
    """
    try:
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return "Error: GOOGLE_MAPS_API_KEY environment variable is not set."

        # If property ID or address is passed and coords are 0, resolve coordinates
        if (latitude == 0.0 and longitude == 0.0) and address:
            addr_query = address.strip()
            if addr_query.startswith("prop-"):
                db = get_firestore_client()
                p_doc = db.collection("properties").document(addr_query).get()
                if p_doc.exists:
                    p_data = p_doc.to_dict()
                    addr_query = f"{p_data.get('neighborhood', '')}, {p_data.get('city', '')}"

            encoded = urllib.parse.quote(addr_query)
            geo_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded}&key={api_key}"
            req_geo = urllib.request.Request(geo_url, headers={"User-Agent": "BuildWithGemini-RealEstate/1.0"})
            with urllib.request.urlopen(req_geo, timeout=8) as resp_geo:
                geo_data = json.loads(resp_geo.read().decode())
            if geo_data.get("status") == "OK" and geo_data.get("results"):
                coords = geo_data["results"][0].get("geometry", {}).get("location", {})
                latitude = coords.get("lat", 0.0)
                longitude = coords.get("lng", 0.0)

        if latitude == 0.0 and longitude == 0.0:
            return "Error: Please specify coordinates (latitude, longitude) or a valid address."

        # Places API (New) searchNearby REST endpoint confirmed via Developer Knowledge MCP
        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
        }
        safe_radius = max(100.0, min(float(radius_meters), 50000.0))
        body = {
            "includedTypes": [place_type.lower().strip()],
            "maxResultCount": 5,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                    "radius": safe_radius,
                }
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        places = data.get("places", [])
        if not places:
            return f"No nearby '{place_type}' places found within {int(radius_meters)}m of ({latitude}, {longitude})."

        output_lines = [f"Found {len(places)} nearby '{place_type}' places:"]
        for p in places:
            name = p.get("displayName", {}).get("text", "Unknown Name")
            formatted_addr = p.get("formattedAddress", "N/A")
            loc = p.get("location", {})
            p_lat = loc.get("latitude")
            p_lng = loc.get("longitude")
            output_lines.append(
                f"- Name: {name}\n"
                f"  Address: {formatted_addr}\n"
                f"  Location: latitude {p_lat}, longitude {p_lng}"
            )

        return "\n".join(output_lines)
    except Exception as e:
        return f"Error calling Google Places API (New): {e}"


async def generate_property_rendering(
    prompt: str,
    property_id: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Generates an architectural rendering, interior staging, or room redesign image using gemini-3.1-flash-lite-image in the global region.

    Saves the image as a session artifact and uploads it to public Cloud Storage, returning the public HTTPS URL.

    Args:
        prompt: Description of the architectural rendering, interior staging, or redesign visualization (e.g., 'Modern luxury chef kitchen with marble waterfall island and pendant lighting', 'Spacious primary bedroom with minimalist mid-century furniture and floor-to-ceiling windows').
        property_id: Optional property ID (e.g. 'prop-101') to ground the rendering to a specific listing from the catalog.
        tool_context: Context provided by the ADK runner for saving session artifacts.

    Returns:
        Public Cloud Storage HTTPS URL of the generated rendering along with details.
    """
    try:
        from google import genai
        from google.cloud import storage

        genai_client = genai.Client(
            vertexai=True,
            project=FIRESTORE_PROJECT_ID,
            location="global",
        )

        full_prompt = prompt.strip()
        prop_prefix = ""
        if property_id:
            db = get_firestore_client()
            doc = db.collection("properties").document(property_id.strip()).get()
            if doc.exists:
                p_data = doc.to_dict()
                title = p_data.get("title", "")
                prop_prefix = f"{property_id.strip()}_"
                full_prompt = f"Architectural photo rendering for '{title}': {prompt}"

        # Generate image using gemini-3.1-flash-lite-image in the global region
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=[full_prompt],
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.parts:
            for part in response.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return "Failed to generate image: no image data returned by the model."

        ext = "png" if "png" in mime_type else "jpg"
        filename = f"{prop_prefix}render_{uuid.uuid4().hex[:8]}.{ext}"

        # (1) Save with tool_context.save_artifact so it shows up in Playground's Artifacts panel
        if tool_context and hasattr(tool_context, "save_artifact"):
            try:
                artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                res = tool_context.save_artifact(filename=filename, artifact=artifact_part)
                if inspect.isawaitable(res):
                    await res
            except Exception:
                pass

        # (2) Upload the same image bytes to the public Cloud Storage bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return (
            f"Successfully generated property rendering!\n"
            f"- Prompt: {prompt}\n"
            f"- Artifact Saved: {filename}\n"
            f"- Public Image URL: {public_url}"
        )
    except Exception as e:
        return f"Error generating property rendering: {e}"


async def generate_property_video(
    prompt: str,
    property_id: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Generates a short property walkthrough, cinematic drone flythrough, or neighborhood tour video using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Saves the video as a session artifact so it appears in the Playground's Artifacts panel, and uploads it to public Cloud Storage, returning the public HTTPS URL.

    Args:
        prompt: Description of the video scene, camera motion, lighting, and architectural details (e.g., 'Cinematic drone flythrough of a modern luxury estate backyard with pool at sunset', 'Smooth walkthrough of an open-concept living room and chef kitchen with morning sunlight').
        property_id: Optional property ID (e.g. 'prop-101') to ground the video to a specific listing from the catalog.
        tool_context: Context provided by the ADK runner for saving session artifacts.

    Returns:
        Public Cloud Storage HTTPS URL of the generated video along with details.
    """
    try:
        import base64
        from google import genai
        from google.cloud import storage

        genai_client = genai.Client(
            vertexai=True,
            project="qwiklabs-gcp-04-b4fbcb7610df",
            location="global",
        )

        full_prompt = prompt.strip()
        prop_prefix = ""
        if property_id:
            db = get_firestore_client()
            doc = db.collection("properties").document(property_id.strip()).get()
            if doc.exists:
                p_data = doc.to_dict()
                title = p_data.get("title", "")
                prop_prefix = f"{property_id.strip()}_"
                full_prompt = f"Cinematic video tour for '{title}': {prompt}"

        # Generate short video using gemini-omni-flash-preview in the global region
        interaction = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=full_prompt,
            response_format={"type": "video"},
        )

        video_bytes = None
        mime_type = "video/mp4"

        if (
            hasattr(interaction, "output_video")
            and interaction.output_video
            and getattr(interaction.output_video, "data", None)
        ):
            raw = interaction.output_video.data
            video_bytes = base64.b64decode(raw) if isinstance(raw, str) else raw
            mime_type = getattr(interaction.output_video, "mime_type", "video/mp4") or "video/mp4"
        elif hasattr(interaction, "steps"):
            for step in interaction.steps:
                if getattr(step, "type", "") == "model_output" and hasattr(step, "content"):
                    for c in step.content:
                        if getattr(c, "type", "") == "video" and getattr(c, "data", None):
                            raw = c.data
                            video_bytes = base64.b64decode(raw) if isinstance(raw, str) else raw
                            mime_type = getattr(c, "mime_type", "video/mp4") or "video/mp4"
                            break

        if not video_bytes:
            return "Failed to generate video: no video data returned by gemini-omni-flash-preview."

        ext = "mp4"
        filename = f"{prop_prefix}video_{uuid.uuid4().hex[:8]}.{ext}"

        # (1) Save with tool_context.save_artifact so it shows up in the Playground's Artifacts panel
        if tool_context and hasattr(tool_context, "save_artifact"):
            try:
                artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
                res = tool_context.save_artifact(filename=filename, artifact=artifact_part)
                if inspect.isawaitable(res):
                    await res
            except Exception:
                pass

        # (2) Upload the same video bytes to the public Cloud Storage bucket
        storage_client = storage.Client(project="qwiklabs-gcp-04-b4fbcb7610df")
        bucket = storage_client.bucket("smart-real-estate-finder-qwiklabs-gcp-04-b4fbcb7610df")
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/smart-real-estate-finder-qwiklabs-gcp-04-b4fbcb7610df/{filename}"

        return (
            f"Successfully generated property video tour!\n"
            f"- Prompt: {prompt}\n"
            f"- Artifact Saved: {filename}\n"
            f"- Public Video URL: {public_url}"
        )
    except Exception as e:
        return f"Error generating property video: {e}"


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

role_description = (
    "You are the Smart Real Estate Finder agent, an autonomous production-grade real estate advisory system. "
    "You help home seekers discover, evaluate, visualize, and tour properties from your curated listings database. "
    "You remember the user's stated preferences, budget, property criteria, and facts from previous conversations and use them to personalize your recommendations and responses. "
    "Follow a disciplined ReAct cognitive framework on every turn: "
    "1. GOAL DECOMPOSITION: Analyze complex multi-criteria requests into clear sequential sub-goals (e.g. check memories -> search listings -> verify neighborhood amenities & air quality -> compute mortgage math). "
    "2. PLAN & ACT: Select and invoke the most effective tools with precise, validated arguments. "
    "3. EVALUATE & REFLECT: Inspect tool results carefully. If no properties match, or an external API experiences issues, reflect and provide helpful alternatives (e.g. adjust budget or search adjacent neighborhoods) instead of halting or hallucinating. "
    "4. COMPLETION DETECTION: Ensure all aspects of the user's objective have been evaluated before delivering the final response. "
    "Always use your available tools to search properties, view property details, calculate mortgage "
    "affordability, check neighborhood environmental & air quality metrics, geocode locations, "
    "find nearby amenities and places (schools, parks, transit, restaurants) via Google Places, "
    "generate architectural renderings and interior staging designs, generate property walkthrough videos, "
    "add new listings, or schedule showings. Provide clear, structured, and helpful guidance. "
    "When performing complex calculations, data analysis, mortgage comparisons, or investment ROI models, "
    "you can safely write and run Python code in your secure sandbox environment."
)

instruction = schema_manager.generate_system_prompt(
    role_description=role_description,
    workflow_description=(
        "Decompose the user's objective, execute relevant domain tools, evaluate the observations, "
        "and return structured A2UI declarative surfaces when presenting properties, tours, calculations, or neighborhood reports."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=AgentEngineSandboxCodeExecutor(
        sandbox_resource_name=SANDBOX_RESOURCE_NAME,
    ),
    tools=[
        PreloadMemoryTool(),
        search_properties,
        get_property_details,
        get_property_amenities,
        calculate_mortgage_payment,
        get_neighborhood_air_quality,
        geocode_address,
        find_nearby_places,
        generate_property_rendering,
        generate_property_video,
        add_property_listing,
        schedule_property_tour,
        get_weather,
        get_current_time,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
