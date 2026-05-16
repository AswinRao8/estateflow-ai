from fastapi import APIRouter
from app.models.base import APIResponse

router = APIRouter(prefix="/agents", tags=["Agents"])

# Phase 8 — Human Handoff
# Endpoints to implement:
#   GET  /agents                         — list agents and their active lead counts
#   POST /agents/{agent_id}/takeover     — agent takes control of a lead
#   POST /agents/{agent_id}/release      — agent releases lead back to AI
#   GET  /agents/{agent_id}/leads        — leads currently assigned to this agent


@router.get("", response_model=APIResponse, summary="List agents [Phase 8]")
def list_agents():
    return APIResponse(success=False, message="Not yet implemented — Phase 8")


@router.post("/{agent_id}/takeover", response_model=APIResponse, summary="Take over lead [Phase 8]")
def takeover_lead(agent_id: str):
    return APIResponse(success=False, message="Not yet implemented — Phase 8")


@router.post("/{agent_id}/release", response_model=APIResponse, summary="Release lead to AI [Phase 8]")
def release_lead(agent_id: str):
    return APIResponse(success=False, message="Not yet implemented — Phase 8")
