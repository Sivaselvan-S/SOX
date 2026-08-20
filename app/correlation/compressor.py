import logging
from typing import List, Dict, Any

import networkx as nx

logger = logging.getLogger("griffsox.compressor")



class GraphCompressor:
    """Semantic graph compressor collapsing benign cyclical iterations and retry loops into single meta-nodes."""

    @classmethod
    def compress(cls, graph: nx.DiGraph) -> nx.DiGraph:
        if graph.number_of_nodes() <= 1:
            return graph.copy()

        compressed = graph.copy()
        
        # Sort nodes topologically or by timestamp if available
        try:
            nodes_in_order = list(nx.topological_sort(compressed))
        except nx.NetworkXUnfeasible:
            # Graph has cycles, fallback to node sequence
            nodes_in_order = list(compressed.nodes())

        if not nodes_in_order:
            return compressed

        # Identify consecutive nodes with identical signature and benign detections
        consecutive_groups: List[List[str]] = []
        current_group: List[str] = [nodes_in_order[0]]

        for node_id in nodes_in_order[1:]:
            prev_node_id = current_group[-1]
            prev_attrs = compressed.nodes[prev_node_id]
            curr_attrs = compressed.nodes[node_id]

            # Check if curr node is child of prev node
            is_linear_successor = compressed.has_edge(prev_node_id, node_id)

            # Check signature similarity (same operation, same tool, benign detections)
            same_op = prev_attrs.get("operation_name") == curr_attrs.get("operation_name")
            same_tool = prev_attrs.get("tool_name") == curr_attrs.get("tool_name")
            same_cat = prev_attrs.get("tool_category") == curr_attrs.get("tool_category")
            
            # Check if both are benign (no fastpath match, no policy violation, no judge anomaly)
            prev_det = prev_attrs.get("detections", {})
            curr_det = curr_attrs.get("detections", {})
            prev_benign = cls._is_benign(prev_det)
            curr_benign = cls._is_benign(curr_det)

            if is_linear_successor and same_op and same_tool and same_cat and prev_benign and curr_benign:
                current_group.append(node_id)
            else:
                if len(current_group) > 1:
                    consecutive_groups.append(current_group)
                current_group = [node_id]

        if len(current_group) > 1:
            consecutive_groups.append(current_group)

        # Collapse groups into meta-nodes.
        # Bug fix: process groups in REVERSE order so that earlier collapses
        # do not invalidate node IDs still referenced by subsequent groups.
        for group in reversed(consecutive_groups):
            # Guard: all nodes in this group must still exist (previous iteration may have removed some)
            if not all(compressed.has_node(nid) for nid in group):
                logger.warning(f"Skipping compression of group {group}: one or more nodes already removed.")
                continue

            first_node_id = group[0]
            last_node_id = group[-1]
            first_attrs = compressed.nodes[first_node_id]

            meta_node_id = f"meta_{first_node_id}_to_{last_node_id}"
            meta_attrs: Dict[str, Any] = dict(first_attrs)
            meta_attrs.update({
                "event_id": meta_node_id,
                "is_meta_node": True,
                "compressed_count": len(group),
                "collapsed_node_ids": group,
            })

            # Preserve incoming edges to first node and outgoing edges from last node
            in_edges = list(compressed.in_edges(first_node_id))
            out_edges = list(compressed.out_edges(last_node_id))

            compressed.add_node(meta_node_id, **meta_attrs)

            for u, _ in in_edges:
                if u not in group:
                    compressed.add_edge(u, meta_node_id)

            for _, v in out_edges:
                if v not in group:
                    compressed.add_edge(meta_node_id, v)

            # Remove collapsed original nodes
            for nid in group:
                compressed.remove_node(nid)

        return compressed

    @staticmethod
    def _is_benign(detections: dict) -> bool:
        """Check if node detections indicate a benign operation."""
        fp = detections.get("fastpath") or {}
        pol = detections.get("policy") or {}
        judge = detections.get("judge") or {}

        if fp.get("matched", False):
            return False
        if pol.get("allowed", True) is False:
            return False
        if judge.get("is_anomalous", False):
            return False

        return True
