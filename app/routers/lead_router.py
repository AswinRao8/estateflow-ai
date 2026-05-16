from fastapi import APIRouter
from app.models.base import APIResponse

router = APIRouter(prefix="/leads", tags=["Leads"])

# Phase 3 — Session and Lead Management
# Endpoints to implement:
#   GET  /leads                  — list active leads with state and last activity
#   GET  /leads/{lead_id}        — lead detail: conversation, buyer profile, listing interests
#   PUT  /leads/{lead_id}/state  — advance or update lifecycle state


@router.get("", response_model=APIResponse, summary="List leads [Phase 3]")
def list_leads():
    return APIResponse(success=False, message="Not yet implemented — Phase 3")


@router.get("/{lead_id}", response_model=APIResponse, summary="Get lead detail [Phase 3]")
def get_lead(lead_id: str):
    return APIResponse(success=False, message="Not yet implemented — Phase 3")
