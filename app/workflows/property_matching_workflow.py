from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.exceptions import InvalidStateTransitionError
from app.models.context import BuyerProfile, ConversationContext, WorkflowResult
from app.models.enums import LeadState, WorkflowType
from app.services import lead_service, listing_service, matching_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

# States from which this workflow advances the lead into MATCHING_PROPERTIES.
# When the workflow is re-entered on a lead already in MATCHING_PROPERTIES,
# no state advancement is attempted.
_MATCHING_ENTRY_STATES = frozenset({
    LeadState.NEW_INQUIRY,
    LeadState.CONTEXT_IDENTIFIED,
    LeadState.QUALIFYING,
})


async def run(db: AsyncSession, context: ConversationContext) -> WorkflowResult:
    market = get_settings().market
    profile = BuyerProfile.from_qualification_data(context.lead.qualification_data)

    matches = await listing_service.match_listings(db, profile=profile)

    logger.info(
        "Property matching | lead=%s | type=%s | location=%s | budget_max=%s | results=%d",
        context.lead.id,
        profile.property_type,
        profile.location,
        profile.budget_max,
        len(matches),
    )

    result = await matching_service.run_matching_turn(context, matches, market)

    new_state: LeadState | None = None

    if LeadState(context.lead.state) in _MATCHING_ENTRY_STATES:
        try:
            await lead_service.advance_state(
                db, lead_id=context.lead.id, to_state=LeadState.MATCHING_PROPERTIES
            )
            new_state = LeadState.MATCHING_PROPERTIES
        except InvalidStateTransitionError:
            logger.warning(
                "Could not advance to MATCHING_PROPERTIES | lead=%s | state=%s",
                context.lead.id,
                context.lead.state,
            )

    if result.viewing_interest_detected:
        try:
            await lead_service.advance_state(
                db, lead_id=context.lead.id, to_state=LeadState.VIEWING_INTEREST
            )
            new_state = LeadState.VIEWING_INTEREST
        except InvalidStateTransitionError:
            logger.warning(
                "Could not advance to VIEWING_INTEREST | lead=%s | state=%s",
                context.lead.id,
                context.lead.state,
            )

    return WorkflowResult(
        outbound_message=result.recommendation_text,
        new_lead_state=new_state,
        workflow_type=WorkflowType.MATCHING_PROPERTIES,
    )
