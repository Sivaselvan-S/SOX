"""Shared dynamic rule-parsing and discrepancy filtering engine.

Centralizes memory rule detection, semantic intent parsing, and discrepancy
filtering to prevent logic divergence between live LLM and fallback modules.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

_NEGATIVE_WORDS: Set[str] = {
    "bad", "poor", "worst", "worse", "negative", "unhappy", "failure",
    "fail", "failed", "loss", "decline", "unfriendly", "terrible", "weak",
    "broken", "decrease", "decreased", "down", "error", "risk", "threat",
    "slow", "inefficient", "toxic", "hostile", "corrupt", "denied",
    "unreliable", "insecure", "flaky", "vulnerable", "delayed", "breached", "disrupted"
}

_POSITIVE_WORDS: Set[str] = {
    "good", "great", "excellent", "best", "better", "positive", "happy",
    "success", "successful", "improve", "improved", "gain", "growth",
    "friendly", "amazing", "innovative", "leading", "robust", "stable",
    "efficient", "strong", "increase", "increased", "up", "win", "reliable",
    "fast", "compliant", "secure", "smooth", "optimal", "healthy", "delighted"
}


def parse_active_rules(system_content: str) -> Dict[str, bool]:
    """Parse active rule flags from system prompt and injected memory block."""
    sys_lower = system_content.lower()
    return {
        "negative_only": ("negative" in sys_lower or "-ve" in sys_lower) and ("only" in sys_lower or "focus" in sys_lower or "suppress" in sys_lower),
        "numerical": "numerical" in sys_lower or "budget" in sys_lower or "metric" in sys_lower,
        "high_sev": "high severity" in sys_lower or "high only" in sys_lower,
        "ignore_tone": "ignore tone" in sys_lower or "factual only" in sys_lower,
    }


def apply_rule_filter(
    discrepancies: List[Dict[str, Any]],
    rules: Dict[str, bool],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Filter discrepancies based on active rules.

    Returns:
        (filtered_discrepancies, active_rule_description_or_None)
    """
    if not discrepancies:
        return [], None

    if rules.get("negative_only"):
        filtered = [
            d for d in discrepancies
            if "Negative Sentiment Shift" in d.get("description", "") or
               "Negative" in d.get("description", "") or
               any(nw in d.get("description", "").lower() for nw in _NEGATIVE_WORDS)
        ]
        return filtered, "Focus strictly on negative word changes (neutral/mild phrasing suppressed)"

    if rules.get("numerical"):
        filtered = [
            d for d in discrepancies
            if d.get("category") in {"Factual", "Financial"} and
               ("$" in d.get("description", "") or "%" in d.get("description", "") or any(c.isdigit() for c in d.get("description", "")))
        ]
        return filtered, "Focus strictly on numerical/metric changes (stylistic shifts suppressed)"

    if rules.get("high_sev"):
        filtered = [d for d in discrepancies if d.get("severity") == "High"]
        return filtered, "High severity filter active (Medium and Low findings suppressed)"

    if rules.get("ignore_tone"):
        filtered = [d for d in discrepancies if d.get("category") != "Tone"]
        return filtered, "Tone suppression active (reporting factual/structural differences only)"

    return list(discrepancies), None
