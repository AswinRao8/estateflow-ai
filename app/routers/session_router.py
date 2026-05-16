from fastapi import APIRouter
from app.models.base import APIResponse

router = APIRouter(prefix="/sessions", tags=["Sessions"])

# Phase 3 — Session and Lead Management
# Endpoints to implement:
#   GET /sessions/{session_id}  — inspect session state for debugging
#
# Note: sessions are created internally by the WhatsApp inbound handler,
# not through this API. This router exists for agent dashboard inspection only.


@router.get("/{session_id}", response_model=APIResponse, summary="Get session [Phase 3]")
def get_session(session_id: str):
    return APIResponse(success=False, message="Not yet implemented — Phase 3")
