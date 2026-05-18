import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.dependencies import DbSessionDep
from app.exceptions import InvalidStateTransitionError, LeadNotFoundError
from app.models.base import APIResponse
from app.models.enums import HandoffReason, LeadState
from app.models.handoff import HandoffBriefing
from app.models.lead import LeadRead
from app.services import handoff_service, lead_service

router = APIRouter(prefix="/agents", tags=["Agents"])


class TakeoverRequest(BaseModel):
    lead_id: uuid.UUID
    session_id: uuid.UUID | None = None


class ReleaseRequest(BaseModel):
    lead_id: uuid.UUID
    to_state: LeadState


@router.post(
    "/{agent_id}/takeover",
    response_model=APIResponse[HandoffBriefing],
    summary="Agent takes control of a lead",
)
async def takeover_lead(
    agent_id: str,
    body: TakeoverRequest,
    db: DbSessionDep,
) -> APIResponse[HandoffBriefing]:
    """Claim a lead and return its handoff briefing.

    If the lead was already escalated by the AI (HUMAN_ACTIVE), only the
    assigned agent is updated. If not yet active, the full state transition
    is performed. The briefing is assembled after the claim is recorded.
    """
    try:
        await lead_service.claim_lead(db, lead_id=body.lead_id, agent_id=agent_id)
    except LeadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidStateTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    briefing = await handoff_service.prepare(
        db,
        lead_id=body.lead_id,
        session_id=body.session_id,
        reason=HandoffReason.AGENT_INITIATED,
    )
    return APIResponse(data=briefing)


@router.post(
    "/{agent_id}/release",
    response_model=APIResponse[LeadRead],
    summary="Agent releases lead back to AI",
)
async def release_lead(
    agent_id: str,
    body: ReleaseRequest,
    db: DbSessionDep,
) -> APIResponse[LeadRead]:
    """Release a human-active lead and return AI control.

    to_state must be a valid target from HUMAN_ACTIVE per the lead state
    machine. The AI pipeline resumes processing the lead's next inbound
    message once is_human_active is cleared.
    """
    try:
        lead = await lead_service.release_human(
            db, lead_id=body.lead_id, to_state=body.to_state
        )
    except LeadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidStateTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return APIResponse(data=LeadRead.model_validate(lead))
