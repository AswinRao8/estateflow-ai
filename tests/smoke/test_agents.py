"""Smoke tests for the /api/v1/agents endpoints.

All tests use rw_client (real DB, savepoint rollback).
Leads are inserted directly into the shared session before each HTTP call so
the request handler can find them on the same connection.
"""

import uuid

import pytest
from app.models.enums import LeadState
from app.models.lead import Lead

pytestmark = pytest.mark.asyncio

_TAKEOVER = "/api/v1/agents/{agent_id}/takeover"
_RELEASE = "/api/v1/agents/{agent_id}/release"
_LEADS = "/api/v1/leads"


async def _insert_lead(session, state: LeadState) -> Lead:
    """Add a lead to the session and flush so it's visible in HTTP calls."""
    lead = Lead(
        tenant_id="default",
        phone_number=f"+smoke{uuid.uuid4().hex[:10]}",
        state=state,
        is_human_active=(state == LeadState.HUMAN_ACTIVE),
    )
    session.add(lead)
    await session.flush()
    return lead


# ---------------------------------------------------------------------------
# Takeover
# ---------------------------------------------------------------------------


async def test_takeover_qualifying_lead_returns_200(rw_client):
    client, session = rw_client
    lead = await _insert_lead(session, LeadState.QUALIFYING)

    resp = await client.post(
        _TAKEOVER.format(agent_id="agent-alice"),
        json={"lead_id": str(lead.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"] is not None


async def test_takeover_sets_human_active_state(rw_client):
    client, session = rw_client
    lead = await _insert_lead(session, LeadState.QUALIFYING)

    await client.post(
        _TAKEOVER.format(agent_id="agent-alice"),
        json={"lead_id": str(lead.id)},
    )
    detail = (await client.get(f"{_LEADS}/{lead.id}")).json()["data"]
    assert detail["state"] == "HUMAN_ACTIVE"
    assert detail["is_human_active"] is True
    assert detail["assigned_agent_id"] == "agent-alice"


async def test_takeover_nonexistent_lead_returns_404(rw_client):
    client, _ = rw_client
    resp = await client.post(
        _TAKEOVER.format(agent_id="agent-alice"),
        json={"lead_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
    assert resp.json()["success"] is False


async def test_takeover_terminal_lead_returns_409(rw_client):
    client, session = rw_client
    lead = await _insert_lead(session, LeadState.CLOSED_WON)

    resp = await client.post(
        _TAKEOVER.format(agent_id="agent-alice"),
        json={"lead_id": str(lead.id)},
    )
    assert resp.status_code == 409
    assert resp.json()["success"] is False


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------


async def test_release_lead_returns_200(rw_client):
    client, session = rw_client
    lead = await _insert_lead(session, LeadState.HUMAN_ACTIVE)
    lead.assigned_agent_id = "agent-bob"
    await session.flush()

    resp = await client.post(
        _RELEASE.format(agent_id="agent-bob"),
        json={"lead_id": str(lead.id), "to_state": "QUALIFYING"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["state"] == "QUALIFYING"
    assert data["is_human_active"] is False
    assert data["assigned_agent_id"] is None


async def test_release_nonexistent_lead_returns_404(rw_client):
    client, _ = rw_client
    resp = await client.post(
        _RELEASE.format(agent_id="agent-bob"),
        json={"lead_id": str(uuid.uuid4()), "to_state": "QUALIFYING"},
    )
    assert resp.status_code == 404


async def test_release_non_human_active_lead_returns_409(rw_client):
    client, session = rw_client
    lead = await _insert_lead(session, LeadState.QUALIFYING)

    resp = await client.post(
        _RELEASE.format(agent_id="agent-bob"),
        json={"lead_id": str(lead.id), "to_state": "QUALIFYING"},
    )
    assert resp.status_code == 409
