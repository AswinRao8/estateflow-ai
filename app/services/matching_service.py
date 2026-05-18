"""Property matching AI explanation service.

SQL filtering in listing_service determines which listings are eligible.
This module's sole role: generate a conversational recommendation message
that explains why each SQL-matched listing fits the buyer's stated criteria.

Hallucination containment: the AI receives only the structured listing fields
serialised in _format_listing_facts. It must not be asked to infer, embellish,
or reference any attribute not present in that payload.
"""
import asyncio
from typing import Any

import anthropic

from app.config import MarketConfig, get_settings
from app.models.context import BuyerProfile, ConversationContext, PropertyMatchResult
from app.models.enums import TransactionType
from app.models.listing import Listing
from app.utils.logging import get_logger

logger = get_logger(__name__)

_anthropic_client: anthropic.AsyncAnthropic | None = None
_MATCHING_TIMEOUT = 12.0
_NO_MATCH_FALLBACK = (
    "Based on your preferences I don't have listings that match all your criteria right now. "
    "Would you like to adjust any of your requirements — for example a different location, "
    "a wider budget range, or a different property type? I can search again with updated criteria."
)

_MATCHING_TOOL: dict[str, Any] = {
    "name": "property_match",
    "description": (
        "Present SQL-matched listings to the buyer with brief fit reasoning. "
        "Reference ONLY the facts supplied in the listing_facts payload. "
        "Do not invent prices, locations, amenities, or any attribute not listed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "recommendation_text": {
                "type": "string",
                "description": (
                    "Conversational WhatsApp message presenting the matched listings. "
                    "No markdown. Use only facts from the listing_facts provided. "
                    "For each listing, explain briefly why it fits the buyer's stated criteria."
                ),
            },
            "viewing_interest_detected": {
                "type": "boolean",
                "description": (
                    "True only if the buyer's current message explicitly asks to view "
                    "or visit a property."
                ),
            },
        },
        "required": ["recommendation_text", "viewing_interest_detected"],
    },
}


def _get_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _anthropic_client


async def run_matching_turn(
    context: ConversationContext,
    matches: list[Listing],
    market: MarketConfig,
) -> PropertyMatchResult:
    """Generate a recommendation message for the SQL-matched listings.

    Returns the no-match fallback immediately when matches is empty — no API call.
    """
    if not matches:
        return PropertyMatchResult(recommendation_text=_NO_MATCH_FALLBACK)
    prompt = _build_matching_prompt(context, matches, market)
    try:
        return await asyncio.wait_for(_call_matching_api(prompt), timeout=_MATCHING_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("Matching turn timed out | lead=%s", context.lead.id)
        return PropertyMatchResult(recommendation_text=_NO_MATCH_FALLBACK)
    except Exception:
        logger.exception("Matching turn failed | lead=%s", context.lead.id)
        return PropertyMatchResult(recommendation_text=_NO_MATCH_FALLBACK)


async def _call_matching_api(prompt: str) -> PropertyMatchResult:
    settings = get_settings()
    response = await _get_client().messages.create(
        model=settings.anthropic_model,
        max_tokens=768,
        tools=[_MATCHING_TOOL],
        tool_choice={"type": "tool", "name": "property_match"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "property_match":
            return _parse_matching_response(block.input)
    raise ValueError("No property_match block in matching response")


def _build_matching_prompt(
    context: ConversationContext,
    matches: list[Listing],
    market: MarketConfig,
) -> str:
    profile = BuyerProfile.from_qualification_data(context.lead.qualification_data)
    profile_section = _format_buyer_profile(profile, market)
    listing_facts = "\n\n".join(
        _format_listing_facts(i + 1, listing, market) for i, listing in enumerate(matches)
    )
    history = "\n".join(f"  [{i + 1}] {msg}" for i, msg in enumerate(context.recent_messages[-5:]))
    count = len(matches)
    return (
        "You are a real estate assistant presenting property matches to a buyer.\n\n"
        f"Buyer's stated criteria:\n{profile_section}\n\n"
        f"SQL-matched listings ({count} result{'s' if count != 1 else ''}):\n"
        f"{listing_facts}\n\n"
        f"Recent conversation:\n{history}\n\n"
        f"Buyer's latest message: {context.current_message}\n\n"
        "Instructions:\n"
        "1. Present each listing conversationally. Explain briefly why it fits "
        "the buyer's stated criteria.\n"
        "2. Use ONLY the facts listed above for each property. Do not add, infer, "
        "or invent any attribute, price, location, or amenity.\n"
        "3. Keep the message suitable for WhatsApp — no markdown, concise.\n"
        "4. Set viewing_interest_detected to true only if the buyer's current message "
        "explicitly asks to view or visit a property.\n\n"
        "Use the property_match tool to respond."
    )


def _format_buyer_profile(profile: BuyerProfile, market: MarketConfig) -> str:
    sym, code = market.currency_symbol, market.currency_code
    lines: list[str] = []
    if profile.budget_min is not None and profile.budget_max is not None:
        lines.append(f"  Budget: {sym}{profile.budget_min:,.0f}–{sym}{profile.budget_max:,.0f} {code}")
    elif profile.budget_max is not None:
        lines.append(f"  Budget (max): {sym}{profile.budget_max:,.0f} {code}")
    elif profile.budget_min is not None:
        lines.append(f"  Budget (from): {sym}{profile.budget_min:,.0f} {code}")
    if profile.location:
        lines.append(f"  Location: {profile.location}")
    if profile.property_type:
        lines.append(f"  Property type: {profile.property_type}")
    if profile.bedrooms is not None:
        lines.append(f"  Bedrooms (minimum): {profile.bedrooms}")
    return "\n".join(lines) if lines else "  No specific criteria stated."


def _format_listing_facts(n: int, listing: Listing, market: MarketConfig) -> str:
    price_str = _format_listing_price(listing, market) or "not provided"
    bedrooms = str(listing.bedrooms) if listing.bedrooms is not None else "not provided"
    bathrooms = str(listing.bathrooms) if listing.bathrooms is not None else "not provided"
    return (
        f"Listing {n}:\n"
        f"  Reference: {listing.reference_code}\n"
        f"  Title: {listing.title}\n"
        f"  Type: {listing.property_type.lower()}\n"
        f"  Transaction: {listing.transaction_type.lower()}\n"
        f"  Price: {price_str}\n"
        f"  Location: {listing.location_area or 'not provided'}\n"
        f"  Bedrooms: {bedrooms}\n"
        f"  Bathrooms: {bathrooms}\n"
        f"  Description: {listing.description or 'not provided'}"
    )


def _format_listing_price(listing: Listing, market: MarketConfig) -> str | None:
    sym, code = market.currency_symbol, market.currency_code
    if listing.transaction_type == TransactionType.RENTAL:
        if listing.price_per_month is not None:
            return f"{sym}{listing.price_per_month:,.0f} {code}/month"
        if listing.price is not None:
            return f"{sym}{listing.price:,.0f} {code}/month"
    elif listing.price is not None:
        return f"{sym}{listing.price:,.0f} {code}"
    return None


def _parse_matching_response(tool_input: dict[str, Any]) -> PropertyMatchResult:
    text = str(tool_input.get("recommendation_text", "")).strip()
    viewing = bool(tool_input.get("viewing_interest_detected", False))
    if not text:
        text = _NO_MATCH_FALLBACK
    return PropertyMatchResult(recommendation_text=text, viewing_interest_detected=viewing)
