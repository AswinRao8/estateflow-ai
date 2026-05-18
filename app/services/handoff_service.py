"""Human handoff briefing service.

Assembles a factual briefing from persisted lead, session, and conversation
data. No AI calls. No inference. No scoring. No summarisation.

The briefing is the single source of context for the receiving agent.
All fields are read directly from the database — nothing is derived.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.conversation import Message
from app.models.enums import BuyerType, HandoffReason, LeadState, MessageDirection
from app.models.handoff import HandoffBriefing, HandoffMessage
from app.models.lead import Lead
from app.models.session import Session
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def prepare(
    db: AsyncSession,
    *,
    lead_id: uuid.UUID,
    session_id: uuid.UUID | None,
    reason: HandoffReason,
) -> HandoffBriefing:
    """Assemble a factual handoff briefing from persisted data.

    Reads the pre-handoff lead state — caller must invoke this before
    advancing the lead to HUMAN_ACTIVE so the briefing reflects where
    the lead was in the pipeline when the handoff was triggered.
    """
    tenant_id = get_settings().default_tenant_id
    lead = await _fetch_lead(db, lead_id, tenant_id)
    session_listing_ref = (
        await _fetch_session_listing_ref(db, session_id, tenant_id) if session_id else None
    )
    messages = await _fetch_recent_messages(db, lead_id, tenant_id, limit=10)
    return _build_briefing(
        lead=lead,
        session_listing_ref=session_listing_ref,
        messages=messages,
        reason=reason,
    )


def _build_briefing(
    *,
    lead: Lead,
    session_listing_ref: str | None,
    messages: list[Message],
    reason: HandoffReason,
) -> HandoffBriefing:
    highlights = [
        HandoffMessage(direction=MessageDirection(m.direction), body=m.body)
        for m in messages
    ]
    buyer_type = BuyerType(lead.buyer_type) if lead.buyer_type else None
    return HandoffBriefing(
        lead_id=lead.id,
        phone_number=lead.phone_number,
        lead_state=LeadState(lead.state),
        buyer_type=buyer_type,
        qualification_summary=lead.qualification_data,
        source_listing_ref=lead.source_listing_ref_code,
        session_listing_ref=session_listing_ref,
        conversation_highlights=highlights,
        handoff_reason=reason,
    )


async def _fetch_lead(db: AsyncSession, lead_id: uuid.UUID, tenant_id: str) -> Lead:
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise ValueError(f"Lead {lead_id} not found for briefing")
    return lead


async def _fetch_session_listing_ref(
    db: AsyncSession, session_id: uuid.UUID, tenant_id: str
) -> str | None:
    result = await db.execute(
        select(Session.listing_ref_code).where(
            Session.id == session_id, Session.tenant_id == tenant_id
        )
    )
    return result.scalar_one_or_none()


async def _fetch_recent_messages(
    db: AsyncSession, lead_id: uuid.UUID, tenant_id: str, *, limit: int
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.lead_id == lead_id, Message.tenant_id == tenant_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()  # chronological order: oldest first
    return rows
