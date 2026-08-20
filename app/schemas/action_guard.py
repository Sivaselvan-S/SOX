from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class GuardOutcome(str, Enum):
    BLOCK = "block"
    REQUIRE_HITL = "require_hitl"
    LOG_AND_ALLOW = "log_and_allow"
    ALLOW = "allow"


class HITLStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ConditionRule(BaseModel):
    param: str
    operator: str  # ">", "<", "==", "!=", "contains", "not_in", "in"
    value: Any


class ActionRule(BaseModel):
    id: str
    name: str
    tool: str
    condition: ConditionRule
    outcome: GuardOutcome
    reason: str


class ActionGuardResult(BaseModel):
    outcome: GuardOutcome
    matched_rule: Optional[ActionRule] = None
    reason: str
    dry_run: bool = False


class AuditRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    trace_id: str
    agent_id: str
    identity_urn: str
    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    outcome: GuardOutcome
    rule_id: Optional[str] = None
    rule_name: Optional[str] = None
    reason: str
    hitl_status: Optional[HITLStatus] = None
    dry_run: bool = False
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
