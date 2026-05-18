"""Unit tests for Phase 9 follow-up service.

Tests cover the pure functions exclusively — prompt building and response
parsing — which are deterministic and require no DB or Anthropic access.
All trigger types, qualification data variants, and fallback paths are verified.
"""
from types import SimpleNamespace

import pytest

from app.config import MarketConfig
from app.models.enums import FollowUpTriggerType, LeadState
from app.services.followup_service import (
    _build_follow_up_prompt,
    _get_trigger_context,
    _get_trigger_fallback,
    _parse_follow_up_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_MARKET = MarketConfig(currency_symbol="$", currency_code="USD")


def _fake_lead(**overrides) -> SimpleNamespace:
    defaults = {
        "state": LeadState.QUALIFYING,
        "qualification_data": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# _get_trigger_context — each trigger type has a distinct non-empty string
# ---------------------------------------------------------------------------

def test_trigger_context_post_viewing_24h():
    ctx = _get_trigger_context(FollowUpTriggerType.POST_VIEWING_24H)
    assert ctx
    assert "24" in ctx or "yesterday" in ctx.lower() or "viewed" in ctx.lower()


def test_trigger_context_post_viewing_48h():
    ctx = _get_trigger_context(FollowUpTriggerType.POST_VIEWING_48H)
    assert ctx
    assert "48" in ctx


def test_trigger_context_stalled_3d():
    ctx = _get_trigger_context(FollowUpTriggerType.STALLED_3D)
    assert ctx
    assert "3 day" in ctx or "inactive" in ctx.lower()


def test_trigger_context_no_response_48h():
    ctx = _get_trigger_context(FollowUpTriggerType.NO_RESPONSE_48H)
    assert ctx
    assert "48" in ctx or "no response" in ctx.lower() or "recommendation" in ctx.lower()


def test_all_trigger_types_have_context():
    for trigger in FollowUpTriggerType:
        ctx = _get_trigger_context(trigger)
        assert isinstance(ctx, str) and len(ctx) > 10


def test_all_trigger_contexts_are_distinct():
    contexts = [_get_trigger_context(t) for t in FollowUpTriggerType]
    assert len(set(contexts)) == len(contexts), "Each trigger type must have a unique context"


# ---------------------------------------------------------------------------
# _get_trigger_fallback — safe non-empty strings for each trigger type
# ---------------------------------------------------------------------------

def test_all_trigger_types_have_fallback():
    for trigger in FollowUpTriggerType:
        fallback = _get_trigger_fallback(trigger)
        assert isinstance(fallback, str) and len(fallback) > 10


def test_all_trigger_fallbacks_are_distinct():
    fallbacks = [_get_trigger_fallback(t) for t in FollowUpTriggerType]
    assert len(set(fallbacks)) == len(fallbacks)


# ---------------------------------------------------------------------------
# _build_follow_up_prompt — structure and content
# ---------------------------------------------------------------------------

def test_prompt_includes_trigger_context():
    lead = _fake_lead()
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.POST_VIEWING_24H, [], _DEFAULT_MARKET
    )
    expected = _get_trigger_context(FollowUpTriggerType.POST_VIEWING_24H)
    assert expected in prompt


def test_prompt_includes_lead_state():
    lead = _fake_lead(state=LeadState.POST_VIEWING)
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.POST_VIEWING_24H, [], _DEFAULT_MARKET
    )
    assert "POST_VIEWING" in prompt


def test_prompt_includes_recent_messages():
    messages = ["I liked the villa", "What is the parking situation?"]
    lead = _fake_lead()
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.NO_RESPONSE_48H, messages, _DEFAULT_MARKET
    )
    assert "I liked the villa" in prompt
    assert "What is the parking situation?" in prompt


def test_prompt_uses_only_last_five_messages():
    messages = [f"msg_{i}" for i in range(10)]
    lead = _fake_lead()
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.STALLED_3D, messages, _DEFAULT_MARKET
    )
    # Last 5: msg_5 through msg_9
    for i in range(5, 10):
        assert f"msg_{i}" in prompt
    # First 5 should not appear
    for i in range(5):
        assert f"msg_{i}" not in prompt


def test_prompt_handles_no_messages():
    lead = _fake_lead()
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.STALLED_3D, [], _DEFAULT_MARKET
    )
    assert "no prior messages" in prompt


def test_prompt_includes_qualification_data_budget():
    lead = _fake_lead(
        qualification_data={"budget_min": 200_000, "budget_max": 400_000}
    )
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.NO_RESPONSE_48H, [], _DEFAULT_MARKET
    )
    assert "200,000" in prompt
    assert "400,000" in prompt


