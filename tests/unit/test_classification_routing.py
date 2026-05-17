"""Tests for intent classification helpers and the deterministic router.

No network calls are made here. classify_intent() fallback paths are tested
by patching asyncio.wait_for / _call_classification_api so the Anthropic client
is never initialised.
"""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.context import ClassificationResult, ConversationContext
from app.models.enums import IntentType, LeadState, WorkflowType
from app.services.conversation_service import (
    _build_classification_prompt,
    _parse_classification_response,
    classify_intent,
)
from app.workflows.inbound_message_workflow import CONFIDENCE_THRESHOLD, _route


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_context(
    current_message: str = "Hello",
    recent_messages: list[str] | None = None,
    state: str = LeadState.NEW_INQUIRY,
    listing=None,
) -> ConversationContext:
    lead = SimpleNamespace(id=uuid.uuid4(), state=state)
    session = SimpleNamespace(id=uuid.uuid4())
    return ConversationContext(
        lead=lead,
        session=session,
        recent_messages=recent_messages or [],
        current_message=current_message,
        listing=listing,
    )


def _fake_listing(title="Ocean View Villa", property_type="VILLA", transaction_type="SALE"):
    return SimpleNamespace(title=title, property_type=property_type, transaction_type=transaction_type)


# ---------------------------------------------------------------------------
# _route — confidence threshold
# ---------------------------------------------------------------------------

def test_route_zero_confidence_returns_clarification():
    assert _route(IntentType.LISTING_INQUIRY, 0.0) == WorkflowType.CLARIFICATION


def test_route_just_below_threshold_returns_clarification():
    assert _route(IntentType.GENERAL_INQUIRY, CONFIDENCE_THRESHOLD - 0.01) == WorkflowType.CLARIFICATION


def test_route_exactly_at_threshold_routes_to_workflow():
    # At the threshold value the confidence check passes (< not <=)
    assert _route(IntentType.LISTING_INQUIRY, CONFIDENCE_THRESHOLD) == WorkflowType.LISTING_INQUIRY


def test_route_above_threshold_routes_correctly():
    assert _route(IntentType.LISTING_INQUIRY, 0.9) == WorkflowType.LISTING_INQUIRY


# ---------------------------------------------------------------------------
# _route — HUMAN_REQUESTED always escalates regardless of confidence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("confidence", [0.0, CONFIDENCE_THRESHOLD - 0.01, CONFIDENCE_THRESHOLD, 1.0])
def test_route_human_requested_always_escalates(confidence):
    assert _route(IntentType.HUMAN_REQUESTED, confidence) == WorkflowType.ESCALATION


# ---------------------------------------------------------------------------
# _route — full intent→workflow mapping at high confidence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("intent,expected", [
    (IntentType.LISTING_INQUIRY,    WorkflowType.LISTING_INQUIRY),
    (IntentType.BUYER_QUALIFICATION, WorkflowType.QUALIFICATION),
    (IntentType.VIEWING_REQUEST,    WorkflowType.VIEWING_REQUEST),
    (IntentType.FOLLOW_UP,          WorkflowType.GENERAL_INQUIRY),
    (IntentType.HUMAN_REQUESTED,    WorkflowType.ESCALATION),
    (IntentType.GENERAL_INQUIRY,    WorkflowType.GENERAL_INQUIRY),
    (IntentType.OUT_OF_SCOPE,       WorkflowType.OUT_OF_SCOPE),
])
def test_route_maps_each_intent_at_full_confidence(intent, expected):
    assert _route(intent, 1.0) == expected


# ---------------------------------------------------------------------------
# _parse_classification_response
# ---------------------------------------------------------------------------

def test_parse_valid_tool_response():
    result = _parse_classification_response({
        "intent": "LISTING_INQUIRY",
        "confidence": 0.9,
        "reasoning": "User asked about the villa price.",
    })
    assert result.intent == IntentType.LISTING_INQUIRY
    assert result.confidence == 0.9
    assert result.reasoning == "User asked about the villa price."


def test_parse_clamps_confidence_above_one():
    result = _parse_classification_response({"intent": "GENERAL_INQUIRY", "confidence": 1.8, "reasoning": ""})
    assert result.confidence == 1.0


def test_parse_clamps_confidence_below_zero():
    result = _parse_classification_response({"intent": "GENERAL_INQUIRY", "confidence": -0.5, "reasoning": ""})
    assert result.confidence == 0.0


def test_parse_unknown_intent_falls_back_to_general_inquiry():
    result = _parse_classification_response({"intent": "TOTALLY_MADE_UP", "confidence": 0.9, "reasoning": ""})
    assert result.intent == IntentType.GENERAL_INQUIRY


def test_parse_empty_dict_uses_safe_defaults():
    result = _parse_classification_response({})
    assert result.intent == IntentType.GENERAL_INQUIRY
    assert result.confidence == 0.0
    assert result.reasoning == ""


def test_parse_all_intent_values_round_trip():
    for intent in IntentType:
        result = _parse_classification_response({"intent": intent.value, "confidence": 0.8, "reasoning": "x"})
        assert result.intent == intent


# ---------------------------------------------------------------------------
# _build_classification_prompt
# ---------------------------------------------------------------------------

def test_prompt_includes_lead_state():
    ctx = _fake_context(state=LeadState.QUALIFYING)
    prompt = _build_classification_prompt(ctx)
    assert "QUALIFYING" in prompt


def test_prompt_includes_current_message():
    ctx = _fake_context(current_message="Is parking included?")
    prompt = _build_classification_prompt(ctx)
    assert "Is parking included?" in prompt


def test_prompt_includes_recent_messages():
    ctx = _fake_context(recent_messages=["Hello", "Tell me more"])
    prompt = _build_classification_prompt(ctx)
    assert "Hello" in prompt
    assert "Tell me more" in prompt


def test_prompt_limits_history_to_last_five_messages():
    messages = [f"msg_{i}" for i in range(10)]
    ctx = _fake_context(recent_messages=messages)
    prompt = _build_classification_prompt(ctx)
    # Last 5 should appear
    for i in range(5, 10):
        assert f"msg_{i}" in prompt
    # First 5 should not
    for i in range(5):
        assert f"msg_{i}" not in prompt


def test_prompt_includes_listing_context_when_present():
    ctx = _fake_context(listing=_fake_listing("Sea View Apartment", "APARTMENT", "RENTAL"))
    prompt = _build_classification_prompt(ctx)
    assert "Sea View Apartment" in prompt
    assert "APARTMENT" in prompt
    assert "RENTAL" in prompt


def test_prompt_excludes_listing_section_when_no_listing():
    ctx = _fake_context(listing=None)
    prompt = _build_classification_prompt(ctx)
    assert "Listing context:" not in prompt


# ---------------------------------------------------------------------------
# classify_intent — fallback paths (no real API calls)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_intent_returns_fallback_on_timeout():
    ctx = _fake_context()

    async def _raise_timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch("app.services.conversation_service.asyncio.wait_for", side_effect=_raise_timeout):
        result = await classify_intent(ctx)

    assert result.intent == IntentType.GENERAL_INQUIRY
    assert result.confidence == 0.0
    assert "timed out" in result.reasoning.lower()


@pytest.mark.asyncio
async def test_classify_intent_returns_fallback_on_api_exception():
    ctx = _fake_context()

    with patch(
        "app.services.conversation_service._call_classification_api",
        new_callable=AsyncMock,
        side_effect=RuntimeError("API unreachable"),
    ):
        result = await classify_intent(ctx)

    assert result.intent == IntentType.GENERAL_INQUIRY
    assert result.confidence == 0.0
