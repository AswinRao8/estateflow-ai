import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin


class Session(Base, TimestampMixin):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Channel from which the session originated (e.g. "whatsapp").
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="whatsapp")
    # Reference to the listing URL that initiated this session, if any.
    listing_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Wall-clock timestamp of the most recent inbound or outbound message.
    last_activity_at: Mapped[datetime | None] = mapped_column(
        nullable=True
    )


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: str
    lead_id: uuid.UUID
    channel: str
    listing_ref: str | None = None
    is_active: bool
    last_activity_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SessionCreate(BaseModel):
    tenant_id: str
    lead_id: uuid.UUID
    channel: str = "whatsapp"
    listing_ref: str | None = None
