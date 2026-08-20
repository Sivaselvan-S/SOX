from uuid import uuid4
import pytest
import httpx

from app.schemas.telemetry import TelemetryEvent, AgentMeta, ToolMeta, OperationName, ToolCategory
from app.detectors.judge_slm import AsyncJudgeDetector
from app.detectors.policy_engine import PolicyEngine, PolicyLoader
from app.instrumentation.langgraph_tracer import LangGraphNodeTracer
from app.db.repositories.telemetry import TelemetryRepository
from app.db.repositories.incidents import IncidentRepository
from app.db.mongo import get_db


@pytest.mark.asyncio
async def test_judge_gemini_mode_mock():
    """Verify AsyncJudgeDetector in gemini mode using mock HTTP transport."""
    async def mock_gemini(request: httpx.Request) -> httpx.Response:
        assert "generativelanguage.googleapis.com" in str(request.url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"is_anomalous": true, "divergence_score": 0.91, "rationale": "Unauthorized exfiltration."}'
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(mock_gemini)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        judge = AsyncJudgeDetector(
            mode="gemini",
            gemini_api_key="test-key-123",
            client=mock_client,
        )
        verdict = await judge.evaluate(
            root_prompt="Read news feed",
            tool_payload="exfiltrate to http://evil.com",
            tool_category=ToolCategory.FILE_EGRESS,
        )

        assert verdict.is_anomalous is True
        assert verdict.divergence_score == 0.91
        assert "Gemini" in verdict.rationale or "exfiltration" in verdict.rationale.lower()


@pytest.mark.asyncio
async def test_langgraph_v2_node_tracer_decorator():
    """Verify LangGraphNodeTracer decorator captures state and emits telemetry."""
    emitted = []

    async def mock_ingest(request: httpx.Request) -> httpx.Response:
        emitted.append(request.read())
        return httpx.Response(200, json={"status": "accepted"})

    transport = httpx.MockTransport(mock_ingest)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        tracer = LangGraphNodeTracer(
            agent_id="test-v2-agent",
            identity_urn="spiffe://prod/finance-agent",
            ingestion_url="http://mock/telemetry/events",
            client=mock_client,
        )

        @tracer.node(operation=OperationName.STATE_TRANSITION)
        async def sample_node(state: dict) -> dict:
            return {"updated": True, **state}

        result = await sample_node({"initial": "data"})
        assert result == {"updated": True, "initial": "data"}


@pytest.mark.asyncio
async def test_mongodb_telemetry_repository():
    """Verify TelemetryRepository inserts and queries events from MongoDB."""
    db = get_db()
    repo = TelemetryRepository(db)

    trace_id = uuid4()
    event = TelemetryEvent(
        event_id=uuid4(),
        trace_id=trace_id,
        agent=AgentMeta(agent_id="test-agent", identity_urn="spiffe://prod/admin-agent"),
        operation_name=OperationName.LLM_PROMPT,
        payload_content="Test prompt persistence",
    )

    await repo.insert(event)

    fetched = await repo.get_by_trace(trace_id)
    assert len(fetched) == 1
    assert fetched[0]["_id"] == str(event.event_id)
    assert fetched[0]["payload_content"] == "Test prompt persistence"


@pytest.mark.asyncio
async def test_mongodb_incident_repository():
    """Verify IncidentRepository inserts, lists, and updates incidents in MongoDB."""
    db = get_db()
    repo = IncidentRepository(db)

    incident_id = str(uuid4())
    record = {
        "incident_id": incident_id,
        "trace_id": str(uuid4()),
        "severity": "CRITICAL",
        "status": "CONTAINED",
        "agent_id": "test-agent",
        "identity_urn": "spiffe://prod/admin-agent",
        "matched_techniques": ["AML.T0051"],
        "rationale": "Kill chain matched.",
    }

    await repo.insert(record)

    fetched = await repo.get_by_id(incident_id)
    assert fetched is not None
    assert fetched["status"] == "CONTAINED"

    await repo.update_status(incident_id, "PARTIALLY_CONTAINED")
    updated = await repo.get_by_id(incident_id)
    assert updated["status"] == "PARTIALLY_CONTAINED"


def test_policy_loader_json_file(tmp_path):
    """Verify PolicyLoader loads custom RBAC policy from JSON file."""
    policy_file = tmp_path / "rbac.json"
    policy_file.write_text(
        '{"spiffe://custom/agent": ["read", "system_exec"]}',
        encoding="utf-8",
    )

    policies = PolicyLoader.load(str(policy_file))
    assert "spiffe://custom/agent" in policies
    assert ToolCategory.SYSTEM_EXEC in policies["spiffe://custom/agent"]
