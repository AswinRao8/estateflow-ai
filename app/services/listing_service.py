import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.exceptions import ListingNotFoundError
from app.models.enums import PropertyStatus
from app.models.listing import Listing, ListingCreate, ListingStatusUpdate


async def get_listing(db: AsyncSession, *, listing_id: uuid.UUID) -> Listing:
    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id, Listing.tenant_id == tenant_id)
    )
    listing = result.scalar_one_or_none()
    if listing is None:
        raise ListingNotFoundError(str(listing_id))
    return listing


async def get_listing_by_ref(db: AsyncSession, *, reference_code: str) -> Listing:
    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(Listing).where(
            Listing.reference_code == reference_code, Listing.tenant_id == tenant_id
        )
    )
    listing = result.scalar_one_or_none()
    if listing is None:
        raise ListingNotFoundError(reference_code)
    return listing


async def list_available(
    db: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[Listing]:
    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(Listing)
        .where(Listing.tenant_id == tenant_id, Listing.status == PropertyStatus.AVAILABLE)
        .order_by(Listing.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def create_listing(db: AsyncSession, *, data: ListingCreate) -> Listing:
    listing = Listing(**data.model_dump(), tenant_id=get_settings().default_tenant_id)
    db.add(listing)
    await db.commit()
    return listing


async def update_listing_status(
    db: AsyncSession,
    *,
    listing_id: uuid.UUID,
    update: ListingStatusUpdate,
) -> Listing:
    listing = await get_listing(db, listing_id=listing_id)
    listing.status = update.status
    await db.commit()
    return listing
