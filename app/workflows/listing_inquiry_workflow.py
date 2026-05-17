from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import WorkflowType

_STUB_MESSAGE = (
    "Thank you for your interest! I'm pulling up the listing details for you. "
    "Please give me a moment."
)


async def run(db: AsyncSession, context: ConversationContext) -> WorkflowResult:
    # Phase 5: Fetch listing details from DB and generate a tailored response.
    return WorkflowResult(
        outbound_message=_STUB_MESSAGE,
        workflow_type=WorkflowType.LISTING_INQUIRY,
    )
