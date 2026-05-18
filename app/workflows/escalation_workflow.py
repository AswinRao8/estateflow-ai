from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import HandoffReason, LeadState, WorkflowType
from app.services import handoff_service, lead_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

_ESCALATION_ACK = (
    "I've connected you with one of our agents who will be in touch with you shortly. "
    "Thank you for your patience!"
)


async def run(
    db: AsyncSession,
    context: ConversationContext,
    *,
    reason: HandoffReason,
) -> WorkflowResult:
    # Build the briefing first so it captures the pre-handoff lead state.
    try:
        briefing = await handoff_service.prepare(
            db,
            lead_id=context.lead.id,
            session_id=context.session.id,
            reason=reason,
        )
        logger.info(
            "Handoff briefing assembled | lead=%s | state=%s | reason=%s | qual=%s | highlights=%d",
            context.lead.id,
            briefing.lead_state,
            reason,
            bool(briefing.qualification_summary),
            len(briefing.conversation_highlights),
        )
    except Exception:
        logger.exception("Failed to build handoff briefing | lead=%s", context.lead.id)

    try:
        await lead_service.set_human_active(
            db,
            lead_id=context.lead.id,
            agent_id="ai_escalation",
        )
        logger.info(
            "Lead escalated to human | lead=%s | reason=%s",
            context.lead.id,
            reason,
        )
    except Exception:
        logger.exception(
            "Failed to set lead human-active | lead=%s | reason=%s",
            context.lead.id,
            reason,
        )

    return WorkflowResult(
        outbound_message=_ESCALATION_ACK,
        new_lead_state=LeadState.HUMAN_ACTIVE,
        workflow_type=WorkflowType.ESCALATION,
    )
