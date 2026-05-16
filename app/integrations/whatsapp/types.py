from datetime import datetime

from pydantic import BaseModel


class InboundMessage(BaseModel):
    """Internal representation of a received WhatsApp message.
    Decoupled from provider payload structure — services never see raw provider JSON."""
    phone_number: str           # Sender E.164 phone number
    message_id: str             # Provider message ID (used for deduplication)
    body: str                   # Text content
    timestamp: datetime         # When the message was sent (from provider timestamp)
    listing_ref: str | None = None  # Populated when a click-to-chat referral is present


class DeliveryStatus(BaseModel):
    """Parsed delivery status event from WhatsApp provider."""
    message_id: str             # Provider message ID
    recipient_phone_number: str
    status: str                 # "sent" | "delivered" | "read" | "failed"
    timestamp: datetime
