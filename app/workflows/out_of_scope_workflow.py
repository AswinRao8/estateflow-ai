import re

from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import LeadState, WorkflowType

_OUT_OF_SCOPE_MESSAGE = (
    "I'm a real estate assistant and can only help with property-related questions — "
    "buying, renting, viewing, or listing a property. "
    "Is there anything property-related I can help you with today?"
)
_STOP_MESSAGE = (
    "Understood — I've updated your preferences. "
    "If you'd like to continue your property search in the future, feel free to reach out."
)

_STOP_RE = re.compile(
    r"\b(stop|unsubscribe|opt.?out|cancel|not\s+interested|leave\s+me\s+alone|quit)\b",
    re.IGNORECASE,
)


async def run(context: ConversationContext) -> WorkflowResult:
    if _STOP_RE.search(context.current_message):
        return WorkflowResult(
            outbound_message=_STOP_MESSAGE,
            new_lead_state=LeadState.CLOSED_LOST,
            workflow_type=WorkflowType.OUT_OF_SCOPE,
        )
    return WorkflowResult(
        outbound_message=_OUT_OF_SCOPE_MESSAGE,
        workflow_type=WorkflowType.OUT_OF_SCOPE,
    )
