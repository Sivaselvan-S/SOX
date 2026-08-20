import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, status, Depends
from pydantic import BaseModel, ConfigDict

from app.core.sanitizer import TelemetrySanitizer
from app.schemas.telemetry import TelemetryEvent, OperationName
from app.detectors.fastpath_rules import FastPathDetector, FastPathResult
from app.detectors.policy_engine import PolicyEngine, PolicyResult
from app.detectors.judge_slm import AsyncJudgeDetector, JudgeVerdict
from app.correlation.graph_builder import GraphStore, EventDetections
from app.correlation.atlas_matcher import AtlasMatcher
from app.response.containment import ContainmentEngine
from app.response.notifier import SIEMNotifier, SIEMNotification
from app.db.mongo import get_db
from app.db.repositories.telemetry import TelemetryRepository
from app.db.repositories.incidents import IncidentRepository
from app.api.v1.incidents import store_manager

logger = logging.getLogger("griffsox.ingestion")
router = APIRouter()

# Shared singletons
graph_store = GraphStore()
containment_engine = ContainmentEngine()
siem_notifier = SIEMNotifier()
policy_engine = PolicyEngine.from_settings()
_root_prompts: dict[str, str] = {}  # trace_id -> initial root_prompt


class IngestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    trace_id: UUID
    status: str = "accepted"
    sanitized_payload: str
    detections: EventDetections
    incident_created: bool = False
    incident_severity: Optional[str] = None
    executive_summary: Optional[str] = None


@router.get("/events", response_model=list[TelemetryEvent])
async def list_telemetry_events(db=Depends(get_db)):
    """Retrieve all ingested telemetry events."""
    repo = TelemetryRepository(db)
    docs = await repo.get_all(limit=100)
    # Parse back into TelemetryEvent objects
    return [TelemetryEvent(**doc) for doc in docs]


