from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import LeadState, PropertyStatus, WorkflowType
from app.services import ai_service

_NO_LISTING_MESSAGE = (
    "I don't have details for that listing right now. "
    "If you have the exact reference or a link, feel free to share it and I'll look it up."
)


async def run(db: AsyncSession, context: ConversationContext) -> WorkflowResult:
    if context.listing is None:
        return WorkflowResult(
            outbound_message=_NO_LISTING_MESSAGE,
            workflow_type=WorkflowType.LISTING_INQUIRY,
        )

    if context.listing.status != PropertyStatus.AVAILABLE:
        status_label = str(context.listing.status).lower().replace("_", " ")
        message = (
            f"{context.listing.title} is currently {status_label} and no longer available. "
            "Would you like me to help you find a similar property?"
        )
        return WorkflowResult(
            outbound_message=message,
            workflow_type=WorkflowType.LISTING_INQUIRY,
        )

    market = get_settings().market
    result = await ai_service.generate_listing_response(context, market)

    return WorkflowResult(
        outbound_message=result.response_text,
        new_lead_state=LeadState.VIEWING_INTEREST if result.viewing_interest_detected else None,
        workflow_type=WorkflowType.LISTING_INQUIRY,
    )
