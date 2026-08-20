import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_list_and_create_connections():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # List connections
        res = await client.get("/api/v1/connections")
        assert res.status_code == 200
        connections = res.json()
        assert len(connections) >= 2

        # Create connection
        payload = {
            "name": "Test Support Agent",
            "description": "Test remote support bot",
            "target_url": "http://127.0.0.1:8000/api/v1/agent/chat",
            "identity_urn": "spiffe://prod/support-agent",
            "allowed_tools": ["read_file"],
            "enforcement_mode": "strict_enforce",
        }
        res_create = await client.post("/api/v1/connections", json=payload)
        assert res_create.status_code == 201
        created = res_create.json()
        assert created["name"] == "Test Support Agent"
        assert created["identity_urn"] == "spiffe://prod/support-agent"

        # Delete connection
        conn_id = created["id"]
        res_del = await client.delete(f"/api/v1/connections/{conn_id}")
        assert res_del.status_code == 204
