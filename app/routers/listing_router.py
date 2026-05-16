from fastapi import APIRouter
from app.models.base import APIResponse

router = APIRouter(prefix="/listings", tags=["Listings"])

# Phase 1 — Data Layer / Phase 5 — Listing-Aware Responses
# Endpoints to implement:
#   GET  /listings               — list available listings with optional filters
#   GET  /listings/{listing_id}  — listing detail
#   POST /listings               — create listing (agent dashboard)
#   PUT  /listings/{listing_id}  — update listing
#   POST /listings/search        — structured search by type, price, location


@router.get("", response_model=APIResponse, summary="List listings [Phase 1]")
def list_listings():
    return APIResponse(success=False, message="Not yet implemented — Phase 1")


@router.get("/{listing_id}", response_model=APIResponse, summary="Get listing [Phase 1]")
def get_listing(listing_id: str):
    return APIResponse(success=False, message="Not yet implemented — Phase 1")
