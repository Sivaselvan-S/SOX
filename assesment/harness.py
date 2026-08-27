"""Execution harness managing retries, infinite loop traps, token budgets, and structured logging.

This module provides the `ProductionAgentHarness` production wrapper that enforces
resilience, cost controls, cognitive execution monitoring, and structured JSON telemetry.
"""

from __future__ import annotations

import collections
import json
import logging
import random
import sys
import time
import traceback
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from config import AgentConfig
from memory import AgentMemory, format_memory_for_prompt
from tools import TOOL_HANDLERS, TOOL_SCHEMAS
from agent_loop import act, perceive, reflect


class JsonStructuredFormatter(logging.Formatter):
    """Custom logging formatter that outputs log records as standard JSON strings."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record into a valid structured JSON string."""
        log_data: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Ingest custom structured attributes attached to the LogRecord
        if hasattr(record, "event_type"):
            log_data["event_type"] = record.event_type
        if hasattr(record, "payload"):
            log_data["payload"] = record.payload
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def get_structured_logger(name: str = "agent_harness") -> logging.Logger:
    """Configure and retrieve a JSON structured logger instance.

    Args:
        name: Name identifier for the logger instance.

    Returns:
        Configured `logging.Logger` outputting structured JSON to stdout.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonStructuredFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


class ProductionAgentHarness:
    """Production wrapper providing retries, guardrails, and telemetry for the cognitive agent."""

    def __init__(self, config: AgentConfig, memory: AgentMemory) -> None:
        """Initialize the Production Agent Harness.

        Args:
            config: Runtime configuration containing timeouts, budgets, and retry limits.
            memory: Stateful memory instance managing episodic and preference records.
        """
        self.config = config
        self.memory = memory
        self.logger = get_structured_logger()
        self._recent_actions: Deque[str] = collections.deque(maxlen=3)

    def log_event(self, event_type: str, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Emit a structured JSON log entry with event metadata.

        Args:
            event_type: Categorical event identifier (e.g., 'iteration_step', 'guardrail_trigger').
            message: Human-readable summary string.
            payload: Structured dictionary containing telemetry metrics or contextual data.
        """
        extra = {
            "event_type": event_type,
            "payload": payload or {},
        }
        self.logger.info(message, extra=extra)

    def execute_with_retry(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a callable with exponential backoff and jitter on exceptions.

        Backoff formula: `base_backoff * (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)`

        Args:
            func: The callable to invoke.
            *args: Positional arguments forwarded to func.
            **kwargs: Keyword arguments forwarded to func.

        Returns:
            The return value of the successful invocation.

        Raises:
            Exception: The final caught exception if all retry attempts are exhausted.
        """
        start_time = time.perf_counter()
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                self.log_event(
                    event_type="api_call_success",
                    message=f"API call succeeded on attempt {attempt}",
                    payload={
                        "attempt": attempt,
                        "latency_ms": round(latency_ms, 2),
                    },
                )
                return result

            except Exception as exc:
                last_exception = exc
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                if attempt < self.config.max_retries:
                    backoff_delay = (
                        self.config.base_backoff * (2 ** (attempt - 1))
                        + random.uniform(0.1, 0.5)
                    )

                    self.log_event(
                        event_type="retry_triggered",
                        message=f"Attempt {attempt} failed; retrying in {backoff_delay:.2f}s",
                        payload={
                            "attempt": attempt,
                            "max_retries": self.config.max_retries,
                            "backoff_delay_seconds": round(backoff_delay, 2),
                            "error": str(exc),
                            "trace": traceback.format_exc(),
                        },
                    )
                    time.sleep(backoff_delay)
                else:
                    self.log_event(
                        event_type="guardrail_trigger",
                        message=f"Exhausted all {self.config.max_retries} retries",
                        payload={
                            "attempt": attempt,
                            "total_latency_ms": round(latency_ms, 2),
                            "error": str(exc),
                        },
                    )

        if last_exception is not None:
            raise last_exception

    def detect_infinite_loop(self, action_signature: str) -> bool:
        """Monitor recent agent action signatures and detect infinite repetitive loops.

        Triggers when 3 identical consecutive actions occur.

        Args:
            action_signature: String signature identifying the action (e.g. 'tool:diff').

        Returns:
            True if 3 consecutive identical actions have occurred; False otherwise.
        """
        self._recent_actions.append(action_signature)

        if len(self._recent_actions) == 3:
            if (
                self._recent_actions[0]
                == self._recent_actions[1]
                == self._recent_actions[2]
                == action_signature
            ):
                self.log_event(
                    event_type="loop_stuck_detected",
                    message=f"Infinite loop detected for action '{action_signature}'",
                    payload={"action_signature": action_signature, "occurrences": 3},
                )
                return True

        return False

    def run_monitored_session(
        self,
        session_id: str,
        text_a: str,
        text_b: str,
        client: Any,
    ) -> Dict[str, Any]:
        """Execute a fully monitored, safe agent comparison session with memory injection.

        Integrates memory recall, token budget tracking, loop-stuck detection,
        and structured telemetry.

        Args:
            session_id: The session identifier.
            text_a: Baseline text.
            text_b: Comparison text.
            client: OpenAI or compatible API client instance.

        Returns:
            Dictionary summarizing session execution status, tokens, iterations, and results.
        """
        # Clear loop detection history for new session
        self._recent_actions.clear()

        # Step 1: Memory Recall & System Prompt Preparation
        recalled = self.memory.recall_relevant_context(
            session_id=session_id,
            query="rules preferences comparison instructions style",
            top_k=3,
            client=client,
        )
        memory_prompt_block = format_memory_for_prompt(recalled)

        base_system = (
            "You are an expert Text Comparison Agent. Your objective is to thoroughly compare Text A "
            "and Text B, identify differences, categorize each discrepancy using the "
            "`categorize_discrepancy` tool, and provide a final comprehensive summary highlighting the key differences."
        )
        full_system_prompt = f"{base_system}\n{memory_prompt_block}" if memory_prompt_block else base_system

        initial_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": full_system_prompt},
            {
                "role": "user",
                "content": f"Please compare the following texts and highlight differences.\n\n--- TEXT A ---\n{text_a}\n\n--- TEXT B ---\n{text_b}",
            },
        ]

        state: Dict[str, Any] = {
            "session_id": session_id,
            "messages": initial_messages,
            "iterations": 0,
            "done": False,
            "status": "RUNNING",
            "result": None,
            "discrepancies": [],
            "recalled_memories": recalled,
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

        # Step 2: Monitored Execution Loop
        while not state["done"] and state["iterations"] < self.config.max_iterations:
            state["iterations"] += 1
            iteration_start = time.perf_counter()

            self.log_event(
                event_type="iteration_step",
                message=f"Starting cognitive iteration {state['iterations']}/{self.config.max_iterations}",
                payload={
                    "session_id": session_id,
                    "iteration": state["iterations"],
                    "total_tokens_spent": state["token_usage"]["total_tokens"],
                },
            )

            # Reason via execute_with_retry
            def _dispatch_reason() -> Any:
                kwargs: Dict[str, Any] = {
                    "model": self.config.model,
                    "messages": state["messages"],
                    "tools": TOOL_SCHEMAS,
                    "tool_choice": "auto",
                }
                response = client.chat.completions.create(**kwargs)
                return response

            try:
                completion_response = self.execute_with_retry(_dispatch_reason)
            except Exception as exc:
                state["status"] = "API_ERROR"
                state["result"] = f"Aborted due to persistent API failure: {str(exc)}"
                break

            decision_message = completion_response.choices[0].message

            # Track token usage
            usage = getattr(completion_response, "usage", None)
            if usage:
                state["token_usage"]["prompt_tokens"] += getattr(usage, "prompt_tokens", 0)
                state["token_usage"]["completion_tokens"] += getattr(usage, "completion_tokens", 0)
                state["token_usage"]["total_tokens"] += getattr(usage, "total_tokens", 0)

            # Guardrail: Token Budget Check
            if state["token_usage"]["total_tokens"] > self.config.token_budget:
                self.log_event(
                    event_type="guardrail_trigger",
                    message="Token budget exceeded safety limit",
                    payload={
                        "token_budget": self.config.token_budget,
                        "consumed_tokens": state["token_usage"]["total_tokens"],
                    },
                )
                state["status"] = "GUARDRAIL_TRIGGERED: TOKEN_BUDGET_EXCEEDED"
                state["result"] = "Terminated early: Exceeded token budget limit."
                break

            # Append assistant decision to message history
            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            if getattr(decision_message, "content", None):
                assistant_msg["content"] = decision_message.content
            if getattr(decision_message, "tool_calls", None):
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in decision_message.tool_calls
                ]
            state["messages"].append(assistant_msg)

            # Act Step
            tool_name, tool_call_id, action_result = act(
                decision_message=decision_message,
                tool_handlers=TOOL_HANDLERS,
            )

            if tool_name and tool_call_id:
                # Guardrail: Check for Infinite Action Loop
                action_signature = f"tool:{tool_name}"
                if self.detect_infinite_loop(action_signature):
                    state["status"] = "GUARDRAIL_TRIGGERED: INFINITE_LOOP_DETECTED"
                    state["result"] = f"Terminated early: Repeated tool action '{action_signature}' detected."
                    break

                if tool_name == "categorize_discrepancy" and action_result:
                    try:
                        parsed = json.loads(action_result)
                        state["discrepancies"].append(parsed)
                    except Exception:
                        pass

                # Ingest observation into perception
                perceive(
                    state=state,
                    observation=action_result,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                )
                reflect(state=state, final_content=None, action_result=action_result)

            else:
                # Direct response / summary
                reflect(state=state, final_content=action_result, action_result=None)
                if state.get("done"):
                    state["status"] = "SUCCESS"

            step_duration = (time.perf_counter() - iteration_start) * 1000.0
            self.log_event(
                event_type="iteration_step",
                message=f"Completed cognitive iteration {state['iterations']}",
                payload={
                    "iteration": state["iterations"],
                    "latency_ms": round(step_duration, 2),
                    "done": state.get("done", False),
                },
            )

        if state["status"] == "RUNNING":
            if state["done"]:
                state["status"] = "SUCCESS"
            else:
                state["status"] = "MAX_ITERATIONS_REACHED"
                if not state["result"]:
                    state["result"] = "Maximum iterations reached before final output completion."

        return state
