from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.exceptions import InvalidStateTransitionError
from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import LeadState, WorkflowType
from app.models.lead import LeadQualificationUpdate
from app.services import lead_service, qualification_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

# States from which the workflow advances the lead into QUALIFYING.
_QUALIFYING_ENTRY_STATES = frozenset({LeadState.NEW_INQUIRY, LeadState.CONTEXT_IDENTIFIED})


async def run(db: AsyncSession, context: ConversationContext) -> WorkflowResult:
    market = get_settings().market
    result = await qualification_service.run_qualification_turn(context, market)

    if result.extracted_data or result.buyer_type:
        await lead_service.update_qualification(
            db,
            lead_id=context.lead.id,
            update=LeadQualificationUpdate(
                buyer_type=result.buyer_type,
                qualification_data=result.extracted_data if result.extracted_data else None,
            ),
        )

    new_state = None
    if LeadState(context.lead.state) in _QUALIFYING_ENTRY_STATES:
        try:
            await lead_service.advance_state(db, lead_id=context.lead.id, to_state=LeadState.QUALIFYING)
            new_state = LeadState.QUALIFYING
        except InvalidStateTransitionError:
            logger.warning(
                "Could not advance lead to QUALIFYING | lead=%s | state=%s",
                context.lead.id,
                context.lead.state,
            )

    return WorkflowResult(
        outbound_message=result.next_question,
        new_lead_state=new_state,
        workflow_type=WorkflowType.QUALIFICATION,
    )
