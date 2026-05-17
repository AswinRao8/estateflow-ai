from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ListingNotFoundError
from app.integrations.whatsapp.types import InboundMessage
from app.models.context import ClassificationResult, ConversationContext, WorkflowResult
from app.models.conversation import Message, MessageCreate
from app.models.enums import HandoffReason, IntentType, LeadState, MessageDirection, WorkflowType
from app.models.lead import Lead
from app.models.listing import Listing
from app.models.session import Session
from app.services import (
    conversation_service,
    lead_service,
    listing_service,
    notification_service,
    session_service,
)
from app.utils.listing_ref import extract_listing_ref_code
from app.utils.logging import get_logger
from app.utils.message import is_agent_request
from app.utils.response import sanitize_response
from app.workflows import (
    clarification_workflow,
    escalation_workflow,
    general_inquiry_workflow,
    listing_inquiry_workflow,
    out_of_scope_workflow,
    qualification_workflow,
    viewing_request_workflow,
)

logger = get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.65

_INTENT_TO_WORKFLOW: dict[IntentType, WorkflowType] = {
    IntentType.LISTING_INQUIRY: WorkflowType.LISTING_INQUIRY,
    IntentType.BUYER_QUALIFICATION: WorkflowType.QUALIFICATION,
    IntentType.VIEWING_REQUEST: WorkflowType.VIEWING_REQUEST,
    IntentType.FOLLOW_UP: WorkflowType.GENERAL_INQUIRY,
    IntentType.HUMAN_REQUESTED: WorkflowType.ESCALATION,
    IntentType.GENERAL_INQUIRY: WorkflowType.GENERAL_INQUIRY,
    IntentType.OUT_OF_SCOPE: WorkflowType.OUT_OF_SCOPE,
}


@dataclass
class InboundPipelineResult:
    lead: Lead
    session: Session
    message: Message
    is_human_active: bool
    workflow_type: WorkflowType | None = None


async def process_inbound_message(
    db: AsyncSession,
    *,
    message: InboundMessage,
) -> InboundPipelineResult:
    """Orchestrate the full inbound pipeline: lead → session → message → AI → response.

    Pipeline sections in order:
    1. Lead/session/message persistence
    2. Human-active gate (AI stays silent when a human agent owns the lead)
    3. Pre-LLM fast-path escalation (keyword detection, NEGOTIATION state)
    4. Context assembly
    5. Intent classification
    6. Deterministic routing
    7. Workflow dispatch
    8. Response send + outbound message persistence
    """
    listing_ref_code = extract_listing_ref_code(message.listing_ref_url)

    lead = await lead_service.get_or_create_lead(
        db,
        phone_number=message.phone_number,
        source_listing_ref_code=listing_ref_code,
    )

    session = await session_service.get_or_create_active_session(
        db,
        lead_id=lead.id,
        listing_ref_code=listing_ref_code,
    )

    stored_message = await conversation_service.save_message(
        db,
        data=MessageCreate(
            session_id=session.id,
            lead_id=lead.id,
            direction=MessageDirection.INBOUND,
            body=message.body,
            provider_message_id=message.message_id,
        ),
    )

    # --- Section 2: Human-active gate ---

    if lead.is_human_active:
        logger.info(
            "Message from %s held for human agent | lead=%s",
            message.phone_number,
            lead.id,
        )
        return InboundPipelineResult(
            lead=lead,
            session=session,
            message=stored_message,
            is_human_active=True,
        )

    # --- Section 3: Pre-LLM fast-path escalation ---

    if is_agent_request(message.body):
        logger.info("Agent-request keyword detected | lead=%s", lead.id)
        bare_context = ConversationContext(
            lead=lead, session=session,
            recent_messages=[], current_message=message.body,
        )
        workflow_result = await escalation_workflow.run(
            db, bare_context, reason=HandoffReason.USER_REQUESTED
        )
        await _send_and_persist(
            db, workflow_result, lead=lead, session=session,
            phone_number=message.phone_number,
        )
        return InboundPipelineResult(
            lead=lead, session=session, message=stored_message,
            is_human_active=True, workflow_type=WorkflowType.ESCALATION,
        )

    if LeadState(lead.state) == LeadState.NEGOTIATION:
        logger.info("Lead in NEGOTIATION — auto-escalating | lead=%s", lead.id)
        bare_context = ConversationContext(
            lead=lead, session=session,
            recent_messages=[], current_message=message.body,
        )
        workflow_result = await escalation_workflow.run(
            db, bare_context, reason=HandoffReason.NEGOTIATION
        )
        await _send_and_persist(
            db, workflow_result, lead=lead, session=session,
            phone_number=message.phone_number,
        )
        return InboundPipelineResult(
            lead=lead, session=session, message=stored_message,
            is_human_active=True, workflow_type=WorkflowType.ESCALATION,
        )

    # --- Section 4: Context assembly ---

    recent = await conversation_service.get_lead_recent_messages(
        db, lead_id=lead.id, limit=10
    )
    recent_bodies = [m.body for m in recent]

    listing: Listing | None = None
    if session.listing_ref_code:
        try:
            listing = await listing_service.get_listing_by_ref(
                db, reference_code=session.listing_ref_code
            )
        except ListingNotFoundError:
            logger.warning(
                "Listing ref %s not found | session=%s",
                session.listing_ref_code,
                session.id,
            )

    context = ConversationContext(
        lead=lead,
        session=session,
        recent_messages=recent_bodies,
        current_message=message.body,
        listing=listing,
    )

    # --- Section 5: Intent classification ---

    classification = await conversation_service.classify_intent(context)
    logger.info(
        "Intent classified | lead=%s | intent=%s | confidence=%.2f | reasoning=%s",
        lead.id,
        classification.intent,
        classification.confidence,
        classification.reasoning,
    )

    # --- Section 6: Deterministic routing ---

    workflow_type = _route(classification.intent, classification.confidence)

    # --- Section 7: Workflow dispatch ---

    workflow_result = await _dispatch(db, context, workflow_type, classification)

    # --- Section 8: Response send + persist ---

    listing_price = listing.price if listing else None
    await _send_and_persist(
        db, workflow_result, lead=lead, session=session,
        phone_number=message.phone_number, listing_price=listing_price,
    )

    logger.info(
        "Pipeline complete | lead=%s | session=%s | workflow=%s | state=%s",
        lead.id,
        session.id,
        workflow_type,
        lead.state,
    )

    return InboundPipelineResult(
        lead=lead,
        session=session,
        message=stored_message,
        is_human_active=workflow_result.new_lead_state == LeadState.HUMAN_ACTIVE,
        workflow_type=workflow_type,
    )


