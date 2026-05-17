from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import WorkflowType

_CLARIFICATION_MESSAGE = (
    "I want to make sure I help you with the right thing. "
    "Are you looking to buy, rent, or sell a property? "
    "Or do you have a specific question about a listing?"
)


async def run(context: ConversationContext) -> WorkflowResult:
    return WorkflowResult(
        outbound_message=_CLARIFICATION_MESSAGE,
        workflow_type=WorkflowType.CLARIFICATION,
    )
