from enum import StrEnum


class LeadState(StrEnum):
    """Lifecycle states a lead moves through from first contact to closure."""
    NEW_INQUIRY = "NEW_INQUIRY"
    CONTEXT_IDENTIFIED = "CONTEXT_IDENTIFIED"
    QUALIFYING = "QUALIFYING"
    MATCHING_PROPERTIES = "MATCHING_PROPERTIES"
    VIEWING_INTEREST = "VIEWING_INTEREST"
    VIEWING_SCHEDULED = "VIEWING_SCHEDULED"
    POST_VIEWING = "POST_VIEWING"
    NEGOTIATION = "NEGOTIATION"
    HUMAN_ACTIVE = "HUMAN_ACTIVE"
    FOLLOW_UP = "FOLLOW_UP"
    CLOSED_WON = "CLOSED_WON"
    CLOSED_LOST = "CLOSED_LOST"


class IntentType(StrEnum):
    """Output categories of the intent classifier."""
    LISTING_INQUIRY = "LISTING_INQUIRY"
    BUYER_QUALIFICATION = "BUYER_QUALIFICATION"
    VIEWING_REQUEST = "VIEWING_REQUEST"
    FOLLOW_UP = "FOLLOW_UP"
    HUMAN_REQUESTED = "HUMAN_REQUESTED"
    GENERAL_INQUIRY = "GENERAL_INQUIRY"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class PropertyType(StrEnum):
    HOUSE = "HOUSE"
    APARTMENT = "APARTMENT"
    LAND = "LAND"
    VILLA = "VILLA"
    PENTHOUSE = "PENTHOUSE"
    COMMERCIAL = "COMMERCIAL"


class PropertyStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNDER_OFFER = "UNDER_OFFER"
    SOLD = "SOLD"
    RENTED = "RENTED"
    INACTIVE = "INACTIVE"


class TransactionType(StrEnum):
    SALE = "SALE"
    RENTAL = "RENTAL"


class BuyerType(StrEnum):
    RESIDENTIAL = "RESIDENTIAL"
    LAND = "LAND"
    EXPAT = "EXPAT"
    INVESTOR = "INVESTOR"
    RENTER = "RENTER"
    SELLER = "SELLER"
    EXPLORATORY = "EXPLORATORY"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class HandoffReason(StrEnum):
    NEGOTIATION = "NEGOTIATION"
    LEGAL_COMPLEXITY = "LEGAL_COMPLEXITY"
    LOW_AI_CONFIDENCE = "LOW_AI_CONFIDENCE"
    USER_REQUESTED = "USER_REQUESTED"
    HIGH_INTENT_BUYER = "HIGH_INTENT_BUYER"
    AGENT_INITIATED = "AGENT_INITIATED"


class WorkflowType(StrEnum):
    LISTING_INQUIRY = "listing_inquiry"
    QUALIFICATION = "qualification"
    MATCHING_PROPERTIES = "matching_properties"
    VIEWING_REQUEST = "viewing_request"
    GENERAL_INQUIRY = "general_inquiry"
    CLARIFICATION = "clarification"
    OUT_OF_SCOPE = "out_of_scope"
    ESCALATION = "escalation"


class FollowUpTriggerType(StrEnum):
    POST_VIEWING_24H = "POST_VIEWING_24H"
    POST_VIEWING_48H = "POST_VIEWING_48H"
    STALLED_3D = "STALLED_3D"
    NO_RESPONSE_48H = "NO_RESPONSE_48H"


class FollowUpStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    SUPPRESSED = "SUPPRESSED"   # due but lead was human-active; skipped
    CANCELLED = "CANCELLED"     # obsoleted before firing (lead responded or closed)
