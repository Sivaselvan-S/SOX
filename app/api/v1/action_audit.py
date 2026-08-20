import logging
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from app.schemas.action_guard import AuditRecord, GuardOutcome, HITLStatus
from app.detectors.action_guard import ActionRuleLoader
from app.core.config import settings

logger = logging.getLogger("griffsox.action_audit")
router = APIRouter()


def _execute_approved_tool(tool_name: str, parameters: dict) -> dict:
    """Execute an approved HITL tool call against the real finance database."""
    from app.db import finance_db

    try:
        if tool_name == "database_delete":
            query = parameters.get("query", "")
            record_count = int(parameters.get("record_count", 1))
            result = finance_db.delete_finance_records(query, record_count)
            logger.info(f"HITL approved: executed database_delete — {result}")
            return result

        elif tool_name == "database_insert":
            count = int(parameters.get("count", 1))
            vendor_name = parameters.get("vendor_name", "Approved Insert")
            category = parameters.get("category", "General")
            amount = float(parameters.get("amount", 0.0))
            result = finance_db.insert_finance_records(count, vendor_name, category, amount)
            logger.info(f"HITL approved: executed database_insert — {result}")
            return result

        elif tool_name == "database_query" or tool_name == "count_records":
            result = finance_db.query_finance_records()
            logger.info(f"HITL approved: executed {tool_name} — {result}")
            return result

        else:
            logger.warning(f"HITL approved for unknown tool '{tool_name}' — no execution handler registered.")
            return {"message": f"Tool '{tool_name}' approved but no auto-execution handler registered. Execute manually."}

    except Exception as e:
        logger.error(f"HITL approved execution error for tool '{tool_name}': {e}")
        return {"error": str(e), "message": f"Approval recorded but execution of '{tool_name}' failed: {e}"}


