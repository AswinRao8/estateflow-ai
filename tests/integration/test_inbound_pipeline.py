import uuid
from datetime import datetime, timezone

import pytest

from app.integrations.whatsapp.types import InboundMessage
from app.models.enums import MessageDirection
from app.services import lead_service
from app.workflows.inbound_message_workflow import process_inbound_message

TENANT = "tenant_pipeline_test"


def _make_message(phone: str, body: str = "Hello", listing_ref: str | None = None) -> InboundMessage:
    return InboundMessage(
        phone_number=phone,
        message_id=f"wamid.{uuid.uuid4().hex[:12]}",
        body=body,
        timestamp=datetime.now(timezone.utc),
        listing_ref=listing_ref,
    )


def _unique_phone() -> str:
    return f"+1{uuid.uuid4().int % 10_000_000_000:010d}"


# ---------------------------------------------------------------------------
# Lead and session creation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_message_creates_lead_session_and_message(db):
    phone = _unique_phone()
    result = await process_inbound_message(
        db, message=_make_message(phone, "I'm interested in the villa"), tenant_id=TENANT
    )

    assert result.lead.phone_number == phone
    assert result.lead.tenant_id == TENANT
    assert result.session.lead_id == result.lead.id
    assert result.session.tenant_id == TENANT
    assert result.message.body == "I'm interested in the villa"
    assert result.message.direction == MessageDirection.INBOUND
    assert result.message.session_id == result.session.id
    assert result.message.lead_id == result.lead.id
    assert result.is_human_active is False


@pytest.mark.asyncio
async def test_second_message_reuses_existing_lead_and_session(db):
    phone = _unique_phone()
    result1 = await process_inbound_message(db, message=_make_message(phone, "First"), tenant_id=TENANT)
    result2 = await process_inbound_message(db, message=_make_message(phone, "Second"), tenant_id=TENANT)

    assert result1.lead.id == result2.lead.id, "Same lead must be returned"
    assert result1.session.id == result2.session.id, "Same session must be returned"
    assert result2.message.body == "Second"


@pytest.mark.asyncio
async def test_different_phone_numbers_get_separate_leads(db):
    phone_a = _unique_phone()
    phone_b = _unique_phone()
    result_a = await process_inbound_message(db, message=_make_message(phone_a), tenant_id=TENANT)
    result_b = await process_inbound_message(db, message=_make_message(phone_b), tenant_id=TENANT)

    assert result_a.lead.id != result_b.lead.id
    assert result_a.session.id != result_b.session.id


# ---------------------------------------------------------------------------
# Listing ref propagation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_listing_ref_stored_on_lead_and_session(db):
    phone = _unique_phone()
    result = await process_inbound_message(
        db,
        message=_make_message(phone, "Tell me more", listing_ref="https://agency.com/listings/villa-88"),
        tenant_id=TENANT,
    )

    assert result.lead.source_listing_ref == "https://agency.com/listings/villa-88"
    assert result.session.listing_ref == "https://agency.com/listings/villa-88"


@pytest.mark.asyncio
async def test_listing_ref_not_overwritten_on_second_message(db):
    phone = _unique_phone()
    await process_inbound_message(
        db,
        message=_make_message(phone, "First", listing_ref="https://agency.com/listings/original"),
        tenant_id=TENANT,
    )
    result2 = await process_inbound_message(
        db,
        message=_make_message(phone, "Second", listing_ref="https://agency.com/listings/other"),
        tenant_id=TENANT,
    )
    # Session was created with the first listing_ref — it must not be overwritten
    assert result2.session.listing_ref == "https://agency.com/listings/original"


# ---------------------------------------------------------------------------
# Human-active detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_human_active_lead_returns_is_human_active_true(db):
    phone = _unique_phone()
    # First message creates the lead
    first = await process_inbound_message(db, message=_make_message(phone, "Hi"), tenant_id=TENANT)

    # Set the lead to human-active
    await lead_service.set_human_active(
        db, lead_id=first.lead.id, tenant_id=TENANT, agent_id="agent-007"
    )

    # Second message — should be flagged as human-active
    result = await process_inbound_message(db, message=_make_message(phone, "Follow up"), tenant_id=TENANT)
    assert result.is_human_active is True


@pytest.mark.asyncio
async def test_human_active_message_is_still_persisted(db):
    """Messages from human-active leads are stored even though AI does not respond."""
    phone = _unique_phone()
    first = await process_inbound_message(db, message=_make_message(phone), tenant_id=TENANT)
    await lead_service.set_human_active(
        db, lead_id=first.lead.id, tenant_id=TENANT, agent_id="agent-007"
    )

    result = await process_inbound_message(
        db, message=_make_message(phone, "Need help urgently"), tenant_id=TENANT
    )
    assert result.is_human_active is True
    assert result.message.body == "Need help urgently"
    assert result.message.direction == MessageDirection.INBOUND


@pytest.mark.asyncio
async def test_non_human_active_lead_returns_is_human_active_false(db):
    phone = _unique_phone()
    result = await process_inbound_message(db, message=_make_message(phone), tenant_id=TENANT)
    assert result.is_human_active is False


