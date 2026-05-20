"""Smoke tests for stub endpoints, dashboard, and webhook verification.

None of these endpoints require DB access; http_client is used throughout
(the DB override is registered but never triggered for these routes).
"""

import pytest

pytestmark = pytest.mark.asyncio


async def test_admin_config_stub_returns_200(http_client):
    resp = await http_client.get("/api/v1/admin/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "Not yet implemented" in body.get("message", "")


async def test_session_stub_returns_200(http_client):
    resp = await http_client.get("/api/v1/sessions/any-session-id")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "Not yet implemented" in body.get("message", "")


async def test_dashboard_returns_html(http_client):
    resp = await http_client.get("/dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert len(resp.text) > 100  # non-trivial HTML


async def test_webhook_verify_valid_token(http_client):
    resp = await http_client.get(
        "/webhook/inbound",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "test-challenge-xyz",
            "hub.verify_token": "estateflow-verify",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "test-challenge-xyz"


async def test_webhook_verify_wrong_token_returns_403(http_client):
    resp = await http_client.get(
        "/webhook/inbound",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "test-challenge-xyz",
            "hub.verify_token": "definitely-wrong",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["success"] is False
