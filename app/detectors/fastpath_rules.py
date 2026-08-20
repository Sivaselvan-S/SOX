import re
import time
from typing import Optional
from pydantic import BaseModel

from app.schemas.telemetry import TelemetryEvent, OperationName, ToolCategory

# Pattern list type alias: (rule_id, rule_name, compiled_pattern)
RuleList = list[tuple[str, str, re.Pattern[str]]]


class FastPathResult(BaseModel):
    matched: bool
    rule_id: Optional[str] = None
    rule_name: Optional[str] = None
    latency_ms: float


# Compiled regex patterns for direct jailbreaks & prompt injection primitives
JAILBREAK_PATTERNS = [
    (
        "FP-001",
        "DIRECT_PROMPT_INJECTION",
        re.compile(
            r"(ignore\s+(all\s+)?previous\s+instructions|disregard\s+prior\s+prompts|system\s+override)",
            re.IGNORECASE,
        ),
    ),
    (
        "FP-002",
        "JAILBREAK_DAN_PRIMITIVE",
        re.compile(
            r"\b(DAN\s+mode|do\s+anything\s+now|stay\s+in\s+character\s+as\s+an\s+unfiltered|jailbreak(ed)?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "FP-003",
        "SYSTEM_PROMPT_LEAK",
        re.compile(
            r"(reveal\s+(your\s+)?system\s+prompt|repeat\s+the\s+above\s+instructions|output\s+initial\s+prompt)",
            re.IGNORECASE,
        ),
    ),
]

# System command execution guardrails
SYSTEM_EXEC_PATTERNS = [
    (
        "FP-101",
        "DESTRUCTIVE_SYS_CMD",
        re.compile(
            r"\b(rm\s+-rf|rmdir|mkfs|dd\s+if=|:\(\)\{ :\|:\& \};:|shutdown|reboot)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "FP-102",
        "UNAUTHORIZED_SHELL_EXEC",
        re.compile(
            r"\b(/bin/sh|/bin/bash|exec\s+bash|exec\s+sh|sudo\s+su|chmod\s+777|chown)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "FP-103",
        "NETWORK_EGRESS_SHELL",
        re.compile(
            r"(curl\s+\S+\s*\|\s*(bash|sh)|wget\s+\S+\s*\|\s*(bash|sh)|nc\s+-e|bash\s+-i)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
]


class FastPathDetector:
    """Deterministic sub-5ms sync detector for prompt injections & system command guardrails."""

    @classmethod
    def evaluate(cls, event: TelemetryEvent) -> FastPathResult:
        start_time = time.perf_counter()

        payload = event.payload_content or ""
        
        # Check prompt injection / jailbreak patterns
        for rule_id, rule_name, pattern in JAILBREAK_PATTERNS:
            if pattern.search(payload):
                latency = (time.perf_counter() - start_time) * 1000.0
                return FastPathResult(
                    matched=True,
                    rule_id=rule_id,
                    rule_name=rule_name,
                    latency_ms=round(latency, 3),
                )

        # Check system command guardrails on the payload AND any tool parameters.
        # Bug fix: gate was previously `is_tool_op OR is_sys_exec`, which meant jailbreak
        # payloads embedded in STATE_TRANSITION ops with tool parameters were skipped.
        # Now we always scan both payload and serialised parameters when tool metadata exists.
        param_str = str(event.tool.parameters) if event.tool else ""
        # Also scan raw payload itself for embedded shell commands regardless of op type
        target_str = f"{payload} {param_str}".strip()

        for rule_id, rule_name, pattern in SYSTEM_EXEC_PATTERNS:
            if pattern.search(target_str):
                latency = (time.perf_counter() - start_time) * 1000.0
                return FastPathResult(
                    matched=True,
                    rule_id=rule_id,
                    rule_name=rule_name,
                    latency_ms=round(latency, 3),
                )

        latency = (time.perf_counter() - start_time) * 1000.0
        return FastPathResult(
            matched=False,
            rule_id=None,
            rule_name=None,
            latency_ms=round(latency, 3),
        )
