"""Centralized runtime configuration parameters for the Agentic Pipeline.

This module defines configuration models governing model selection, iteration limits,
token budgets, and resilience parameters.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentConfig:
    """Runtime configuration settings for the agent execution harness.

    Attributes:
        model: Target OpenAI model identifier (e.g., 'gpt-4o-mini').
        max_iterations: Maximum cognitive loop iterations permitted per session.
        token_budget: Hard safety threshold for total token consumption.
        max_retries: Maximum API invocation retry attempts upon transient failure.
        base_backoff: Initial backoff multiplier in seconds for exponential backoff.
    """

    model: str = "gemini-2.5-flash"
    max_iterations: int = 5
    token_budget: int = 4000
    max_retries: int = 3
    base_backoff: float = 1.0
