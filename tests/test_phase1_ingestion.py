from uuid import uuid4
import pytest
from httpx import AsyncClient

from app.core.sanitizer import TelemetrySanitizer
from app.instrumentation.langgraph_tracer import LangGraphTracer
from app.schemas.telemetry import OperationName, ToolCategory, TelemetryEvent


@pytest.mark.asyncio
async def test_sanitizer_standalone():
    """Verify standalone TelemetrySanitizer scrubbing rules."""
    raw_payload = (
        "User admin@corp.com connected with Authorization: Bearer secret_bearer_token_123456 "
        "and API Key sk-1234567890abcdef12345678."
    )
    scrubbed = TelemetrySanitizer.scrub(raw_payload)

    assert "admin@corp.com" not in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed

    assert "secret_bearer_token_123456" not in scrubbed
    assert "Bearer [REDACTED_TOKEN]" in scrubbed

    assert "sk-1234567890abcdef12345678" not in scrubbed
    assert "[REDACTED_API_KEY]" in scrubbed


@pytest.mark.asyncio
async def test_ingest_event_success_and_redaction(client: AsyncClient):
    """Verify POST /api/v1/telemetry/events returns 202 Accepted and redacts sensitive credentials."""
    event_payload = {
        "event_id": str(uuid4()),
        "trace_id": str(uuid4()),
        "agent": {
            "agent_id": "finance-orchestrator-01",
            "framework": "langgraph",
            "identity_urn": "spiffe://prod/finance-agent",
            "delegation_chain": ["usr_102", "agent_orchestrator", "agent_worker"],
        },
        "operation_name": "execute_tool",
        "tool": {
            "name": "db_query",
            "category": "database_write",
            "call_id": "call_999",
            "parameters": {"query": "SELECT * FROM users;"},
        },
        "payload_content": "Query run by user user@test.com with key sk-abcdef1234567890abcdef1234 and Bearer token1234567890123",
    }

    response = await client.post("/api/v1/telemetry/events", json=event_payload)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert "sanitized_payload" in data

    sanitized = data["sanitized_payload"]
    assert "user@test.com" not in sanitized
    assert "[REDACTED_EMAIL]" in sanitized
    assert "sk-abcdef1234567890abcdef1234" not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized
    assert "token1234567890123" not in sanitized
    assert "Bearer [REDACTED_TOKEN]" in sanitized


@pytest.mark.asyncio
async def test_ingest_event_invalid_schema(client: AsyncClient):
    """Verify 422 Unprocessable Entity on schema validation failure."""
    invalid_payload = {
        "operation_name": "invalid_operation",
        "payload_content": "some content",
    }

    response = await client.post("/api/v1/telemetry/events", json=invalid_payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_langgraph_tracer_event_creation(client: AsyncClient):
    """Verify LangGraphTracer generates compliant TelemetryEvents."""
    trace_id = uuid4()
    tracer = LangGraphTracer(
        agent_id="test-agent-01",
        identity_urn="spiffe://test/agent",
        trace_id=trace_id,
        client=client,
    )

    event = tracer.create_event(
        operation_name=OperationName.LLM_PROMPT,
        payload_content="Contact dev@example.com with Bearer sample_bearer_token_123456",
    )

    assert event.trace_id == trace_id
    assert event.agent.agent_id == "test-agent-01"
    assert event.agent.identity_urn == "spiffe://test/agent"
    assert event.operation_name == OperationName.LLM_PROMPT

    # Test sending via tracer to ingestion API
    response = await tracer._send_event(event)
    assert response is not None
    assert response.status_code == 202
    res_data = response.json()
    assert res_data["sanitized_payload"] == (
        "Contact [REDACTED_EMAIL] with Bearer [REDACTED_TOKEN]"
    )
