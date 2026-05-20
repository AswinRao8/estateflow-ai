import pytest
import os
from fastapi.testclient import TestClient


# Force testing environment before any app code is imported.
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:united8@localhost:5432/estateflow_test")


@pytest.fixture(scope="session")
def app():
    from app.main import create_app
    return create_app()


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app) as c:
        yield c
