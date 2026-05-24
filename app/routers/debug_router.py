"""Development-only diagnostic endpoints.

Mounted ONLY when ENVIRONMENT=development. Each endpoint bypasses the ORM
entirely and queries PostgreSQL via raw SQL so there is no identity-map,
session-cache, or serialisation layer between the response and the actual DB row.

Use GET /debug/lead/{lead_id} to verify what state the DB actually holds for a
specific lead and compare it with what the ORM and API layers return.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.database import engine
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/debug", tags=["Debug (dev only)"])


@router.get("/lead/{lead_id}", summary="Raw DB row for a lead — bypasses ORM entirely")
async def debug_lead(lead_id: uuid.UUID) -> dict:
    """Return the raw PostgreSQL row for a lead, reading directly via asyncpg.

    This endpoint uses a fresh connection from the engine pool and executes
    plain SQL — no SQLAlchemy ORM, no identity map, no Pydantic coercion.
    The `state` value you see here is the literal string stored in the DB column.
    """
    sql = text(
        "SELECT id, phone_number, state, is_human_active, updated_at "
        "FROM leads WHERE id = :lead_id"
    )
    async with engine.connect() as conn:
        result = await conn.execute(sql, {"lead_id": str(lead_id)})
        row = result.mappings().fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")

    db_state = row["state"]
    logger.info(
        "DEBUG /debug/lead/%s | db_state=%r | updated_at=%s",
        lead_id, db_state, row["updated_at"],
    )
    return {
        "source": "raw_sql_no_orm",
        "id": str(row["id"]),
        "phone_number": row["phone_number"],
        "state": db_state,
        "is_human_active": row["is_human_active"],
        "updated_at": row["updated_at"].isoformat() if isinstance(row["updated_at"], datetime) else str(row["updated_at"]),
        "note": "state is the literal string from the DB column — no enum coercion",
    }
