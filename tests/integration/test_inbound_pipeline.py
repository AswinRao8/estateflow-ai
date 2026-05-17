"""Integration tests for the inbound message pipeline.

External I/O (Anthropic classify_intent, WhatsApp send_whatsapp_text) is mocked
so tests run against the real DB without network dependencies. All other service
code — lead/session/message persistence, state transitions, workflow dispatch —
runs end-to-end.
"""
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.whatsapp.types import InboundMessage
from app.models.context import ClassificationResult
from app.models.enums import IntentType, LeadState, MessageDirection, WorkflowType
from app.services import conversation_service, lead_service
from app.workflows.inbound_message_workflow import process_inbound_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(
    phone: str,
    body: str = "Hello",
    listing_ref_url: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        phone_number=phone,
        message_id=f"wamid.{uuid.uuid4().hex[:12]}",
        body=body,
        timestamp=datetime.now(timezone.utc),
        listing_ref_url=listing_ref_url,
    )


def _unique_phone() -> str:
    return f"+1{uuid.uuid4().int % 10_000_000_000:010d}"


def _patch_classify(intent: IntentType = IntentType.GENERAL_INQUIRY, confidence: float = 0.9):
    """Context manager: mock classify_intent to return a controlled result."""
    return patch(
        "app.services.conversation_service.classify_intent",
        new_callable=AsyncMock,
        return_value=ClassificationResult(
            intent=intent,
            confidence=confidence,
            reasoning="integration test mock",
        ),
    )


def _patch_notify(provider_id: str = "wamid.mock001"):
    """Context manager: mock send_whatsapp_text to avoid real API calls."""
    return patch(
        "app.services.notification_service.send_whatsapp_text",
        new_callable=AsyncMock,
        return_value=provider_id,
    )


# ---------------------------------------------------------------------------
# Lead and session creation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_message_creates_lead_session_and_message(db):
    phone = _unique_phone()
    with _patch_classify(), _patch_notify():
        result = await process_inbound_message(
            db, message=_make_message(phone, "I'm interested in the villa")
        )

    assert result.lead.phone_number == phone
    assert result.session.lead_id == result.lead.id
    assert result.message.body == "I'm interested in the villa"
    assert result.message.direction == MessageDirection.INBOUND
    assert result.message.session_id == result.session.id
    assert result.message.lead_id == result.lead.id
    assert result.is_human_active is False


@pytest.mark.asyncio
async def test_second_message_reuses_existing_lead_and_session(db):
    phone = _unique_phone()
    with _patch_classify(), _patch_notify():
        result1 = await process_inbound_message(db, message=_make_message(phone, "First"))
        result2 = await process_inbound_message(db, message=_make_message(phone, "Second"))

    assert result1.lead.id == result2.lead.id
    assert result1.session.id == result2.session.id
    assert result2.message.body == "Second"


@pytest.mark.asyncio
async def test_different_phone_numbers_get_separate_leads(db):
    phone_a, phone_b = _unique_phone(), _unique_phone()
    with _patch_classify(), _patch_notify():
        result_a = await process_inbound_message(db, message=_make_message(phone_a))
        result_b = await process_inbound_message(db, message=_make_message(phone_b))

    assert result_a.lead.id != result_b.lead.id
    assert result_a.session.id != result_b.session.id


# ---------------------------------------------------------------------------
# Listing ref extraction and propagation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_listing_ref_code_extracted_from_url_and_stored(db):
    phone = _unique_phone()
    with _patch_classify(), _patch_notify():
        result = await process_inbound_message(
            db,
            message=_make_message(
                phone, "Tell me more",
                listing_ref_url="https://agency.com/listings/villa-88",
            ),
        )

    # The URL is parsed — only the last path segment is stored as the reference code.
    assert result.lead.source_listing_ref_code == "villa-88"
    assert result.session.listing_ref_code == "villa-88"


@pytest.mark.asyncio
async def test_listing_ref_code_not_overwritten_on_second_message(db):
    phone = _unique_phone()
    with _patch_classify(), _patch_notify():
        await process_inbound_message(
            db,
            message=_make_message(
                phone, "First",
                listing_ref_url="https://agency.com/listings/original",
            ),
        )
        result2 = await process_inbound_message(
            db,
            message=_make_message(
                phone, "Second",
                listing_ref_url="https://agency.com/listings/other",
            ),
        )

    # Session was created with "original" — must not be overwritten by the second message.
    assert result2.session.listing_ref_code == "original"


# ---------------------------------------------------------------------------
# Human-active gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_human_active_lead_returns_is_human_active_true(db):
    phone = _unique_phone()
    with _patch_classify(), _patch_notify():
        first = await process_inbound_message(db, message=_make_message(phone, "Hi"))

    await lead_service.set_human_active(db, lead_id=first.lead.id, agent_id="agent-007")

    # No mocks needed — pipeline returns before reaching AI layer.
    result = await process_inbound_message(db, message=_make_message(phone, "Follow up"))
    assert result.is_human_active is True


@pytest.mark.asyncio
async def test_human_active_message_is_still_persisted(db):
    phone = _unique_phone()
    with _patch_classify(), _patch_notify():
        first = await process_inbound_message(db, message=_make_message(phone))

    await lead_service.set_human_active(db, lead_id=first.lead.id, agent_id="agent-007")

    result = await process_inbound_message(
        db, message=_make_message(phone, "Need help urgently")
    )
    assert result.is_human_active is True
    assert result.message.body == "Need help urgently"
    assert result.message.direction == MessageDirection.INBOUND


