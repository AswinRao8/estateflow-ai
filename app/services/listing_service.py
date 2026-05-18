import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.exceptions import ListingNotFoundError
from app.models.context import BuyerProfile
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


async def match_listings(
    db: AsyncSession,
    *,
    profile: BuyerProfile,
    limit: int = 5,
) -> list[Listing]:
    """Return available listings that satisfy the buyer's stated criteria.

    SQL is the sole arbiter of eligibility. All populated profile fields are
    applied as AND-ed WHERE clauses. Location matching uses ILIKE for fuzzy
    geographic lookup — this is a temporary MVP approximation, not canonical
    location intelligence. Results are ranked by price proximity to the buyer's
    budget midpoint when both bounds are known; by recency otherwise.
    The result set is always bounded.
    """
    tenant_id = get_settings().default_tenant_id

    filters = [
        Listing.tenant_id == tenant_id,
        Listing.status == PropertyStatus.AVAILABLE,
    ]

    if profile.property_type:
        filters.append(func.lower(Listing.property_type) == profile.property_type.lower())

    if profile.budget_min is not None:
        filters.append(Listing.price >= profile.budget_min)

    if profile.budget_max is not None:
        filters.append(Listing.price <= profile.budget_max)

    if profile.location:
        filters.append(Listing.location_area.ilike(f"%{profile.location}%"))

    if profile.bedrooms is not None:
        filters.append(Listing.bedrooms >= profile.bedrooms)

    if profile.budget_min is not None and profile.budget_max is not None:
        midpoint = (profile.budget_min + profile.budget_max) / 2.0
        order_by = func.abs(Listing.price - midpoint)
    else:
        order_by = Listing.created_at.desc()

    result = await db.execute(
        select(Listing).where(*filters).order_by(order_by).limit(limit)
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
