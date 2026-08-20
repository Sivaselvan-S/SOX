import json
import logging
from typing import Dict, Set, Optional
from pathlib import Path

from pydantic import BaseModel

from app.schemas.telemetry import TelemetryEvent, ToolCategory, OperationName

logger = logging.getLogger("griffsox.policy")

MAX_DELEGATION_CHAIN_DEPTH = 5


class PolicyViolation(Exception):
    """Raised when an identity attempts an unauthorized tool execution."""

    def __init__(self, identity_urn: str, attempted_category: ToolCategory, allowed_categories: Set[ToolCategory]):
        self.identity_urn = identity_urn
        self.attempted_category = attempted_category
        self.allowed_categories = allowed_categories
        msg = f"Identity '{identity_urn}' violated policy by executing tool category '{attempted_category.value}'. Allowed: {[c.value for c in allowed_categories]}"
        super().__init__(msg)


class PolicyResult(BaseModel):
    allowed: bool
    identity_urn: str
    tool_category: Optional[ToolCategory] = None
    reason: Optional[str] = None


DEFAULT_POLICIES: Dict[str, Set[ToolCategory]] = {
    "spiffe://prod/read-only-agent": {ToolCategory.READ},
    "spiffe://prod/finance-agent": {ToolCategory.READ, ToolCategory.DATABASE_WRITE},
    "spiffe://prod/egress-agent": {ToolCategory.READ, ToolCategory.FILE_EGRESS},
    "spiffe://prod/admin-agent": {
        ToolCategory.READ,
        ToolCategory.DATABASE_WRITE,
        ToolCategory.FILE_EGRESS,
        ToolCategory.SYSTEM_EXEC,
    },
}


class PolicyLoader:
    """Loads RBAC policy from a JSON file or falls back to DEFAULT_POLICIES."""

    @classmethod
    def load(cls, policy_path: Optional[str] = None) -> Dict[str, Set[ToolCategory]]:
        """Load policy from JSON file. Falls back to DEFAULT_POLICIES if path is None or file missing."""
        if not policy_path:
            return DEFAULT_POLICIES

        path = Path(policy_path)
        if not path.exists():
            logger.warning(f"RBAC policy file '{policy_path}' not found. Using DEFAULT_POLICIES.")
            return DEFAULT_POLICIES

        try:
            raw: Dict[str, list] = json.loads(path.read_text(encoding="utf-8"))
            loaded: Dict[str, Set[ToolCategory]] = {}
            for urn, cats in raw.items():
                try:
                    loaded[urn] = {ToolCategory(c) for c in cats}
                except ValueError as e:
                    logger.warning(f"Skipping invalid tool category in RBAC policy for '{urn}': {e}")
            logger.info(f"Loaded RBAC policy from '{policy_path}' ({len(loaded)} identities).")
            return loaded
        except Exception as e:
            logger.error(f"Failed to parse RBAC policy file '{policy_path}': {e}. Using DEFAULT_POLICIES.")
            return DEFAULT_POLICIES


class PolicyEngine:
    """Rego-lite deterministic RBAC policy engine."""

    def __init__(self, policies: Optional[Dict[str, Set[ToolCategory]]] = None):
        self.policies = policies if policies is not None else DEFAULT_POLICIES

    @classmethod
    def from_settings(cls) -> "PolicyEngine":
        """Construct from app settings — the standard production factory."""
        from app.core.config import settings
        policies = PolicyLoader.load(settings.RBAC_POLICY_PATH)
        return cls(policies=policies)

    def evaluate(self, event: TelemetryEvent, raise_on_violation: bool = False) -> PolicyResult:
        # Policy checks only apply to tool executions with a tool metadata
        if event.operation_name != OperationName.EXECUTE_TOOL or not event.tool:
            return PolicyResult(allowed=True, identity_urn=event.agent.identity_urn)

        identity_urn = event.agent.identity_urn
        attempted_category = event.tool.category

        allowed_categories = self.policies.get(identity_urn)

        # If identity is not explicitly registered, log a warning and default to restrictive policy (READ only)
        if allowed_categories is None:
            logger.warning(
                f"Unregistered identity URN '{identity_urn}' — applying default restrictive READ-only policy."
            )
            allowed_categories = {ToolCategory.READ}

        # Advisory: delegation chains longer than MAX_DELEGATION_CHAIN_DEPTH are a privilege escalation signal
        chain_depth = len(event.agent.delegation_chain)
        if chain_depth > MAX_DELEGATION_CHAIN_DEPTH:
            logger.warning(
                f"Delegation chain depth {chain_depth} exceeds threshold {MAX_DELEGATION_CHAIN_DEPTH} "
                f"for identity '{identity_urn}' — possible privilege escalation."
            )

        if attempted_category not in allowed_categories:
            reason = (
                f"Unauthorized tool category '{attempted_category.value}' for identity URN '{identity_urn}'"
            )
            if raise_on_violation:
                raise PolicyViolation(
                    identity_urn=identity_urn,
                    attempted_category=attempted_category,
                    allowed_categories=allowed_categories,
                )
            return PolicyResult(
                allowed=False,
                identity_urn=identity_urn,
                tool_category=attempted_category,
                reason=reason,
            )

        return PolicyResult(
            allowed=True,
            identity_urn=identity_urn,
            tool_category=attempted_category,
        )
