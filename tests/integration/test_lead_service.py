import pytest

from app.exceptions import InvalidStateTransitionError, LeadNotFoundError
from app.models.enums import BuyerType, LeadState
from app.models.lead import LeadQualificationUpdate
from app.services import lead_service

TENANT = "tenant_test"


@pytest.fixture
def phone():
    import uuid
    return f"+1{uuid.uuid4().hex[:10]}"


@pytest.mark.asyncio
async def test_get_or_create_lead_creates_new(db, phone):
    lead = await lead_service.get_or_create_lead(db, tenant_id=TENANT, phone_number=phone)
    assert lead.id is not None
    assert lead.phone_number == phone
    assert lead.state == LeadState.NEW_INQUIRY
    assert lead.is_human_active is False


@pytest.mark.asyncio
async def test_get_or_create_lead_returns_existing(db, phone):
    first = await lead_service.get_or_create_lead(db, tenant_id=TENANT, phone_number=phone)
    second = await lead_service.get_or_create_lead(db, tenant_id=TENANT, phone_number=phone)
    assert first.id == second.id


@pytest.mark.asyncio
async def test_get_lead_raises_for_unknown_id(db):
    import uuid
    with pytest.raises(LeadNotFoundError):
        await lead_service.get_lead(db, lead_id=uuid.uuid4(), tenant_id=TENANT)


@pytest.mark.asyncio
async def test_list_leads_returns_paginated_results(db):
    import uuid
    for _ in range(3):
        await lead_service.get_or_create_lead(
            db, tenant_id=TENANT, phone_number=f"+1{uuid.uuid4().hex[:10]}"
        )
    results = await lead_service.list_leads(db, tenant_id=TENANT, limit=2, offset=0)
    assert len(results) <= 2


@pytest.mark.asyncio
async def test_advance_state_valid_transition(db, phone):
    lead = await lead_service.get_or_create_lead(db, tenant_id=TENANT, phone_number=phone)
    updated = await lead_service.advance_state(
        db, lead_id=lead.id, tenant_id=TENANT, to_state=LeadState.QUALIFYING
    )
    assert updated.state == LeadState.QUALIFYING


@pytest.mark.asyncio
async def test_advance_state_invalid_transition_raises(db, phone):
    lead = await lead_service.get_or_create_lead(db, tenant_id=TENANT, phone_number=phone)
    with pytest.raises(InvalidStateTransitionError):
        await lead_service.advance_state(
            db, lead_id=lead.id, tenant_id=TENANT, to_state=LeadState.CLOSED_WON
        )


@pytest.mark.asyncio
async def test_advance_state_to_human_active_sets_flag(db, phone):
    lead = await lead_service.get_or_create_lead(db, tenant_id=TENANT, phone_number=phone)
    updated = await lead_service.advance_state(
        db, lead_id=lead.id, tenant_id=TENANT, to_state=LeadState.HUMAN_ACTIVE
    )
    assert updated.is_human_active is True


@pytest.mark.asyncio
async def test_set_human_active_stores_agent_id(db, phone):
    lead = await lead_service.get_or_create_lead(db, tenant_id=TENANT, phone_number=phone)
    updated = await lead_service.set_human_active(
        db, lead_id=lead.id, tenant_id=TENANT, agent_id="agent-42"
    )
    assert updated.is_human_active is True
    assert updated.assigned_agent_id == "agent-42"


@pytest.mark.asyncio
async def test_release_human_clears_flag(db, phone):
    lead = await lead_service.get_or_create_lead(db, tenant_id=TENANT, phone_number=phone)
    await lead_service.set_human_active(db, lead_id=lead.id, tenant_id=TENANT, agent_id="agent-1")
    released = await lead_service.release_human(
        db, lead_id=lead.id, tenant_id=TENANT, to_state=LeadState.QUALIFYING
    )
    assert released.is_human_active is False
    assert released.assigned_agent_id is None
    assert released.state == LeadState.QUALIFYING


@pytest.mark.asyncio
async def test_release_human_rejects_invalid_target_state(db, phone):
    lead = await lead_service.get_or_create_lead(db, tenant_id=TENANT, phone_number=phone)
    await lead_service.set_human_active(db, lead_id=lead.id, tenant_id=TENANT, agent_id="agent-1")
    with pytest.raises(InvalidStateTransitionError):
        # NEW_INQUIRY is not a valid release target from HUMAN_ACTIVE
        await lead_service.release_human(
            db, lead_id=lead.id, tenant_id=TENANT, to_state=LeadState.NEW_INQUIRY
        )


@pytest.mark.asyncio
async def test_update_qualification_merges_data(db, phone):
    lead = await lead_service.get_or_create_lead(db, tenant_id=TENANT, phone_number=phone)
    first = await lead_service.update_qualification(
        db,
        lead_id=lead.id,
        tenant_id=TENANT,
        update=LeadQualificationUpdate(
            buyer_type=BuyerType.RESIDENTIAL,
            qualification_data={"budget": 500000},
        ),
    )
    assert first.buyer_type == BuyerType.FIRST_TIME
    assert first.qualification_data["budget"] == 500000

    second = await lead_service.update_qualification(
        db,
        lead_id=lead.id,
        tenant_id=TENANT,
        update=LeadQualificationUpdate(qualification_data={"timeline": "6 months"}),
    )
    # Prior key preserved, new key added
    assert second.qualification_data["budget"] == 500000
    assert second.qualification_data["timeline"] == "6 months"
