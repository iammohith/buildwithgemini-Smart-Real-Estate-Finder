#!/usr/bin/env python3
"""Seed script for Smart Real Estate Finder Firestore database."""

from google.cloud import firestore

# Hardcode GCP Project ID as requested to avoid project number issues on Agent Platform
PROJECT_ID = "qwiklabs-gcp-04-b4fbcb7610df"

PROPERTIES = [
    {
        "id": "prop-101",
        "title": "Modern Craftsman in South Congress",
        "price": 650000,
        "city": "Austin",
        "neighborhood": "South Congress",
        "bedrooms": 3,
        "bathrooms": 2.5,
        "sqft": 2100,
        "property_type": "Single Family",
        "status": "Available",
        "year_built": 2021,
        "description": "Stunning modern craftsman walking distance to trendy South Congress restaurants, shops, and parks. Features an open-concept chef's kitchen, high ceilings, and a private fenced yard.",
        "features": ["hardwood floors", "quartz countertops", "solar panels", "fenced yard", "walk-in closet", "EV charger"],
    },
    {
        "id": "prop-102",
        "title": "Luxury Skyline Loft in Downtown",
        "price": 485000,
        "city": "Austin",
        "neighborhood": "Downtown",
        "bedrooms": 2,
        "bathrooms": 2.0,
        "sqft": 1250,
        "property_type": "Condo",
        "status": "Available",
        "year_built": 2019,
        "description": "High-floor loft with floor-to-ceiling panoramic skyline views. Building includes 24/7 concierge, infinity rooftop pool, fitness center, and secure parking.",
        "features": ["skyline views", "balcony", "rooftop pool", "concierge", "gym", "in-unit laundry"],
    },
    {
        "id": "prop-103",
        "title": "Contemporary Townhome in Ballard",
        "price": 795000,
        "city": "Seattle",
        "neighborhood": "Ballard",
        "bedrooms": 3,
        "bathrooms": 3.0,
        "sqft": 1850,
        "property_type": "Townhouse",
        "status": "Available",
        "year_built": 2022,
        "description": "Sleek 3-story townhome near the Ballard Locks and Golden Gardens. Boasts a private rooftop deck with mountain views, energy-efficient heat pump, and designated carport.",
        "features": ["rooftop deck", "mini-split A/C", "gas range", "mountain views", "attached carport"],
    },
    {
        "id": "prop-104",
        "title": "Charming Mid-Century Ranch in Crestview",
        "price": 575000,
        "city": "Austin",
        "neighborhood": "Crestview",
        "bedrooms": 3,
        "bathrooms": 2.0,
        "sqft": 1600,
        "property_type": "Single Family",
        "status": "Available",
        "year_built": 1965,
        "description": "Lovingly updated mid-century home with original oak floors, remodeled bathrooms, and a lush backyard with mature pecan trees. Minutes from commuter rail.",
        "features": ["original hardwood", "large backyard", "mature trees", "updated plumbing", "near metro rail"],
    },
    {
        "id": "prop-105",
        "title": "Sunny Victorian in Capitol Hill",
        "price": 720000,
        "city": "Denver",
        "neighborhood": "Capitol Hill",
        "bedrooms": 4,
        "bathrooms": 3.0,
        "sqft": 2400,
        "property_type": "Single Family",
        "status": "Available",
        "year_built": 1910,
        "description": "Historic charm meets modern living. High ceilings, exposed brick accent walls, gas fireplace, detached 2-car garage, and private landscaped courtyard patio.",
        "features": ["exposed brick", "fireplace", "historic character", "detached garage", "private patio"],
    },
]


def seed_properties():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    properties_ref = db.collection("properties")

    for item in PROPERTIES:
        doc_id = item["id"]
        properties_ref.document(doc_id).set(item)
        print(f"✓ Seeded property {doc_id}: {item['title']} (${item['price']:,})")

    print("\nAll sample properties successfully seeded into Firestore!")


if __name__ == "__main__":
    seed_properties()
