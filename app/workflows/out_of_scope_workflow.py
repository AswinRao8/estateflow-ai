from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import WorkflowType

_OUT_OF_SCOPE_MESSAGE = (
    "I'm a real estate assistant and can only help with property-related questions — "
    "buying, renting, viewing, or listing a property. "
    "Is there anything property-related I can help you with today?"
)


async def run(context: ConversationContext) -> WorkflowResult:
    return WorkflowResult(
        outbound_message=_OUT_OF_SCOPE_MESSAGE,
        workflow_type=WorkflowType.OUT_OF_SCOPE,
    )
