"""Unit tests for Phase 7 property matching components.

Tests cover: _build_matching_prompt, _parse_matching_response,
run_matching_turn fallback paths, and property_matching_workflow.run()
branch logic (state advancement, viewing interest, no-match handling).

No Anthropic API calls or database access — all external calls are patched.
"""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import MarketConfig
from app.models.context import BuyerProfile, ConversationContext, PropertyMatchResult
from app.models.enums import LeadState, WorkflowType
from app.services.matching_service import (
    _build_matching_prompt,
    _parse_matching_response,
    run_matching_turn,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _market(**overrides) -> MarketConfig:
    return MarketConfig(**overrides)


def _context(
    current_message: str = "Show me what you have",
    qualification_data: dict | None = None,
    state: str = LeadState.QUALIFYING,
    recent: list[str] | None = None,
) -> ConversationContext:
    lead = SimpleNamespace(id=uuid.uuid4(), state=state, qualification_data=qualification_data)
    session = SimpleNamespace(id=uuid.uuid4())
    return ConversationContext(
        lead=lead,
        session=session,
        recent_messages=recent or [],
        current_message=current_message,
    )


def _fake_listing(
    ref: str = "REF-001",
    title: str = "Sea View Apartment",
    property_type: str = "APARTMENT",
    transaction_type: str = "SALE",
    price: float | None = 350_000.0,
    price_per_month: float | None = None,
    location_area: str | None = "Coastal District",
    bedrooms: int | None = 2,
    bathrooms: int | None = 2,
    description: str | None = "Spacious unit with sea views",
) -> SimpleNamespace:
    return SimpleNamespace(
        reference_code=ref,
        title=title,
        property_type=property_type,
        transaction_type=transaction_type,
        price=price,
        price_per_month=price_per_month,
        location_area=location_area,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        description=description,
    )


# ---------------------------------------------------------------------------
# _build_matching_prompt
# ---------------------------------------------------------------------------

def test_prompt_includes_listing_title():
    ctx = _context()
    prompt = _build_matching_prompt(ctx, [_fake_listing(title="Harbour View Villa")], _market())
    assert "Harbour View Villa" in prompt


def test_prompt_includes_listing_reference():
    ctx = _context()
    prompt = _build_matching_prompt(ctx, [_fake_listing(ref="APT-042")], _market())
    assert "APT-042" in prompt


def test_prompt_includes_formatted_price():
    ctx = _context()
    prompt = _build_matching_prompt(
        ctx, [_fake_listing(price=400_000.0)], _market(currency_symbol="$", currency_code="USD")
    )
    assert "$400,000" in prompt
    assert "USD" in prompt


def test_prompt_includes_location():
    ctx = _context()
    prompt = _build_matching_prompt(ctx, [_fake_listing(location_area="Marina Bay")], _market())
    assert "Marina Bay" in prompt


def test_prompt_shows_not_provided_for_none_location():
    ctx = _context()
    prompt = _build_matching_prompt(ctx, [_fake_listing(location_area=None)], _market())
    assert "not provided" in prompt


def test_prompt_shows_not_provided_for_none_description():
    ctx = _context()
    prompt = _build_matching_prompt(ctx, [_fake_listing(description=None)], _market())
    assert "not provided" in prompt


def test_prompt_includes_buyer_budget_from_qualification_data():
    ctx = _context(qualification_data={"budget_min": 300_000, "budget_max": 500_000})
    prompt = _build_matching_prompt(ctx, [_fake_listing()], _market(currency_symbol="$", currency_code="USD"))
    assert "300,000" in prompt
    assert "500,000" in prompt


def test_prompt_shows_no_criteria_when_no_qualification_data():
    ctx = _context(qualification_data=None)
    prompt = _build_matching_prompt(ctx, [_fake_listing()], _market())
    assert "No specific criteria stated" in prompt


def test_prompt_includes_buyer_location_from_qualification_data():
    ctx = _context(qualification_data={"location": "Riverside"})
    prompt = _build_matching_prompt(ctx, [_fake_listing()], _market())
    assert "Riverside" in prompt


def test_prompt_includes_current_message():
    ctx = _context(current_message="I want to book a viewing this weekend")
    prompt = _build_matching_prompt(ctx, [_fake_listing()], _market())
    assert "I want to book a viewing this weekend" in prompt


def test_prompt_limits_history_to_last_five():
    messages = [f"msg_{i}" for i in range(8)]
    ctx = _context(recent=messages)
    prompt = _build_matching_prompt(ctx, [_fake_listing()], _market())
    for i in range(3, 8):
        assert f"msg_{i}" in prompt
    for i in range(3):
        assert f"msg_{i}" not in prompt


def test_prompt_includes_count_of_listings():
    ctx = _context()
    listings = [_fake_listing(ref=f"REF-{i}") for i in range(3)]
    prompt = _build_matching_prompt(ctx, listings, _market())
    assert "3 results" in prompt


def test_prompt_includes_hallucination_containment_instruction():
    ctx = _context()
    prompt = _build_matching_prompt(ctx, [_fake_listing()], _market())
    assert "Do not add" in prompt or "Do not" in prompt


def test_prompt_formats_rental_price_per_month():
    listing = _fake_listing(
        transaction_type="RENTAL", price=None, price_per_month=2_500.0
    )
    ctx = _context()
    prompt = _build_matching_prompt(ctx, [listing], _market(currency_symbol="£", currency_code="GBP"))
    assert "2,500" in prompt
    assert "month" in prompt


# ---------------------------------------------------------------------------
# _parse_matching_response
# ---------------------------------------------------------------------------

def test_parse_extracts_recommendation_text():
    result = _parse_matching_response({
        "recommendation_text": "Here are two properties that match your criteria.",
        "viewing_interest_detected": False,
    })
    assert result.recommendation_text == "Here are two properties that match your criteria."


def test_parse_detects_viewing_interest_true():
    result = _parse_matching_response({
        "recommendation_text": "Great choices available.",
        "viewing_interest_detected": True,
    })
    assert result.viewing_interest_detected is True


def test_parse_viewing_interest_false_by_default():
    result = _parse_matching_response({
        "recommendation_text": "Here are some options.",
        "viewing_interest_detected": False,
    })
    assert result.viewing_interest_detected is False


def test_parse_empty_text_uses_fallback():
    result = _parse_matching_response({"recommendation_text": "", "viewing_interest_detected": False})
    assert result.recommendation_text
    assert len(result.recommendation_text) > 0


def test_parse_empty_dict_returns_safe_defaults():
    result = _parse_matching_response({})
    assert result.recommendation_text
    assert result.viewing_interest_detected is False


# ---------------------------------------------------------------------------
# run_matching_turn — fallback paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_matches_returns_fallback_without_api_call():
    ctx = _context()
    result = await run_matching_turn(ctx, [], _market())
    assert result.recommendation_text
    assert "criteria" in result.recommendation_text.lower() or "match" in result.recommendation_text.lower()
    assert result.viewing_interest_detected is False


@pytest.mark.asyncio
async def test_timeout_returns_fallback():
    ctx = _context()

    async def _raise_timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch("app.services.matching_service.asyncio.wait_for", side_effect=_raise_timeout):
        result = await run_matching_turn(ctx, [_fake_listing()], _market())

    assert result.recommendation_text
    assert result.viewing_interest_detected is False


@pytest.mark.asyncio
async def test_exception_returns_fallback():
    ctx = _context()
    with patch(
        "app.services.matching_service._call_matching_api",
        new_callable=AsyncMock,
        side_effect=RuntimeError("API error"),
    ):
        result = await run_matching_turn(ctx, [_fake_listing()], _market())

    assert result.recommendation_text
    assert result.viewing_interest_detected is False


# ---------------------------------------------------------------------------
# property_matching_workflow.run() — state and persistence logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_advances_lead_from_qualifying_to_matching():
    from app.workflows import property_matching_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.QUALIFYING)
    ai_result = PropertyMatchResult(recommendation_text="Here are your matches.")

    with patch("app.workflows.property_matching_workflow.listing_service.match_listings", new_callable=AsyncMock, return_value=[_fake_listing()]), \
         patch("app.workflows.property_matching_workflow.matching_service.run_matching_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.property_matching_workflow.lead_service.advance_state", new_callable=AsyncMock) as mock_advance:
        result = await property_matching_workflow.run(db, ctx)

    mock_advance.assert_awaited_once_with(db, lead_id=ctx.lead.id, to_state=LeadState.MATCHING_PROPERTIES)
    assert result.new_lead_state == LeadState.MATCHING_PROPERTIES


