from uuid import uuid4
import pytest
import httpx
from httpx import AsyncClient

from app.response.containment import ContainmentEngine, ContainmentTier
from app.response.notifier import SIEMNotification, SIEMNotifier
from app.api.v1.incidents import store_manager, containment_engine, siem_notifier


@pytest.fixture(autouse=True)
def clear_incident_store():
    """Isolate incident store state between every test to prevent cross-test contamination."""
    store_manager.incidents.clear()
    yield
    store_manager.incidents.clear()


@pytest.mark.asyncio
async def test_containment_critical_triggers_all_tiers():
    """Verify CRITICAL incident severity triggers Tier 1, Tier 2, and Tier 3 containment actions."""
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "success"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        engine = ContainmentEngine(
            sts_revoke_url="http://mock/sts/revoke",
            docker_evict_url="http://mock/docker/evict",
            langgraph_interrupt_url="http://mock/langgraph/interrupt",
            client=mock_client,
        )

        incident_id = uuid4()
        res = await engine.enforce(
            incident_id=incident_id,
            severity="CRITICAL",
            agent_id="finance-orchestrator-01",
            identity_urn="spiffe://prod/finance-agent",
        )

        assert res.status == "CONTAINED"
        assert res.executed_tiers == [
            ContainmentTier.TIER_1_SOFT,
            ContainmentTier.TIER_2_MEDIUM,
            ContainmentTier.TIER_3_HARD,
        ]
        assert len(res.action_results) == 3
        assert all(action.success for action in res.action_results)


@pytest.mark.asyncio
async def test_containment_high_triggers_tiers_1_and_2():
    """Verify HIGH incident severity triggers Tier 1 and Tier 2 actions only."""
    engine = ContainmentEngine()
    incident_id = uuid4()

    res = await engine.enforce(
        incident_id=incident_id,
        severity="HIGH",
        agent_id="finance-orchestrator-01",
        identity_urn="spiffe://prod/finance-agent",
    )

    assert res.status == "CONTAINED"
    assert res.executed_tiers == [ContainmentTier.TIER_1_SOFT, ContainmentTier.TIER_2_MEDIUM]


@pytest.mark.asyncio
async def test_rest_create_and_list_incidents(client: AsyncClient):
    """Verify POST /api/v1/incidents creates incident, runs containment, and supports GET endpoints."""
    trace_id = str(uuid4())
    payload = {
        "trace_id": trace_id,
        "severity": "CRITICAL",
        "agent_id": "agent-test-01",
        "identity_urn": "spiffe://prod/test-agent",
        "matched_techniques": ["AML.T0051", "AML.T0061", "AML.T0062"],
        "rationale": "Multi-hop kill chain detected.",
    }

    # POST create incident
    response = await client.post("/api/v1/incidents", json=payload)
    assert response.status_code == 201
    data = response.json()
    incident_id = data["incident_id"]
    assert data["status"] == "CONTAINED"
    assert data["severity"] == "CRITICAL"

    # GET list incidents
    list_res = await client.get("/api/v1/incidents")
    assert list_res.status_code == 200
    incidents_list = list_res.json()
    assert any(inc["incident_id"] == incident_id for inc in incidents_list)

    # GET single incident detail
    detail_res = await client.get(f"/api/v1/incidents/{incident_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["incident_id"] == incident_id


@pytest.mark.asyncio
async def test_siem_notifier_dispatch():
    """Verify SIEMNotifier dispatches structured notification payload."""
    dispatched_payload = {}

    async def mock_siem(request: httpx.Request) -> httpx.Response:
        nonlocal dispatched_payload
        dispatched_payload = request.read().decode("utf-8")
        return httpx.Response(202, json={"status": "accepted"})

    transport = httpx.MockTransport(mock_siem)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        notifier = SIEMNotifier(
            webhook_url="http://mock/siem/webhook",
            client=mock_client,
        )

        notification = SIEMNotification(
            incident_id=str(uuid4()),
            trace_id=str(uuid4()),
            severity="CRITICAL",
            matched_techniques=["AML.T0051", "AML.T0061", "AML.T0062"],
            status="CONTAINED",
            summary="Attack kill chain contained.",
        )

        success = await notifier.dispatch(notification)
        assert success is True
        assert "AML.T0051" in dispatched_payload
        assert "CONTAINED" in dispatched_payload


# ─── Regression tests for Phase 4 review fixes ──────────────────────────────

@pytest.mark.asyncio
async def test_invalid_severity_returns_422(client: AsyncClient):
    """Bug fix: invalid severity must return 422, not silently default to NO_ACTION."""
    payload = {
        "trace_id": str(uuid4()),
        "severity": "SUPER_CRITICAL",  # invalid
        "agent_id": "agent-01",
        "identity_urn": "spiffe://prod/test-agent",
        "matched_techniques": [],
        "rationale": "Test.",
    }
    response = await client.post("/api/v1/incidents", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_low_severity_produces_no_action():
    """Verify LOW severity returns NO_ACTION status without executing any tier."""
    engine = ContainmentEngine()
    incident_id = uuid4()

    res = await engine.enforce(
        incident_id=incident_id,
        severity="LOW",
        agent_id="agent-01",
        identity_urn="spiffe://prod/test-agent",
    )

    assert res.status == "NO_ACTION"
    assert res.executed_tiers == []
    assert res.action_results == []


@pytest.mark.asyncio
async def test_incident_404_for_unknown_id(client: AsyncClient):
    """Verify GET /incidents/{id} returns 404 for non-existent incident ID."""
    fake_id = str(uuid4())
    response = await client.get(f"/api/v1/incidents/{fake_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_partially_contained_when_tier_fails():
    """Verify status is PARTIALLY_CONTAINED when one tier action fails due to connection error."""
    call_count = {"n": 0}

    async def flaky_handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        # First call (Tier 1) fails, subsequent succeed
        if call_count["n"] == 1:
            raise httpx.ConnectError("Connection refused")
        return httpx.Response(200, json={"status": "success"})

    transport = httpx.MockTransport(flaky_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        engine = ContainmentEngine(
            sts_revoke_url="http://mock/sts/revoke",
            docker_evict_url="http://mock/docker/evict",
            langgraph_interrupt_url="http://mock/langgraph/interrupt",
            client=mock_client,
        )

        res = await engine.enforce(
            incident_id=uuid4(),
            severity="CRITICAL",
            agent_id="agent-01",
            identity_urn="spiffe://prod/test-agent",
        )

        assert res.status == "PARTIALLY_CONTAINED"
        # All 3 tiers were still attempted even though Tier 1 failed
        assert len(res.action_results) == 3
        tier1_result = next(r for r in res.action_results if r.tier.value == "tier_1_soft")
        assert tier1_result.success is False
