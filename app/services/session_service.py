import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.session import Session


async def get_or_create_active_session(
    db: AsyncSession,
    *,
    lead_id: uuid.UUID,
    channel: str = "whatsapp",
    listing_ref_code: str | None = None,
) -> Session:
    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(Session).where(
            Session.tenant_id == tenant_id,
            Session.lead_id == lead_id,
            Session.is_active == True,
        )
    )
    session = result.scalar_one_or_none()
    if session is not None:
        return await touch_session(db, session=session)
    session = Session(
        tenant_id=tenant_id,
        lead_id=lead_id,
        channel=channel,
        listing_ref_code=listing_ref_code,
        last_activity_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()
    return session


async def get_session(
    db: AsyncSession, *, session_id: uuid.UUID
) -> Session | None:
    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def get_active_session(
    db: AsyncSession, *, lead_id: uuid.UUID
) -> Session | None:
    tenant_id = get_settings().default_tenant_id
    result = await db.execute(
        select(Session).where(
            Session.lead_id == lead_id,
            Session.tenant_id == tenant_id,
            Session.is_active == True,
        )
    )
    return result.scalar_one_or_none()


async def touch_session(db: AsyncSession, *, session: Session) -> Session:
    session.last_activity_at = datetime.now(timezone.utc)
    await db.commit()
    return session


async def deactivate_session(db: AsyncSession, *, session: Session) -> Session:
    session.is_active = False
    await db.commit()
    return session
