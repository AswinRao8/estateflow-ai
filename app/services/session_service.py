import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session, SessionCreate


async def get_or_create_active_session(
    db: AsyncSession,
    *,
    tenant_id: str,
    lead_id: uuid.UUID,
    channel: str = "whatsapp",
    listing_ref: str | None = None,
) -> Session:
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
        listing_ref=listing_ref,
        last_activity_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()
    return session


async def get_session(
    db: AsyncSession, *, session_id: uuid.UUID, tenant_id: str
) -> Session | None:
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def get_active_session(
    db: AsyncSession, *, lead_id: uuid.UUID, tenant_id: str
) -> Session | None:
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
