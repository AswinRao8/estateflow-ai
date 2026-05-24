"""Unit tests for Phase 5 listing-aware response components.

Tests cover: _format_price, _format_area, _resolve_property_type_label,
_build_listing_prompt, _parse_listing_response, generate_listing_response
fallback paths, and listing_inquiry_workflow.run() branch logic.

No Anthropic API calls are made — external calls are intercepted via
asyncio.wait_for or _call_listing_api patches.
"""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import MarketConfig
from app.models.context import ConversationContext, ListingResponseResult, WorkflowResult
from app.models.enums import LeadState, PropertyStatus, TransactionType, WorkflowType
from app.services.ai_service import (
    _build_listing_prompt,
    _format_area,
    _format_price,
    _parse_listing_response,
    _resolve_property_type_label,
    generate_listing_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _market(**overrides) -> MarketConfig:
    return MarketConfig(**overrides)


def _listing(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=uuid.uuid4(),
        reference_code="VILLA-01",
        title="Ocean View Villa",
        property_type="VILLA",
        transaction_type=TransactionType.SALE,
        status=PropertyStatus.AVAILABLE,
        price=1_500_000.0,
        price_per_month=None,
        location_area="Palm Beach",
        location_description=None,
        bedrooms=4,
        bathrooms=3,
        floor_area_sqm=280.0,
        land_area_sqm=500.0,
        description="Stunning sea-facing villa.",
        features="Pool, Gym, Sea view",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _context(listing=None, current_message="Tell me about the villa", recent=None) -> ConversationContext:
    lead = SimpleNamespace(id=uuid.uuid4(), state=LeadState.NEW_INQUIRY)
    session = SimpleNamespace(id=uuid.uuid4())
    return ConversationContext(
        lead=lead,
        session=session,
        recent_messages=recent or [],
        current_message=current_message,
        listing=listing,
    )


# ---------------------------------------------------------------------------
# _format_price
# ---------------------------------------------------------------------------

def test_format_price_sale_uses_price():
    listing = _listing(transaction_type=TransactionType.SALE, price=1_500_000.0)
    result = _format_price(listing, _market(currency_symbol="$", currency_code="USD"))
    assert result == "$1,500,000 USD"


def test_format_price_rental_uses_price_per_month():
    listing = _listing(transaction_type=TransactionType.RENTAL, price_per_month=5000.0, price=None)
    result = _format_price(listing, _market(currency_symbol="AED", currency_code="AED"))
    assert result == "AED5,000 AED/month"


def test_format_price_rental_falls_back_to_price_when_no_monthly():
    listing = _listing(transaction_type=TransactionType.RENTAL, price_per_month=None, price=60_000.0)
    result = _format_price(listing, _market(currency_symbol="$", currency_code="USD"))
    assert result == "$60,000 USD/month"


def test_format_price_returns_none_when_no_price():
    listing = _listing(transaction_type=TransactionType.SALE, price=None, price_per_month=None)
    assert _format_price(listing, _market()) is None


def test_format_price_uses_market_currency_symbol_and_code():
    listing = _listing(transaction_type=TransactionType.SALE, price=2_000_000.0)
    result = _format_price(listing, _market(currency_symbol="€", currency_code="EUR"))
    assert result == "€2,000,000 EUR"


# ---------------------------------------------------------------------------
# _format_area
# ---------------------------------------------------------------------------

def test_format_area_sqm_default():
    result = _format_area(150.0, _market(area_unit="sqm"))
    assert result == "150 sq m"


def test_format_area_sqft_converts_correctly():
    result = _format_area(100.0, _market(area_unit="sqft"))
    assert "sq ft" in result
    assert "1,076" in result  # 100 * 10.764 ≈ 1076


def test_format_area_none_returns_none():
    assert _format_area(None, _market()) is None


# ---------------------------------------------------------------------------
# _resolve_property_type_label
# ---------------------------------------------------------------------------

def test_resolve_label_returns_lowercase_default():
    assert _resolve_property_type_label("VILLA", _market()) == "villa"


def test_resolve_label_uses_terminology_override():
    market = _market(property_terminology={"VILLA": "luxury villa"})
    assert _resolve_property_type_label("VILLA", market) == "luxury villa"


def test_resolve_label_falls_back_for_unknown_type():
    assert _resolve_property_type_label("PENTHOUSE", _market()) == "penthouse"


# ---------------------------------------------------------------------------
# _build_listing_prompt
# ---------------------------------------------------------------------------

def test_prompt_includes_listing_title():
    ctx = _context(listing=_listing(title="Sunset Penthouse"))
    prompt = _build_listing_prompt(ctx, _market())
    assert "Sunset Penthouse" in prompt


def test_prompt_includes_reference_code():
    ctx = _context(listing=_listing(reference_code="REF-999"))
    prompt = _build_listing_prompt(ctx, _market())
    assert "REF-999" in prompt


def test_prompt_includes_formatted_price():
    ctx = _context(listing=_listing(price=750_000.0))
    prompt = _build_listing_prompt(ctx, _market(currency_symbol="$", currency_code="USD"))
    assert "$750,000 USD" in prompt


def test_prompt_says_not_provided_for_missing_price():
    ctx = _context(listing=_listing(price=None, price_per_month=None))
    prompt = _build_listing_prompt(ctx, _market())
    assert "Price: not provided" in prompt


def test_prompt_uses_property_type_label():
    market = _market(property_terminology={"VILLA": "beachfront villa"})
    ctx = _context(listing=_listing(property_type="VILLA"))
    prompt = _build_listing_prompt(ctx, market)
    assert "beachfront villa" in prompt


def test_prompt_includes_current_message():
    ctx = _context(listing=_listing(), current_message="How many bedrooms?")
    prompt = _build_listing_prompt(ctx, _market())
    assert "How many bedrooms?" in prompt


def test_prompt_limits_history_to_last_five():
    messages = [f"msg_{i}" for i in range(8)]
    ctx = _context(listing=_listing(), recent=messages)
    prompt = _build_listing_prompt(ctx, _market())
    for i in range(3, 8):
        assert f"msg_{i}" in prompt
    for i in range(3):
        assert f"msg_{i}" not in prompt


def test_prompt_says_not_provided_for_none_bedrooms():
    ctx = _context(listing=_listing(bedrooms=None))
    prompt = _build_listing_prompt(ctx, _market())
    assert "Bedrooms: not provided" in prompt


def test_prompt_includes_sqft_when_market_uses_sqft():
    ctx = _context(listing=_listing(floor_area_sqm=100.0))
    prompt = _build_listing_prompt(ctx, _market(area_unit="sqft"))
    assert "sq ft" in prompt


# ---------------------------------------------------------------------------
# _parse_listing_response
# ---------------------------------------------------------------------------

def test_parse_valid_response():
    result = _parse_listing_response({"response_text": "It has 4 bedrooms.", "viewing_interest_detected": False})
    assert result.response_text == "It has 4 bedrooms."
    assert result.viewing_interest_detected is False


def test_parse_viewing_interest_true():
    result = _parse_listing_response({"response_text": "Sure!", "viewing_interest_detected": True})
    assert result.viewing_interest_detected is True


def test_parse_empty_response_text_uses_fallback():
    result = _parse_listing_response({"response_text": "", "viewing_interest_detected": False})
    assert result.response_text  # fallback message is non-empty


def test_parse_missing_keys_uses_safe_defaults():
    result = _parse_listing_response({})
    assert result.response_text  # fallback message
    assert result.viewing_interest_detected is False


# ---------------------------------------------------------------------------
# generate_listing_response — fallback paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_listing_response_timeout_returns_fallback():
    ctx = _context(listing=_listing())

    async def _raise_timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch("app.services.ai_service.asyncio.wait_for", side_effect=_raise_timeout):
        result = await generate_listing_response(ctx, _market())

    assert result.response_text
    assert result.viewing_interest_detected is False


@pytest.mark.asyncio
async def test_generate_listing_response_exception_returns_fallback():
    ctx = _context(listing=_listing())

    with patch(
        "app.services.ai_service._call_listing_api",
        new_callable=AsyncMock,
        side_effect=RuntimeError("API down"),
    ):
        result = await generate_listing_response(ctx, _market())

    assert result.response_text
    assert result.viewing_interest_detected is False


# ---------------------------------------------------------------------------
# listing_inquiry_workflow.run() — branch logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_returns_no_listing_message_when_context_has_no_listing():
    from app.workflows import listing_inquiry_workflow

    db = AsyncMock()
    ctx = _context(listing=None)
    result = await listing_inquiry_workflow.run(db, ctx)

    assert result.outbound_message
    assert result.workflow_type == WorkflowType.LISTING_INQUIRY
    assert result.new_lead_state is None


@pytest.mark.asyncio
async def test_run_returns_unavailable_message_for_non_available_listing():
    from app.workflows import listing_inquiry_workflow

    db = AsyncMock()
    ctx = _context(listing=_listing(status=PropertyStatus.SOLD, title="Sea Villa"))
    result = await listing_inquiry_workflow.run(db, ctx)

    assert "Sea Villa" in result.outbound_message
    assert "sold" in result.outbound_message.lower()
    assert result.workflow_type == WorkflowType.LISTING_INQUIRY
    assert result.new_lead_state is None


@pytest.mark.asyncio
async def test_run_sets_viewing_interest_state_when_detected():
    from app.workflows import listing_inquiry_workflow

    db = AsyncMock()
    ctx = _context(listing=_listing())
    ai_result = ListingResponseResult(response_text="Sure, let me arrange that!", viewing_interest_detected=True)

    with patch("app.workflows.listing_inquiry_workflow.ai_service.generate_listing_response", new_callable=AsyncMock, return_value=ai_result):
        result = await listing_inquiry_workflow.run(db, ctx)

    assert result.new_lead_state == LeadState.VIEWING_INTEREST
    assert result.workflow_type == WorkflowType.LISTING_INQUIRY


@pytest.mark.asyncio
async def test_run_does_not_set_state_when_no_viewing_interest():
    from app.workflows import listing_inquiry_workflow

    db = AsyncMock()
    ctx = _context(listing=_listing())
    ai_result = ListingResponseResult(response_text="It has 4 bedrooms.", viewing_interest_detected=False)

    with patch("app.workflows.listing_inquiry_workflow.ai_service.generate_listing_response", new_callable=AsyncMock, return_value=ai_result):
        result = await listing_inquiry_workflow.run(db, ctx)

    assert result.new_lead_state == LeadState.CONTEXT_IDENTIFIED
    assert result.outbound_message == "It has 4 bedrooms."


@pytest.mark.asyncio
async def test_run_passes_market_config_to_ai_service():
    from app.workflows import listing_inquiry_workflow

    db = AsyncMock()
    ctx = _context(listing=_listing())
    ai_result = ListingResponseResult(response_text="Details here.", viewing_interest_detected=False)

    with patch("app.workflows.listing_inquiry_workflow.ai_service.generate_listing_response", new_callable=AsyncMock, return_value=ai_result) as mock_fn:
        await listing_inquiry_workflow.run(db, ctx)

    call_args = mock_fn.call_args
    assert call_args[0][0] is ctx
    assert isinstance(call_args[0][1], MarketConfig)
