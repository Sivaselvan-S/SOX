import logging
from typing import Dict, Any, Optional
from uuid import UUID

import networkx as nx
from pydantic import BaseModel

from app.schemas.telemetry import TelemetryEvent
from app.detectors.fastpath_rules import FastPathResult
from app.detectors.policy_engine import PolicyResult
from app.detectors.judge_slm import JudgeVerdict

logger = logging.getLogger("griffsox.graph")

MAX_SESSIONS = 10_000  # Guard against unbounded memory growth


class EventDetections(BaseModel):
    fastpath: Optional[FastPathResult] = None
    policy: Optional[PolicyResult] = None
    judge: Optional[JudgeVerdict] = None


class CausalGraphBuilder:
    """Builds and maintains a sessionized NetworkX Directed Acyclic Graph (DAG) for a trace_id."""

    def __init__(self, trace_id: UUID):
        self.trace_id = trace_id
        self.graph = nx.DiGraph(trace_id=str(trace_id))

    def add_event(
        self,
        event: TelemetryEvent,
        detections: Optional[EventDetections] = None,
    ) -> None:
        """Add event node and causal parent->child directed edge to graph."""
        node_id = str(event.event_id)
        parent_id = str(event.parent_span_id) if event.parent_span_id else None

        node_attrs: Dict[str, Any] = {
            "event_id": str(event.event_id),
            "trace_id": str(event.trace_id),
            "parent_span_id": parent_id,
            "timestamp": event.timestamp,
            # Bug fix: OperationName is always a str-Enum — .value always exists, no hasattr needed
            "operation_name": event.operation_name.value,
            "agent_id": event.agent.agent_id,
            "identity_urn": event.agent.identity_urn,
            "tool_name": event.tool.name if event.tool else None,
            # Bug fix: ToolCategory is always a str-Enum — simplify redundant hasattr guard
            "tool_category": event.tool.category.value if event.tool else None,
            "payload_content": event.payload_content,
            "sanitized_payload": event.sanitized_payload,
            "detections": detections.model_dump() if detections else {},
            "is_meta_node": False,
        }

        self.graph.add_node(node_id, **node_attrs)

        # Add directed edge from parent to child if parent exists in graph
        if parent_id:
            if self.graph.has_node(parent_id):
                self.graph.add_edge(parent_id, node_id)
            else:
                # Bug fix: log warning instead of silently dropping the causal edge
                logger.warning(
                    f"Parent node '{parent_id}' not found in graph for trace '{self.trace_id}'. "
                    f"Event '{node_id}' added as disconnected node — possible out-of-order delivery."
                )

    def get_graph(self) -> nx.DiGraph:
        """Return the internal DAG. Treat as read-only; mutating it directly bypasses validation."""
        return self.graph


class GraphStore:
    """In-memory sessionized graph store managing causal graphs by trace_id."""

    def __init__(self, max_sessions: int = MAX_SESSIONS):
        self._stores: Dict[str, CausalGraphBuilder] = {}
        self.max_sessions = max_sessions

    def get_or_create_builder(self, trace_id: UUID) -> CausalGraphBuilder:
        key = str(trace_id)
        if key not in self._stores:
            if len(self._stores) >= self.max_sessions:
                logger.error(
                    f"GraphStore at capacity ({self.max_sessions} sessions). "
                    "Cannot create new session for trace '{key}'. Consider increasing MAX_SESSIONS."
                )
                raise MemoryError(f"GraphStore session limit ({self.max_sessions}) exceeded.")
            self._stores[key] = CausalGraphBuilder(trace_id)
        return self._stores[key]

    def get_graph(self, trace_id: UUID) -> Optional[nx.DiGraph]:
        key = str(trace_id)
        builder = self._stores.get(key)
        return builder.get_graph() if builder else None

    def remove(self, trace_id: UUID) -> bool:
        """Remove a completed or evicted trace session to free memory."""
        key = str(trace_id)
        if key in self._stores:
            del self._stores[key]
            return True
        return False

    def clear(self) -> None:
        self._stores.clear()
