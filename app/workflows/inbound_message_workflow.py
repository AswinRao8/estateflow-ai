from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

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
    followup_service,
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
    property_matching_workflow,
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
    req_id: str = field(default="")


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
    req_id = uuid4().hex[:8]
    now = datetime.now(timezone.utc)

    logger.info(
        "[%s] PIPELINE START | phone=%s | msg=%.120r | listing_ref_url=%s",
        req_id,
        message.phone_number,
        message.body,
        message.listing_ref_url or "(none)",
    )

    # --- Section 1: Lead/session/message persistence ---

    listing_ref_code = extract_listing_ref_code(message.listing_ref_url)
    logger.info(
        "[%s] Listing ref extracted | ref_code=%s",
        req_id,
        listing_ref_code or "(none)",
    )

    lead = await lead_service.get_or_create_lead(
        db,
        phone_number=message.phone_number,
        source_listing_ref_code=listing_ref_code,
    )
    logger.info(
        "[%s] Lead resolved | lead=%s | state=%s | is_human_active=%s",
        req_id,
        lead.id,
        lead.state,
        lead.is_human_active,
    )

    session = await session_service.get_or_create_active_session(
        db,
        lead_id=lead.id,
        listing_ref_code=listing_ref_code,
    )
    logger.info(
        "[%s] Session resolved | session=%s | listing_ref=%s",
        req_id,
        session.id,
        session.listing_ref_code or "(none)",
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
    logger.info(
        "[%s] Inbound message persisted | msg_id=%s",
        req_id,
        stored_message.id,
    )

    # Cancel pending follow-ups — the lead has responded, so they are no longer stale.
    await followup_service.cancel_pending(db, lead_id=lead.id)
    logger.info("[%s] Pending follow-ups cancelled | lead=%s", req_id, lead.id)

    # Dispatch any overdue follow-ups for all leads (lightweight DB poll).
    dispatched = await followup_service.dispatch_due(db, now=now)
    if dispatched:
        logger.info("[%s] Dispatched %d overdue follow-up(s)", req_id, dispatched)

    # --- Section 2: Human-active gate ---

    if lead.is_human_active:
        logger.info(
            "[%s] PIPELINE END (held for human) | lead=%s | agent=%s",
            req_id,
            lead.id,
            lead.assigned_agent_id or "(unassigned)",
        )
        return InboundPipelineResult(
            lead=lead,
            session=session,
            message=stored_message,
            is_human_active=True,
            req_id=req_id,
        )

    # --- Section 3: Pre-LLM fast-path escalation ---

    if is_agent_request(message.body):
        logger.info("[%s] Fast-path: agent-request keyword detected | lead=%s", req_id, lead.id)
        bare_context = ConversationContext(
            lead=lead, session=session,
            recent_messages=[], current_message=message.body,
        )
        workflow_result = await escalation_workflow.run(
            db, bare_context, reason=HandoffReason.USER_REQUESTED
        )
        await _send_and_persist(
            db, workflow_result, lead=lead, session=session,
            phone_number=message.phone_number, req_id=req_id,
        )
        logger.info(
            "[%s] PIPELINE END (escalated:user_requested) | lead=%s",
            req_id, lead.id,
        )
        return InboundPipelineResult(
            lead=lead, session=session, message=stored_message,
            is_human_active=True, workflow_type=WorkflowType.ESCALATION, req_id=req_id,
        )

    if LeadState(lead.state) == LeadState.NEGOTIATION:
        logger.info("[%s] Fast-path: NEGOTIATION state — auto-escalating | lead=%s", req_id, lead.id)
        bare_context = ConversationContext(
            lead=lead, session=session,
            recent_messages=[], current_message=message.body,
        )
        workflow_result = await escalation_workflow.run(
            db, bare_context, reason=HandoffReason.NEGOTIATION
        )
        await _send_and_persist(
            db, workflow_result, lead=lead, session=session,
            phone_number=message.phone_number, req_id=req_id,
        )
        logger.info(
            "[%s] PIPELINE END (escalated:negotiation) | lead=%s",
            req_id, lead.id,
        )
        return InboundPipelineResult(
            lead=lead, session=session, message=stored_message,
            is_human_active=True, workflow_type=WorkflowType.ESCALATION, req_id=req_id,
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
            logger.info(
                "[%s] Listing resolved | ref=%s | price=%s",
                req_id,
                session.listing_ref_code,
                listing.price,
            )
        except ListingNotFoundError:
            logger.warning(
                "[%s] Listing ref not found | ref=%s | session=%s",
                req_id,
                session.listing_ref_code,
                session.id,
            )

    logger.info(
        "[%s] Context assembled | recent_msgs=%d | listing=%s",
        req_id,
        len(recent_bodies),
        session.listing_ref_code or "(none)",
    )

    context = ConversationContext(
        lead=lead,
        session=session,
        recent_messages=recent_bodies,
        current_message=message.body,
        listing=listing,
    )

    # --- Section 5: Intent classification ---

    logger.info("[%s] Classifying intent via LLM...", req_id)
    classification = await conversation_service.classify_intent(context)
    logger.info(
        "[%s] Intent classified | intent=%s | confidence=%.2f | reasoning=%s",
        req_id,
        classification.intent,
        classification.confidence,
        classification.reasoning,
    )

    # --- Section 6: Deterministic routing ---

    workflow_type = _route(classification.intent, classification.confidence)
    logger.info(
        "[%s] Routing decision | workflow=%s | lead_state=%s",
        req_id,
        workflow_type,
        lead.state,
    )

    # --- Section 7: Workflow dispatch ---

    workflow_result = await _dispatch(db, context, workflow_type, classification, req_id=req_id)
    logger.info(
        "[%s] Workflow complete | workflow=%s | new_state=%s | has_response=%s",
        req_id,
        workflow_result.workflow_type,
        workflow_result.new_lead_state,
        workflow_result.outbound_message is not None,
    )

    # Apply state transition signalled by the workflow (escalation handles HUMAN_ACTIVE itself).
    if workflow_result.new_lead_state is not None and workflow_result.new_lead_state != LeadState.HUMAN_ACTIVE:
        logger.info(
            "[%s] State transition | lead=%s | %s → %s",
            req_id, lead.id, lead.state, workflow_result.new_lead_state,
        )
        try:
            lead = await lead_service.advance_state(db, lead_id=lead.id, to_state=workflow_result.new_lead_state)
            logger.info(
                "[%s] State transition applied | lead=%s | new_state=%s",
                req_id, lead.id, lead.state,
            )
        except Exception:
            logger.exception(
                "[%s] State transition failed | lead=%s | to_state=%s",
                req_id, lead.id, workflow_result.new_lead_state,
            )

    # Schedule follow-ups based on workflow outcome.
    if workflow_result.new_lead_state == LeadState.POST_VIEWING:
        await followup_service.schedule_post_viewing(db, lead_id=lead.id, now=now)
        logger.info("[%s] Post-viewing follow-up scheduled | lead=%s", req_id, lead.id)
    if workflow_result.workflow_type == WorkflowType.MATCHING_PROPERTIES:
        await followup_service.schedule_no_response(db, lead_id=lead.id, now=now)
        logger.info("[%s] No-response follow-up scheduled | lead=%s", req_id, lead.id)

    # --- Section 8: Response send + persist ---

    listing_price = listing.price if listing else None
    await _send_and_persist(
        db, workflow_result, lead=lead, session=session,
        phone_number=message.phone_number, listing_price=listing_price, req_id=req_id,
    )

    is_human_active = workflow_result.new_lead_state == LeadState.HUMAN_ACTIVE
    logger.info(
        "[%s] PIPELINE COMPLETE | lead=%s | session=%s | workflow=%s | state=%s | is_human_active=%s",
        req_id,
        lead.id,
        session.id,
        workflow_type,
        lead.state,
        is_human_active,
    )

    return InboundPipelineResult(
        lead=lead,
        session=session,
        message=stored_message,
        is_human_active=is_human_active,
        workflow_type=workflow_type,
        req_id=req_id,
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
    *,
    req_id: str,
) -> WorkflowResult:
    # State-based override: leads already in MATCHING_PROPERTIES stay in the
    # matching workflow for qualification and general inquiry intents so that
    # re-stating or refining criteria re-runs the SQL match rather than
    # restarting the qualification flow.
    if (
        LeadState(context.lead.state) == LeadState.MATCHING_PROPERTIES
        and workflow_type in {WorkflowType.QUALIFICATION, WorkflowType.GENERAL_INQUIRY}
    ):
        logger.info(
            "[%s] State override: MATCHING_PROPERTIES → property_matching_workflow",
            req_id,
        )
        return await property_matching_workflow.run(db, context)

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
    req_id: str = "",
) -> None:
    if result.outbound_message is None:
        logger.info("[%s] No outbound message to send", req_id)
        return

    body = sanitize_response(result.outbound_message, listing_price=listing_price)
    logger.info(
        "[%s] Sending outbound message | phone=%s | len=%d | preview=%.80r",
        req_id, phone_number, len(body), body,
    )
    provider_id = await notification_service.send_whatsapp_text(phone_number, body)
    logger.info(
        "[%s] Outbound message sent | provider_id=%s",
        req_id, provider_id,
    )

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
    logger.info("[%s] Outbound message persisted | lead=%s", req_id, lead.id)
