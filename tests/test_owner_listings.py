"""Tests for RESTAMP Owner V1 property listing endpoints:
- POST /owner/listings (create listing)
- GET /owner/listings (list caller's listings)
- GET /owner/listings/{listing_id} (detail)
- Role verification (OWNER required)
"""
import pytest
from tests.conftest import auth_header, make_postcode, register_phone


def _setup_owner(client) -> tuple[dict, str]:
    """Register a user and upgrade their role to OWNER."""
    token_out = register_phone(client, "+919876543210")
    token = token_out["access_token"]

    # Upgrade role to OWNER
    r = client.post(
        "/users/me/role",
        json={"role": "OWNER"},
        headers=auth_header(token),
    )
    assert r.status_code == 200, r.text
    # Re-verify profile or use token (role is evaluated from DB / token)
    return token_out, token


def test_create_listing_requires_auth(client):
    c, session = client
    r = c.post("/owner/listings", json={"title": "Test Apartment", "price_rupees": 5000000})
    assert r.status_code == 401


def test_create_listing_requires_owner_role(client):
    c, session = client
    # Default registered user is BUYER
    token_out = register_phone(c, "+919876543211")
    token = token_out["access_token"]

    r = c.post(
        "/owner/listings",
        json={
            "title": "Test Villa",
            "price_rupees": 7500000,
            "locality": "Indiranagar",
            "city": "Bengaluru",
            "pincode": "560038",
        },
        headers=auth_header(token),
    )
    assert r.status_code == 403


def test_create_and_fetch_owner_listing(client):
    c, session = client
    _, token = _setup_owner(c)

    # 1. Create a listing
    payload = {
        "title": "Luxury 3BHK Apartment in Indiranagar",
        "transaction_type": "BUY",
        "property_type": "APARTMENT",
        "price_rupees": 12500000,
        "price_period": "TOTAL",
        "locality": "Indiranagar",
        "city": "Bengaluru",
        "pincode": "560038",
        "address_line": "100 Feet Road, 12th Main",
        "area_value": 1850,
        "area_unit": "sqft",
        "bedrooms": 3,
        "bathrooms": 3,
        "description": "Spacious north-facing apartment with 2 car parks.",
        "construction_status": "READY_TO_MOVE",
        "images": [
            "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?w=800",
            "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800",
        ],
    }

    r = c.post("/owner/listings", json=payload, headers=auth_header(token))
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["title"] == "Luxury 3BHK Apartment in Indiranagar"
    assert created["price_paise"] == 1250000000
    assert created["verification_status"] == "PENDING"
    assert created["listing_status"] == "AVAILABLE"
    assert created["bedrooms"] == 3
    assert created["bathrooms"] == 3
    assert created["locality"] == "Indiranagar"
    assert created["cover_image_url"] == payload["images"][0]
    listing_id = created["listing_id"]

    # 2. List caller's listings
    r = c.get("/owner/listings", headers=auth_header(token))
    assert r.status_code == 200, r.text
    list_data = r.json()
    assert list_data["total"] >= 1
    found = [item for item in list_data["items"] if item["listing_id"] == listing_id]
    assert len(found) == 1
    assert found[0]["title"] == "Luxury 3BHK Apartment in Indiranagar"

    # 3. Get single listing detail
    r = c.get(f"/owner/listings/{listing_id}", headers=auth_header(token))
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["listing_id"] == listing_id
    assert detail["gallery"] == payload["images"]
    assert detail["cover_image_url"] == payload["images"][0]


def test_owner_cannot_access_other_owner_listing(client):
    c, session = client
    # Setup Owner A
    token_out_a = register_phone(c, "+919876543212")
    token_a = token_out_a["access_token"]
    c.post("/users/me/role", json={"role": "OWNER"}, headers=auth_header(token_a))

    # Setup Owner B
    token_out_b = register_phone(c, "+919876543213")
    token_b = token_out_b["access_token"]
    c.post("/users/me/role", json={"role": "OWNER"}, headers=auth_header(token_b))

    # Owner A creates listing
    r = c.post(
        "/owner/listings",
        json={
            "title": "Owner A Villa",
            "price_rupees": 5000000,
            "locality": "Whitefield",
            "city": "Bengaluru",
            "pincode": "560066",
        },
        headers=auth_header(token_a),
    )
    assert r.status_code == 201
    listing_id = r.json()["listing_id"]

    # Owner B tries to read Owner A's listing via /owner/listings/{id}
    r = c.get(f"/owner/listings/{listing_id}", headers=auth_header(token_b))
    assert r.status_code == 404
