"""Smoke tests for /health and /ready endpoints."""

import pytest

pytestmark = pytest.mark.asyncio


async def test_health_status_200(http_client):
    resp = await http_client.get("/health")
    assert resp.status_code == 200


async def test_health_envelope_structure(http_client):
    body = (await http_client.get("/health")).json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "ok"
    for field in ("app", "version", "environment", "timestamp"):
        assert field in data, f"missing field {field!r}"


async def test_health_market_block(http_client):
    data = (await http_client.get("/health")).json()["data"]
    assert "market" in data
    market = data["market"]
    for key in ("currency", "area_unit", "timezone", "locale"):
        assert key in market, f"missing market key {key!r}"


async def test_ready_skips_db_in_testing_env(http_client):
    # ENVIRONMENT=testing is set by the root conftest → DB check is skipped
    resp = await http_client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["checks"]["database"] == "skipped"
    assert body["data"]["status"] == "ready"