class AuditManager:
    """In-memory store and WebSocket dispatcher for Action Guardrail Audit Log & HITL Queue."""

    def __init__(self):
        self.audit_records: List[AuditRecord] = []
        self.pending_hitl: Dict[str, AuditRecord] = {}
        self.active_connections: List[WebSocket] = []
        self.dry_run: bool = settings.DRY_RUN

    async def connect_ws(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect_ws(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_ws(self, message: dict):
        for ws in list(self.active_connections):
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"WebSocket broadcast error: {e}")
                self.disconnect_ws(ws)

    async def record_action(self, record: AuditRecord) -> AuditRecord:
        self.audit_records.insert(0, record)
        if record.outcome == GuardOutcome.REQUIRE_HITL and record.hitl_status == HITLStatus.PENDING:
            self.pending_hitl[str(record.id)] = record

        await self.broadcast_ws({
            "event_type": "ACTION_EVALUATED",
            "record": record.model_dump(mode="json"),
        })
        return record

    async def resolve_hitl(self, record_id: str, approved: bool) -> AuditRecord:
        record = self.pending_hitl.get(record_id)
        if not record:
            raise HTTPException(status_code=404, detail="Pending HITL decision not found.")

        record.hitl_status = HITLStatus.APPROVED if approved else HITLStatus.REJECTED
        del self.pending_hitl[record_id]

        # If approved, actually execute the intercepted tool call now
        execution_result = None
        if approved:
            execution_result = _execute_approved_tool(record.tool_name, record.parameters)

        await self.broadcast_ws({
            "event_type": "HITL_RESOLVED",
            "approved": approved,
            "execution_result": execution_result,
            "record": record.model_dump(mode="json"),
        })
        return record


audit_manager = AuditManager()


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/log", response_model=List[AuditRecord])
async def list_audit_log(limit: int = 100) -> List[AuditRecord]:
    """Retrieve audit log of evaluated tool actions."""
    return audit_manager.audit_records[:limit]


@router.get("/hitl/pending", response_model=List[AuditRecord])
async def list_pending_hitl() -> List[AuditRecord]:
    """List pending Human-In-The-Loop action decisions awaiting approval."""
    return list(audit_manager.pending_hitl.values())


@router.post("/hitl/{record_id}/approve", response_model=AuditRecord)
async def approve_hitl(record_id: str) -> AuditRecord:
    """Approve a pending HITL tool execution."""
    return await audit_manager.resolve_hitl(record_id, approved=True)


@router.post("/hitl/{record_id}/reject", response_model=AuditRecord)
async def reject_hitl(record_id: str) -> AuditRecord:
    """Reject a pending HITL tool execution."""
    return await audit_manager.resolve_hitl(record_id, approved=False)


from app.schemas.action_guard import ActionRule

# ─── MongoDB-backed rule persistence ──────────────────────────────────────────
# Rules are stored in MongoDB (griffsox_db.action_rules) so they survive
# container restarts and redeployments. Falls back to action_rules.yaml on
# first boot to seed the initial ruleset.

def _get_rules_collection():
    """Return the MongoDB action_rules collection via sync PyMongo, or None if not connected."""
    try:
        from pymongo import MongoClient
        client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
        db = client[settings.MONGO_DB_NAME]
        return db["action_rules"]
    except Exception as e:
        logger.warning(f"MongoDB not available for rule persistence: {e}")
        return None


def _load_rules_from_mongo() -> Optional[List[ActionRule]]:
    """Load all rules from MongoDB. Returns None if unavailable."""
    col = _get_rules_collection()
    if col is None:
        return None
    try:
        docs = list(col.find({}, {"_id": 0}))
        if not docs:
            return None  # empty — will fall through to YAML seed
        return [ActionRule(**d) for d in docs]
    except Exception as e:
        logger.error(f"Failed to load rules from MongoDB: {e}")
        return None


def _save_rules_to_mongo(rules: List[ActionRule]) -> bool:
    """Persist all rules to MongoDB (full replace)."""
    col = _get_rules_collection()
    if col is None:
        return False
    try:
        col.delete_many({})  # clear existing
        if rules:
            col.insert_many([r.model_dump(mode="json") for r in rules])
        logger.info(f"Saved {len(rules)} action rules to MongoDB.")
        return True
    except Exception as e:
        logger.error(f"Failed to save rules to MongoDB: {e}")
        return False


def _load_rules_persistent() -> List[ActionRule]:
    """Load rules: prefer MongoDB, fall back to action_rules.yaml, then seed Mongo."""
    mongo_rules = _load_rules_from_mongo()
    if mongo_rules is not None:
        return mongo_rules
    # First boot: seed from YAML file
    yaml_rules = ActionRuleLoader.load(settings.ACTION_RULES_PATH)
    if yaml_rules:
        logger.info(f"Seeding {len(yaml_rules)} rules from YAML into MongoDB.")
        _save_rules_to_mongo(yaml_rules)
    return yaml_rules


@router.get("/rules")
async def get_active_rules():
    """Return active declarative action guardrail rules."""
    rules = _load_rules_persistent()
    return {
        "rules_file": "mongodb:action_rules",
        "dry_run": audit_manager.dry_run,
        "rules": [r.model_dump(mode="json") for r in rules],
    }


@router.post("/rules", status_code=status.HTTP_201_CREATED, response_model=ActionRule)
async def create_action_rule(rule: ActionRule):
    """Add a new action guardrail rule (persisted to MongoDB)."""
    rules = _load_rules_persistent()
    existing_idx = next((i for i, r in enumerate(rules) if r.id == rule.id), None)
    if existing_idx is not None:
        rules[existing_idx] = rule
    else:
        rules.append(rule)
    _save_rules_to_mongo(rules)
    # Also keep YAML in sync as backup
    ActionRuleLoader.save(rules, settings.ACTION_RULES_PATH)
    logger.info(f"Created/Updated action rule: {rule.id} ({rule.name})")
    return rule


@router.put("/rules/{rule_id}", response_model=ActionRule)
async def update_action_rule(rule_id: str, rule: ActionRule):
    """Update an existing action guardrail rule (persisted to MongoDB)."""
    rules = _load_rules_persistent()
    existing_idx = next((i for i, r in enumerate(rules) if r.id == rule_id), None)
    if existing_idx is None:
        raise HTTPException(status_code=404, detail=f"Rule with id '{rule_id}' not found.")
    rules[existing_idx] = rule
    _save_rules_to_mongo(rules)
    ActionRuleLoader.save(rules, settings.ACTION_RULES_PATH)
    logger.info(f"Updated action rule: {rule_id}")
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_action_rule(rule_id: str):
    """Delete an action guardrail rule by ID (persisted to MongoDB)."""
    rules = _load_rules_persistent()
    filtered = [r for r in rules if r.id != rule_id]
    if len(filtered) == len(rules):
        raise HTTPException(status_code=404, detail=f"Rule with id '{rule_id}' not found.")
    _save_rules_to_mongo(filtered)
    ActionRuleLoader.save(filtered, settings.ACTION_RULES_PATH)
    logger.info(f"Deleted action rule: {rule_id}")
    return


class ActionEvaluateRequest(BaseModel):
    tool_name: str
    parameters: dict = Field(default_factory=dict)
    agent_id: str = "builtin-finance"
    identity_urn: str = "spiffe://prod/finance-agent"
    trace_id: Optional[str] = None


@router.post("/evaluate", response_model=AuditRecord)
async def evaluate_action(req: ActionEvaluateRequest) -> AuditRecord:
    """Direct pre-execution action evaluation endpoint for testing and simulation."""
    from app.detectors.action_guard import ActionGuardEngine
    from uuid import uuid4

    guard = ActionGuardEngine.from_settings()
    res = guard.evaluate(req.tool_name, req.parameters)
    trace_id = req.trace_id or str(uuid4())

    audit_rec = AuditRecord(
        trace_id=trace_id,
        agent_id=req.agent_id,
        identity_urn=req.identity_urn,
        tool_name=req.tool_name,
        parameters=req.parameters,
        outcome=res.outcome,
        rule_id=res.matched_rule.id if res.matched_rule else None,
        rule_name=res.matched_rule.name if res.matched_rule else None,
        reason=res.reason,
        hitl_status=HITLStatus.PENDING if res.outcome == GuardOutcome.REQUIRE_HITL else None,
        dry_run=res.dry_run,
    )
    return await audit_manager.record_action(audit_rec)


@router.post("/dry-run/toggle")
async def toggle_dry_run():
    """Toggle Dry-Run mode on or off at runtime."""
    audit_manager.dry_run = not audit_manager.dry_run
    logger.info(f"Dry-run mode toggled to: {audit_manager.dry_run}")
    await audit_manager.broadcast_ws({
        "event_type": "DRY_RUN_TOGGLED",
        "dry_run": audit_manager.dry_run,
    })
    return {"dry_run": audit_manager.dry_run}


@router.get("/dry-run-report")
async def get_dry_run_report():
    """Return summary report of simulated dry-run violations."""
    dry_runs = [r for r in audit_manager.audit_records if r.dry_run]
    violations = [r for r in dry_runs if r.outcome in (GuardOutcome.BLOCK, GuardOutcome.REQUIRE_HITL)]
    return {
        "total_simulated_actions": len(dry_runs),
        "total_violations_flagged": len(violations),
        "dry_run_enabled": audit_manager.dry_run,
        "violations": [v.model_dump(mode="json") for v in violations],
    }


@router.get("/db-status")
async def get_finance_db_status():
    """Get current SQLite financial database status and record count."""
    from app.db import finance_db
    return finance_db.query_finance_records()


@router.post("/db-reset")
async def reset_finance_db():
    """Reset SQLite financial database back to original 30 seed records."""
    from app.db import finance_db
    res = finance_db.reset_db_to_seed()
    await audit_manager.broadcast_ws({
        "event_type": "DB_RESET",
        "total_records": res["total_records"],
    })
    return res


@router.websocket("/stream")
async def action_audit_stream(websocket: WebSocket):
    """WebSocket endpoint for real-time action evaluation streaming."""
    await audit_manager.connect_ws(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        audit_manager.disconnect_ws(websocket)
