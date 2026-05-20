"""Fixtures for the smoke test suite.

Two HTTP client fixtures:
- http_client  — backed by the real database, no rollback; for read-only tests.
- rw_client    — backed by the real database with savepoint rollback; for write tests.
                 Yields (AsyncClient, AsyncSession) so tests can insert fixtures
                 directly into the same connection that the HTTP layer uses.

Both fixtures override get_db_session on the shared session-scoped app so that
every request in a test hits the real database instead of the test-DB URL that
the root conftest injects via os.environ.setdefault.

The dotenv_values() call reads the .env file directly (without touching the
process environment) to get the real DATABASE_URL regardless of what the root
conftest has already written into os.environ.
"""

import pytest_asyncio
from dotenv import dotenv_values
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_dot = dotenv_values()
REAL_DB_URL: str = _dot.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:united8@localhost:5432/estateflow",
)


@pytest_asyncio.fixture
async def http_client(app):
    """Read-only HTTP client connected to the real DB.

    Each FastAPI request gets a fresh session from the real engine.
    No transaction wrapping — reads see committed data from seed.py.
    """
    from app.database import get_db_session

    engine = create_async_engine(REAL_DB_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db_session, None)
    await engine.dispose()


@pytest_asyncio.fixture
async def rw_client(app):
    """Read-write HTTP client with savepoint rollback isolation.

    All DB writes performed during the test (both via HTTP and via the yielded
    session directly) are rolled back when the fixture tears down.

    Yields (AsyncClient, AsyncSession).  Tests that need pre-existing DB
    fixtures can insert them via the session and flush before making HTTP calls.

    join_transaction_mode="create_savepoint": session.commit() inside a service
    releases the current SAVEPOINT rather than committing the outer transaction,
    so the outer conn.rollback() in teardown still undoes everything.
    """
    from app.database import get_db_session

    engine = create_async_engine(REAL_DB_URL, echo=False)
    conn = await engine.connect()
    await conn.begin()
    session = AsyncSession(
        bind=conn,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async def _override():
        yield session

    app.dependency_overrides[get_db_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, session
    app.dependency_overrides.pop(get_db_session, None)
    try:
        await session.close()
    except Exception:
        pass
    await conn.rollback()
    await conn.close()
    await engine.dispose()
