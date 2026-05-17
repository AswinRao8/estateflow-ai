import asyncio
import uuid
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.context import ClassificationResult, ConversationContext
from app.models.conversation import Message, MessageCreate
from app.models.enums import IntentType
from app.utils.logging import get_logger

logger = get_logger(__name__)

_anthropic_client: anthropic.AsyncAnthropic | None = None

_CLASSIFICATION_TOOL: dict[str, Any] = {
    "name": "classify_intent",
    "description": "Classify the intent of the most recent inbound message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": [e.value for e in IntentType],
                "description": "The primary intent category.",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score between 0.0 and 1.0.",
            },
            "reasoning": {
                "type": "string",
                "description": "One sentence explaining the classification.",
            },
        },
        "required": ["intent", "confidence", "reasoning"],
    },
}

_CLASSIFICATION_TIMEOUT = 8.0


def _get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(
            api_key=get_settings().anthropic_api_key
        )
    return _anthropic_client


async def save_message(db: AsyncSession, *, data: MessageCreate) -> Message:
    message = Message(**data.model_dump(), tenant_id=get_settings().default_tenant_id)
    db.add(message)
    await db.commit()
    return message


async def get_session_messages(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[Message]:
    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id, Message.tenant_id == tenant_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_lead_recent_messages(
    db: AsyncSession,
    *,
    lead_id: uuid.UUID,
    limit: int = 20,
) -> list[Message]:
    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(Message)
        .where(Message.lead_id == lead_id, Message.tenant_id == tenant_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def classify_intent(context: ConversationContext) -> ClassificationResult:
    """Classify the intent of context.current_message via Anthropic tool use.

    Uses forced tool use (tool_choice) to guarantee structured JSON output.
    Times out after _CLASSIFICATION_TIMEOUT seconds and falls back to
    GENERAL_INQUIRY with zero confidence so the router degrades gracefully.
    """
    prompt = _build_classification_prompt(context)
    try:
        return await asyncio.wait_for(
            _call_classification_api(prompt),
            timeout=_CLASSIFICATION_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Intent classification timed out | lead=%s", context.lead.id
        )
        return ClassificationResult(
            intent=IntentType.GENERAL_INQUIRY,
            confidence=0.0,
            reasoning="Classification timed out — fallback.",
        )
    except Exception:
        logger.exception(
            "Intent classification failed | lead=%s", context.lead.id
        )
        return ClassificationResult(
            intent=IntentType.GENERAL_INQUIRY,
            confidence=0.0,
            reasoning="Classification error — fallback.",
        )


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
    history = "\n".join(
        f"  [{i + 1}] {body}"
        for i, body in enumerate(context.recent_messages[-5:])
    )
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
    reasoning = str(tool_input.get("reasoning", ""))
    return ClassificationResult(intent=intent, confidence=confidence, reasoning=reasoning)
