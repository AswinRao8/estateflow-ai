import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.dependencies import DbSessionDep
from app.exceptions import LeadNotFoundError
from app.models.base import APIResponse
from app.models.conversation import MessageRead
from app.models.enums import BuyerType, LeadState
from app.models.follow_up import FollowUpRead
from app.models.lead import LeadRead
from app.services import conversation_service, followup_service, lead_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/leads", tags=["Leads"])


class LeadDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone_number: str
    state: LeadState
    buyer_type: BuyerType | None = None
    qualification_data: dict | None = None
    source_listing_ref_code: str | None = None
    is_human_active: bool
    assigned_agent_id: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageRead]
    follow_ups: list[FollowUpRead]


@router.get("", response_model=APIResponse[list[LeadRead]])
async def list_leads(
    db: DbSessionDep,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> APIResponse[list[LeadRead]]:
    leads = await lead_service.list_leads(db, limit=limit, offset=offset)
    logger.info("GET /leads | count=%d", len(leads))
    for lead in leads:
        logger.debug("  lead=%s | phone=%s | state=%s", lead.id, lead.phone_number, lead.state)
    return APIResponse(data=[LeadRead.model_validate(lead) for lead in leads])


@router.get("/{lead_id}", response_model=APIResponse[LeadDetailRead])
async def get_lead(
    lead_id: uuid.UUID,
    db: DbSessionDep,
) -> APIResponse[LeadDetailRead]:
    try:
        lead = await lead_service.get_lead(db, lead_id=lead_id)
    except LeadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    logger.info("GET /leads/%s | state=%s", lead_id, lead.state)

    messages = await conversation_service.get_lead_recent_messages(
        db, lead_id=lead.id, limit=200
    )
    follow_ups = await followup_service.list_for_lead(db, lead_id=lead.id)

    detail = LeadDetailRead(
        id=lead.id,
        phone_number=lead.phone_number,
        state=LeadState(lead.state),
        buyer_type=BuyerType(lead.buyer_type) if lead.buyer_type else None,
        qualification_data=lead.qualification_data,
        source_listing_ref_code=lead.source_listing_ref_code,
        is_human_active=lead.is_human_active,
        assigned_agent_id=lead.assigned_agent_id,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        messages=[MessageRead.model_validate(m) for m in messages],
        follow_ups=[FollowUpRead.model_validate(f) for f in follow_ups],
    )
    return APIResponse(data=detail)
