from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import HandoffReason, LeadState, WorkflowType
from app.services import lead_service
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
