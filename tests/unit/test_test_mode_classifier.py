"""Unit tests for the TEST_MODE keyword classifier in ai_service.

No network calls. All tests verify the deterministic keyword rules and the
classify_intent() integration that activates the classifier when no API key
is configured.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models.context import ConversationContext
from app.models.enums import IntentType
from app.services.ai_service import _test_mode_classify, classify_intent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(
    message: str,
    listing_ref_code: str | None = None,
    listing=None,
) -> ConversationContext:
    lead = SimpleNamespace(id=uuid.uuid4(), state="NEW_INQUIRY")
    session = SimpleNamespace(id=uuid.uuid4(), listing_ref_code=listing_ref_code)
    return ConversationContext(
        lead=lead,
        session=session,
        recent_messages=[],
        current_message=message,
        listing=listing,
    )


def _fake_listing():
    return SimpleNamespace(title="Test Listing", price=500_000)


# ---------------------------------------------------------------------------
# Priority 1 — human agent request
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "I want to speak to a human",
    "Can I talk to an agent please",
    "Connect me with a representative",
    "call me back",
    "I need support",
])
def test_human_keywords_return_human_requested(msg):
    result = _test_mode_classify(msg, _ctx(msg))
    assert result.intent == IntentType.HUMAN_REQUESTED
    assert result.confidence >= 0.90


# ---------------------------------------------------------------------------
# Priority 2 — stop / opt-out
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "STOP",
    "unsubscribe me",
    "I'm not interested",
    "leave me alone",
    "cancel",
])
def test_stop_keywords_return_out_of_scope(msg):
    result = _test_mode_classify(msg, _ctx(msg))
    assert result.intent == IntentType.OUT_OF_SCOPE
    assert result.confidence >= 0.88


# ---------------------------------------------------------------------------
# Priority 3 — viewing booking (specific time or booking phrase)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "I'd like to book a viewing",
    "Can we schedule a viewing for tomorrow?",
    "I want to book a visit on Monday at 10am",
    "arrange a viewing please",
    "viewing on Saturday morning",
    "visit next week",
])
def test_booking_keywords_return_viewing_request_with_high_confidence(msg):
    result = _test_mode_classify(msg, _ctx(msg))
    assert result.intent == IntentType.VIEWING_REQUEST
    assert result.confidence >= 0.90


# ---------------------------------------------------------------------------
# Priority 4 — generic viewing interest (no time)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "I'd like to visit the property",
    "Can I have a viewing?",
    "I want to view it",
    "I want to see property",
    "walk through the apartment",
])
def test_viewing_interest_keywords_return_viewing_request(msg):
    result = _test_mode_classify(msg, _ctx(msg))
    assert result.intent == IntentType.VIEWING_REQUEST
    assert result.confidence >= 0.85


# ---------------------------------------------------------------------------
# Priority 5 — listing reference in message
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "Tell me about REF-001",
    "I'm interested in ref 42",
    "What can you tell me about AB-123?",
])
def test_listing_ref_in_message_returns_listing_inquiry(msg):
    result = _test_mode_classify(msg, _ctx(msg))
    assert result.intent == IntentType.LISTING_INQUIRY


def test_active_listing_in_session_returns_listing_inquiry():
    ctx = _ctx("Tell me more about it", listing_ref_code="REF-001", listing=_fake_listing())
    result = _test_mode_classify(ctx.current_message, ctx)
    assert result.intent == IntentType.LISTING_INQUIRY


def test_listing_ref_in_session_without_listing_object_falls_through():
    # listing_ref_code set but listing=None means the listing wasn't found;
    # the session ref alone should not trigger LISTING_INQUIRY.
    ctx = _ctx("Hello", listing_ref_code="REF-001", listing=None)
    result = _test_mode_classify(ctx.current_message, ctx)
    assert result.intent != IntentType.LISTING_INQUIRY


# ---------------------------------------------------------------------------
# Priority 6 — buyer qualification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "I want to buy a 3-bedroom apartment",
    "I'm looking for a house under 600k",
    "Searching for properties in the city center",
    "I need a 2-bed flat",
    "I'm interested in buying something",
])
def test_qualify_keywords_return_buyer_qualification(msg):
    result = _test_mode_classify(msg, _ctx(msg))
    assert result.intent == IntentType.BUYER_QUALIFICATION
    assert result.confidence >= 0.85


# ---------------------------------------------------------------------------
# Priority 7 — fallback
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "Hello",
    "Hi there",
    "What is the weather like?",
    "ok",
])
def test_fallback_returns_general_inquiry_below_threshold(msg):
    result = _test_mode_classify(msg, _ctx(msg))
    assert result.intent == IntentType.GENERAL_INQUIRY
    assert result.confidence < 0.65


# ---------------------------------------------------------------------------
# Priority ordering — higher-priority rules beat lower ones
# ---------------------------------------------------------------------------

def test_human_beats_viewing():
    msg = "I want to talk to a human agent about booking a viewing"
    result = _test_mode_classify(msg, _ctx(msg))
    assert result.intent == IntentType.HUMAN_REQUESTED


def test_stop_beats_qualify():
    msg = "I want to stop looking for a property"
    result = _test_mode_classify(msg, _ctx(msg))
    assert result.intent == IntentType.OUT_OF_SCOPE


def test_booking_beats_generic_viewing():
    msg = "I want to schedule a viewing for Monday"
    result = _test_mode_classify(msg, _ctx(msg))
    assert result.intent == IntentType.VIEWING_REQUEST
    assert result.confidence >= 0.90  # booking-level confidence, not interest-level


# ---------------------------------------------------------------------------
# classify_intent() integration — TEST_MODE activates when no API key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_intent_uses_test_mode_when_no_api_key():
    ctx = _ctx("I want to buy a flat")
    with patch("app.services.ai_service.get_settings") as mock_settings:
        mock_settings.return_value.anthropic_api_key = ""
        result = await classify_intent(ctx)
    assert result.intent == IntentType.BUYER_QUALIFICATION
    assert "TEST_MODE" in result.reasoning


@pytest.mark.asyncio
async def test_classify_intent_skips_test_mode_when_api_key_present(monkeypatch):
    ctx = _ctx("I want to buy a flat")
    called = []

    async def _fake_api_call(*_):
        from app.models.context import ClassificationResult
        called.append(True)
        return ClassificationResult(
            intent=IntentType.BUYER_QUALIFICATION,
            confidence=0.92,
            reasoning="real API",
        )

    monkeypatch.setattr("app.services.ai_service.get_settings", lambda: SimpleNamespace(
        anthropic_api_key="sk-test-key",
        anthropic_model="claude-sonnet-4-6",
    ))
    monkeypatch.setattr("app.services.ai_service._call_classification_api", _fake_api_call)

    result = await classify_intent(ctx)
    assert called, "Real API path was not reached"
    assert "TEST_MODE" not in result.reasoning


@pytest.mark.asyncio
async def test_classify_intent_logs_test_mode_message(caplog):
    import logging
    ctx = _ctx("looking for a 2-bed apartment")
    with patch("app.services.ai_service.get_settings") as mock_settings:
        mock_settings.return_value.anthropic_api_key = ""
        with caplog.at_level(logging.INFO, logger="app.services.ai_service"):
            await classify_intent(ctx)
    assert any("TEST_MODE classifier used" in r.message for r in caplog.records)
