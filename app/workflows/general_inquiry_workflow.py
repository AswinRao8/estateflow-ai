from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import WorkflowType

_STUB_MESSAGE = (
    "Thanks for reaching out! I'm here to help with any property-related questions. "
    "What would you like to know?"
)


async def run(context: ConversationContext) -> WorkflowResult:
    # Phase 5: LLM-generated response using conversation context.
    return WorkflowResult(
        outbound_message=_STUB_MESSAGE,
        workflow_type=WorkflowType.GENERAL_INQUIRY,
    )
