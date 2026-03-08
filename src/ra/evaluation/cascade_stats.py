"""Cascade funnel statistics and completion tracking (Phase 2).

Provides:

1. cascade_funnel(results, timeframe, dep_graph) — Multi-level funnel:
   - Per-level counts (leaf, composite, terminal)
   - Conversion rates between levels (e.g., displacement → MSS)
   - Level ordering: leaf → composite → terminal

2. cascade_completion(results, timeframe, dep_graph) — Chain tracking:
   - Traces upstream_refs chains for composite/terminal detections
   - Reports complete_count vs total_count per composite primitive

Handles zero-detection edge cases (no division by zero, returns 0).
"""

import logging
from collections import defaultdict
from typing import Any

from ra.engine.base import DetectionResult

logger = logging.getLogger(__name__)

# Primitives classified by their cascade role
_LEAF_PRIMITIVES = frozenset({
    "fvg", "ifvg", "bpr", "swing_points", "displacement",
    "session_liquidity", "asia_range", "reference_levels", "equal_hl",
})

_TERMINAL_PRIMITIVES = frozenset({
    "liquidity_sweep",
})

# Composite = everything else that has upstream dependencies and is not terminal
# (mss, order_block, htf_liquidity, ote)

# Key cascade conversion relationships.
# Maps composite → list of upstream primitives to compute conversion rates from.
_CONVERSION_RELATIONSHIPS: dict[str, list[str]] = {
    "mss": ["displacement", "swing_points"],
    "order_block": ["mss", "displacement"],
    "ote": ["mss"],
    "htf_liquidity": ["swing_points"],
    "liquidity_sweep": ["displacement", "swing_points"],
}


def _classify_level_type(
    primitive: str, dep_graph: dict[str, list[str]]
) -> str:
    """Classify a primitive as leaf, composite, or terminal.

    Args:
        primitive: Primitive name.
        dep_graph: Dependency graph (primitive -> list of upstream).

    Returns:
        "leaf", "composite", or "terminal".
    """
    if primitive in _TERMINAL_PRIMITIVES:
        return "terminal"

    upstream = dep_graph.get(primitive, [])
    if not upstream:
        return "leaf"

    # Check if it's in the known leaf set (overrides graph)
    if primitive in _LEAF_PRIMITIVES:
        return "leaf"

    return "composite"


def cascade_funnel(
    results: dict[str, dict[str, DetectionResult]],
    timeframe: str,
    dep_graph: dict[str, list[str]],
) -> dict[str, Any]:
    """Compute cascade funnel statistics for a given timeframe.

    Args:
        results: Cascade results dict (primitive -> tf -> DetectionResult).
        timeframe: Timeframe to analyze (e.g., "5m").
        dep_graph: Dependency graph (primitive -> list of upstream names).

    Returns:
        Dict with:
            timeframe: str
            levels: list of level dicts, ordered leaf → composite → terminal
                Each level: {name, count, type, conversion_rates?}
    """
    # Collect primitives that have results for this timeframe
    available_primitives = set()
    for prim, tf_dict in results.items():
        if timeframe in tf_dict:
            available_primitives.add(prim)

    # Build level info for each primitive
    leaf_levels: list[dict[str, Any]] = []
    composite_levels: list[dict[str, Any]] = []
    terminal_levels: list[dict[str, Any]] = []

    for prim in sorted(available_primitives):
        det_result = results[prim][timeframe]
        count = len(det_result.detections)
        level_type = _classify_level_type(prim, dep_graph)

        level = {
            "name": prim,
            "count": count,
            "type": level_type,
        }

        # Compute conversion rates for composite and terminal levels
        if level_type in ("composite", "terminal"):
            conversion_rates = _compute_conversion_rates(
                prim, count, results, timeframe, dep_graph
            )
            level["conversion_rates"] = conversion_rates

        if level_type == "leaf":
            leaf_levels.append(level)
        elif level_type == "composite":
            composite_levels.append(level)
        else:
            terminal_levels.append(level)

    # Ordered: leaf → composite → terminal
    levels = leaf_levels + composite_levels + terminal_levels

    return {
        "timeframe": timeframe,
        "levels": levels,
    }


