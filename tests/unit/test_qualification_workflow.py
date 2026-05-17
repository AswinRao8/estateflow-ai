"""Unit tests for Phase 6 buyer qualification components.

Tests cover: _build_qualification_prompt, _parse_qualification_response,
run_qualification_turn fallback paths, and qualification_workflow.run()
branch logic (state advancement, data persistence, skip-when-no-data).

No Anthropic API calls or database access — all external calls are patched.
"""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import MarketConfig
from app.models.context import ConversationContext, QualificationResult
from app.models.enums import BuyerType, LeadState, WorkflowType
from app.services.qualification_service import (
    _build_qualification_prompt,
    _parse_qualification_response,
    run_qualification_turn,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _market(**overrides) -> MarketConfig:
    return MarketConfig(**overrides)


def _context(
    current_message: str = "I have a budget of around $500k",
    qualification_data: dict | None = None,
    state: str = LeadState.NEW_INQUIRY,
    listing=None,
    recent: list[str] | None = None,
) -> ConversationContext:
    lead = SimpleNamespace(id=uuid.uuid4(), state=state, qualification_data=qualification_data)
    session = SimpleNamespace(id=uuid.uuid4())
    return ConversationContext(
        lead=lead,
        session=session,
        recent_messages=recent or [],
        current_message=current_message,
        listing=listing,
    )


def _fake_listing(title: str = "Sea View Apartment", property_type: str = "APARTMENT"):
    return SimpleNamespace(title=title, property_type=property_type)


# ---------------------------------------------------------------------------
# _build_qualification_prompt
# ---------------------------------------------------------------------------

def test_prompt_includes_market_currency():
    ctx = _context()
    prompt = _build_qualification_prompt(ctx, _market(currency_symbol="AED", currency_code="AED"))
    assert "AED" in prompt


def test_prompt_shows_none_answered_when_no_qualification_data():
    ctx = _context(qualification_data=None)
    prompt = _build_qualification_prompt(ctx, _market())
    assert "None yet" in prompt


def test_prompt_shows_answered_fields():
    ctx = _context(qualification_data={"budget_min": 400000, "location": "Downtown"})
    prompt = _build_qualification_prompt(ctx, _market())
    assert "budget_min" in prompt
    assert "400000" in prompt
    assert "Downtown" in prompt


def test_prompt_includes_current_message():
    ctx = _context(current_message="I want a 3-bedroom villa near the beach")
    prompt = _build_qualification_prompt(ctx, _market())
    assert "3-bedroom villa near the beach" in prompt


def test_prompt_includes_listing_hint_when_listing_present():
    ctx = _context(listing=_fake_listing("Sea View Apartment", "APARTMENT"))
    prompt = _build_qualification_prompt(ctx, _market())
    assert "Sea View Apartment" in prompt
    assert "apartment" in prompt.lower()


def test_prompt_omits_listing_hint_when_no_listing():
    ctx = _context(listing=None)
    prompt = _build_qualification_prompt(ctx, _market())
    assert "contacted you via a specific listing" not in prompt


def test_prompt_limits_history_to_last_five_messages():
    messages = [f"msg_{i}" for i in range(8)]
    ctx = _context(recent=messages)
    prompt = _build_qualification_prompt(ctx, _market())
    for i in range(3, 8):
        assert f"msg_{i}" in prompt
    for i in range(3):
        assert f"msg_{i}" not in prompt


def test_prompt_instructs_one_question_at_a_time():
    ctx = _context()
    prompt = _build_qualification_prompt(ctx, _market())
    assert "one field only" in prompt.lower() or "one" in prompt.lower()


# ---------------------------------------------------------------------------
# _parse_qualification_response
# ---------------------------------------------------------------------------

def test_parse_extracts_budget_fields():
    result = _parse_qualification_response({
        "next_question": "Where would you like to live?",
        "extracted_budget_min": 300_000,
        "extracted_budget_max": 500_000,
        "all_key_fields_answered": False,
    })
    assert result.extracted_data["budget_min"] == 300_000
    assert result.extracted_data["budget_max"] == 500_000


def test_parse_extracts_location():
    result = _parse_qualification_response({
        "next_question": "What type of property?",
        "extracted_location": "Palm Jumeirah",
        "all_key_fields_answered": False,
    })
    assert result.extracted_data["location"] == "Palm Jumeirah"


def test_parse_extracts_all_fields():
    result = _parse_qualification_response({
        "next_question": "Anything else?",
        "extracted_budget_min": 200_000,
        "extracted_budget_max": 400_000,
        "extracted_location": "Marina",
        "extracted_property_type": "apartment",
        "extracted_bedrooms": 2,
        "extracted_timeline": "6 months",
        "extracted_urgency": "flexible",
        "all_key_fields_answered": False,
    })
    assert result.extracted_data["budget_min"] == 200_000
    assert result.extracted_data["location"] == "Marina"
    assert result.extracted_data["property_type"] == "apartment"
    assert result.extracted_data["bedrooms"] == 2
    assert result.extracted_data["timeline"] == "6 months"
    assert result.extracted_data["urgency"] == "flexible"


def test_parse_extracts_buyer_type():
    result = _parse_qualification_response({
        "next_question": "What's your budget?",
        "buyer_type": BuyerType.INVESTOR,
        "all_key_fields_answered": False,
    })
    assert result.buyer_type == BuyerType.INVESTOR


def test_parse_ignores_unknown_buyer_type():
    result = _parse_qualification_response({
        "next_question": "What's your budget?",
        "buyer_type": "UNKNOWN_TYPE",
        "all_key_fields_answered": False,
    })
    assert result.buyer_type is None


def test_parse_sets_qualification_complete_when_all_fields_answered():
    result = _parse_qualification_response({
        "next_question": "Any other preferences?",
        "all_key_fields_answered": True,
    })
    assert result.qualification_complete is True


def test_parse_empty_question_uses_fallback():
    result = _parse_qualification_response({"next_question": "", "all_key_fields_answered": False})
    assert result.next_question


def test_parse_omits_none_fields_from_extracted_data():
    result = _parse_qualification_response({
        "next_question": "Where?",
        "extracted_budget_min": None,
        "all_key_fields_answered": False,
    })
    assert "budget_min" not in result.extracted_data


def test_parse_empty_dict_returns_safe_defaults():
    result = _parse_qualification_response({})
    assert result.next_question
    assert result.extracted_data == {}
    assert result.buyer_type is None
    assert result.qualification_complete is False


# ---------------------------------------------------------------------------
# run_qualification_turn — fallback paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_qualification_turn_timeout_returns_fallback():
    ctx = _context()

    async def _raise_timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch("app.services.qualification_service.asyncio.wait_for", side_effect=_raise_timeout):
        result = await run_qualification_turn(ctx, _market())

    assert result.next_question
    assert result.extracted_data == {}
    assert result.qualification_complete is False


@pytest.mark.asyncio
async def test_run_qualification_turn_exception_returns_fallback():
    ctx = _context()

    with patch(
        "app.services.qualification_service._call_qualification_api",
        new_callable=AsyncMock,
        side_effect=RuntimeError("API error"),
    ):
        result = await run_qualification_turn(ctx, _market())

    assert result.next_question
    assert result.extracted_data == {}


# ---------------------------------------------------------------------------
# qualification_workflow.run() — state and persistence logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_advances_lead_from_new_inquiry_to_qualifying():
    from app.workflows import qualification_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.NEW_INQUIRY)
    ai_result = QualificationResult(next_question="What's your budget?", extracted_data={})

    with patch("app.workflows.qualification_workflow.qualification_service.run_qualification_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.qualification_workflow.lead_service.update_qualification", new_callable=AsyncMock), \
         patch("app.workflows.qualification_workflow.lead_service.advance_state", new_callable=AsyncMock) as mock_advance:
        result = await qualification_workflow.run(db, ctx)

    mock_advance.assert_awaited_once_with(db, lead_id=ctx.lead.id, to_state=LeadState.QUALIFYING)
    assert result.new_lead_state == LeadState.QUALIFYING