@router.post("/events", status_code=status.HTTP_202_ACCEPTED, response_model=IngestionResponse)
async def ingest_telemetry_event(
    event: TelemetryEvent,
    db=Depends(get_db),
) -> IngestionResponse:
    """Ingest OpenTelemetry GenAI span event, sanitize, evaluate 3-layer security guard, update Causal DAG, and trigger SOAR containment."""
    trace_key = str(event.trace_id)

    # 1. In-flight PII / Credential Sanitization
    scrubbed = TelemetrySanitizer.scrub(event.payload_content)
    event.sanitized_payload = scrubbed

    # Track root prompt for semantic intent divergence comparison
    if event.operation_name == OperationName.LLM_PROMPT and trace_key not in _root_prompts:
        _root_prompts[trace_key] = scrubbed
    root_prompt = _root_prompts.get(trace_key, scrubbed)

    # 2. Layer 1: Sub-5ms Synchronous FastPath Guardrail
    fastpath_res: FastPathResult = FastPathDetector.evaluate(event)

    # 3. Layer 2: Rego-Lite RBAC Policy Check
    policy_res: PolicyResult = policy_engine.evaluate(event)

    # 4. Layer 3: Async Gemini / SLM Intent Divergence Judge
    judge_detector = AsyncJudgeDetector.from_settings()
    judge_verdict: Optional[JudgeVerdict] = await judge_detector.evaluate_event_async(
        event, root_prompt=root_prompt
    )

    detections = EventDetections(
        fastpath=fastpath_res,
        policy=policy_res,
        judge=judge_verdict,
    )
    event.detections = detections.model_dump(mode="json")

    # 5. Persist event to MongoDB Atlas
    telemetry_repo = TelemetryRepository(db)
    try:
        await telemetry_repo.insert(event)
    except Exception as e:
        logger.warning(f"MongoDB persistence warning: {e}")

    # 6. Sessionize & Update Causal NetworkX DAG
    builder = graph_store.get_or_create_builder(event.trace_id)
    builder.add_event(event, detections=detections)

    # 7. MITRE ATLAS Kill-Chain Evaluation
    graph = builder.get_graph()
    incident_score = AtlasMatcher.match_kill_chain(graph)

    incident_created = False
    incident_severity = None

    # Check if a threat incident should be registered & contained
    should_trigger_incident = (
        incident_score.severity in ("MEDIUM", "HIGH", "CRITICAL")
        or fastpath_res.matched
        or (policy_res.allowed is False)
        or (judge_verdict and judge_verdict.is_anomalous)
    )

    if should_trigger_incident:
        severity = incident_score.severity if incident_score.severity != "LOW" else (
            "CRITICAL" if (fastpath_res.matched and policy_res.allowed is False) else "HIGH"
        )
        incident_severity = severity

        # Execute Agent-Native SOAR Containment Matrix
        containment_res = await containment_engine.enforce(
            incident_id=event.event_id,
            severity=severity,
            agent_id=event.agent.agent_id,
            identity_urn=event.agent.identity_urn,
        )

        matched_techs = incident_score.matched_techniques
        if not matched_techs and fastpath_res.matched:
            matched_techs.append("AML.T0051")
        if not matched_techs and policy_res.allowed is False:
            matched_techs.append("AML.T0061")

        inc_record = {
            "incident_id": str(event.event_id),
            "trace_id": trace_key,
            "severity": severity,
            "status": containment_res.status,
            "agent_id": event.agent.agent_id,
            "identity_urn": event.agent.identity_urn,
            "matched_techniques": matched_techs,
            "rationale": incident_score.rationale or f"Threat detected: {fastpath_res.rule_name or policy_res.reason}",
            "containment_result": containment_res.model_dump(mode="json"),
            "created_at": event.timestamp.isoformat(),
        }

        # Store in memory & MongoDB
        from app.api.v1.incidents import IncidentRecord
        store_manager.incidents[str(event.event_id)] = IncidentRecord(**inc_record)

        try:
            inc_repo = IncidentRepository(db)
            await inc_repo.insert(inc_record)
        except Exception as e:
            logger.warning(f"MongoDB incident insert warning: {e}")

        # Broadcast live alert to WebSocket listeners
        ws_payload = {
          "event_type": "INCIDENT_CREATED",
          "incident": inc_record,
        }
        await store_manager.broadcast_ws(ws_payload)

        # Dispatch SIEM Webhook
        await siem_notifier.dispatch(
            SIEMNotification(
                incident_id=str(event.event_id),
                trace_id=trace_key,
                severity=severity,
                matched_techniques=matched_techs,
                status=containment_res.status,
                summary=inc_record["rationale"],
            )
        )

        incident_created = True

    # Generate plain English executive summary
    if incident_created:
        parts = ["**Critical security incident detected.**"]
        
        if policy_res and not policy_res.allowed:
            parts.append(f"The agent attempted an action that violates its assigned role (RBAC Policy Violation). Reason: {policy_res.reason}.")
            
        if judge_verdict and judge_verdict.is_anomalous:
            parts.append(f"The AI judge analyzed the intent and found it to be anomalous or malicious. Rationale: {judge_verdict.rationale}.")
            
        if fastpath_res and fastpath_res.matched:
            parts.append(f"The payload matched known threat signatures for {fastpath_res.rule_name}.")
            
        parts.append(f"A SOAR containment workflow was triggered to halt the agent, and the incident was assigned a severity of {incident_severity}.")
        executive_summary = " ".join(parts)
    else:
        executive_summary = "**The AI agent behaved normally.** No policy violations or anomalous intents were detected, and the action was allowed to proceed."

    return IngestionResponse(
        event_id=event.event_id,
        trace_id=event.trace_id,
        status="accepted",
        sanitized_payload=scrubbed,
        detections=detections,
        incident_created=incident_created,
        incident_severity=incident_severity,
        executive_summary=executive_summary
    )
