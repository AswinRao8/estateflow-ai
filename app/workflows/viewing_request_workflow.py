import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context import ConversationContext, WorkflowResult
from app.models.enums import LeadState, WorkflowType

_INTEREST_MESSAGE = (
    "Great — I'll help you arrange a viewing. "
    "What dates and times work best for you?"
)
_BOOKING_MESSAGE = (
    "Noted! I'll get that viewing arranged for you. "
    "A member of our team will confirm the details shortly."
)

_BOOKING_PHRASES = frozenset({
    "book viewing", "schedule viewing", "book a viewing", "schedule a viewing",
    "book a visit", "schedule a visit", "arrange a viewing", "make an appointment",
})
_DATE_RE = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|tomorrow|today|next\s+week|this\s+week"
    r"|\d{1,2}[\/\-\.]\d{1,2}"
    r"|\d{1,2}\s*(?:am|pm)"
    r"|morning|afternoon|evening|noon)\b",
    re.IGNORECASE,
)


def _is_booking_request(message: str) -> bool:
    """True when the message signals a specific viewing booking (not just interest)."""
    lower = message.lower()
    if any(ph in lower for ph in _BOOKING_PHRASES):
        return True
    has_viewing_word = any(w in lower for w in ("viewing", "visit", "view", "appointment"))
    return has_viewing_word and bool(_DATE_RE.search(lower))


async def run(db: AsyncSession, context: ConversationContext) -> WorkflowResult:
    if _is_booking_request(context.current_message):
        return WorkflowResult(
            outbound_message=_BOOKING_MESSAGE,
            new_lead_state=LeadState.VIEWING_SCHEDULED,
            workflow_type=WorkflowType.VIEWING_REQUEST,
        )
    return WorkflowResult(
        outbound_message=_INTEREST_MESSAGE,
        new_lead_state=LeadState.VIEWING_INTEREST,
        workflow_type=WorkflowType.VIEWING_REQUEST,
    )