@pytest.mark.asyncio
async def test_workflow_advances_lead_from_context_identified_to_qualifying():
    from app.workflows import qualification_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.CONTEXT_IDENTIFIED)
    ai_result = QualificationResult(next_question="What's your budget?", extracted_data={})

    with patch("app.workflows.qualification_workflow.qualification_service.run_qualification_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.qualification_workflow.lead_service.update_qualification", new_callable=AsyncMock), \
         patch("app.workflows.qualification_workflow.lead_service.advance_state", new_callable=AsyncMock) as mock_advance:
        result = await qualification_workflow.run(db, ctx)

    mock_advance.assert_awaited_once_with(db, lead_id=ctx.lead.id, to_state=LeadState.QUALIFYING)
    assert result.new_lead_state == LeadState.QUALIFYING


@pytest.mark.asyncio
async def test_workflow_does_not_advance_state_when_already_qualifying():
    from app.workflows import qualification_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.QUALIFYING)
    ai_result = QualificationResult(next_question="What's your timeline?", extracted_data={})

    with patch("app.workflows.qualification_workflow.qualification_service.run_qualification_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.qualification_workflow.lead_service.update_qualification", new_callable=AsyncMock), \
         patch("app.workflows.qualification_workflow.lead_service.advance_state", new_callable=AsyncMock) as mock_advance:
        result = await qualification_workflow.run(db, ctx)

    mock_advance.assert_not_called()
    assert result.new_lead_state is None


