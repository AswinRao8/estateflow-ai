import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin
from app.models.enums import IntentType, MessageDirection


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "inbound" (from lead) or "outbound" (from system/agent)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Classified intent for inbound messages; null for outbound.
    intent_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Provider-assigned message ID for delivery tracking.
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    lead_id: uuid.UUID
    direction: MessageDirection
    body: str
    intent_type: IntentType | None = None
    provider_message_id: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    session_id: uuid.UUID
    lead_id: uuid.UUID
    direction: MessageDirection
    body: str
    intent_type: IntentType | None = None
    provider_message_id: str | None = None
