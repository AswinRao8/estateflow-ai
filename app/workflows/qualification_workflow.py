from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import WorkflowType

_STUB_MESSAGE = (
    "I'd love to help you find the right property. "
    "Could you tell me a bit more about what you're looking for — "
    "your budget, preferred location, and how many bedrooms you need?"
)


async def run(db: AsyncSession, context: ConversationContext) -> WorkflowResult:
    # Phase 5: Progressive qualification question sequence.
    return WorkflowResult(
        outbound_message=_STUB_MESSAGE,
        workflow_type=WorkflowType.QUALIFICATION,
    )
