from datetime import datetime

from pydantic import BaseModel


class InboundMessage(BaseModel):
    """Internal representation of a received WhatsApp message.
    Decoupled from provider payload structure — services never see raw provider JSON."""
    phone_number: str               # Sender E.164 phone number
    message_id: str                 # Provider message ID (used for deduplication)
    body: str                       # Text content
    timestamp: datetime             # When the message was sent (from provider timestamp)
    # Raw source_url from the WhatsApp referral object — transport context only.
    # This is the click-to-chat entry URL, not a canonical listing identity.
    # Resolve to a listing reference code via extract_listing_ref_code() before
    # writing anything to the domain layer. The raw URL is discarded after extraction.
    listing_ref_url: str | None = None


class DeliveryStatus(BaseModel):
    """Parsed delivery status event from WhatsApp provider."""
    message_id: str             # Provider message ID
    recipient_phone_number: str
    status: str                 # "sent" | "delivered" | "read" | "failed"
    timestamp: datetime
