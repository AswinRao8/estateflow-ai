"""Anthropic AI calls for intent classification and listing response generation.

All functions in this module make external API calls via the Anthropic SDK.
No database access — the caller assembles context before invoking these functions.

When ANTHROPIC_API_KEY is absent, classify_intent falls back to a deterministic
keyword classifier (_test_mode_classify) so local offline development produces
visible state transitions without any external dependencies.
"""
import asyncio
import re
from typing import Any

import anthropic

from app.config import MarketConfig, get_settings
from app.models.context import ClassificationResult, ConversationContext, ListingResponseResult
from app.models.enums import IntentType, TransactionType
from app.utils.logging import get_logger

logger = get_logger(__name__)

_anthropic_client: anthropic.AsyncAnthropic | None = None
_CLASSIFICATION_TIMEOUT = 8.0
_LISTING_RESPONSE_TIMEOUT = 10.0

# ---------------------------------------------------------------------------
# TEST_MODE keyword classifier — used when ANTHROPIC_API_KEY is absent.
# Rules are applied in priority order; first match wins.
# ---------------------------------------------------------------------------

_TM_HUMAN_WORDS = frozenset({"human", "agent", "representative", "staff", "support"})
_TM_HUMAN_PHRASES = frozenset({"call me", "speak to", "talk to", "connect me"})
_TM_STOP_WORDS = frozenset({"stop", "unsubscribe", "cancel", "quit", "optout", "opt-out"})
_TM_BOOKING_PHRASES = frozenset({
    "book viewing", "schedule viewing", "book a viewing", "schedule a viewing",
    "book a visit", "schedule a visit", "arrange a viewing", "make an appointment",
})
_TM_VIEWING_WORDS = frozenset({"visit", "viewing", "view"})
_TM_VIEWING_PHRASES = frozenset({"see property", "see the property", "walk through", "have a look"})
_TM_QUALIFY_WORDS = frozenset({
    "buy", "buying", "purchase", "looking", "searching",
    "search", "interested", "need", "want", "find",
})
_TM_DATE_RE = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|tomorrow|today|next\s+week|this\s+week"
    r"|\d{1,2}[\/\-\.]\d{1,2}"
    r"|\d{1,2}\s*(?:am|pm)"
    r"|morning|afternoon|evening|noon)\b",
    re.IGNORECASE,
)
_TM_LISTING_REF_RE = re.compile(r"\b(ref[-\s]?\d+|[A-Z]{2,}-\d+)\b", re.IGNORECASE)


def _test_mode_classify(text: str, context: ConversationContext) -> ClassificationResult:
    """Deterministic keyword classifier for offline development.

    Runs when ANTHROPIC_API_KEY is absent. Returns high-confidence results so
    the pipeline routes to the correct workflow and produces visible state changes.
    Priority: human > stop > booking > viewing > listing_ref > qualify > fallback.
    """
    lower = text.lower()
    words = set(re.findall(r"\b\w+\b", lower))

    # 1. Human agent request — always escalate, regardless of other keywords.
    if (words & _TM_HUMAN_WORDS) or any(ph in lower for ph in _TM_HUMAN_PHRASES):
        return ClassificationResult(
            intent=IntentType.HUMAN_REQUESTED,
            confidence=0.95,
            reasoning="TEST_MODE: human/agent keyword",
        )

    # 2. Stop / opt-out.
    if words & _TM_STOP_WORDS or "not interested" in lower or "leave me alone" in lower:
        return ClassificationResult(
            intent=IntentType.OUT_OF_SCOPE,
            confidence=0.90,
            reasoning="TEST_MODE: stop/opt-out keyword",
        )

    # 3. Booking with specific time — higher specificity than generic viewing interest.
    has_booking = any(ph in lower for ph in _TM_BOOKING_PHRASES)
    has_datetime = bool(_TM_DATE_RE.search(lower))
    has_viewing_word = bool(words & _TM_VIEWING_WORDS) or any(ph in lower for ph in _TM_VIEWING_PHRASES)
    if has_booking or (has_viewing_word and has_datetime):
        return ClassificationResult(
            intent=IntentType.VIEWING_REQUEST,
            confidence=0.92,
            reasoning="TEST_MODE: viewing booking or time-qualified viewing request",
        )

    # 4. Generic viewing interest (no specific time).
    if has_viewing_word:
        return ClassificationResult(
            intent=IntentType.VIEWING_REQUEST,
            confidence=0.88,
            reasoning="TEST_MODE: viewing interest keyword",
        )

    # 5. Listing reference in message text or active listing in session.
    if _TM_LISTING_REF_RE.search(text) or (
        context.session.listing_ref_code and context.listing is not None
    ):
        return ClassificationResult(
            intent=IntentType.LISTING_INQUIRY,
            confidence=0.88,
            reasoning="TEST_MODE: listing reference detected",
        )

    # 6. Buyer qualification signal.
    if words & _TM_QUALIFY_WORDS:
        return ClassificationResult(
            intent=IntentType.BUYER_QUALIFICATION,
            confidence=0.88,
            reasoning="TEST_MODE: qualification keyword",
        )

    # 7. Fallback — confidence below CONFIDENCE_THRESHOLD (0.65) routes to CLARIFICATION.
    return ClassificationResult(
        intent=IntentType.GENERAL_INQUIRY,
        confidence=0.30,
        reasoning="TEST_MODE: no keyword match — fallback",
    )
