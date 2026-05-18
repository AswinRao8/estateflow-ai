"""Unit tests for Phase 8 handoff briefing assembly.

Tests cover _build_briefing exclusively — the pure function that assembles
a HandoffBriefing from pre-fetched domain objects. No database access.
All invariants from the operational constraints are verified:
  - Deterministic and factual fields only
  - Chronological ordering preserved
  - Direction fidelity preserved
  - Null fields handled safely
"""
import uuid
from types import SimpleNamespace

import pytest

from app.models.enums import BuyerType, HandoffReason, LeadState, MessageDirection
from app.services.handoff_service import _build_briefing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_lead(**overrides) -> SimpleNamespace:
    defaults = {
        "id": uuid.uuid4(),
        "phone_number": "+15550001234",
        "state": LeadState.QUALIFYING,
        "buyer_type": BuyerType.RESIDENTIAL,
        "qualification_data": {"budget_min": 250_000, "location": "Riverside"},
        "source_listing_ref_code": "REF-001",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _fake_message(direction: MessageDirection = MessageDirection.INBOUND, body: str = "Hello") -> SimpleNamespace:
    return SimpleNamespace(direction=direction.value, body=body)


# ---------------------------------------------------------------------------
# Phone number and identifiers
# ---------------------------------------------------------------------------

def test_briefing_includes_lead_id():
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.lead_id == lead.id


def test_briefing_includes_phone_number():
    lead = _fake_lead(phone_number="+447911123456")
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.phone_number == "+447911123456"


# ---------------------------------------------------------------------------
# Lead state
# ---------------------------------------------------------------------------

def test_briefing_lead_state_matches_pre_handoff_state():
    lead = _fake_lead(state=LeadState.QUALIFYING)
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.lead_state == LeadState.QUALIFYING


def test_briefing_lead_state_matching_properties():
    lead = _fake_lead(state=LeadState.MATCHING_PROPERTIES)
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.NEGOTIATION)
    assert briefing.lead_state == LeadState.MATCHING_PROPERTIES


# ---------------------------------------------------------------------------
# Buyer type
# ---------------------------------------------------------------------------

def test_briefing_includes_buyer_type():
    lead = _fake_lead(buyer_type=BuyerType.INVESTOR)
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.buyer_type == BuyerType.INVESTOR


def test_briefing_buyer_type_none_when_not_set():
    lead = _fake_lead(buyer_type=None)
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.buyer_type is None


# ---------------------------------------------------------------------------
# Qualification summary
# ---------------------------------------------------------------------------

def test_briefing_includes_qualification_summary():
    data = {"budget_min": 200_000, "budget_max": 400_000, "location": "Downtown"}
    lead = _fake_lead(qualification_data=data)
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.qualification_summary == data


def test_briefing_qualification_summary_none_when_not_set():
    lead = _fake_lead(qualification_data=None)
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.qualification_summary is None


# ---------------------------------------------------------------------------
# Listing references
# ---------------------------------------------------------------------------

def test_briefing_includes_source_listing_ref():
    lead = _fake_lead(source_listing_ref_code="APT-007")
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.source_listing_ref == "APT-007"


def test_briefing_source_listing_ref_none_when_not_set():
    lead = _fake_lead(source_listing_ref_code=None)
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.source_listing_ref is None


def test_briefing_includes_session_listing_ref():
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref="VILLA-003", messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.session_listing_ref == "VILLA-003"


def test_briefing_session_listing_ref_none_when_not_provided():
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.session_listing_ref is None


# ---------------------------------------------------------------------------
# Handoff reason
# ---------------------------------------------------------------------------

def test_briefing_includes_handoff_reason_user_requested():
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.handoff_reason == HandoffReason.USER_REQUESTED


def test_briefing_includes_handoff_reason_negotiation():
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.NEGOTIATION)
    assert briefing.handoff_reason == HandoffReason.NEGOTIATION


def test_briefing_includes_handoff_reason_low_confidence():
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.LOW_AI_CONFIDENCE)
    assert briefing.handoff_reason == HandoffReason.LOW_AI_CONFIDENCE


def test_briefing_includes_handoff_reason_agent_initiated():
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.AGENT_INITIATED)
    assert briefing.handoff_reason == HandoffReason.AGENT_INITIATED


# ---------------------------------------------------------------------------
# Conversation highlights — fidelity
# ---------------------------------------------------------------------------

def test_briefing_highlights_contain_message_body():
    messages = [_fake_message(body="I want to buy a villa")]
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=messages, reason=HandoffReason.USER_REQUESTED)
    assert briefing.conversation_highlights[0].body == "I want to buy a villa"


def test_briefing_highlights_preserve_inbound_direction():
    messages = [_fake_message(direction=MessageDirection.INBOUND, body="Hello")]
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=messages, reason=HandoffReason.USER_REQUESTED)
    assert briefing.conversation_highlights[0].direction == MessageDirection.INBOUND


def test_briefing_highlights_preserve_outbound_direction():
    messages = [_fake_message(direction=MessageDirection.OUTBOUND, body="Here are some options")]
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=messages, reason=HandoffReason.USER_REQUESTED)
    assert briefing.conversation_highlights[0].direction == MessageDirection.OUTBOUND


def test_briefing_highlights_chronological_order():
    messages = [
        _fake_message(body="First message"),
        _fake_message(body="Second message"),
        _fake_message(body="Third message"),
    ]
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=messages, reason=HandoffReason.USER_REQUESTED)
    assert briefing.conversation_highlights[0].body == "First message"
    assert briefing.conversation_highlights[1].body == "Second message"
    assert briefing.conversation_highlights[2].body == "Third message"


def test_briefing_highlights_count_matches_messages():
    messages = [_fake_message(body=f"msg_{i}") for i in range(7)]
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=messages, reason=HandoffReason.USER_REQUESTED)
    assert len(briefing.conversation_highlights) == 7


def test_briefing_empty_highlights_when_no_messages():
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=[], reason=HandoffReason.USER_REQUESTED)
    assert briefing.conversation_highlights == []


def test_briefing_highlights_mixed_directions():
    messages = [
        _fake_message(direction=MessageDirection.INBOUND, body="I want 3 bedrooms"),
        _fake_message(direction=MessageDirection.OUTBOUND, body="What is your budget?"),
        _fake_message(direction=MessageDirection.INBOUND, body="Around $400k"),
    ]
    lead = _fake_lead()
    briefing = _build_briefing(lead=lead, session_listing_ref=None, messages=messages, reason=HandoffReason.USER_REQUESTED)
    assert briefing.conversation_highlights[0].direction == MessageDirection.INBOUND
    assert briefing.conversation_highlights[1].direction == MessageDirection.OUTBOUND
    assert briefing.conversation_highlights[2].direction == MessageDirection.INBOUND
