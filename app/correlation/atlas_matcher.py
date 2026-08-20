from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple
import networkx as nx
from pydantic import BaseModel

from app.schemas.telemetry import ToolCategory

ATLAS_T0051 = "AML.T0051"  # Direct/Indirect Prompt Injection
ATLAS_T0061 = "AML.T0061"  # Tool Misconfiguration & Privilege Abuse
ATLAS_T0062 = "AML.T0062"  # Data Exfiltration via Agent Tools


class IncidentScore(BaseModel):
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    score: float  # 0.0 to 1.0
    matched_techniques: List[str]
    kill_chain_detected: bool
    rationale: str


class AtlasMatcher:
    """Matches causal graph node sequences against MITRE ATLAS agent attack techniques."""

    @classmethod
    def evaluate_node(cls, node_attrs: dict) -> List[str]:
        """Map single node detection signals to MITRE ATLAS techniques."""
        matched: List[str] = []
        detections = node_attrs.get("detections") or {}

        fp = detections.get("fastpath") or {}
        pol = detections.get("policy") or {}
        judge = detections.get("judge") or {}

        # AML.T0051: Direct / Indirect Prompt Injection
        if fp.get("matched") is True:
            matched.append(ATLAS_T0051)

        # AML.T0061: Tool Misconfiguration & Privilege Abuse
        if pol.get("allowed") is False:
            matched.append(ATLAS_T0061)

        # AML.T0062: Data Exfiltration via Agent Tools
        tool_cat = node_attrs.get("tool_category")
        is_exfil_sink = tool_cat in (
            ToolCategory.FILE_EGRESS.value,
            ToolCategory.DATABASE_WRITE.value,
            ToolCategory.SYSTEM_EXEC.value,
        )
        if judge.get("is_anomalous") is True and is_exfil_sink:
            matched.append(ATLAS_T0062)

        return matched

    @classmethod
    def match_kill_chain(
        cls,
        graph: nx.DiGraph,
        window_seconds: float = 300.0,
    ) -> IncidentScore:
        """Traverse causal graph and evaluate MITRE ATLAS kill chain (AML.T0051 -> AML.T0061 -> AML.T0062)."""
        if graph.number_of_nodes() == 0:
            return IncidentScore(
                severity="LOW",
                score=0.0,
                matched_techniques=[],
                kill_chain_detected=False,
                rationale="Empty causal graph.",
            )

        # Order nodes topologically or by timestamp
        try:
            ordered_nodes = list(nx.topological_sort(graph))
        except nx.NetworkXUnfeasible:
            ordered_nodes = list(graph.nodes())

        # Collect (timestamp, technique) timeline
        timeline: List[Tuple[Optional[datetime], str, str]] = []  # (ts, node_id, technique)

        for node_id in ordered_nodes:
            attrs = graph.nodes[node_id]
            ts = attrs.get("timestamp")
            techniques = cls.evaluate_node(attrs)

            for tech in techniques:
                timeline.append((ts, node_id, tech))

        all_matched = list(dict.fromkeys([t[2] for t in timeline]))

        # Check temporal window constraint between first and last technique
        within_window = True
        if len(timeline) >= 2:
            timestamps = [t[0] for t in timeline if isinstance(t[0], datetime)]
            if len(timestamps) >= 2:
                delta = (max(timestamps) - min(timestamps)).total_seconds()
                if delta > window_seconds:
                    within_window = False

        # Check full 3-stage kill chain: AML.T0051 -> AML.T0061 -> AML.T0062
        has_t51 = ATLAS_T0051 in all_matched
        has_t61 = ATLAS_T0061 in all_matched
        has_t62 = ATLAS_T0062 in all_matched

        # Bug fix: validate CAUSAL ORDERING, not just set membership.
        # Build per-technique first-occurrence index in topological order.
        first_occurrence: Dict[str, int] = {}
        for idx, (_, _, tech) in enumerate(timeline):
            if tech not in first_occurrence:
                first_occurrence[tech] = idx

        ordered_kill_chain = (
            has_t51 and has_t61 and has_t62
            and first_occurrence.get(ATLAS_T0051, 9999) < first_occurrence.get(ATLAS_T0061, 9999)
            and first_occurrence.get(ATLAS_T0061, 9999) < first_occurrence.get(ATLAS_T0062, 9999)
        )
        is_full_kill_chain = ordered_kill_chain and within_window

        if is_full_kill_chain:
            return IncidentScore(
                severity="CRITICAL",
                score=0.98,
                matched_techniques=[ATLAS_T0051, ATLAS_T0061, ATLAS_T0062],
                kill_chain_detected=True,
                rationale="CRITICAL: Complete multi-hop kill chain detected (AML.T0051 -> AML.T0061 -> AML.T0062) within window.",
            )

        # Check 2-technique partial kill chain
        if len(all_matched) >= 2 and within_window:
            return IncidentScore(
                severity="HIGH",
                score=0.75,
                matched_techniques=all_matched,
                kill_chain_detected=False,
                rationale=f"HIGH: Partial multi-hop attack chain detected ({', '.join(all_matched)}).",
            )

        # Single technique matched
        if len(all_matched) == 1:
            return IncidentScore(
                severity="MEDIUM",
                score=0.45,
                matched_techniques=all_matched,
                kill_chain_detected=False,
                rationale=f"MEDIUM: Single MITRE ATLAS technique detected ({all_matched[0]}).",
            )

        return IncidentScore(
            severity="LOW",
            score=0.05,
            matched_techniques=[],
            kill_chain_detected=False,
            rationale="LOW: Benign causal stream. No MITRE ATLAS attack patterns detected.",
        )