def test_prompt_includes_qualification_location():
    lead = _fake_lead(qualification_data={"location": "Downtown"})
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.NO_RESPONSE_48H, [], _DEFAULT_MARKET
    )
    assert "Downtown" in prompt


def test_prompt_includes_qualification_property_type():
    lead = _fake_lead(qualification_data={"property_type": "villa"})
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.NO_RESPONSE_48H, [], _DEFAULT_MARKET
    )
    assert "villa" in prompt


def test_prompt_includes_qualification_bedrooms():
    lead = _fake_lead(qualification_data={"bedrooms": 3})
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.NO_RESPONSE_48H, [], _DEFAULT_MARKET
    )
    assert "3" in prompt


def test_prompt_handles_none_qualification_data():
    lead = _fake_lead(qualification_data=None)
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.STALLED_3D, [], _DEFAULT_MARKET
    )
    assert "No qualification data" in prompt


def test_prompt_handles_empty_qualification_data():
    lead = _fake_lead(qualification_data={})
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.STALLED_3D, [], _DEFAULT_MARKET
    )
    # Empty dict is falsy — treated the same as None (no qualification data).
    assert "No qualification data" in prompt


def test_prompt_uses_market_currency_symbol():
    market = MarketConfig(currency_symbol="£", currency_code="GBP")
    lead = _fake_lead(qualification_data={"budget_max": 500_000})
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.NO_RESPONSE_48H, [], market
    )
    assert "£" in prompt
    assert "GBP" in prompt


def test_prompt_budget_max_only():
    lead = _fake_lead(qualification_data={"budget_max": 300_000})
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.NO_RESPONSE_48H, [], _DEFAULT_MARKET
    )
    assert "300,000" in prompt
    assert "max" in prompt.lower()


def test_prompt_budget_min_only():
    lead = _fake_lead(qualification_data={"budget_min": 150_000})
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.NO_RESPONSE_48H, [], _DEFAULT_MARKET
    )
    assert "150,000" in prompt
    assert "from" in prompt.lower()


def test_prompt_instructs_no_markdown():
    lead = _fake_lead()
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.POST_VIEWING_24H, [], _DEFAULT_MARKET
    )
    assert "No markdown" in prompt


def test_prompt_references_tool_name():
    lead = _fake_lead()
    prompt = _build_follow_up_prompt(
        lead, FollowUpTriggerType.POST_VIEWING_24H, [], _DEFAULT_MARKET
    )
    assert "follow_up_message" in prompt


def test_prompt_each_trigger_type_produces_unique_prompt():
    lead = _fake_lead()
    prompts = [
        _build_follow_up_prompt(lead, trigger, [], _DEFAULT_MARKET)
        for trigger in FollowUpTriggerType
    ]
    assert len(set(prompts)) == len(prompts), "Each trigger type must produce a distinct prompt"


# ---------------------------------------------------------------------------
# _parse_follow_up_response — extraction and fallback
# ---------------------------------------------------------------------------

def test_parse_extracts_message_text():
    result = _parse_follow_up_response(
        {"message": "Hi! Just checking in."},
        FollowUpTriggerType.POST_VIEWING_24H,
    )
    assert result == "Hi! Just checking in."


def test_parse_strips_whitespace():
    result = _parse_follow_up_response(
        {"message": "  Hello there.  "},
        FollowUpTriggerType.POST_VIEWING_24H,
    )
    assert result == "Hello there."


def test_parse_falls_back_on_empty_message():
    result = _parse_follow_up_response(
        {"message": ""},
        FollowUpTriggerType.STALLED_3D,
    )
    assert result == _get_trigger_fallback(FollowUpTriggerType.STALLED_3D)


def test_parse_falls_back_on_missing_key():
    result = _parse_follow_up_response(
        {},
        FollowUpTriggerType.NO_RESPONSE_48H,
    )
    assert result == _get_trigger_fallback(FollowUpTriggerType.NO_RESPONSE_48H)


def test_parse_falls_back_on_whitespace_only():
    result = _parse_follow_up_response(
        {"message": "   "},
        FollowUpTriggerType.POST_VIEWING_48H,
    )
    assert result == _get_trigger_fallback(FollowUpTriggerType.POST_VIEWING_48H)


def test_parse_uses_trigger_specific_fallback():
    fallback_24h = _parse_follow_up_response({}, FollowUpTriggerType.POST_VIEWING_24H)
    fallback_48h = _parse_follow_up_response({}, FollowUpTriggerType.POST_VIEWING_48H)
    assert fallback_24h != fallback_48h