@pytest.mark.asyncio
async def test_human_active_pipeline_does_not_call_classify_intent(db):
    phone = _unique_phone()
    with _patch_classify(), _patch_notify():
        first = await process_inbound_message(db, message=_make_message(phone))

    await lead_service.set_human_active(db, lead_id=first.lead.id, agent_id="agent-007")

    with _patch_classify() as mock_classify:
        await process_inbound_message(db, message=_make_message(phone, "Still waiting"))

    mock_classify.assert_not_called()


@pytest.mark.asyncio
async def test_non_human_active_lead_returns_is_human_active_false(db):
    phone = _unique_phone()
    with _patch_classify(), _patch_notify():
        result = await process_inbound_message(db, message=_make_message(phone))

    assert result.is_human_active is False


# ---------------------------------------------------------------------------
# Pre-LLM keyword escalation fast-path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_keyword_escalation_sets_human_active(db):
    phone = _unique_phone()
    with _patch_notify():
        result = await process_inbound_message(
            db, message=_make_message(phone, "I want to speak to a human agent")
        )

    assert result.is_human_active is True
    assert result.workflow_type == WorkflowType.ESCALATION


@pytest.mark.asyncio
async def test_keyword_escalation_does_not_call_classify_intent(db):
    phone = _unique_phone()
    with _patch_classify() as mock_classify, _patch_notify():
        await process_inbound_message(
            db, message=_make_message(phone, "Please connect me with a real agent")
        )

    mock_classify.assert_not_called()


@pytest.mark.asyncio
async def test_keyword_escalation_persists_outbound_ack(db):
    phone = _unique_phone()
    with _patch_notify():
        result = await process_inbound_message(
            db, message=_make_message(phone, "I need to talk to a human")
        )

    messages = await conversation_service.get_session_messages(db, session_id=result.session.id)
    outbound = [m for m in messages if m.direction == MessageDirection.OUTBOUND]
    assert len(outbound) == 1
    assert outbound[0].body  # Acknowledgement was sent


# ---------------------------------------------------------------------------
# Pre-LLM NEGOTIATION state escalation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_negotiation_state_triggers_auto_escalation(db):
    phone = _unique_phone()
    # Create lead and advance it to NEGOTIATION via HUMAN_ACTIVE shortcut.
    with _patch_classify(), _patch_notify():
        first = await process_inbound_message(db, message=_make_message(phone))

    await lead_service.advance_state(db, lead_id=first.lead.id, to_state=LeadState.HUMAN_ACTIVE)
    await lead_service.advance_state(db, lead_id=first.lead.id, to_state=LeadState.NEGOTIATION)

    with _patch_notify():
        result = await process_inbound_message(
            db, message=_make_message(phone, "Can we discuss price?")
        )

    assert result.is_human_active is True
    assert result.workflow_type == WorkflowType.ESCALATION


@pytest.mark.asyncio
async def test_negotiation_escalation_does_not_call_classify_intent(db):
    phone = _unique_phone()
    with _patch_classify(), _patch_notify():
        first = await process_inbound_message(db, message=_make_message(phone))

    await lead_service.advance_state(db, lead_id=first.lead.id, to_state=LeadState.HUMAN_ACTIVE)
    await lead_service.advance_state(db, lead_id=first.lead.id, to_state=LeadState.NEGOTIATION)

    with _patch_classify() as mock_classify, _patch_notify():
        await process_inbound_message(db, message=_make_message(phone, "Offer accepted?"))

    mock_classify.assert_not_called()


# ---------------------------------------------------------------------------
# Intent classification and routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_high_confidence_classification_sets_workflow_type(db):
    phone = _unique_phone()
    with _patch_classify(IntentType.LISTING_INQUIRY, confidence=0.95), _patch_notify():
        result = await process_inbound_message(
            db, message=_make_message(phone, "Tell me about the property")
        )

    assert result.workflow_type == WorkflowType.LISTING_INQUIRY
    assert result.is_human_active is False


@pytest.mark.asyncio
async def test_low_confidence_routes_to_clarification(db):
    phone = _unique_phone()
    with _patch_classify(IntentType.LISTING_INQUIRY, confidence=0.4), _patch_notify():
        result = await process_inbound_message(
            db, message=_make_message(phone, "Maybe something?")
        )

    assert result.workflow_type == WorkflowType.CLARIFICATION
    assert result.is_human_active is False


@pytest.mark.asyncio
async def test_human_requested_intent_escalates_regardless_of_confidence(db):
    phone = _unique_phone()
    # Even at low confidence, HUMAN_REQUESTED must escalate.
    with _patch_classify(IntentType.HUMAN_REQUESTED, confidence=0.3), _patch_notify():
        result = await process_inbound_message(
            db, message=_make_message(phone, "Human please")
        )

    assert result.is_human_active is True
    assert result.workflow_type == WorkflowType.ESCALATION


# ---------------------------------------------------------------------------
# Outbound message persistence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_outbound_message_is_persisted_after_workflow_dispatch(db):
    phone = _unique_phone()
    with _patch_classify(IntentType.GENERAL_INQUIRY, confidence=0.9), _patch_notify():
        result = await process_inbound_message(
            db, message=_make_message(phone, "What properties do you have?")
        )

    messages = await conversation_service.get_session_messages(db, session_id=result.session.id)
    outbound = [m for m in messages if m.direction == MessageDirection.OUTBOUND]
    assert len(outbound) == 1
    assert outbound[0].body


@pytest.mark.asyncio
async def test_outbound_message_uses_provider_id_from_notification_service(db):
    phone = _unique_phone()
    with _patch_classify(), _patch_notify(provider_id="wamid.expected123"):
        result = await process_inbound_message(
            db, message=_make_message(phone, "Hello")
        )

    messages = await conversation_service.get_session_messages(db, session_id=result.session.id)
    outbound = [m for m in messages if m.direction == MessageDirection.OUTBOUND]
    assert outbound[0].provider_message_id == "wamid.expected123"
