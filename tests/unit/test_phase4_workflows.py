"""Unit tests for the four Phase 4 workflow functions.

Escalation workflow tests mock lead_service.set_human_active so no real
database is required. Clarification and out_of_scope workflows have no
external dependencies.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import HandoffReason, LeadState, WorkflowType
from app.workflows import clarification_workflow, escalation_workflow, out_of_scope_workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_lead(lead_id=None, state=LeadState.NEW_INQUIRY):
    return SimpleNamespace(id=lead_id or uuid.uuid4(), state=state)


def _fake_context(state=LeadState.NEW_INQUIRY) -> ConversationContext:
    return ConversationContext(
        lead=_fake_lead(state=state),
        session=SimpleNamespace(id=uuid.uuid4()),
        recent_messages=[],
        current_message="Test message",
        listing=None,
    )


# ---------------------------------------------------------------------------
# clarification_workflow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clarification_workflow_returns_outbound_message():
    result = await clarification_workflow.run(_fake_context())
    assert result.outbound_message is not None
    assert len(result.outbound_message) > 0


@pytest.mark.asyncio
async def test_clarification_workflow_sets_correct_workflow_type():
    result = await clarification_workflow.run(_fake_context())
    assert result.workflow_type == WorkflowType.CLARIFICATION


@pytest.mark.asyncio
async def test_clarification_workflow_does_not_change_lead_state():
    result = await clarification_workflow.run(_fake_context())
    assert result.new_lead_state is None


@pytest.mark.asyncio
async def test_clarification_workflow_message_mentions_property():
    result = await clarification_workflow.run(_fake_context())
    assert "property" in result.outbound_message.lower()


# ---------------------------------------------------------------------------
# out_of_scope_workflow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_out_of_scope_workflow_returns_outbound_message():
    result = await out_of_scope_workflow.run(_fake_context())
    assert result.outbound_message is not None
    assert len(result.outbound_message) > 0


@pytest.mark.asyncio
async def test_out_of_scope_workflow_sets_correct_workflow_type():
    result = await out_of_scope_workflow.run(_fake_context())
    assert result.workflow_type == WorkflowType.OUT_OF_SCOPE


@pytest.mark.asyncio
async def test_out_of_scope_workflow_does_not_change_lead_state():
    result = await out_of_scope_workflow.run(_fake_context())
    assert result.new_lead_state is None


@pytest.mark.asyncio
async def test_out_of_scope_workflow_message_redirects_to_property():
    result = await out_of_scope_workflow.run(_fake_context())
    text = result.outbound_message.lower()
    assert "property" in text or "real estate" in text


# ---------------------------------------------------------------------------
# escalation_workflow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalation_workflow_calls_set_human_active():
    db = AsyncMock()
    ctx = _fake_context()

    with patch(
        "app.workflows.escalation_workflow.lead_service.set_human_active",
        new_callable=AsyncMock,
    ) as mock_fn:
        await escalation_workflow.run(db, ctx, reason=HandoffReason.USER_REQUESTED)

    mock_fn.assert_awaited_once_with(db, lead_id=ctx.lead.id, agent_id="ai_escalation")


@pytest.mark.asyncio
async def test_escalation_workflow_returns_human_active_state():
    db = AsyncMock()
    ctx = _fake_context()

    with patch(
        "app.workflows.escalation_workflow.lead_service.set_human_active",
        new_callable=AsyncMock,
    ):
        result = await escalation_workflow.run(db, ctx, reason=HandoffReason.NEGOTIATION)

    assert result.new_lead_state == LeadState.HUMAN_ACTIVE


@pytest.mark.asyncio
async def test_escalation_workflow_returns_ack_message():
    db = AsyncMock()
    ctx = _fake_context()

    with patch(
        "app.workflows.escalation_workflow.lead_service.set_human_active",
        new_callable=AsyncMock,
    ):
        result = await escalation_workflow.run(db, ctx, reason=HandoffReason.USER_REQUESTED)

    assert result.outbound_message is not None
    assert len(result.outbound_message) > 0


@pytest.mark.asyncio
async def test_escalation_workflow_sets_correct_workflow_type():
    db = AsyncMock()
    ctx = _fake_context()

    with patch(
        "app.workflows.escalation_workflow.lead_service.set_human_active",
        new_callable=AsyncMock,
    ):
        result = await escalation_workflow.run(db, ctx, reason=HandoffReason.LOW_AI_CONFIDENCE)

    assert result.workflow_type == WorkflowType.ESCALATION


@pytest.mark.asyncio
async def test_escalation_workflow_still_returns_ack_when_set_human_active_raises():
    db = AsyncMock()
    ctx = _fake_context()

    with patch(
        "app.workflows.escalation_workflow.lead_service.set_human_active",
        new_callable=AsyncMock,
        side_effect=Exception("DB error"),
    ):
        result = await escalation_workflow.run(db, ctx, reason=HandoffReason.USER_REQUESTED)

    # ACK must still be sent even if the DB update fails
    assert result.outbound_message is not None
    assert result.new_lead_state == LeadState.HUMAN_ACTIVE


@pytest.mark.parametrize("reason", list(HandoffReason))
@pytest.mark.asyncio
async def test_escalation_workflow_accepts_any_handoff_reason(reason):
    db = AsyncMock()
    ctx = _fake_context()

    with patch(
        "app.workflows.escalation_workflow.lead_service.set_human_active",
        new_callable=AsyncMock,
    ):
        result = await escalation_workflow.run(db, ctx, reason=reason)

    assert isinstance(result, WorkflowResult)
    assert result.workflow_type == WorkflowType.ESCALATION