@pytest.mark.asyncio
async def test_workflow_advances_lead_from_context_identified_to_matching():
    from app.workflows import property_matching_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.CONTEXT_IDENTIFIED)
    ai_result = PropertyMatchResult(recommendation_text="Here are your matches.")

    with patch("app.workflows.property_matching_workflow.listing_service.match_listings", new_callable=AsyncMock, return_value=[_fake_listing()]), \
         patch("app.workflows.property_matching_workflow.matching_service.run_matching_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.property_matching_workflow.lead_service.advance_state", new_callable=AsyncMock) as mock_advance:
        result = await property_matching_workflow.run(db, ctx)

    mock_advance.assert_awaited_once_with(db, lead_id=ctx.lead.id, to_state=LeadState.MATCHING_PROPERTIES)
    assert result.new_lead_state == LeadState.MATCHING_PROPERTIES


@pytest.mark.asyncio
async def test_workflow_does_not_advance_when_already_in_matching():
    from app.workflows import property_matching_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.MATCHING_PROPERTIES)
    ai_result = PropertyMatchResult(recommendation_text="Here are updated matches.")

    with patch("app.workflows.property_matching_workflow.listing_service.match_listings", new_callable=AsyncMock, return_value=[_fake_listing()]), \
         patch("app.workflows.property_matching_workflow.matching_service.run_matching_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.property_matching_workflow.lead_service.advance_state", new_callable=AsyncMock) as mock_advance:
        result = await property_matching_workflow.run(db, ctx)

    mock_advance.assert_not_called()
    assert result.new_lead_state is None


