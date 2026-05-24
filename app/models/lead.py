import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin
from app.models.enums import BuyerType, LeadState

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

# Defines which transitions are valid for each LeadState.
# Services validate against this map before persisting a state change.
# CLOSED_WON is terminal — no exits. CLOSED_LOST allows re-engagement only.
VALID_LEAD_TRANSITIONS: dict[LeadState, frozenset[LeadState]] = {
    LeadState.NEW_INQUIRY: frozenset({
        LeadState.CONTEXT_IDENTIFIED,
        LeadState.QUALIFYING,
        LeadState.VIEWING_INTEREST,
        LeadState.VIEWING_SCHEDULED,  # direct booking on first contact
        LeadState.HUMAN_ACTIVE,
        LeadState.CLOSED_LOST,        # immediate opt-out
    }),
    LeadState.CONTEXT_IDENTIFIED: frozenset({
        LeadState.QUALIFYING,
        LeadState.MATCHING_PROPERTIES,
        LeadState.HUMAN_ACTIVE,
        LeadState.CLOSED_LOST,
    }),
    LeadState.QUALIFYING: frozenset({
        LeadState.MATCHING_PROPERTIES,
        LeadState.VIEWING_INTEREST,  # lead with a specific property in mind
        LeadState.HUMAN_ACTIVE,
        LeadState.FOLLOW_UP,
        LeadState.CLOSED_LOST,
    }),
    LeadState.MATCHING_PROPERTIES: frozenset({
        LeadState.VIEWING_INTEREST,
        LeadState.QUALIFYING,
        LeadState.HUMAN_ACTIVE,
        LeadState.FOLLOW_UP,
        LeadState.CLOSED_LOST,
    }),
    LeadState.VIEWING_INTEREST: frozenset({
        LeadState.VIEWING_SCHEDULED,
        LeadState.HUMAN_ACTIVE,
        LeadState.FOLLOW_UP,
        LeadState.CLOSED_LOST,
    }),
    LeadState.VIEWING_SCHEDULED: frozenset({
        LeadState.POST_VIEWING,
        LeadState.HUMAN_ACTIVE,
        LeadState.FOLLOW_UP,
        LeadState.CLOSED_LOST,
    }),
    LeadState.POST_VIEWING: frozenset({
        LeadState.NEGOTIATION,
        LeadState.FOLLOW_UP,
        LeadState.HUMAN_ACTIVE,
        LeadState.CLOSED_LOST,
    }),
    LeadState.NEGOTIATION: frozenset({
        LeadState.HUMAN_ACTIVE,
        LeadState.CLOSED_WON,
        LeadState.CLOSED_LOST,
        LeadState.FOLLOW_UP,
    }),
    # Human agent has full control — can move a lead to any non-terminal state.
    LeadState.HUMAN_ACTIVE: frozenset({
        LeadState.QUALIFYING,
        LeadState.MATCHING_PROPERTIES,
        LeadState.VIEWING_INTEREST,
        LeadState.VIEWING_SCHEDULED,
        LeadState.POST_VIEWING,
        LeadState.NEGOTIATION,
        LeadState.FOLLOW_UP,
        LeadState.CLOSED_WON,
        LeadState.CLOSED_LOST,
    }),
    LeadState.FOLLOW_UP: frozenset({
        LeadState.QUALIFYING,
        LeadState.HUMAN_ACTIVE,
        LeadState.CLOSED_LOST,
    }),
    LeadState.CLOSED_WON: frozenset(),  # Terminal
    LeadState.CLOSED_LOST: frozenset({
        LeadState.NEW_INQUIRY,  # Re-engagement path
    }),
}


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------

class Lead(Base, TimestampMixin):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "phone_number", name="uq_lead_tenant_phone"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    state: Mapped[str] = mapped_column(
        String(50), nullable=False, default=LeadState.NEW_INQUIRY
    )
    buyer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Stores progressive qualification answers: budget, location prefs, timeline, etc.
    # Schema-free at MVP — structured extraction happens in Phase 6.
    qualification_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Resolved listing reference code from the entry URL (e.g. "REF-001"), populated
    # if the lead arrived via a click-to-chat link and the reference code could be
    # extracted. This is a reference code, not a raw URL.
    source_listing_ref_code: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_human_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    assigned_agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


# ---------------------------------------------------------------------------
# Pydantic DTOs
# ---------------------------------------------------------------------------

class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone_number: str
    state: LeadState
    buyer_type: BuyerType | None = None
    qualification_data: dict | None = None
    source_listing_ref_code: str | None = None
    is_human_active: bool
    assigned_agent_id: str | None = None
    created_at: datetime
    updated_at: datetime


class LeadCreate(BaseModel):
    phone_number: str
    source_listing_ref_code: str | None = None


class LeadQualificationUpdate(BaseModel):
    """Partial update for qualification data collected during conversation."""
    buyer_type: BuyerType | None = None
    qualification_data: dict | None = None
