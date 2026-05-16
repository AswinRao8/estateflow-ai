import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message, MessageCreate
from app.models.enums import IntentType


async def save_message(db: AsyncSession, *, data: MessageCreate) -> Message:
    message = Message(**data.model_dump())
    db.add(message)
    await db.commit()
    return message


async def get_session_messages(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id, Message.tenant_id == tenant_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_lead_recent_messages(
    db: AsyncSession,
    *,
    lead_id: uuid.UUID,
    tenant_id: str,
    limit: int = 20,
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.lead_id == lead_id, Message.tenant_id == tenant_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return rows
