"""Smoke tests for the /api/v1/leads endpoints.

All tests are read-only; leads are created by scripts/seed.py.
Uses http_client (real DB, no rollback).
"""

import uuid

import pytest

pytestmark = pytest.mark.asyncio

_API = "/api/v1/leads"


async def test_list_leads_200(http_client):
    resp = await http_client.get(_API)
    assert resp.status_code == 200


async def test_list_leads_envelope(http_client):
    body = (await http_client.get(_API)).json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


async def test_list_leads_pagination(http_client):
    resp = await http_client.get(f"{_API}?limit=3&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) <= 3


async def test_list_leads_fields(http_client):
    resp = await http_client.get(f"{_API}?limit=1")
    assert resp.status_code == 200
    leads = resp.json()["data"]
    if not leads:
        pytest.skip("no leads in DB — run scripts/seed.py first")
    lead = leads[0]
    for field in ("id", "phone_number", "state", "is_human_active", "created_at"):
        assert field in lead, f"missing field {field!r}"


async def test_get_lead_detail(http_client):
    leads = (await http_client.get(f"{_API}?limit=1")).json()["data"]
    if not leads:
        pytest.skip("no leads in DB — run scripts/seed.py first")
    lid = leads[0]["id"]

    resp = await http_client.get(f"{_API}/{lid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["id"] == lid
    assert "messages" in data and isinstance(data["messages"], list)
    assert "follow_ups" in data and isinstance(data["follow_ups"], list)


async def test_get_lead_not_found_returns_404(http_client):
    resp = await http_client.get(f"{_API}/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["success"] is False


async def test_get_lead_invalid_uuid_returns_422(http_client):
    resp = await http_client.get(f"{_API}/not-a-uuid")
    assert resp.status_code == 422
    assert resp.json()["success"] is False
