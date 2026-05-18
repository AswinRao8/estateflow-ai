import uuid

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import DbSessionDep
from app.exceptions import ListingNotFoundError
from app.models.base import APIResponse
from app.models.listing import ListingCreate, ListingRead, ListingStatusUpdate, ListingUpdate
from app.services import listing_service

router = APIRouter(prefix="/listings", tags=["Listings"])


@router.get("", response_model=APIResponse[list[ListingRead]])
async def list_listings(
    db: DbSessionDep,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> APIResponse[list[ListingRead]]:
    listings = await listing_service.list_all(db, limit=limit, offset=offset)
    return APIResponse(data=[ListingRead.model_validate(l) for l in listings])


@router.get("/{listing_id}", response_model=APIResponse[ListingRead])
async def get_listing(
    listing_id: uuid.UUID,
    db: DbSessionDep,
) -> APIResponse[ListingRead]:
    try:
        listing = await listing_service.get_listing(db, listing_id=listing_id)
    except ListingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return APIResponse(data=ListingRead.model_validate(listing))


@router.post("", response_model=APIResponse[ListingRead], status_code=201)
async def create_listing(
    body: ListingCreate,
    db: DbSessionDep,
) -> APIResponse[ListingRead]:
    listing = await listing_service.create_listing(db, data=body)
    return APIResponse(data=ListingRead.model_validate(listing))


@router.put("/{listing_id}", response_model=APIResponse[ListingRead])
async def update_listing(
    listing_id: uuid.UUID,
    body: ListingUpdate,
    db: DbSessionDep,
) -> APIResponse[ListingRead]:
    try:
        listing = await listing_service.update_listing(db, listing_id=listing_id, data=body)
    except ListingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return APIResponse(data=ListingRead.model_validate(listing))


@router.patch("/{listing_id}/status", response_model=APIResponse[ListingRead])
async def update_listing_status(
    listing_id: uuid.UUID,
    body: ListingStatusUpdate,
    db: DbSessionDep,
) -> APIResponse[ListingRead]:
    try:
        listing = await listing_service.update_listing_status(
            db, listing_id=listing_id, update=body
        )
    except ListingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return APIResponse(data=ListingRead.model_validate(listing))
