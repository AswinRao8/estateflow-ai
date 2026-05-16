from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.whatsapp.types import InboundMessage
from app.models.conversation import Message, MessageCreate
from app.models.enums import MessageDirection
from app.models.lead import Lead
from app.models.session import Session
from app.services import conversation_service, lead_service, session_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class InboundPipelineResult:
    lead: Lead
    session: Session
    message: Message
    is_human_active: bool


async def process_inbound_message(
    db: AsyncSession,
    *,
    message: InboundMessage,
    tenant_id: str,
) -> InboundPipelineResult:
    """Orchestrate the core inbound pipeline: lead → session → message persistence.

    Enforces the human-active check before any AI path is entered.
    Phase 4 adds intent classification and workflow routing after this point.
    """
    lead = await lead_service.get_or_create_lead(
        db,
        tenant_id=tenant_id,
        phone_number=message.phone_number,
        source_listing_ref=message.listing_ref,
    )

    session = await session_service.get_or_create_active_session(
        db,
        tenant_id=tenant_id,
        lead_id=lead.id,
        listing_ref=message.listing_ref,
    )

    stored_message = await conversation_service.save_message(
        db,
        data=MessageCreate(
            tenant_id=tenant_id,
            session_id=session.id,
            lead_id=lead.id,
            direction=MessageDirection.INBOUND,
            body=message.body,
            provider_message_id=message.message_id,
        ),
    )

    if lead.is_human_active:
        logger.info(
            "Lead %s is human-active — message routed to agent queue | session=%s",
            lead.id,
            session.id,
        )
        return InboundPipelineResult(
            lead=lead,
            session=session,
            message=stored_message,
            is_human_active=True,
        )

    logger.info(
        "Inbound processed | lead=%s | session=%s | state=%s | phone=%s",
        lead.id,
        session.id,
        lead.state,
        message.phone_number,
    )

    # Phase 4: intent classification and routing inserted here.
    return InboundPipelineResult(
        lead=lead,
        session=session,
        message=stored_message,
        is_human_active=False,
    )
