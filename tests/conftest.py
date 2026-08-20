"""
GriffSOX Test Configuration
- Uses mongomock-motor for hermetic in-memory MongoDB (no Atlas/Docker needed in tests)
- Provides a shared FastAPI TestClient and isolated DB per test session
"""
import pytest
import mongomock_motor
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db import mongo as db_module


@pytest.fixture(scope="session")
def mock_mongo_client():
    """Shared mongomock-motor client for the entire test session."""
    return mongomock_motor.AsyncMongoMockClient()


@pytest.fixture(autouse=True)
async def patch_mongo(mock_mongo_client, monkeypatch):
    """Patch the motor client used by all db modules with the mock client."""
    monkeypatch.setattr(db_module, "_client", mock_mongo_client)
    yield
    # Drop all collections after each test for isolation
    db = mock_mongo_client[db_module.settings.MONGO_DB_NAME]
    for name in ["telemetry_events", "incidents", "causal_graphs"]:
        await db[name].drop()


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP test client for GriffSOX FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
