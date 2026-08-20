from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_serializer


class OperationName(str, Enum):
    LLM_PROMPT = "llm_prompt"
    EXECUTE_TOOL = "execute_tool"
    STATE_TRANSITION = "state_transition"


class ToolCategory(str, Enum):
    DATABASE_WRITE = "database_write"
    FILE_EGRESS = "file_egress"
    SYSTEM_EXEC = "system_exec"
    READ = "read"


class AgentMeta(BaseModel):
    agent_id: str
    framework: str = "langgraph"
    identity_urn: str
    delegation_chain: list[str] = Field(default_factory=list)


class ToolMeta(BaseModel):
    name: str
    category: ToolCategory
    call_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class TelemetryEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    parent_span_id: UUID | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent: AgentMeta
    operation_name: OperationName
    tool: ToolMeta | None = None
    payload_content: str
    sanitized_payload: str | None = None
    detections: dict[str, Any] | None = None

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime, _info: Any) -> str:
        return dt.isoformat()
