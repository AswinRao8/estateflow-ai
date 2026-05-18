from dataclasses import dataclass, field

from app.models.enums import BuyerType, IntentType, LeadState, WorkflowType
from app.models.lead import Lead
from app.models.listing import Listing
from app.models.session import Session


@dataclass
class BuyerProfile:
    """Typed view into lead.qualification_data used by listing_service.match_listings.

    Extracts only the fields that map to SQL filter criteria. timeline, urgency,
    and other conversational fields remain in qualification_data and are used only
    in AI prompt construction — never as SQL predicates.
    """
    budget_min: float | None = None
    budget_max: float | None = None
    location: str | None = None
    property_type: str | None = None
    bedrooms: int | None = None

    @classmethod
    def from_qualification_data(cls, data: dict | None) -> "BuyerProfile":
        if not data:
            return cls()
        bedrooms_raw = data.get("bedrooms")
        return cls(
            budget_min=data.get("budget_min"),
            budget_max=data.get("budget_max"),
            location=data.get("location"),
            property_type=data.get("property_type"),
            bedrooms=int(bedrooms_raw) if bedrooms_raw is not None else None,
        )

    @property
    def has_criteria(self) -> bool:
        return (
            self.budget_min is not None
            or self.budget_max is not None
            or self.location is not None
            or self.property_type is not None
            or self.bedrooms is not None
        )


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


@dataclass
class QualificationResult:
    """Output of a single buyer qualification AI turn.

    extracted_data contains only new field values found in the current message.
    The caller merges these into the existing lead.qualification_data — this
    dataclass never carries the full profile, only the delta.
    """
    next_question: str
    extracted_data: dict
    buyer_type: BuyerType | None = None
    qualification_complete: bool = False


@dataclass
class PropertyMatchResult:
    """Output of the property matching AI explanation call.

    The AI receives only SQL-matched listings and explains why each fits
    the buyer's stated criteria. It never determines match eligibility —
    that is done entirely by listing_service.match_listings before this
    result is produced.
    """
    recommendation_text: str
    viewing_interest_detected: bool = False
