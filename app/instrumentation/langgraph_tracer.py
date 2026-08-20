from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
import httpx
from langchain_core.callbacks import BaseCallbackHandler

from app.schemas.telemetry import (
    AgentMeta,
    OperationName,
    TelemetryEvent,
    ToolCategory,
    ToolMeta,
)


class LangGraphTracer(BaseCallbackHandler):
    """Custom LangChain / LangGraph BaseCallbackHandler that converts agent spans

    to OpenTelemetry GenAI events and exports them to GriffSOX.
    """

    def __init__(
        self,
        agent_id: str,
        identity_urn: str,
        trace_id: Optional[UUID] = None,
        delegation_chain: Optional[List[str]] = None,
        ingestion_url: str = "http://localhost:8000/api/v1/telemetry/events",
        client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__()
        self.agent_id = agent_id
        self.identity_urn = identity_urn
        self.trace_id = trace_id or uuid4()
        self.delegation_chain = delegation_chain or [agent_id]
        self.ingestion_url = ingestion_url
        self.client = client
        self._last_span_id: Optional[UUID] = None

    def _build_agent_meta(self) -> AgentMeta:
        return AgentMeta(
            agent_id=self.agent_id,
            framework="langgraph",
            identity_urn=self.identity_urn,
            delegation_chain=self.delegation_chain,
        )

    async def _send_event(self, event: TelemetryEvent) -> Optional[httpx.Response]:
        """Send telemetry event to ingestion service."""
        payload = event.model_dump(mode="json")
        if self.client:
            return await self.client.post(self.ingestion_url, json=payload)
        async with httpx.AsyncClient() as client:
            return await client.post(self.ingestion_url, json=payload)

    def create_event(
        self,
        operation_name: OperationName,
        payload_content: str,
        tool: Optional[ToolMeta] = None,
        parent_span_id: Optional[UUID] = None,
    ) -> TelemetryEvent:
        """Helper to create a TelemetryEvent with current trace context."""
        event_id = uuid4()
        parent = parent_span_id or self._last_span_id
        event = TelemetryEvent(
            event_id=event_id,
            trace_id=self.trace_id,
            parent_span_id=parent,
            agent=self._build_agent_meta(),
            operation_name=operation_name,
            tool=tool,
            payload_content=payload_content,
        )
        self._last_span_id = event_id
        return event

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any,
    ) -> None:
        """Handle LLM start callback."""
        prompt_text = "\n".join(prompts) if prompts else ""
        self.create_event(
            operation_name=OperationName.LLM_PROMPT,
            payload_content=prompt_text,
        )

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Handle tool execution start callback."""
        tool_name = serialized.get("name", "unknown_tool")
        cat_str = kwargs.get("category", "read")
        try:
            category = ToolCategory(cat_str)
        except ValueError:
            category = ToolCategory.READ

        tool_meta = ToolMeta(
            name=tool_name,
            category=category,
            call_id=str(kwargs.get("run_id", uuid4())),
            parameters=kwargs.get("inputs", {}),
        )

        self.create_event(
            operation_name=OperationName.EXECUTE_TOOL,
            payload_content=input_str,
            tool=tool_meta,
        )

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Handle state transition callback."""
        chain_name = serialized.get("id", ["state_transition"])[-1]
        self.create_event(
            operation_name=OperationName.STATE_TRANSITION,
            payload_content=str(inputs),
        )


# ─── LangGraph v0.2+ StateGraph Node Tracer ─────────────────────────────────
import asyncio
import functools
from typing import Callable, TypeVar

_F = TypeVar("_F", bound=Callable)


class LangGraphNodeTracer:
    """Decorator-based tracer for LangGraph v0.2+ StateGraph nodes.

    Usage:
        tracer = LangGraphNodeTracer(
            agent_id="my-agent",
            identity_urn="spiffe://prod/read-only-agent",
        )

        @tracer.node(operation=OperationName.STATE_TRANSITION)
        async def my_node(state: dict) -> dict:
            ...

        builder = StateGraph(MyState)
        builder.add_node("my_node", my_node)
    """

    def __init__(
        self,
        agent_id: str,
        identity_urn: str,
        trace_id: Optional[UUID] = None,
        delegation_chain: Optional[List[str]] = None,
        ingestion_url: str = "http://localhost:8000/api/v1/telemetry/events",
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.agent_id = agent_id
        self.identity_urn = identity_urn
        self.trace_id = trace_id or uuid4()
        self.delegation_chain = delegation_chain or [agent_id]
        self.ingestion_url = ingestion_url
        self.client = client
        self._last_span_id: Optional[UUID] = None

    def _build_agent_meta(self) -> AgentMeta:
        return AgentMeta(
            agent_id=self.agent_id,
            framework="langgraph_v2",
            identity_urn=self.identity_urn,
            delegation_chain=self.delegation_chain,
        )

    async def _emit(self, event: TelemetryEvent) -> None:
        """Fire-and-forget telemetry emission — never blocks the node."""
        payload = event.model_dump(mode="json")
        try:
            if self.client:
                await self.client.post(self.ingestion_url, json=payload, timeout=2.0)
            else:
                async with httpx.AsyncClient() as c:
                    await c.post(self.ingestion_url, json=payload, timeout=2.0)
        except Exception as e:
            import logging as _log
            _log.getLogger("griffsox.node_tracer").warning(f"Telemetry emit failed: {e}")

    def node(
        self,
        operation: OperationName = OperationName.STATE_TRANSITION,
        tool_name: Optional[str] = None,
        tool_category: Optional[ToolCategory] = None,
    ) -> Callable[[_F], _F]:
        """Decorator factory for LangGraph v0.2+ StateGraph node functions."""
        def decorator(fn: _F) -> _F:
            @functools.wraps(fn)
            async def async_wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
                event_id = uuid4()
                parent = self._last_span_id
                self._last_span_id = event_id

                tool: Optional[ToolMeta] = None
                if tool_name and tool_category:
                    tool = ToolMeta(
                        name=tool_name,
                        category=tool_category,
                        call_id=str(event_id),
                        parameters=state if isinstance(state, dict) else {},
                    )

                event = TelemetryEvent(
                    event_id=event_id,
                    trace_id=self.trace_id,
                    parent_span_id=parent,
                    agent=self._build_agent_meta(),
                    operation_name=operation,
                    tool=tool,
                    payload_content=str(state)[:2048],  # cap payload size
                )

                # Emit telemetry as a background task — never blocks node execution
                asyncio.create_task(self._emit(event))

                return await fn(state, *args, **kwargs)

            @functools.wraps(fn)
            def sync_wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
                # Sync node support: run event emission in the current event loop
                event_id = uuid4()
                parent = self._last_span_id
                self._last_span_id = event_id

                tool: Optional[ToolMeta] = None
                if tool_name and tool_category:
                    tool = ToolMeta(
                        name=tool_name,
                        category=tool_category,
                        call_id=str(event_id),
                        parameters=state if isinstance(state, dict) else {},
                    )

                event = TelemetryEvent(
                    event_id=event_id,
                    trace_id=self.trace_id,
                    parent_span_id=parent,
                    agent=self._build_agent_meta(),
                    operation_name=operation,
                    tool=tool,
                    payload_content=str(state)[:2048],
                )

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self._emit(event))
                    else:
                        loop.run_until_complete(self._emit(event))
                except Exception:
                    pass  # telemetry must never block the agent node

                return fn(state, *args, **kwargs)

            if asyncio.iscoroutinefunction(fn):
                return async_wrapper  # type: ignore[return-value]
            return sync_wrapper  # type: ignore[return-value]

        return decorator
