import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin
from app.models.enums import FollowUpStatus, FollowUpTriggerType


class FollowUp(Base, TimestampMixin):
    __tablename__ = "follow_ups"
    __table_args__ = (
        Index("ix_follow_ups_scheduled_at", "scheduled_at"),
        Index("ix_follow_ups_status_scheduled", "status", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=FollowUpStatus.PENDING
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FollowUpRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    trigger_type: FollowUpTriggerType
    status: FollowUpStatus
    scheduled_at: datetime
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
