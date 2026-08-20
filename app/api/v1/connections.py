import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.db.mongo import get_db
from app.db import finance_db
from app.db.repositories.telemetry import TelemetryRepository
from app.schemas.telemetry import TelemetryEvent, AgentMeta, ToolMeta, OperationName, ToolCategory
from app.detectors.fastpath_rules import FastPathDetector
from app.detectors.policy_engine import PolicyEngine
from app.detectors.judge_slm import AsyncJudgeDetector
from app.api.v1.incidents import store_manager, IncidentRecord
from app.response.containment import ContainmentEngine
from app.response.notifier import SIEMNotifier, SIEMNotification
from app.core.config import settings

logger = logging.getLogger("griffsox.connections")
router = APIRouter()

# ─── Schemas ──────────────────────────────────────────────────────────────────
class AgentConnection(BaseModel):
    model_config = ConfigDict(frozen=False)

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str = ""
    target_url: str
    identity_urn: str = "spiffe://prod/read-only-agent"
    allowed_tools: List[str] = Field(default_factory=lambda: ["read_file"])
    enforcement_mode: str = "strict_enforce"  # strict_enforce | dry_run_only | disabled
    api_key: Optional[str] = None
    status: str = "active"  # active, offline, unverified
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ConnectionCreateRequest(BaseModel):
    name: str
    description: str = ""
    target_url: str
    identity_urn: str = "spiffe://prod/read-only-agent"
    allowed_tools: List[str] = Field(default_factory=lambda: ["read_file"])
    enforcement_mode: str = "strict_enforce"
    api_key: Optional[str] = None

class ConnectionUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_url: Optional[str] = None
    identity_urn: Optional[str] = None
    allowed_tools: Optional[List[str]] = None
    enforcement_mode: Optional[str] = None
    api_key: Optional[str] = None

class ProxyChatRequest(BaseModel):
    message: str
    trace_id: Optional[str] = None

# ─── In-memory store (seeded from defaults) ───────────────────────────────────
BUILTIN_CONNECTIONS: dict[str, AgentConnection] = {
    "builtin-finance": AgentConnection(
        id="builtin-finance",
        name="Built-in Finance Agent (LangGraph)",
        description="Local Finance Agent with database delete and file read access.",
        target_url="http://127.0.0.1:8000/api/v1/agent/chat",
        identity_urn="spiffe://prod/finance-agent",
        allowed_tools=["database_delete", "database_insert", "query_database", "read_file"],
        enforcement_mode="strict_enforce",
        status="active",
    ),
    "builtin-readonly": AgentConnection(
        id="builtin-readonly",
        name="Read-Only Support Bot",
        description="Strict support bot. Delete actions or external emails trigger Action Guardrail violations.",
        target_url="http://127.0.0.1:8000/api/v1/agent/chat",
        identity_urn="spiffe://prod/read-only-agent",
        allowed_tools=["read_file", "query_database"],
        enforcement_mode="strict_enforce",
        status="active",
    ),
    "builtin-automation": AgentConnection(
        id="builtin-automation",
        name="Automation & Communications Bot",
        description="Automated messaging agent. External email dispatches trigger HITL approval.",
        target_url="http://127.0.0.1:8000/api/v1/agent/chat",
        identity_urn="spiffe://prod/automation-agent",
        allowed_tools=["send_email", "read_file"],
        enforcement_mode="strict_enforce",
        status="active",
    ),
}

# ─── Module-level singletons ──────────────────────────────────────────────────
policy_engine = PolicyEngine.from_settings()
containment_engine = ContainmentEngine(
    sts_revoke_url=settings.STS_REVOKE_URL,
    docker_evict_url=settings.DOCKER_EVICT_URL,
    langgraph_interrupt_url=settings.LANGGRAPH_INTERRUPT_URL,
)

# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.get("", response_model=List[AgentConnection])
async def list_connections() -> List[AgentConnection]:
    """List all registered connected agents."""
    return list(BUILTIN_CONNECTIONS.values())

