from dataclasses import dataclass, field

from app.models.enums import IntentType, LeadState, WorkflowType
from app.models.lead import Lead
from app.models.listing import Listing
from app.models.session import Session


@dataclass
class ConversationContext:
    """Assembled snapshot passed into classify_intent and all workflow functions.

    Assembled once per inbound message so downstream functions never query
    the database directly. recent_messages is ordered oldest-to-newest.
    listing is None unless the session has a resolved listing_ref_code.
    """
    lead: Lead
    session: Session
    recent_messages: list[str]
    current_message: str
    listing: Listing | None = None


@dataclass
class ClassificationResult:
    """Output of the intent classifier.

    confidence is a [0.0, 1.0] float from the LLM tool call.
    reasoning is a single sentence used for structured logging only — not
    shown to the user and not used for routing decisions.
    """
    intent: IntentType
    confidence: float
    reasoning: str


@dataclass
class WorkflowResult:
    """Output of a workflow function.

    outbound_message is None when the workflow triggers a human handoff
    and the AI should not reply (the human agent's first message takes over).
    new_lead_state is None when the workflow did not change lead state.
    """
    outbound_message: str | None
    new_lead_state: LeadState | None = None
    workflow_type: WorkflowType | None = None


@dataclass
class ListingResponseResult:
    """Output of the listing response AI call.

    viewing_interest_detected is True when the lead's message explicitly
    signals intent to view or visit the property.
    """
    response_text: str
    viewing_interest_detected: bool = False
