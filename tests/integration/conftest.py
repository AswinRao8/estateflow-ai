import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import Base

# Domain models must be imported so Base.metadata knows about their tables.
import app.models.lead  # noqa: F401
import app.models.listing  # noqa: F401
import app.models.session  # noqa: F401
import app.models.conversation  # noqa: F401
import app.models.follow_up  # noqa: F401

TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:united8@localhost:5432/estateflow_test",
)

_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
_SessionFactory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def pytest_configure(config):
    # Mark all tests in this package as requiring a real DB.
    pass


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    try:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        pytest.skip(f"Integration DB unavailable: {exc}")
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Transactional session — rolls back after each test."""
    async with _engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()