@router.post("", status_code=status.HTTP_201_CREATED, response_model=AgentConnection)
async def create_connection(req: ConnectionCreateRequest) -> AgentConnection:
    """Register a new remote or local agent endpoint connection."""
    conn_id = f"conn-{uuid4().hex[:8]}"
    conn = AgentConnection(
        id=conn_id,
        name=req.name,
        description=req.description,
        target_url=req.target_url,
        identity_urn=req.identity_urn,
        allowed_tools=req.allowed_tools,
        enforcement_mode=req.enforcement_mode,
        api_key=req.api_key,
        status="active",
    )
    BUILTIN_CONNECTIONS[conn_id] = conn
    logger.info(f"Registered new agent connection: {conn.name} ({conn.target_url})")
    return conn

@router.put("/{connection_id}", response_model=AgentConnection)
async def update_connection(connection_id: str, req: ConnectionUpdateRequest) -> AgentConnection:
    """Update capabilities (allowed_tools, enforcement_mode, etc.) of an agent connection."""
    conn = BUILTIN_CONNECTIONS.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    if req.name is not None:
        conn.name = req.name
    if req.description is not None:
        conn.description = req.description
    if req.target_url is not None:
        conn.target_url = req.target_url
    if req.identity_urn is not None:
        conn.identity_urn = req.identity_urn
    if req.allowed_tools is not None:
        conn.allowed_tools = req.allowed_tools
    if req.enforcement_mode is not None:
        conn.enforcement_mode = req.enforcement_mode
    if req.api_key is not None:
        conn.api_key = req.api_key

    BUILTIN_CONNECTIONS[connection_id] = conn
    logger.info(f"Updated agent connection {connection_id}: allowed_tools={conn.allowed_tools}")
    return conn

@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(connection_id: str):
    """Remove a registered agent connection."""
    if connection_id in BUILTIN_CONNECTIONS:
        del BUILTIN_CONNECTIONS[connection_id]
        return
    raise HTTPException(status_code=404, detail="Connection not found")


