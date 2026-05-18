import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.exceptions import InvalidStateTransitionError, LeadNotFoundError
from app.models.enums import LeadState
from app.models.lead import Lead, LeadQualificationUpdate, VALID_LEAD_TRANSITIONS


async def get_or_create_lead(
    db: AsyncSession,
    *,
    phone_number: str,
    source_listing_ref_code: str | None = None,
) -> Lead:
    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(Lead).where(Lead.tenant_id == tenant_id, Lead.phone_number == phone_number)
    )
    lead = result.scalar_one_or_none()
    if lead is not None:
        return lead
    lead = Lead(
        tenant_id=tenant_id,
        phone_number=phone_number,
        source_listing_ref_code=source_listing_ref_code,
    )
    db.add(lead)
    await db.commit()
    return lead


async def get_lead(db: AsyncSession, *, lead_id: uuid.UUID) -> Lead:
    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise LeadNotFoundError(str(lead_id))
    return lead


async def list_leads(
    db: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[Lead]:
    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(Lead)
        .where(Lead.tenant_id == tenant_id)
        .order_by(Lead.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def advance_state(
    db: AsyncSession, *, lead_id: uuid.UUID, to_state: LeadState
) -> Lead:
    lead = await get_lead(db, lead_id=lead_id)
    from_state = LeadState(lead.state)
    if to_state not in VALID_LEAD_TRANSITIONS.get(from_state, frozenset()):
        raise InvalidStateTransitionError(from_state, to_state)
    lead.state = to_state
    if to_state == LeadState.HUMAN_ACTIVE:
        lead.is_human_active = True
    elif from_state == LeadState.HUMAN_ACTIVE:
        lead.is_human_active = False
    await db.commit()
    return lead


async def set_human_active(
    db: AsyncSession, *, lead_id: uuid.UUID, agent_id: str
) -> Lead:
    lead = await advance_state(db, lead_id=lead_id, to_state=LeadState.HUMAN_ACTIVE)
    lead.assigned_agent_id = agent_id
    await db.commit()
    return lead


async def release_human(
    db: AsyncSession, *, lead_id: uuid.UUID, to_state: LeadState
) -> Lead:
    lead = await get_lead(db, lead_id=lead_id)
    if LeadState(lead.state) != LeadState.HUMAN_ACTIVE:
        raise InvalidStateTransitionError(lead.state, to_state)
    if to_state not in VALID_LEAD_TRANSITIONS[LeadState.HUMAN_ACTIVE]:
        raise InvalidStateTransitionError(LeadState.HUMAN_ACTIVE, to_state)
    lead.state = to_state
    lead.is_human_active = False
    lead.assigned_agent_id = None
    await db.commit()
    return lead


async def claim_lead(
    db: AsyncSession, *, lead_id: uuid.UUID, agent_id: str
) -> Lead:
    """Assign an agent to a lead, handling both AI-triggered and fresh takeovers.

    If the lead is already HUMAN_ACTIVE (AI triggered the escalation),
    only the assigned_agent_id is updated — no state transition is needed.
    If the lead is not yet HUMAN_ACTIVE, the full set_human_active transition
    is performed. Raises InvalidStateTransitionError if the lead is in a
    terminal state that cannot transition to HUMAN_ACTIVE.
    """
    lead = await get_lead(db, lead_id=lead_id)
    if LeadState(lead.state) == LeadState.HUMAN_ACTIVE:
        lead.assigned_agent_id = agent_id
        await db.commit()
        return lead
    return await set_human_active(db, lead_id=lead_id, agent_id=agent_id)


async def update_qualification(
    db: AsyncSession,
    *,
    lead_id: uuid.UUID,
    update: LeadQualificationUpdate,
) -> Lead:
    lead = await get_lead(db, lead_id=lead_id)
    if update.buyer_type is not None:
        lead.buyer_type = update.buyer_type
    if update.qualification_data is not None:
        existing = lead.qualification_data or {}
        lead.qualification_data = {**existing, **update.qualification_data}
    await db.commit()
    return lead
