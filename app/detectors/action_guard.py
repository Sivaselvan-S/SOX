import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from app.schemas.action_guard import (
    ActionRule,
    ActionGuardResult,
    GuardOutcome,
    ConditionRule,
)

logger = logging.getLogger("griffsox.action_guard")

# Resolve action_rules.yaml relative to the project root (parent of app/)
# This works regardless of CWD — safe for Docker/AWS deployments.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_RULES_PATH = _PROJECT_ROOT / "action_rules.yaml"


class ActionRuleLoader:
    """Loads declarative action guardrail rules from YAML file."""

    @classmethod
    def load(cls, file_path: Optional[str] = None) -> List[ActionRule]:
        if file_path:
            path = Path(file_path)
            # If relative path given, resolve against project root
            if not path.is_absolute():
                path = _PROJECT_ROOT / file_path
        else:
            path = _DEFAULT_RULES_PATH

        if not path.exists():
            logger.warning(f"Action rules file '{path}' not found. Using empty ruleset.")
            return []

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            rules_raw = raw.get("rules", [])
            rules = [ActionRule(**r) for r in rules_raw]
            logger.info(f"Loaded {len(rules)} action guardrail rules from '{path}'.")
            return rules
        except Exception as e:
            logger.error(f"Failed to load action rules from '{path}': {e}")
            return []

    @classmethod
    def save(cls, rules: List[ActionRule], file_path: Optional[str] = None) -> bool:
        if file_path:
            path = Path(file_path)
            if not path.is_absolute():
                path = _PROJECT_ROOT / file_path
        else:
            path = _DEFAULT_RULES_PATH

        try:
            dict_rules = [r.model_dump(mode="json") for r in rules]
            content = yaml.safe_dump({"rules": dict_rules}, sort_keys=False)
            path.write_text(content, encoding="utf-8")
            logger.info(f"Saved {len(rules)} action guardrail rules to '{path}'.")
            return True
        except Exception as e:
            logger.error(f"Failed to save action rules to '{path}': {e}")
            return False


class ActionGuardEngine:
    """Pre-execution action evaluator for agent tool calls."""

    def __init__(self, rules: Optional[List[ActionRule]] = None, dry_run: bool = False):
        self.rules = rules if rules is not None else []
        self.dry_run = dry_run

    @classmethod
    def from_settings(cls) -> "ActionGuardEngine":
        from app.core.config import settings
        from app.api.v1.action_audit import audit_manager
        rules = ActionRuleLoader.load(settings.ACTION_RULES_PATH)
        return cls(rules=rules, dry_run=audit_manager.dry_run)

    def _evaluate_condition(self, condition: ConditionRule, params: Dict[str, Any]) -> bool:
        param_value = params.get(condition.param)
        op = condition.operator.lower()
        target = condition.value

        if param_value is None:
            return False

        try:
            if op == ">":
                return float(param_value) > float(target)
            elif op == "<":
                return float(param_value) < float(target)
            elif op == "==":
                return str(param_value) == str(target)
            elif op == "!=":
                return str(param_value) != str(target)
            elif op == "contains":
                return str(target).lower() in str(param_value).lower()
            elif op == "not_in":
                domain_list = [str(x).lower() for x in target] if isinstance(target, list) else [str(target).lower()]
                return str(param_value).lower() not in domain_list
            elif op == "in":
                domain_list = [str(x).lower() for x in target] if isinstance(target, list) else [str(target).lower()]
                return str(param_value).lower() in domain_list
        except Exception as e:
            logger.warning(f"Error evaluating condition '{op}' on param '{condition.param}': {e}")
            return False

        return False

    def evaluate(self, tool_name: str, parameters: Dict[str, Any]) -> ActionGuardResult:
        """Evaluate pre-execution tool call against action ruleset."""
        for rule in self.rules:
            if rule.tool == tool_name and self._evaluate_condition(rule.condition, parameters):
                logger.info(
                    f"Action Guardrail Matched: Rule '{rule.id}' ({rule.name}) -> Outcome: {rule.outcome.value.upper()}"
                )
                return ActionGuardResult(
                    outcome=rule.outcome,
                    matched_rule=rule,
                    reason=rule.reason,
                    dry_run=self.dry_run,
                )

        return ActionGuardResult(
            outcome=GuardOutcome.ALLOW,
            matched_rule=None,
            reason="Action allowed by default (no guardrail rule matched).",
            dry_run=self.dry_run,
        )
