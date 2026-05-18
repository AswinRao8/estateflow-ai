import uuid

from pydantic import BaseModel

from app.models.enums import BuyerType, HandoffReason, LeadState, MessageDirection


class HandoffMessage(BaseModel):
    """A single conversation message as recorded in the handoff briefing.

    direction and body are copied verbatim from the message record.
    No summarisation, no inference.
    """
    direction: MessageDirection
    body: str


class HandoffBriefing(BaseModel):
    """Factual snapshot assembled at handoff time for the receiving agent.

    All fields are read directly from persisted data — no AI-generated
    content, no scoring, no predictive interpretation.

    conversation_highlights are in chronological order (oldest first)
    and are limited to the 10 most recent messages at briefing time.
    """
    lead_id: uuid.UUID
    phone_number: str
    lead_state: LeadState
    buyer_type: BuyerType | None
    qualification_summary: dict | None
    source_listing_ref: str | None
    session_listing_ref: str | None
    conversation_highlights: list[HandoffMessage]
    handoff_reason: HandoffReason
