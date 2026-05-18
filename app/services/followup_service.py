"""Follow-up scheduling and dispatch service.

Responsibilities:
- Write FollowUp records when trigger conditions are met.
- Cancel pending follow-ups when a lead responds (they're no longer stale).
- Dispatch due follow-ups at message-processing time via a lightweight DB poll.
- Generate contextual AI follow-up messages via Anthropic tool use.

Suppression rule: leads that are HUMAN_ACTIVE are never followed up by AI.
All DB mutations go through this module; no workflow touches follow_ups directly.
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

import anthropic

from app.config import MarketConfig, get_settings
from app.models.conversation import MessageCreate
from app.models.enums import (
    FollowUpStatus,
    FollowUpTriggerType,
    LeadState,
    MessageDirection,
)
from app.models.follow_up import FollowUp
from app.models.lead import Lead
from app.utils.logging import get_logger

logger = get_logger(__name__)

_FOLLOWUP_TIMEOUT = 10.0

# States that are eligible to receive a STALLED_3D follow-up.
_STALL_ELIGIBLE_STATES = frozenset(
    {LeadState.QUALIFYING, LeadState.MATCHING_PROPERTIES, LeadState.VIEWING_INTEREST}
)

_TRIGGER_CONTEXT: dict[FollowUpTriggerType, str] = {
    FollowUpTriggerType.POST_VIEWING_24H: (
        "The lead viewed a property 24 hours ago. Check in warmly on their impressions "
        "and offer to answer any questions."
    ),
    FollowUpTriggerType.POST_VIEWING_48H: (
        "It has been 48 hours since the lead's viewing. Follow up on next steps "
        "and gauge whether they are ready to proceed."
    ),
    FollowUpTriggerType.STALLED_3D: (
        "The lead has been inactive for 3 days. Re-engage with a gentle, "
        "non-pressuring check-in to see if they still need help."
    ),
    FollowUpTriggerType.NO_RESPONSE_48H: (
        "Property recommendations were sent 48 hours ago with no response. "
        "Follow up to see if any listings caught their interest."
    ),
}

_TRIGGER_FALLBACK: dict[FollowUpTriggerType, str] = {
    FollowUpTriggerType.POST_VIEWING_24H: (
        "Hi! Just checking in after yesterday's viewing. What did you think? "
        "Happy to answer any questions."
    ),
    FollowUpTriggerType.POST_VIEWING_48H: (
        "Hi! It's been a couple of days since your viewing. Any questions or "
        "would you like to discuss next steps?"
    ),
    FollowUpTriggerType.STALLED_3D: (
        "Hi! Just checking in — have you had a chance to think more about your "
        "property search? I'm here to help whenever you're ready."
    ),
    FollowUpTriggerType.NO_RESPONSE_48H: (
        "Hi! Just following up on the properties I shared with you. "
        "Did any of them catch your interest?"
    ),
}

_FOLLOWUP_TOOL: dict[str, Any] = {
    "name": "follow_up_message",
    "description": "Generate a contextual follow-up WhatsApp message for a real estate lead.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": (
                    "The follow-up WhatsApp message. Friendly, brief, and suitable "
                    "for WhatsApp. No markdown. Do not invent listing details."
                ),
            }
        },
        "required": ["message"],
    },
}

_anthropic_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(
            api_key=get_settings().anthropic_api_key
        )
    return _anthropic_client


# ---------------------------------------------------------------------------
# Pure helpers — testable without DB or Anthropic
# ---------------------------------------------------------------------------

def _get_trigger_context(trigger_type: FollowUpTriggerType) -> str:
    return _TRIGGER_CONTEXT[trigger_type]


def _get_trigger_fallback(trigger_type: FollowUpTriggerType) -> str:
    return _TRIGGER_FALLBACK[trigger_type]


def _build_follow_up_prompt(
    lead: Any,
    trigger_type: FollowUpTriggerType,
    recent_messages: list[str],
    market: MarketConfig,
) -> str:
    trigger_ctx = _get_trigger_context(trigger_type)
    state = getattr(lead, "state", "unknown")
    qual = getattr(lead, "qualification_data", None)

    qual_section = "  No qualification data on file."
    if qual:
        sym, code = market.currency_symbol, market.currency_code
        lines: list[str] = []
        if qual.get("budget_min") is not None or qual.get("budget_max") is not None:
            lo = qual.get("budget_min")
            hi = qual.get("budget_max")
            if lo is not None and hi is not None:
                lines.append(f"  Budget: {sym}{lo:,.0f}–{sym}{hi:,.0f} {code}")
            elif hi is not None:
                lines.append(f"  Budget (max): {sym}{hi:,.0f} {code}")
            else:
                lines.append(f"  Budget (from): {sym}{lo:,.0f} {code}")
        if qual.get("location"):
            lines.append(f"  Location: {qual['location']}")
        if qual.get("property_type"):
            lines.append(f"  Property type: {qual['property_type']}")
        if qual.get("bedrooms") is not None:
            lines.append(f"  Bedrooms: {qual['bedrooms']}")
        qual_section = "\n".join(lines) if lines else "  No specific criteria stated."

    history = (
        "\n".join(f"  [{i + 1}] {msg}" for i, msg in enumerate(recent_messages[-5:]))
        if recent_messages
        else "  (no prior messages)"
    )

    return (
        "You are a real estate assistant sending a follow-up WhatsApp message to a lead.\n\n"
        f"Follow-up reason: {trigger_ctx}\n\n"
        f"Lead state: {state}\n\n"
        f"Lead's stated property criteria:\n{qual_section}\n\n"
        f"Recent conversation (up to 5 messages):\n{history}\n\n"
        "Instructions:\n"
        "1. Write a brief, warm, and natural WhatsApp message appropriate for the follow-up reason.\n"
        "2. Reference the lead's stated criteria only if relevant and accurate — never invent details.\n"
        "3. Keep it concise and suitable for WhatsApp. No markdown.\n"
        "4. Do not be pushy or use high-pressure sales language.\n\n"
        "Use the follow_up_message tool to respond."
    )


def _parse_follow_up_response(
    tool_input: dict[str, Any],
    trigger_type: FollowUpTriggerType,
) -> str:
    text = str(tool_input.get("message", "")).strip()
    return text if text else _get_trigger_fallback(trigger_type)


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

async def schedule_post_viewing(
    db: Any,
    *,
    lead_id: uuid.UUID,
    now: datetime,
) -> None:
    """Schedule POST_VIEWING_24H and POST_VIEWING_48H after a viewing occurs."""
    tenant_id = get_settings().default_tenant_id
    await _schedule_if_absent(
        db,
        tenant_id=tenant_id,
        lead_id=lead_id,
        trigger=FollowUpTriggerType.POST_VIEWING_24H,
        scheduled_at=now + timedelta(hours=24),
    )
    await _schedule_if_absent(
        db,
        tenant_id=tenant_id,
        lead_id=lead_id,
        trigger=FollowUpTriggerType.POST_VIEWING_48H,
        scheduled_at=now + timedelta(hours=48),
    )
    await db.commit()
    logger.info(
        "Scheduled post-viewing follow-ups | lead=%s | 24h=%s 48h=%s",
        lead_id,
        now + timedelta(hours=24),
        now + timedelta(hours=48),
    )


async def schedule_no_response(
    db: Any,
    *,
    lead_id: uuid.UUID,
    now: datetime,
) -> None:
    """Schedule NO_RESPONSE_48H after property recommendations are sent."""
    tenant_id = get_settings().default_tenant_id
    await _schedule_if_absent(
        db,
        tenant_id=tenant_id,
        lead_id=lead_id,
        trigger=FollowUpTriggerType.NO_RESPONSE_48H,
        scheduled_at=now + timedelta(hours=48),
    )
    await db.commit()
    logger.info(
        "Scheduled no-response follow-up | lead=%s | at=%s",
        lead_id,
        now + timedelta(hours=48),
    )


async def list_for_lead(db: Any, *, lead_id: uuid.UUID) -> list[FollowUp]:
    """Return all follow-ups for a lead ordered by scheduled_at ascending."""
    from sqlalchemy import select

    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(FollowUp)
        .where(FollowUp.lead_id == lead_id, FollowUp.tenant_id == tenant_id)
        .order_by(FollowUp.scheduled_at.asc())
    )
    return list(result.scalars().all())


async def cancel_pending(db: Any, *, lead_id: uuid.UUID) -> None:
    """Cancel all PENDING follow-ups for a lead when they respond."""
    from sqlalchemy import select

    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(FollowUp).where(
            FollowUp.tenant_id == tenant_id,
            FollowUp.lead_id == lead_id,
            FollowUp.status == FollowUpStatus.PENDING,
        )
    )
    rows = list(result.scalars().all())
    if rows:
        for follow_up in rows:
            follow_up.status = FollowUpStatus.CANCELLED
        await db.commit()
        logger.info(
            "Cancelled %d pending follow-up(s) | lead=%s (lead responded)",
            len(rows),
            lead_id,
        )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

async def dispatch_due(db: Any, *, now: datetime, limit: int = 10) -> int:
    """Dispatch all due follow-ups. Returns count of records processed (sent + suppressed).

    Order of operations:
    1. Create STALLED_3D records for newly stalled leads (no pre-scheduling needed).
    2. Fetch PENDING follow-ups whose scheduled_at <= now.
    3. For each: suppress if HUMAN_ACTIVE, otherwise generate message and send.
    """
    from sqlalchemy import select

    from app.models.session import Session
    from app.services import conversation_service, notification_service, session_service

    tenant_id = get_settings().default_tenant_id

    await _create_stalled_records(db, tenant_id=tenant_id, now=now)

    result = await db.execute(
        select(FollowUp)
        .where(
            FollowUp.tenant_id == tenant_id,
            FollowUp.status == FollowUpStatus.PENDING,
            FollowUp.scheduled_at <= now,
        )
        .order_by(FollowUp.scheduled_at.asc())
        .limit(limit)
    )
    due = list(result.scalars().all())

    if not due:
        return 0

    market = get_settings().market
    processed = 0

    for follow_up in due:
        try:
            lead_result = await db.execute(
                select(Lead).where(
                    Lead.id == follow_up.lead_id,
                    Lead.tenant_id == tenant_id,
                )
            )
            lead = lead_result.scalar_one_or_none()
            if lead is None:
                logger.warning(
                    "Lead not found for follow-up | follow_up=%s | lead=%s",
                    follow_up.id,
                    follow_up.lead_id,
                )
                continue

            if lead.is_human_active:
                follow_up.status = FollowUpStatus.SUPPRESSED
                await db.commit()
                logger.info(
                    "Suppressed follow-up (lead human-active) | follow_up=%s | lead=%s",
                    follow_up.id,
                    lead.id,
                )
                processed += 1
                continue

            messages = await conversation_service.get_lead_recent_messages(
                db, lead_id=lead.id, limit=5
            )
            recent_bodies = [m.body for m in messages]

            trigger_type = FollowUpTriggerType(follow_up.trigger_type)
            message_text = await _generate_message(
                lead=lead,
                trigger_type=trigger_type,
                recent_messages=recent_bodies,
                market=market,
            )

            provider_id = await notification_service.send_whatsapp_text(
                lead.phone_number, message_text
            )

            session = await session_service.get_or_create_active_session(
                db, lead_id=lead.id
            )
            await conversation_service.save_message(
                db,
                data=MessageCreate(
                    session_id=session.id,
                    lead_id=lead.id,
                    direction=MessageDirection.OUTBOUND,
                    body=message_text,
                    provider_message_id=provider_id,
                ),
            )

            follow_up.status = FollowUpStatus.SENT
            follow_up.sent_at = now
            await db.commit()

            logger.info(
                "Dispatched follow-up | follow_up=%s | lead=%s | trigger=%s",
                follow_up.id,
                lead.id,
                trigger_type,
            )
            processed += 1

        except Exception:
            logger.exception(
                "Failed to dispatch follow-up | follow_up=%s", follow_up.id
            )

    return processed


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _schedule_if_absent(
    db: Any,
    *,
    tenant_id: str,
    lead_id: uuid.UUID,
    trigger: FollowUpTriggerType,
    scheduled_at: datetime,
) -> None:
    from sqlalchemy import select

    existing = await db.execute(
        select(FollowUp).where(
            FollowUp.lead_id == lead_id,
            FollowUp.trigger_type == trigger,
            FollowUp.status.in_(
                [FollowUpStatus.PENDING, FollowUpStatus.SENT]
            ),
        )
    )
    if existing.scalar_one_or_none() is not None:
        return
    db.add(
        FollowUp(
            tenant_id=tenant_id,
            lead_id=lead_id,
            trigger_type=trigger,
            status=FollowUpStatus.PENDING,
            scheduled_at=scheduled_at,
        )
    )


async def _create_stalled_records(
    db: Any, *, tenant_id: str, now: datetime
) -> None:
    from sqlalchemy import select

    stale_cutoff = now - timedelta(days=3)
    result = await db.execute(
        select(Lead).where(
            Lead.tenant_id == tenant_id,
            Lead.state.in_([s.value for s in _STALL_ELIGIBLE_STATES]),
            Lead.is_human_active == False,  # noqa: E712
            Lead.updated_at < stale_cutoff,
        )
    )
    stalled = list(result.scalars().all())

    for lead in stalled:
        existing = await db.execute(
            select(FollowUp).where(
                FollowUp.lead_id == lead.id,
                FollowUp.trigger_type == FollowUpTriggerType.STALLED_3D,
                FollowUp.status.in_(
                    [FollowUpStatus.PENDING, FollowUpStatus.SENT]
                ),
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        db.add(
            FollowUp(
                tenant_id=tenant_id,
                lead_id=lead.id,
                trigger_type=FollowUpTriggerType.STALLED_3D,
                status=FollowUpStatus.PENDING,
                scheduled_at=now,
            )
        )

    if stalled:
        await db.commit()


async def _generate_message(
    *,
    lead: Any,
    trigger_type: FollowUpTriggerType,
    recent_messages: list[str],
    market: MarketConfig,
) -> str:
    prompt = _build_follow_up_prompt(lead, trigger_type, recent_messages, market)
    try:
        return await asyncio.wait_for(
            _call_followup_api(prompt, trigger_type), timeout=_FOLLOWUP_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Follow-up generation timed out | lead=%s | trigger=%s",
            getattr(lead, "id", "?"),
            trigger_type,
        )
        return _get_trigger_fallback(trigger_type)
    except Exception:
        logger.exception(
            "Follow-up generation failed | lead=%s | trigger=%s",
            getattr(lead, "id", "?"),
            trigger_type,
        )
        return _get_trigger_fallback(trigger_type)


async def _call_followup_api(prompt: str, trigger_type: FollowUpTriggerType) -> str:
    settings = get_settings()
    response = await _get_client().messages.create(
        model=settings.anthropic_model,
        max_tokens=256,
        tools=[_FOLLOWUP_TOOL],
        tool_choice={"type": "tool", "name": "follow_up_message"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "follow_up_message":
            return _parse_follow_up_response(block.input, trigger_type)
    raise ValueError("No follow_up_message block in follow-up response")