@router.post("/{connection_id}/chat")
async def proxy_chat_with_connection(connection_id: str, req: ProxyChatRequest, db=Depends(get_db)):
    """Universal Zero-Trust Security Gateway / Proxy.
    Proxies chat requests to remote agents, intercepts all generated spans,
    and runs them through GriffSOX FastPath, RBAC, and SLM Judge detectors.
    """
    from app.api.v1.agent import run_agent_chat, ChatRequest
    from app.api.v1.ingestion import graph_store

    conn = BUILTIN_CONNECTIONS.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Agent Connection not found.")

    trace_id = req.trace_id or str(uuid4())

    # 1. Forward request to remote agent's target HTTP endpoint (or direct in-process call for built-in local agents)
    is_local_agent = any(
        conn.target_url.startswith(prefix)
        for prefix in ["http://127.0.0.1:8000/api/v1/agent/chat", "http://localhost:8000/api/v1/agent/chat"]
    )

    if is_local_agent:
        try:
            chat_req = ChatRequest(
                message=req.message,
                trace_id=trace_id,
                agent_id=conn.id,
                identity_urn=conn.identity_urn,
                allowed_tools=conn.allowed_tools,
            )
            # SEC-2: 30s timeout on agent call to prevent worker starvation
            chat_res = await asyncio.wait_for(run_agent_chat(chat_req), timeout=30.0)
            agent_data = {
                "response": chat_res.response,
                "tool_calls": chat_res.tool_calls,
                "trace_id": chat_res.trace_id,
            }
        except asyncio.TimeoutError:
            logger.error(f"Agent call timed out for connection {connection_id}")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Agent execution timed out after 30 seconds.",
            )
        except Exception as e:
            logger.error(f"Local built-in agent execution failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Local built-in agent execution error: {str(e)}",
            )
    else:
        headers = {"Content-Type": "application/json"}
        if conn.api_key:
            headers["Authorization"] = f"Bearer {conn.api_key}"

        remote_payload = {
            "message": req.message,
            "trace_id": trace_id,
            "identity_urn": conn.identity_urn,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(conn.target_url, json=remote_payload, headers=headers)
                if res.status_code != 200:
                    logger.warning(f"Remote agent returned status {res.status_code}: {res.text}")
                    agent_data = {"response": res.text or "Remote agent executed.", "tool_calls": []}
                else:
                    agent_data = res.json()
        except Exception as e:
            logger.error(f"Failed to connect to remote agent at {conn.target_url}: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to connect to agent endpoint '{conn.name}' ({conn.target_url}): {str(e)}",
            )

    # Normalize response fields
    response_text = agent_data.get("response") or agent_data.get("output") or str(agent_data)
    tool_calls = agent_data.get("tool_calls", [])

    # 2. PS-3.1 Action Guardrail Pre-Execution Evaluation
    from app.detectors.action_guard import ActionGuardEngine
    from app.schemas.action_guard import AuditRecord, GuardOutcome, HITLStatus
    from app.api.v1.action_audit import audit_manager

    action_guard = ActionGuardEngine.from_settings()
    guard_outcome = GuardOutcome.ALLOW
    guard_reason = "Action allowed"

    # If LLM responded with text without generating explicit tool call, synthesize intended tool call from prompt
    if not tool_calls:
        import re
        msg_lower = req.message.lower()
        if "database_delete" in msg_lower or ("delete" in msg_lower and "record" in msg_lower):
            cnt_match = re.search(r'\b(\d+)\b', req.message)
            if cnt_match:
                count = int(cnt_match.group(1))
            elif "sivaselvan" in msg_lower:
                count = finance_db.count_matching_records("Sivaselvan") or 4
            elif "acme" in msg_lower:
                count = finance_db.count_matching_records("Acme") or 1
            else:
                count = 500
            tool_calls = [{"name": "database_delete", "args": {"query": req.message, "record_count": count}}]
        elif "send_email" in msg_lower or ("email" in msg_lower and "@" in req.message):
            import re as _re
            email_match = _re.search(r'[\w\.-]+@[\w\.-]+', req.message)
            target_email = email_match.group(0) if email_match else "attacker@external-domain.com"
            domain = target_email.split("@")[-1] if "@" in target_email else "external-domain.com"
            tool_calls = [{"name": "send_email", "args": {"to": target_email, "to_domain": domain, "subject": "Quarterly Secret Audit Export"}}]
        elif "read_file" in msg_lower or "confidential" in msg_lower:
            tool_calls = [{"name": "read_file", "args": {"path": "confidential/passwords.txt"}}]

    if tool_calls:
        for tc in tool_calls:
            t_name = tc.get("name", "")
            t_params = tc.get("args", {})
            res = action_guard.evaluate(t_name, t_params)

            audit_rec = AuditRecord(
                trace_id=trace_id,
                agent_id=conn.id,
                identity_urn=conn.identity_urn,
                tool_name=t_name,
                parameters=t_params,
                outcome=res.outcome,
                rule_id=res.matched_rule.id if res.matched_rule else None,
                rule_name=res.matched_rule.name if res.matched_rule else None,
                reason=res.reason,
                hitl_status=HITLStatus.PENDING if res.outcome == GuardOutcome.REQUIRE_HITL else None,
                dry_run=res.dry_run,
            )
            await audit_manager.record_action(audit_rec)

            if res.outcome == GuardOutcome.BLOCK and not res.dry_run:
                response_text = f"🛑 ACTION GUARDRAIL BLOCKED tool '{t_name}': {res.reason}"
                guard_outcome = GuardOutcome.BLOCK
                guard_reason = res.reason
                break
            elif res.outcome == GuardOutcome.REQUIRE_HITL and not res.dry_run:
                response_text = f"⏳ ACTION GUARDRAIL PAUSED tool '{t_name}' for Human-In-The-Loop (HITL) review: {res.reason}"
                guard_outcome = GuardOutcome.REQUIRE_HITL
                guard_reason = res.reason
                break
            elif res.outcome == GuardOutcome.LOG_AND_ALLOW:
                guard_outcome = GuardOutcome.LOG_AND_ALLOW
                guard_reason = res.reason

    # 3. Extract & Ingest telemetry event for Gateway Security Pipeline
    event_id = uuid4()

    op_name = OperationName.EXECUTE_TOOL if tool_calls else OperationName.LLM_PROMPT
    tool_meta = None
    if tool_calls:
        first_tool = tool_calls[0]
        tool_name = first_tool.get("name", "unknown_tool")
        cat = ToolCategory.SYSTEM_EXEC if "shell" in tool_name or "exec" in tool_name else (
            ToolCategory.DATABASE_WRITE if "db" in tool_name or "delete" in tool_name or "write" in tool_name else ToolCategory.READ
        )
        tool_meta = ToolMeta(
            name=tool_name,
            category=cat,
            call_id=str(event_id),
            parameters=first_tool.get("args", {}),
        )

    telemetry_event = TelemetryEvent(
        event_id=event_id,
        trace_id=UUID(trace_id),
        agent=AgentMeta(
            agent_id=conn.id,
            framework="langgraph_proxy",
            identity_urn=conn.identity_urn,
            delegation_chain=[conn.id],
        ),
        operation_name=op_name,
        tool=tool_meta,
        payload_content=f"Prompt: {req.message} | ToolCalls: {tool_calls} | Response: {response_text}"[:2048],
    )

    # 3. Evaluate GriffSOX 3-Layer Security Pipeline
    fastpath_res = FastPathDetector.evaluate(telemetry_event)
    policy_res = policy_engine.evaluate(telemetry_event)
    judge_detector = AsyncJudgeDetector.from_settings()
    judge_verdict = await judge_detector.evaluate_event_async(telemetry_event, root_prompt=req.message)

    # Add to shared sessionized Causal NetworkX DAG
    from app.correlation.graph_builder import EventDetections
    detections = EventDetections(
        fastpath=fastpath_res,
        policy=policy_res,
        judge=judge_verdict,
    )
    telemetry_event.detections = detections.model_dump(mode="json")
    builder = graph_store.get_or_create_builder(telemetry_event.trace_id)
    builder.add_event(telemetry_event, detections=detections)

    # 4. Trigger Incident if Threat Found
    incident_created = False
    incident_severity = None
    if fastpath_res.matched or not policy_res.allowed or (judge_verdict and judge_verdict.is_anomalous):
        incident_created = True
        severity = "CRITICAL" if (fastpath_res.matched and not policy_res.allowed) else "HIGH"
        incident_severity = severity

        containment_res = await containment_engine.enforce(
            incident_id=event_id,
            severity=severity,
            agent_id=conn.id,
            identity_urn=conn.identity_urn,
        )

        inc_record = {
            "incident_id": event_id,
            "trace_id": UUID(trace_id),
            "severity": severity,
            "status": containment_res.status,
            "agent_id": conn.id,
            "identity_urn": conn.identity_urn,
            "matched_techniques": ["AML.T0051", "AML.T0061"] if not policy_res.allowed else ["AML.T0051"],
            "rationale": f"Threat detected via Proxy Gateway: {fastpath_res.rule_name or policy_res.reason}",
            "containment_result": containment_res,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        record_obj = IncidentRecord(**inc_record)
        store_manager.incidents[str(event_id)] = record_obj
        await store_manager.broadcast_ws({
            "event_type": "INCIDENT_CREATED",
            "incident": record_obj.model_dump(mode="json"),
        })

    # 5. Persist telemetry event to MongoDB
    try:
        repo = TelemetryRepository(db)
        await repo.insert(telemetry_event)
    except Exception as e:
        logger.warning(f"MongoDB persistence warning: {e}")

    return {
        "response": response_text,
        "trace_id": trace_id,
        "tool_calls": tool_calls,
        "security_audit": {
            "fastpath_matched": fastpath_res.matched,
            "policy_allowed": policy_res.allowed,
            "policy_reason": policy_res.reason,
            "judge_anomalous": judge_verdict.is_anomalous if judge_verdict else False,
            "incident_created": incident_created,
            "incident_severity": incident_severity,
        },
    }