@pytest.mark.asyncio
async def test_workflow_advances_to_viewing_interest_when_detected():
    from app.workflows import property_matching_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.MATCHING_PROPERTIES)
    ai_result = PropertyMatchResult(recommendation_text="Great choice!", viewing_interest_detected=True)

    with patch("app.workflows.property_matching_workflow.listing_service.match_listings", new_callable=AsyncMock, return_value=[_fake_listing()]), \
         patch("app.workflows.property_matching_workflow.matching_service.run_matching_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.property_matching_workflow.lead_service.advance_state", new_callable=AsyncMock) as mock_advance:
        result = await property_matching_workflow.run(db, ctx)

    mock_advance.assert_awaited_once_with(db, lead_id=ctx.lead.id, to_state=LeadState.VIEWING_INTEREST)
    assert result.new_lead_state == LeadState.VIEWING_INTEREST


@pytest.mark.asyncio
async def test_workflow_advances_through_both_states_when_entry_state_and_viewing_interest():
    from app.workflows import property_matching_workflow
    from app.exceptions import InvalidStateTransitionError

    db = AsyncMock()
    ctx = _context(state=LeadState.QUALIFYING)
    ai_result = PropertyMatchResult(recommendation_text="Matches found!", viewing_interest_detected=True)

    advance_calls: list = []

    async def _advance(db, *, lead_id, to_state):
        advance_calls.append(to_state)

    with patch("app.workflows.property_matching_workflow.listing_service.match_listings", new_callable=AsyncMock, return_value=[_fake_listing()]), \
         patch("app.workflows.property_matching_workflow.matching_service.run_matching_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.property_matching_workflow.lead_service.advance_state", side_effect=_advance):
        result = await property_matching_workflow.run(db, ctx)

    assert LeadState.MATCHING_PROPERTIES in advance_calls
    assert LeadState.VIEWING_INTEREST in advance_calls
    assert result.new_lead_state == LeadState.VIEWING_INTEREST


@pytest.mark.asyncio
async def test_workflow_returns_correct_workflow_type():
    from app.workflows import property_matching_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.MATCHING_PROPERTIES)
    ai_result = PropertyMatchResult(recommendation_text="Here are your options.")

    with patch("app.workflows.property_matching_workflow.listing_service.match_listings", new_callable=AsyncMock, return_value=[_fake_listing()]), \
         patch("app.workflows.property_matching_workflow.matching_service.run_matching_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.property_matching_workflow.lead_service.advance_state", new_callable=AsyncMock):
        result = await property_matching_workflow.run(db, ctx)

    assert result.workflow_type == WorkflowType.MATCHING_PROPERTIES
    assert result.outbound_message == "Here are your options."