@pytest.mark.asyncio
async def test_workflow_persists_extracted_data_and_buyer_type():
    from app.workflows import qualification_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.QUALIFYING)
    ai_result = QualificationResult(
        next_question="What's your timeline?",
        extracted_data={"budget_min": 400_000, "location": "Downtown"},
        buyer_type=BuyerType.RESIDENTIAL,
    )

    with patch("app.workflows.qualification_workflow.qualification_service.run_qualification_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.qualification_workflow.lead_service.update_qualification", new_callable=AsyncMock) as mock_update, \
         patch("app.workflows.qualification_workflow.lead_service.advance_state", new_callable=AsyncMock):
        await qualification_workflow.run(db, ctx)

    mock_update.assert_awaited_once()
    update_arg = mock_update.call_args[1]["update"]
    assert update_arg.qualification_data == {"budget_min": 400_000, "location": "Downtown"}
    assert update_arg.buyer_type == BuyerType.RESIDENTIAL


@pytest.mark.asyncio
async def test_workflow_skips_update_when_no_extracted_data_and_no_buyer_type():
    from app.workflows import qualification_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.QUALIFYING)
    ai_result = QualificationResult(next_question="Where do you want to live?", extracted_data={})

    with patch("app.workflows.qualification_workflow.qualification_service.run_qualification_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.qualification_workflow.lead_service.update_qualification", new_callable=AsyncMock) as mock_update, \
         patch("app.workflows.qualification_workflow.lead_service.advance_state", new_callable=AsyncMock):
        await qualification_workflow.run(db, ctx)

    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_workflow_returns_correct_workflow_type_and_question():
    from app.workflows import qualification_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.QUALIFYING)
    ai_result = QualificationResult(next_question="What's your budget?", extracted_data={})

    with patch("app.workflows.qualification_workflow.qualification_service.run_qualification_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.qualification_workflow.lead_service.update_qualification", new_callable=AsyncMock), \
         patch("app.workflows.qualification_workflow.lead_service.advance_state", new_callable=AsyncMock):
        result = await qualification_workflow.run(db, ctx)

    assert result.workflow_type == WorkflowType.QUALIFICATION
    assert result.outbound_message == "What's your budget?"


@pytest.mark.asyncio
async def test_workflow_tolerates_advance_state_failure():
    from app.workflows import qualification_workflow
    from app.exceptions import InvalidStateTransitionError

    db = AsyncMock()
    ctx = _context(state=LeadState.NEW_INQUIRY)
    ai_result = QualificationResult(next_question="What's your budget?", extracted_data={})

    with patch("app.workflows.qualification_workflow.qualification_service.run_qualification_turn", new_callable=AsyncMock, return_value=ai_result), \
         patch("app.workflows.qualification_workflow.lead_service.update_qualification", new_callable=AsyncMock), \
         patch("app.workflows.qualification_workflow.lead_service.advance_state", new_callable=AsyncMock, side_effect=InvalidStateTransitionError("NEW_INQUIRY", "QUALIFYING")):
        result = await qualification_workflow.run(db, ctx)

    # Pipeline must continue even if state advance fails
    assert result.outbound_message == "What's your budget?"
    assert result.workflow_type == WorkflowType.QUALIFICATION
    assert result.new_lead_state is None


@pytest.mark.asyncio
async def test_workflow_passes_market_config_to_qualification_service():
    from app.workflows import qualification_workflow

    db = AsyncMock()
    ctx = _context(state=LeadState.QUALIFYING)
    ai_result = QualificationResult(next_question="What area?", extracted_data={})

    with patch("app.workflows.qualification_workflow.qualification_service.run_qualification_turn", new_callable=AsyncMock, return_value=ai_result) as mock_fn, \
         patch("app.workflows.qualification_workflow.lead_service.update_qualification", new_callable=AsyncMock), \
         patch("app.workflows.qualification_workflow.lead_service.advance_state", new_callable=AsyncMock):
        await qualification_workflow.run(db, ctx)

    call_args = mock_fn.call_args
    assert call_args[0][0] is ctx
    assert isinstance(call_args[0][1], MarketConfig)