def _route(intent: IntentType, confidence: float) -> WorkflowType:
    if intent == IntentType.HUMAN_REQUESTED:
        return WorkflowType.ESCALATION
    if confidence < CONFIDENCE_THRESHOLD:
        return WorkflowType.CLARIFICATION
    return _INTENT_TO_WORKFLOW.get(intent, WorkflowType.GENERAL_INQUIRY)


async def _dispatch(
    db: AsyncSession,
    context: ConversationContext,
    workflow_type: WorkflowType,
    classification: ClassificationResult,
) -> WorkflowResult:
    if workflow_type == WorkflowType.CLARIFICATION:
        return await clarification_workflow.run(context)
    if workflow_type == WorkflowType.ESCALATION:
        reason = (
            HandoffReason.USER_REQUESTED
            if classification.intent == IntentType.HUMAN_REQUESTED
            else HandoffReason.LOW_AI_CONFIDENCE
        )
        return await escalation_workflow.run(db, context, reason=reason)
    if workflow_type == WorkflowType.OUT_OF_SCOPE:
        return await out_of_scope_workflow.run(context)
    if workflow_type == WorkflowType.LISTING_INQUIRY:
        return await listing_inquiry_workflow.run(db, context)
    if workflow_type == WorkflowType.QUALIFICATION:
        return await qualification_workflow.run(db, context)
    if workflow_type == WorkflowType.VIEWING_REQUEST:
        return await viewing_request_workflow.run(db, context)
    return await general_inquiry_workflow.run(context)


async def _send_and_persist(
    db: AsyncSession,
    result: WorkflowResult,
    *,
    lead: Lead,
    session: Session,
    phone_number: str,
    listing_price: float | None = None,
) -> None:
    if result.outbound_message is None:
        return

    body = sanitize_response(result.outbound_message, listing_price=listing_price)
    provider_id = await notification_service.send_whatsapp_text(phone_number, body)

    await conversation_service.save_message(
        db,
        data=MessageCreate(
            session_id=session.id,
            lead_id=lead.id,
            direction=MessageDirection.OUTBOUND,
            body=body,
            provider_message_id=provider_id,
        ),
    )