@pytest.mark.asyncio
async def test_workflow_passes_market_config_to_matching_service():
    from app.workflows import property_matching_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.MATCHING_PROPERTIES)
    ai_result = PropertyMatchResult(recommendation_text="Options here.")

    with patch("app.workflows.property_matching_workflow.listing_service.match_listings", new_callable=AsyncMock, return_value=[_fake_listing()]), \
         patch("app.workflows.property_matching_workflow.matching_service.run_matching_turn", new_callable=AsyncMock, return_value=ai_result) as mock_fn, \
         patch("app.workflows.property_matching_workflow.lead_service.advance_state", new_callable=AsyncMock):
        await property_matching_workflow.run(db, ctx)

    call_args = mock_fn.call_args
    assert call_args[0][0] is ctx
    assert isinstance(call_args[0][2], MarketConfig)


@pytest.mark.asyncio
async def test_workflow_tolerates_advance_state_failure():
    from app.workflows import property_matching_workflow
    from app.exceptions import InvalidStateTransitionError

    db = AsyncMock()
    ctx = _context(state=LeadState.QUALIFYING)
    ai_result = PropertyMatchResult(recommendation_text="Here are your options.")

    with patch("app.workflows.property_matching_workflow.listing_service.match_listings", new_callable=AsyncMock, return_value=[_fake_listing()]), \
         patch("app.workflows.property_matching_workflow.matching_service.run_matching_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.property_matching_workflow.lead_service.advance_state", new_callable=AsyncMock, side_effect=InvalidStateTransitionError("QUALIFYING", "MATCHING_PROPERTIES")):
        result = await property_matching_workflow.run(db, ctx)

    assert result.outbound_message == "Here are your options."
    assert result.workflow_type == WorkflowType.MATCHING_PROPERTIES
    assert result.new_lead_state is None


@pytest.mark.asyncio
async def test_workflow_returns_no_match_message_when_empty_results():
    from app.workflows import property_matching_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.MATCHING_PROPERTIES)
    no_match_result = PropertyMatchResult(recommendation_text="No matches found right now.")

    with patch("app.workflows.property_matching_workflow.listing_service.match_listings", new_callable=AsyncMock, return_value=[]), \
         patch("app.workflows.property_matching_workflow.matching_service.run_matching_turn", new_callable=AsyncMock, return_value=no_match_result), \
         patch("app.workflows.property_matching_workflow.lead_service.advance_state", new_callable=AsyncMock):
        result = await property_matching_workflow.run(db, ctx)

    assert result.outbound_message == "No matches found right now."
    assert result.workflow_type == WorkflowType.MATCHING_PROPERTIES


@pytest.mark.asyncio
async def test_workflow_passes_empty_matches_to_service():
    from app.workflows import property_matching_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.MATCHING_PROPERTIES)
    no_match_result = PropertyMatchResult(recommendation_text="No matches.")

    with patch("app.workflows.property_matching_workflow.listing_service.match_listings", new_callable=AsyncMock, return_value=[]) as mock_match, \
         patch("app.workflows.property_matching_workflow.matching_service.run_matching_turn", new_callable=AsyncMock, return_value=no_match_result) as mock_service, \
         patch("app.workflows.property_matching_workflow.lead_service.advance_state", new_callable=AsyncMock):
        await property_matching_workflow.run(db, ctx)

    call_args = mock_service.call_args
    assert call_args[0][1] == []


# ---------------------------------------------------------------------------
# BuyerProfile.from_qualification_data
# ---------------------------------------------------------------------------

def test_buyer_profile_extracts_all_fields():
    data = {
        "budget_min": 200_000,
        "budget_max": 400_000,
        "location": "Downtown",
        "property_type": "apartment",
        "bedrooms": 2,
    }
    profile = BuyerProfile.from_qualification_data(data)
    assert profile.budget_min == 200_000.0
    assert profile.budget_max == 400_000.0
    assert profile.location == "Downtown"
    assert profile.property_type == "apartment"
    assert profile.bedrooms == 2


def test_buyer_profile_returns_empty_profile_for_none_data():
    profile = BuyerProfile.from_qualification_data(None)
    assert profile.budget_min is None
    assert profile.budget_max is None
    assert profile.location is None
    assert profile.property_type is None
    assert profile.bedrooms is None
    assert profile.has_criteria is False


def test_buyer_profile_has_criteria_true_when_any_field_set():
    profile = BuyerProfile(location="Riverside")
    assert profile.has_criteria is True


def test_buyer_profile_converts_float_bedrooms_to_int():
    profile = BuyerProfile.from_qualification_data({"bedrooms": 3.0})
    assert profile.bedrooms == 3
    assert isinstance(profile.bedrooms, int)
