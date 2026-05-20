"""Smoke tests for the /api/v1/listings endpoints.

Read tests use http_client (real DB, no rollback).
Write tests use rw_client (real DB, rolled back after each test).
"""

import uuid

import pytest

pytestmark = pytest.mark.asyncio

_API = "/api/v1/listings"


def _new_listing(**overrides) -> dict:
    body = {
        "reference_code": f"SMOKE-{uuid.uuid4().hex[:8]}",
        "title": "Smoke Test Apartment",
        "property_type": "APARTMENT",
        "transaction_type": "SALE",
        "price": 250000.00,
        "bedrooms": 2,
        "bathrooms": 1,
        "location_area": "Smoke Bay",
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Read tests
# ---------------------------------------------------------------------------


async def test_list_listings_200(http_client):
    resp = await http_client.get(_API)
    assert resp.status_code == 200


async def test_list_listings_envelope(http_client):
    body = (await http_client.get(_API)).json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


async def test_list_listings_pagination(http_client):
    resp = await http_client.get(f"{_API}?limit=2&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) <= 2


async def test_get_listing_by_id(http_client):
    first = (await http_client.get(f"{_API}?limit=1")).json()["data"]
    if not first:
        pytest.skip("no listings seeded — run scripts/seed.py first")
    lid = first[0]["id"]

    resp = await http_client.get(f"{_API}/{lid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["id"] == lid
    for field in ("reference_code", "title", "property_type", "status"):
        assert field in body["data"]


async def test_get_listing_not_found_returns_404(http_client):
    resp = await http_client.get(f"{_API}/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["success"] is False


async def test_get_listing_invalid_uuid_returns_422(http_client):
    resp = await http_client.get(f"{_API}/not-a-uuid")
    assert resp.status_code == 422
    assert resp.json()["success"] is False


# ---------------------------------------------------------------------------
# Write tests
# ---------------------------------------------------------------------------


async def test_create_listing_returns_201(rw_client):
    client, _ = rw_client
    resp = await client.post(_API, json=_new_listing())
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["property_type"] == "APARTMENT"
    assert data["transaction_type"] == "SALE"
    assert data["status"] == "AVAILABLE"
    assert "id" in data


async def test_create_listing_db_persistence(rw_client):
    client, _ = rw_client
    ref = f"SMOKE-{uuid.uuid4().hex[:8]}"
    create = await client.post(_API, json=_new_listing(reference_code=ref))
    assert create.status_code == 201
    lid = create.json()["data"]["id"]

    get = await client.get(f"{_API}/{lid}")
    assert get.status_code == 200
    assert get.json()["data"]["reference_code"] == ref


async def test_create_listing_missing_title_returns_422(rw_client):
    client, _ = rw_client
    body = _new_listing()
    del body["title"]
    resp = await client.post(_API, json=body)
    assert resp.status_code == 422
    assert resp.json()["success"] is False


async def test_create_listing_invalid_property_type_returns_422(rw_client):
    client, _ = rw_client
    resp = await client.post(_API, json=_new_listing(property_type="CASTLE"))
    assert resp.status_code == 422
    assert resp.json()["success"] is False


async def test_create_listing_invalid_transaction_type_returns_422(rw_client):
    client, _ = rw_client
    resp = await client.post(_API, json=_new_listing(transaction_type="BARTER"))
    assert resp.status_code == 422
    assert resp.json()["success"] is False


async def test_patch_listing_status(rw_client):
    client, _ = rw_client
    lid = (await client.post(_API, json=_new_listing())).json()["data"]["id"]

    resp = await client.patch(f"{_API}/{lid}/status", json={"status": "UNDER_OFFER"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "UNDER_OFFER"


async def test_patch_listing_status_invalid_value_returns_422(rw_client):
    client, _ = rw_client
    lid = (await client.post(_API, json=_new_listing())).json()["data"]["id"]

    resp = await client.patch(f"{_API}/{lid}/status", json={"status": "IMAGINARY"})
    assert resp.status_code == 422


async def test_patch_listing_status_nonexistent_returns_404(rw_client):
    client, _ = rw_client
    resp = await client.patch(f"{_API}/{uuid.uuid4()}/status", json={"status": "SOLD"})
    assert resp.status_code == 404


async def test_put_listing_update(rw_client):
    client, _ = rw_client
    lid = (await client.post(_API, json=_new_listing())).json()["data"]["id"]

    resp = await client.put(f"{_API}/{lid}", json={"title": "Updated Title", "bedrooms": 4})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["title"] == "Updated Title"
    assert data["bedrooms"] == 4


async def test_put_listing_nonexistent_returns_404(rw_client):
    client, _ = rw_client
    resp = await client.put(f"{_API}/{uuid.uuid4()}", json={"title": "Ghost"})
    assert resp.status_code == 404
