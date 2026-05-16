from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import DateTime, func, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings

_settings = get_settings()

# Single engine instance for the process lifetime.
# pool_pre_ping re-validates connections before handing them out — prevents
# silent failures from stale pool connections after DB restarts.
engine = create_async_engine(
    _settings.database_url,
    echo=_settings.debug,
    pool_pre_ping=True,
)

# expire_on_commit=False: prevents SQLAlchemy from expiring attributes after commit,
# which would trigger lazy-load errors on already-committed objects in async context.
SessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models.

    All domain models (Lead, Listing, Session, etc.) inherit from this.
    Every domain model must also declare a tenant_id column — this is a
    convention enforced by code review, not by the base class itself,
    because not all models require tenant isolation (e.g. internal lookup tables).
    """
    pass


class TimestampMixin:
    """Adds created_at / updated_at to any ORM model.

    Use on every domain model — these fields are always needed and always
    server-generated. Do not set them manually in application code.
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


async def check_database_connection() -> bool:
    """Attempts a lightweight DB ping. Returns True if reachable, False otherwise.

    Used by the readiness endpoint. Does not raise — callers handle the bool.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a transactional database session.

    The session is NOT auto-committed. Services must call session.commit()
    explicitly when a write operation completes. The dependency handles
    rollback on unhandled exceptions and always closes the session.

    Usage in a route or service:
        async def my_handler(db: DbSessionDep): ...
    """
    session = SessionFactory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
