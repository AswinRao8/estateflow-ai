from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import WorkflowType

_STUB_MESSAGE = (
    "Great — I'll help you arrange a viewing. "
    "What dates and times work best for you?"
)


async def run(db: AsyncSession, context: ConversationContext) -> WorkflowResult:
    # Phase 5: Check availability and propose specific time slots.
    return WorkflowResult(
        outbound_message=_STUB_MESSAGE,
        workflow_type=WorkflowType.VIEWING_REQUEST,
    )
