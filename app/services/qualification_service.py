"""Buyer qualification AI turns.

Extracts qualification field values from a single conversation turn and selects
the next question to ask. Merging the extracted delta into the lead record is
the caller's responsibility (qualification_workflow).
"""
import asyncio
from typing import Any

import anthropic

from app.config import MarketConfig, get_settings
from app.models.context import ConversationContext, QualificationResult
from app.models.enums import BuyerType
from app.utils.logging import get_logger

logger = get_logger(__name__)

_anthropic_client: anthropic.AsyncAnthropic | None = None
_QUALIFICATION_TIMEOUT = 10.0
_QUALIFICATION_FALLBACK_QUESTION = (
    "Could you tell me a bit more about what you're looking for — "
    "your budget, preferred location, and property type?"
)

_QUALIFICATION_TOOL: dict[str, Any] = {
    "name": "qualification_turn",
    "description": "Extract buyer qualification data from the current message and select the next question to ask.",
    "input_schema": {
        "type": "object",
        "properties": {
            "next_question": {"type": "string", "description": "The single most important unanswered qualification field to ask about next."},
            "extracted_budget_min": {"type": "number", "description": "Minimum budget extracted (numeric, market currency). Omit if not mentioned."},
            "extracted_budget_max": {"type": "number", "description": "Maximum budget extracted (numeric, market currency). Omit if not mentioned."},
            "extracted_location": {"type": "string", "description": "Location or area preference extracted. Omit if not mentioned."},
            "extracted_property_type": {"type": "string", "description": "Property type preference (e.g. villa, apartment). Omit if not mentioned."},
            "extracted_bedrooms": {"type": "number", "description": "Preferred bedroom count. Omit if not mentioned."},
            "extracted_timeline": {"type": "string", "description": "Purchase or move-in timeline (e.g. 'within 3 months'). Omit if not mentioned."},
            "extracted_urgency": {"type": "string", "description": "Urgency signal (e.g. 'urgent', 'just browsing'). Omit if not mentioned."},
            "buyer_type": {"type": "string", "enum": [e.value for e in BuyerType], "description": "Inferred buyer type if clearly determinable. Omit otherwise."},
            "all_key_fields_answered": {"type": "boolean", "description": "True when budget, location, property type, and timeline are all known."},
        },
        "required": ["next_question", "all_key_fields_answered"],
    },
}


def _get_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _anthropic_client


async def run_qualification_turn(
    context: ConversationContext,
    market: MarketConfig,
) -> QualificationResult:
    """Run one qualification turn: extract new answers and select the next question."""
    prompt = _build_qualification_prompt(context, market)
    try:
        return await asyncio.wait_for(_call_qualification_api(prompt), timeout=_QUALIFICATION_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("Qualification turn timed out | lead=%s", context.lead.id)
        return QualificationResult(next_question=_QUALIFICATION_FALLBACK_QUESTION, extracted_data={})
    except Exception:
        logger.exception("Qualification turn failed | lead=%s", context.lead.id)
        return QualificationResult(next_question=_QUALIFICATION_FALLBACK_QUESTION, extracted_data={})


async def _call_qualification_api(prompt: str) -> QualificationResult:
    settings = get_settings()
    response = await _get_client().messages.create(
        model=settings.anthropic_model,
        max_tokens=512,
        tools=[_QUALIFICATION_TOOL],
        tool_choice={"type": "tool", "name": "qualification_turn"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "qualification_turn":
            return _parse_qualification_response(block.input)
    raise ValueError("No qualification_turn block in response")


def _build_qualification_prompt(context: ConversationContext, market: MarketConfig) -> str:
    existing = context.lead.qualification_data or {}
    answered = "\n".join(f"  {k}: {v}" for k, v in existing.items()) if existing else "  None yet."
    listing_hint = ""
    if context.listing:
        listing_hint = (
            f"\nThe lead contacted you via a specific listing: {context.listing.title} "
            f"({context.listing.property_type.lower()}). "
            "Assume they are interested in this property type. "
            "Prioritise confirming budget and timeline.\n"
        )
    history = "\n".join(f"  [{i+1}] {msg}" for i, msg in enumerate(context.recent_messages[-5:]))
    currency = f"{market.currency_symbol} ({market.currency_code})"
    return (
        "You are a buyer qualification assistant for a real estate agency.\n"
        f"Market currency: {currency}\n"
        f"{listing_hint}"
        f"Qualification fields already answered:\n{answered}\n\n"
        f"Conversation so far:\n{history}\n"
        f"Lead's latest message: {context.current_message}\n\n"
        "Instructions:\n"
        "1. Extract any qualification answers present in the lead's latest message.\n"
        "2. Select the single most important UNANSWERED field to ask about next.\n"
        "   Priority: budget → location → property type → bedrooms → timeline → urgency.\n"
        "   Skip any fields already answered.\n"
        "3. Keep the question conversational, friendly, and concise — one field only.\n\n"
        "Use the qualification_turn tool to respond."
    )


def _parse_qualification_response(tool_input: dict[str, Any]) -> QualificationResult:
    field_map = {
        "extracted_budget_min": "budget_min",
        "extracted_budget_max": "budget_max",
        "extracted_location": "location",
        "extracted_property_type": "property_type",
        "extracted_bedrooms": "bedrooms",
        "extracted_timeline": "timeline",
        "extracted_urgency": "urgency",
    }
    extracted = {field: tool_input[key] for key, field in field_map.items() if tool_input.get(key) is not None}
    buyer_type = None
    if raw := tool_input.get("buyer_type"):
        try:
            buyer_type = BuyerType(raw)
        except ValueError:
            pass
    next_q = str(tool_input.get("next_question", "")).strip() or _QUALIFICATION_FALLBACK_QUESTION
    return QualificationResult(
        next_question=next_q,
        extracted_data=extracted,
        buyer_type=buyer_type,
        qualification_complete=bool(tool_input.get("all_key_fields_answered", False)),
    )