def _compute_conversion_rates(
    primitive: str,
    count: int,
    results: dict[str, dict[str, DetectionResult]],
    timeframe: str,
    dep_graph: dict[str, list[str]],
) -> dict[str, float]:
    """Compute conversion rates from upstream primitives.

    For each upstream primitive in the dependency graph (or known
    conversion relationships), compute:
        rate = this_count / upstream_count

    Returns dict mapping "from_{upstream}" -> rate.
    """
    rates: dict[str, float] = {}

    # Get upstream primitives from the known relationships,
    # falling back to the dependency graph
    upstream_list = _CONVERSION_RELATIONSHIPS.get(
        primitive, dep_graph.get(primitive, [])
    )

    for upstream in upstream_list:
        # Get upstream count for the same timeframe
        upstream_result = results.get(upstream, {}).get(timeframe)
        if upstream_result is None:
            # Try "global" for global primitives
            upstream_result = results.get(upstream, {}).get("global")

        upstream_count = len(upstream_result.detections) if upstream_result else 0

        if upstream_count > 0:
            rate = count / upstream_count
        else:
            rate = 0.0

        rates[f"from_{upstream}"] = round(rate, 4)

    return rates


def cascade_completion(
    results: dict[str, dict[str, DetectionResult]],
    timeframe: str,
    dep_graph: dict[str, list[str]],
) -> dict[str, Any]:
    """Track cascade completion chains via upstream_refs.

    For each composite/terminal primitive, traces the upstream_refs chain
    back to leaf detections. A "complete" chain means the detection has
    upstream_refs that can be resolved all the way to leaf primitives.

    Args:
        results: Cascade results dict.
        timeframe: Timeframe to analyze.
        dep_graph: Dependency graph.

    Returns:
        Dict with:
            chains: {primitive: {total_count, complete_count, incomplete_count}}
    """
    # Build a set of all detection IDs for fast lookup
    all_detection_ids: set[str] = set()
    for prim, tf_dict in results.items():
        det_result = tf_dict.get(timeframe) or tf_dict.get("global")
        if det_result:
            for d in det_result.detections:
                all_detection_ids.add(d.id)

    chains: dict[str, dict[str, Any]] = {}

    for prim in sorted(results.keys()):
        level_type = _classify_level_type(prim, dep_graph)
        if level_type == "leaf":
            continue  # Leaf primitives don't have chains

        det_result = results[prim].get(timeframe)
        if det_result is None:
            continue

        total = len(det_result.detections)
        complete = 0

        for d in det_result.detections:
            if _is_chain_complete(d, results, timeframe, dep_graph, all_detection_ids):
                complete += 1

        chains[prim] = {
            "total_count": total,
            "complete_count": complete,
            "incomplete_count": total - complete,
        }

    return {"chains": chains}


def _is_chain_complete(
    detection,
    results: dict[str, dict[str, DetectionResult]],
    timeframe: str,
    dep_graph: dict[str, list[str]],
    all_detection_ids: set[str],
    max_depth: int = 10,
) -> bool:
    """Check if a detection's upstream chain is complete.

    A chain is "complete" if either:
    1. The detection has upstream_refs and all of them exist in the results
    2. The detection has no upstream_refs but the primitive has upstream
       dependencies that have detections (structural completion)

    This handles the current state where upstream_refs may be empty by
    falling back to structural completion checking.

    Args:
        detection: The detection to check.
        results: All cascade results.
        timeframe: Current timeframe.
        dep_graph: Dependency graph.
        all_detection_ids: Set of all detection IDs for fast lookup.
        max_depth: Maximum recursion depth to prevent infinite loops.

    Returns:
        True if the chain is considered complete.
    """
    if max_depth <= 0:
        return False

    primitive = detection.id.split("_")[0]

    # If detection has explicit upstream_refs, verify they all exist
    if detection.upstream_refs:
        for ref_id in detection.upstream_refs:
            if ref_id not in all_detection_ids:
                return False
        return True

    # Fallback: structural completion — check if all upstream primitives
    # have at least one detection for this timeframe
    upstream = dep_graph.get(primitive, [])
    if not upstream:
        return True  # Leaf = always complete

    for up_prim in upstream:
        up_result = results.get(up_prim, {}).get(timeframe)
        if up_result is None:
            up_result = results.get(up_prim, {}).get("global")
        if up_result is None or len(up_result.detections) == 0:
            return False

    return True