_LISTING_FALLBACK_MESSAGE = (
    "I have some details about this property but I'm having a little trouble pulling them "
    "together right now. Could you ask me a specific question and I'll do my best to help?"
)

_CLASSIFICATION_TOOL: dict[str, Any] = {
    "name": "classify_intent",
    "description": "Classify the intent of the most recent inbound message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": [e.value for e in IntentType], "description": "Primary intent category."},
            "confidence": {"type": "number", "description": "Confidence score 0.0–1.0."},
            "reasoning": {"type": "string", "description": "One sentence explaining the classification."},
        },
        "required": ["intent", "confidence", "reasoning"],
    },
}

_LISTING_RESPONSE_TOOL: dict[str, Any] = {
    "name": "listing_response",
    "description": "Generate a WhatsApp-friendly answer to a lead's question about a listing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "response_text": {"type": "string", "description": "Conversational reply. No markdown formatting."},
            "viewing_interest_detected": {"type": "boolean", "description": "True if the lead asks to view or visit the property."},
        },
        "required": ["response_text", "viewing_interest_detected"],
    },
}


def _get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _anthropic_client


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

async def classify_intent(context: ConversationContext) -> ClassificationResult:
    """Classify the intent of context.current_message.

    When ANTHROPIC_API_KEY is absent the deterministic TEST_MODE keyword
    classifier is used so local development produces visible state transitions
    without any external service dependency.
    """
    if not get_settings().anthropic_api_key:
        result = _test_mode_classify(context.current_message, context)
        logger.info(
            "TEST_MODE classifier used | lead=%s | intent=%s | confidence=%.2f",
            context.lead.id,
            result.intent,
            result.confidence,
        )
        return result

    prompt = _build_classification_prompt(context)
    try:
        return await asyncio.wait_for(_call_classification_api(prompt), timeout=_CLASSIFICATION_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("Intent classification timed out | lead=%s", context.lead.id)
        return ClassificationResult(intent=IntentType.GENERAL_INQUIRY, confidence=0.0, reasoning="Classification timed out — fallback.")
    except Exception:
        logger.exception("Intent classification failed | lead=%s", context.lead.id)
        return ClassificationResult(intent=IntentType.GENERAL_INQUIRY, confidence=0.0, reasoning="Classification error — fallback.")


async def _call_classification_api(prompt: str) -> ClassificationResult:
    settings = get_settings()
    response = await _get_anthropic_client().messages.create(
        model=settings.anthropic_model,
        max_tokens=256,
        tools=[_CLASSIFICATION_TOOL],
        tool_choice={"type": "tool", "name": "classify_intent"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "classify_intent":
            return _parse_classification_response(block.input)
    raise ValueError("No classify_intent block in classification response")


def _build_classification_prompt(context: ConversationContext) -> str:
    history = "\n".join(f"  [{i + 1}] {body}" for i, body in enumerate(context.recent_messages[-5:]))
    listing_line = ""
    if context.listing:
        listing_line = (
            f"\nListing context: {context.listing.title} "
            f"({context.listing.property_type}, {context.listing.transaction_type})\n"
        )
    return (
        "You are an intent classifier for a real estate sales assistant.\n"
        f"Lead state: {context.lead.state}\n"
        f"{listing_line}"
        f"Recent conversation (oldest to newest):\n{history}\n"
        f"Current message: {context.current_message}\n\n"
        "Classify the intent of the CURRENT MESSAGE using the classify_intent tool."
    )


def _parse_classification_response(tool_input: dict[str, Any]) -> ClassificationResult:
    raw_intent = tool_input.get("intent", IntentType.GENERAL_INQUIRY)
    try:
        intent = IntentType(raw_intent)
    except ValueError:
        intent = IntentType.GENERAL_INQUIRY
    confidence = max(0.0, min(1.0, float(tool_input.get("confidence", 0.0))))
    return ClassificationResult(intent=intent, confidence=confidence, reasoning=str(tool_input.get("reasoning", "")))


# ---------------------------------------------------------------------------
# Listing response generation
# ---------------------------------------------------------------------------

async def generate_listing_response(
    context: ConversationContext,
    market: MarketConfig,
) -> ListingResponseResult:
    """Generate a listing-aware AI response using only structured listing data."""
    prompt = _build_listing_prompt(context, market)
    try:
        return await asyncio.wait_for(_call_listing_api(prompt), timeout=_LISTING_RESPONSE_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("Listing response timed out | lead=%s", context.lead.id)
        return ListingResponseResult(response_text=_LISTING_FALLBACK_MESSAGE)
    except Exception:
        logger.exception("Listing response failed | lead=%s", context.lead.id)
        return ListingResponseResult(response_text=_LISTING_FALLBACK_MESSAGE)


async def _call_listing_api(prompt: str) -> ListingResponseResult:
    settings = get_settings()
    response = await _get_anthropic_client().messages.create(
        model=settings.anthropic_model,
        max_tokens=512,
        tools=[_LISTING_RESPONSE_TOOL],
        tool_choice={"type": "tool", "name": "listing_response"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "listing_response":
            return _parse_listing_response(block.input)
    raise ValueError("No listing_response block in response")


def _build_listing_prompt(context: ConversationContext, market: MarketConfig) -> str:
    listing = context.listing
    prop_label = _resolve_property_type_label(listing.property_type, market)
    price_str = _format_price(listing, market) or "not provided"
    floor_str = _format_area(listing.floor_area_sqm, market) or "not provided"
    land_str = _format_area(listing.land_area_sqm, market) or "not provided"
    history = "\n".join(f"  [{i + 1}] {body}" for i, body in enumerate(context.recent_messages[-5:]))
    facts = (
        f"Property type: {prop_label} for {listing.transaction_type.lower()}\n"
        f"Title: {listing.title}\n"
        f"Reference: {listing.reference_code}\n"
        f"Price: {price_str}\n"
        f"Location: {listing.location_area or 'not provided'}\n"
        f"Bedrooms: {listing.bedrooms if listing.bedrooms is not None else 'not provided'}\n"
        f"Bathrooms: {listing.bathrooms if listing.bathrooms is not None else 'not provided'}\n"
        f"Floor area: {floor_str}\n"
        f"Land area: {land_str}\n"
        f"Description: {listing.description or 'not provided'}\n"
        f"Features: {listing.features or 'not provided'}"
    )
    return (
        "You are a real estate assistant answering a lead's question about a specific property.\n"
        "Answer ONLY using the facts below. If a value says 'not provided', acknowledge honestly — do not invent details.\n"
        "Keep your response conversational and suitable for WhatsApp (no markdown formatting).\n\n"
        f"{facts}\n\n"
        f"Conversation so far:\n{history}\n\n"
        f"Lead's latest message: {context.current_message}\n\n"
        "Use the listing_response tool to reply. Set viewing_interest_detected to true only if "
        "the lead explicitly asks to view or visit the property."
    )


def _parse_listing_response(tool_input: dict[str, Any]) -> ListingResponseResult:
    response_text = str(tool_input.get("response_text", "")).strip()
    viewing_interest = bool(tool_input.get("viewing_interest_detected", False))
    if not response_text:
        response_text = _LISTING_FALLBACK_MESSAGE
    return ListingResponseResult(response_text=response_text, viewing_interest_detected=viewing_interest)


def _format_price(listing: Any, market: MarketConfig) -> str | None:
    sym, code = market.currency_symbol, market.currency_code
    if listing.transaction_type == TransactionType.RENTAL:
        if listing.price_per_month is not None:
            return f"{sym}{listing.price_per_month:,.0f} {code}/month"
        if listing.price is not None:
            return f"{sym}{listing.price:,.0f} {code}/month"
    elif listing.price is not None:
        return f"{sym}{listing.price:,.0f} {code}"
    return None


def _format_area(sqm: float | None, market: MarketConfig) -> str | None:
    if sqm is None:
        return None
    if market.area_unit == "sqft":
        return f"{sqm * 10.764:,.0f} sq ft"
    return f"{sqm:,.0f} sq m"


def _resolve_property_type_label(property_type: str, market: MarketConfig) -> str:
    return market.property_terminology.get(property_type, property_type.lower().replace("_", " "))
