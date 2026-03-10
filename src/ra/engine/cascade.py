"""Cascade engine: dependency-aware detector execution with caching.

Parses the dependency_graph from config, topologically sorts modules,
runs detectors in order passing upstream DetectionResults to downstream.

Features:
- Topological sort for correct execution order
- Result caching: unchanged upstream served from cache on re-run
- DAG invalidation: on_param_change(primitive) invalidates primitive +
  all transitive downstream, re-runs invalidated nodes
- DEFERRED module handling: skip gracefully, provide empty DetectionResult
"""

import copy
import hashlib
import json
import logging
from collections import defaultdict
from typing import Any, Optional

import pandas as pd

from ra.engine.base import Detection, DetectionResult, PrimitiveDetector
from ra.engine.registry import Registry

logger = logging.getLogger(__name__)


class CascadeError(Exception):
    """Raised when cascade operations fail."""


class CycleError(CascadeError):
    """Raised when dependency graph contains a cycle."""


def _topo_sort(graph: dict[str, list[str]]) -> list[str]:
    """Topological sort of dependency graph using Kahn's algorithm.

    Args:
        graph: Mapping of node -> list of upstream dependencies.

    Returns:
        List of node names in execution order (upstream first).

    Raises:
        CycleError: If the graph contains a cycle.
    """
    # Build in-degree map and adjacency (downstream) map
    in_degree: dict[str, int] = {node: 0 for node in graph}
    downstream: dict[str, list[str]] = defaultdict(list)

    for node, upstreams in graph.items():
        for up in upstreams:
            if up not in graph:
                raise CascadeError(
                    f"Dependency '{up}' of '{node}' is not in the graph. "
                    f"Available nodes: {sorted(graph.keys())}"
                )
            downstream[up].append(node)
            in_degree[node] += 1

    # Start with nodes having no dependencies
    queue = sorted(n for n, deg in in_degree.items() if deg == 0)
    order = []

    while queue:
        node = queue.pop(0)
        order.append(node)
        for child in sorted(downstream[node]):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
        # Re-sort to get deterministic order
        queue.sort()

    if len(order) != len(graph):
        remaining = set(graph.keys()) - set(order)
        raise CycleError(
            f"Dependency graph contains a cycle involving: {sorted(remaining)}"
        )

    return order


def _get_transitive_downstream(
    graph: dict[str, list[str]], nodes: set[str]
) -> set[str]:
    """Get all transitive downstream nodes from a set of starting nodes.

    Args:
        graph: Mapping of node -> list of upstream dependencies.
        nodes: Starting set of nodes to find downstream for.

    Returns:
        Set of all downstream nodes (NOT including the starting nodes).
    """
    # Build downstream adjacency
    downstream: dict[str, set[str]] = defaultdict(set)
    for node, upstreams in graph.items():
        for up in upstreams:
            downstream[up].add(node)

    visited: set[str] = set()
    queue = list(nodes)

    while queue:
        current = queue.pop(0)
        for child in downstream.get(current, set()):
            if child not in visited:
                visited.add(child)
                queue.append(child)

    return visited


def _params_hash(params: Any) -> str:
    """Compute a stable hash of parameter dict for cache invalidation."""
    serialized = json.dumps(params, sort_keys=True, default=str)
    return hashlib.md5(serialized.encode()).hexdigest()


# Primitives that run on 1m bars regardless of the target timeframe.
# These compute aggregate/structural features from the full 1m dataset.
_GLOBAL_PRIMITIVES = frozenset({
    "session_liquidity",
    "reference_levels",
    "htf_liquidity",
    "asia_range",
})


def _resolve_per_tf_params(
    primitive: str, params: dict, timeframe: str
) -> dict:
    """Resolve per-TF parameters for primitives that need it.

    The swing_points detector expects flat params (N=int, height_filter_pips=float)
    but the cascade stores them as TF maps. This function resolves them.

    Other detectors handle per_tf resolution internally.
    """
    if primitive == "swing_points":
        resolved = dict(params)
        n_val = params.get("N")
        if isinstance(n_val, dict):
            resolved["N"] = n_val.get(timeframe, 3)
        hf_val = params.get("height_filter_pips")
        if isinstance(hf_val, dict):
            resolved["height_filter_pips"] = hf_val.get(timeframe, 3.0)
        return resolved
    return params


class CascadeEngine:
    """Dependency-aware cascade runner for detector modules.

    Usage:
        engine = CascadeEngine(registry, config)
        results = engine.run(bars_by_tf, params_by_primitive)
        # On param change:
        engine.on_param_change("displacement")
        results = engine.run(bars_by_tf, params_by_primitive)

    Variant selection:
        # Global variant (all primitives use same variant):
        engine = CascadeEngine(registry, graph, variant="a8ra_v1")

        # Per-primitive variant overrides:
        engine = CascadeEngine(registry, graph,
                               variant_by_primitive={"mss": "luxalgo_v1"})
        # Unspecified primitives fall back to default "a8ra_v1".
    """

    def __init__(
        self,
        registry: Registry,
        dependency_graph: dict[str, dict],
        variant: str = "a8ra_v1",
        variant_by_primitive: Optional[dict[str, str]] = None,
    ) -> None:
        """Initialize the cascade engine.

        Args:
            registry: Registry containing all detector modules.
            dependency_graph: From config dependency_graph section.
                Maps primitive_name -> {"upstream": [list of upstream names]}.
            variant: Default variant name for looking up detectors (default "a8ra_v1").
                Used for any primitive not overridden by variant_by_primitive.
            variant_by_primitive: Optional dict mapping primitive_name -> variant_name.
                When provided, the cascade uses the specified variant for each
                listed primitive instead of the default. Unspecified primitives
                still use the default variant.
        """
        self._registry = registry
        self._variant = variant
        self._variant_by_primitive: dict[str, str] = (
            dict(variant_by_primitive) if variant_by_primitive else {}
        )

        # Parse graph: primitive_name -> list of upstream primitive names
        # Merge config-declared upstream with detector's required_upstream()
        # to ensure all needed wiring is present.
        self._graph: dict[str, list[str]] = {}
        for name, spec in dependency_graph.items():
            if isinstance(spec, dict):
                config_upstream = list(spec.get("upstream", []))
            else:
                config_upstream = []

            # Augment with detector's declared requirements
            prim_variant = self.get_variant_for_primitive(name)
            if registry.has(name, prim_variant):
                detector = registry.get(name, prim_variant)
                for req in detector.required_upstream():
                    if req not in config_upstream and req in dependency_graph:
                        config_upstream.append(req)
                        logger.debug(
                            "Added missing upstream '%s' -> '%s' "
                            "from detector required_upstream().",
                            req, name,
                        )

            self._graph[name] = config_upstream

        # Compute execution order
        self._execution_order = _topo_sort(self._graph)

        # Cache: primitive_name -> DetectionResult (keyed per timeframe)
        self._cache: dict[str, dict[str, DetectionResult]] = {}
        # Param hashes for cache invalidation
        self._param_hashes: dict[str, str] = {}
        # Set of primitives to invalidate on next run
        self._invalidated: set[str] = set()

        logger.info(
            "CascadeEngine initialized with %d nodes. Order: %s",
            len(self._execution_order),
            self._execution_order,
        )

    @property
    def execution_order(self) -> list[str]:
        """Return the topological execution order."""
        return list(self._execution_order)

    @property
    def graph(self) -> dict[str, list[str]]:
        """Return a copy of the dependency graph."""
        return copy.deepcopy(self._graph)

    @property
    def variant_by_primitive(self) -> dict[str, str]:
        """Return a copy of the per-primitive variant mapping."""
        return dict(self._variant_by_primitive)

    def get_variant_for_primitive(self, primitive: str) -> str:
        """Get the variant name for a given primitive.

        Returns the override from variant_by_primitive if set,
        otherwise falls back to the default variant.

        Args:
            primitive: The primitive name.

        Returns:
            The variant name to use for this primitive.
        """
        return self._variant_by_primitive.get(primitive, self._variant)

    def on_param_change(self, *primitives: str) -> set[str]:
        """Mark primitives as invalidated due to parameter changes.

        Invalidates the specified primitives AND all transitive downstream.

        Args:
            *primitives: Names of primitives whose params changed.

        Returns:
            Set of all invalidated primitive names (including downstream).
        """
        changed = set(primitives)
        downstream = _get_transitive_downstream(self._graph, changed)
        all_invalidated = changed | downstream

        self._invalidated |= all_invalidated

        logger.info(
            "Param change on %s -> invalidated %d nodes: %s",
            list(primitives),
            len(all_invalidated),
            sorted(all_invalidated),
        )

        return all_invalidated

    def run(
        self,
        bars_by_tf: dict[str, pd.DataFrame],
        params_by_primitive: dict[str, dict],
        timeframes: Optional[list[str]] = None,
        context_extras: Optional[dict] = None,
    ) -> dict[str, dict[str, DetectionResult]]:
        """Run the full cascade, respecting cache and invalidation.

        Args:
            bars_by_tf: Mapping of timeframe -> bar DataFrame.
                Must include "1m" for global primitives.
            params_by_primitive: Mapping of primitive_name -> params dict.
            timeframes: List of timeframes to run TF-specific detectors on.
                Defaults to ["1m", "5m", "15m"].
            context_extras: Extra context to pass to detectors (e.g., bars_1m).

        Returns:
            Nested dict: results[primitive_name][timeframe] -> DetectionResult.
        """
        if timeframes is None:
            timeframes = ["1m", "5m", "15m"]

        if context_extras is None:
            context_extras = {}

        # Ensure bars_1m is available in context for detectors that need it
        if "bars_1m" not in context_extras and "1m" in bars_by_tf:
            context_extras["bars_1m"] = bars_by_tf["1m"]

        results: dict[str, dict[str, DetectionResult]] = {}

        for primitive in self._execution_order:
            # Resolve variant for this specific primitive
            prim_variant = self.get_variant_for_primitive(primitive)

            # Check if detector is registered
            # Virtual primitives (ifvg, bpr) are handled by their parent
            # detector (fvg) and don't have separate registry entries.
            if not self._registry.has(primitive, prim_variant):
                # If the variant was explicitly requested via variant_by_primitive,
                # this is an error — the user asked for a variant that doesn't exist.
                if primitive in self._variant_by_primitive:
                    # Delegate to registry.get() which produces a clear error
                    # listing available variants.
                    self._registry.get(primitive, prim_variant)

                logger.info(
                    "Primitive '%s' not in registry for variant '%s' "
                    "(virtual or unimplemented), skipping.",
                    primitive, prim_variant,
                )
                results[primitive] = {}
                continue

            # Check for param changes -> cache invalidation
            params = params_by_primitive.get(primitive, {})
            new_hash = _params_hash(params)

            # Determine if we need to re-run
            need_run = (
                primitive in self._invalidated
                or primitive not in self._cache
                or self._param_hashes.get(primitive) != new_hash
            )

            if not need_run:
                # Serve from cache
                results[primitive] = self._cache[primitive]
                logger.debug("Cache hit for '%s'", primitive)
                continue

            # Run the detector (using per-primitive variant)
            detector = self._registry.get(primitive, prim_variant)

            # Handle DEFERRED modules gracefully
            prim_results: dict[str, DetectionResult] = {}
            try:
                if primitive in _GLOBAL_PRIMITIVES:
                    # Global primitives run on 1m bars only, once
                    prim_results = self._run_global(
                        primitive, detector, bars_by_tf, params, results,
                        context_extras,
                    )
                else:
                    # TF-specific primitives run per timeframe
                    prim_results = self._run_per_tf(
                        primitive, detector, bars_by_tf, params, timeframes,
                        results, context_extras,
                    )
            except NotImplementedError:
                logger.info(
                    "Primitive '%s' is DEFERRED (NotImplementedError), "
                    "providing empty results.",
                    primitive,
                )
                for tf in timeframes:
                    prim_results[tf] = DetectionResult(
                        primitive=primitive,
                        variant=prim_variant,
                        timeframe=tf,
                        detections=[],
                        metadata={"status": "DEFERRED"},
                        params_used=params,
                    )

            # Store in cache
            self._cache[primitive] = prim_results
            self._param_hashes[primitive] = new_hash
            results[primitive] = prim_results

            # Remove from invalidated set
            self._invalidated.discard(primitive)

            total_detections = sum(
                len(r.detections) for r in prim_results.values()
            )
            logger.info(
                "Ran '%s': %d timeframes, %d total detections",
                primitive,
                len(prim_results),
                total_detections,
            )

        # Clear any remaining invalidation flags
        self._invalidated.clear()

        return results

    def _run_global(
        self,
        primitive: str,
        detector: PrimitiveDetector,
        bars_by_tf: dict[str, pd.DataFrame],
        params: dict,
        results: dict[str, dict[str, DetectionResult]],
        context_extras: dict,
    ) -> dict[str, DetectionResult]:
        """Run a global primitive (operates on 1m bars, returns single result).

        These primitives (session_liquidity, reference_levels, htf_liquidity,
        asia_range) don't have per-TF variants — they run once on 1m.
        """
        bars_1m = bars_by_tf.get("1m")
        if bars_1m is None:
            raise CascadeError(
                f"Global primitive '{primitive}' requires 1m bars "
                "but they are not in bars_by_tf."
            )

        # Build upstream dict
        upstream = self._build_upstream(primitive, results)

        # Build context
        context = {"timeframe": "1m", **context_extras}

        result = detector.detect(bars_1m, params, upstream=upstream, context=context)

        # Global primitives return their result under a "global" key
        return {"global": result}

    def _run_per_tf(
        self,
        primitive: str,
        detector: PrimitiveDetector,
        bars_by_tf: dict[str, pd.DataFrame],
        params: dict,
        timeframes: list[str],
        results: dict[str, dict[str, DetectionResult]],
        context_extras: dict,
    ) -> dict[str, DetectionResult]:
        """Run a TF-specific primitive on each requested timeframe."""
        prim_results: dict[str, DetectionResult] = {}

        for tf in timeframes:
            if tf not in bars_by_tf:
                logger.warning(
                    "Timeframe '%s' not in bars_by_tf, skipping '%s' on '%s'.",
                    tf, primitive, tf,
                )
                continue

            bars = bars_by_tf[tf]

            # Resolve per-TF params for primitives that need it
            resolved_params = _resolve_per_tf_params(primitive, params, tf)

            # Build upstream dict for this TF
            upstream = self._build_upstream(primitive, results, tf)

            # Build context
            context = {"timeframe": tf, **context_extras}

            result = detector.detect(
                bars, resolved_params, upstream=upstream, context=context
            )
            prim_results[tf] = result

        return prim_results

    def _build_upstream(
        self,
        primitive: str,
        results: dict[str, dict[str, DetectionResult]],
        timeframe: Optional[str] = None,
    ) -> dict[str, DetectionResult]:
        """Build the upstream dict for a detector.

        For each upstream dependency:
        - If it's a global primitive, use results[up]["global"]
        - If it's TF-specific, use results[up][timeframe]

        Args:
            primitive: The primitive being run.
            results: All results computed so far.
            timeframe: Current timeframe (for TF-specific lookups).

        Returns:
            Dict of upstream_name -> DetectionResult.
        """
        upstream: dict[str, DetectionResult] = {}

        for up_name in self._graph.get(primitive, []):
            up_results = results.get(up_name, {})

            if up_name in _GLOBAL_PRIMITIVES:
                # Global primitives have single "global" result
                if "global" in up_results:
                    upstream[up_name] = up_results["global"]
            else:
                # TF-specific: match the current timeframe
                if timeframe and timeframe in up_results:
                    upstream[up_name] = up_results[timeframe]

        return upstream

    def clear_cache(self) -> None:
        """Clear all cached results and param hashes."""
        self._cache.clear()
        self._param_hashes.clear()
        self._invalidated.clear()
        logger.info("Cascade cache cleared.")


def build_default_registry() -> Registry:
    """Build a registry with all available detector modules.

    Returns:
        Registry populated with all implemented detectors.
    """
    registry = Registry()

    # Import all detector classes
    from ra.detectors.fvg import FVGDetector
    from ra.detectors.swing_points import SwingPointDetector
    from ra.detectors.displacement import DisplacementDetector
    from ra.detectors.session_liquidity import SessionLiquidityDetector
    from ra.detectors.asia_range import AsiaRangeDetector
    from ra.detectors.reference_levels import ReferenceLevelDetector
    from ra.detectors.equal_hl import EqualHLDetector
    from ra.detectors.mss import MSSDetector
    from ra.detectors.order_block import OrderBlockDetector
    from ra.detectors.htf_liquidity import HTFLiquidityDetector
    from ra.detectors.ote import OTEDetector
    from ra.detectors.liquidity_sweep import LiquiditySweepDetector
    from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector

    detectors = [
        FVGDetector,
        SwingPointDetector,
        DisplacementDetector,
        SessionLiquidityDetector,
        AsiaRangeDetector,
        ReferenceLevelDetector,
        EqualHLDetector,
        MSSDetector,
        OrderBlockDetector,
        HTFLiquidityDetector,
        OTEDetector,
        LiquiditySweepDetector,
        LuxAlgoMSSDetector,
    ]

    for det_cls in detectors:
        registry.register(det_cls)

    logger.info("Default registry built with %d detectors.", len(registry))
    return registry


def extract_locked_params_for_cascade(config) -> dict[str, dict]:
    """Extract locked params for all primitives from a loaded config.

    Resolves per-TF overrides and locked values into the flat param dicts
    that each detector's detect() method expects.

    Args:
        config: Validated RAConfig instance from load_config().

    Returns:
        Dict of primitive_name -> params dict.
    """
    from ra.config.loader import get_locked_params

    params: dict[str, dict] = {}

    # Primitives that need per-TF resolved swing params
    _SWING_N = {"1m": 5, "5m": 3, "15m": 2}
    _SWING_HEIGHT = {"1m": 0.5, "5m": 3.0, "15m": 3.0}

    # FVG
    params["fvg"] = {"floor_threshold_pips": 0.5}

    # Swing Points — needs special handling for per-TF
    # The swing detector expects already-resolved N and height_filter_pips
    # for a given TF, but cascade calls per-TF, so we pass the TF maps
    params["swing_points"] = {
        "N": _SWING_N,
        "height_filter_pips": _SWING_HEIGHT,
        "strength_cap": 20,
        "strength_as_gate": False,
    }

    # Displacement — complex nested params
    params["displacement"] = {
        "atr_period": 14,
        "combination_mode": "AND",
        "ltf": {
            "applies_to": ["1m", "5m", "15m"],
            "atr_multiplier": 1.50,
            "body_ratio": 0.60,
            "close_gate": 0.25,
            "structure_close_required": False,
        },
        "htf": {
            "applies_to": ["1H", "4H", "1D"],
            "atr_multiplier": 1.50,
            "body_ratio": 0.65,
            "close_gate": 0.25,
            "structure_close_required": True,
        },
        "decisive_override": {
            "enabled": True,
            "body_min": 0.75,
            "close_max": 0.10,
            "pip_floor": {
                "1m": 3.0, "5m": 5.0, "15m": 6.0,
                "1H": 8.0, "4H": 15.0, "1D": 20.0,
            },
        },
        "cluster": {
            "cluster_2_enabled": True,
            "cluster_3_enabled": False,
            "net_efficiency_min": 0.65,
            "overlap_max": 0.35,
        },
        "quality_grades": {
            "STRONG": {"atr_ratio_min": 2.0},
            "VALID": {"atr_ratio_min": 1.5},
            "WEAK": {"atr_ratio_min": 1.25},
        },
        "evaluation_order": [
            "check_cluster_2", "check_single_atr", "check_single_override"
        ],
    }

    # Session Liquidity
    params["session_liquidity"] = {
        "four_gate_model": {
            "efficiency_threshold": {"locked": 0.60},
            "mid_cross_min": {"locked": 2},
            "balance_score_min": {"locked": 0.30},
        },
        "box_objects": {
            "asia": {
                "window": {"start_ny": "19:00", "end_ny": "00:00"},
                "range_cap_pips": 30,
            },
            "pre_london": {
                "window": {"start_ny": "00:00", "end_ny": "02:00"},
                "range_cap_pips": 15,
            },
            "pre_ny": {
                "window": {"start_ny": "05:00", "end_ny": "07:00"},
                "range_cap_pips": 20,
            },
        },
    }

    # Asia Range
    params["asia_range"] = {
        "classification": {
            "tight_below_pips": 10,
            "mid_below_pips": 20,
            "wide_above_pips": 20,
        },
        "max_cap_pips": 30,
    }

    # Reference Levels
    params["reference_levels"] = {
        "pdh_pdl": {
            "boundary": "forex_day",
            "measurement": "wicks",
        },
        "midnight_open": {"time_ny": "00:00"},
        "equilibrium": {"formula": "midpoint"},
    }

    # Equal HL (DEFERRED)
    params["equal_hl"] = {}

    # IFVG + BPR (virtual nodes handled by FVG detector)
    params["ifvg"] = {}
    params["bpr"] = {}

    # MSS
    params["mss"] = {
        "ltf": {
            "applies_to": ["1m", "5m", "15m"],
            "displacement_required": True,
            "confirmation_window_bars": 3,
            "close_beyond_swing": True,
            "impulse_suppression": {
                "pullback_reset_pips": 5,
                "pullback_reset_atr_factor": 0.25,
                "opposite_displacement_reset": True,
                "new_day_reset": True,
            },
        },
        "htf": {
            "applies_to": ["1H", "4H", "1D"],
            "displacement_required": True,
            "confirmation_window_bars": 1,
            "close_beyond_swing": True,
            "structure_close_required": True,
            "impulse_suppression": {
                "pullback_reset_pips": 5,
                "pullback_reset_atr_factor": 0.25,
                "opposite_displacement_reset": True,
                "new_day_reset": True,
            },
        },
        "fvg_tag_only": True,
        "break_classification": ["REVERSAL", "CONTINUATION"],
        "swing_consumption": True,
    }

    # Order Block
    params["order_block"] = {
        "trigger": "displacement_plus_mss",
        "zone_type": "body",
        "thin_candle_filter": {"min_body_pct": 0.10},
        "fallback_scan": {
            "mode": "ENABLED_CONDITIONAL",
            "lookback_bars": 3,
            "reject_if_none_found": True,
        },
        "expiration_bars": {
            "per_tf": {
                "1m": 10, "5m": 10, "15m": 10,
                "1H": 15, "4H": 20, "1D": 20,
            },
        },
        "min_displacement_grade": "VALID",
    }

    # HTF Liquidity
    params["htf_liquidity"] = {
        "detection_source": "swing_points_fractal_2_2",
        "price_tolerance_pips": {
            "per_tf": {"1H": 2, "4H": 3, "1D": 5, "W1": 10, "MN": 15},
        },
        "min_bars_between_touches": {
            "per_tf": {"1H": 6, "4H": 3, "1D": 2, "W1": 2, "MN": 2},
        },
        "rotation_required": {
            "per_tf": {
                "1H": {"pip_floor": 5, "atr_factor": 0.25},
                "4H": {"pip_floor": 8, "atr_factor": 0.25},
                "1D": {"pip_floor": 12, "atr_factor": 0.25},
                "W1": {"pip_floor": 20, "atr_factor": 0.25},
                "MN": {"pip_floor": 30, "atr_factor": 0.25},
            },
        },
        "max_lookback": {
            "per_tf": {"1H": 500, "4H": 300, "1D": 180, "W1": 104, "MN": 60},
        },
        "asia_range_filter": True,
        "invalidation_during_formation": True,
        "merge_tolerance_factor": 1.5,
        "min_touches": 2,
    }

    # OTE
    params["ote"] = {
        "fib_levels": {
            "lower": 0.618,
            "sweet_spot": 0.705,
            "upper": 0.79,
        },
        "anchor_rule": "most_recent_mss",
        "kill_zone_gate": True,
    }

    # Liquidity Sweep
    params["liquidity_sweep"] = {
        "return_window_bars": 1,
        "rejection_wick_pct": {"locked": 0.40},
        "min_breach_pips": {"per_tf": {"1m": 0.5, "5m": 0.5, "15m": 1.0}},
        "min_reclaim_pips": {"per_tf": {"1m": 0.5, "5m": 0.5, "15m": 1.0}},
        "max_sweep_size_atr_mult": 1.5,
        "directional_close": False,
        "level_sources": {
            "pdh_pdl": {"enabled": True},
            "asia_h_l": {"enabled": True, "valid_after_ny": "00:00"},
            "london_h_l": {"enabled": True, "valid_after_ny": "05:00"},
            "ltf_box_h_l": {"enabled": True, "valid_after": "box_end_time"},
            "htf_eqh_eql": {"enabled": True},
            "pwh_pwl": {"enabled": True, "valid_after_ny": "17:00 Monday"},
            "promoted_swing": {
                "enabled": True,
                "strength_min": 10,
                "height_pips_min": 10.0,
                "scope": "current_forex_day_only",
                "staleness_bars": 20,
            },
            "raw_previous_swings": {"enabled": False},
            "equal_hl": {"enabled": False},
            "pmh_pml": {"enabled": False},
        },
        "level_merge_tolerance_pips": 1.0,
        "qualified_sweep": {
            "displacement_before_lookback": 10,
            "displacement_after_forward": 5,
        },
        "delayed_sweep": {
            "enabled": True,
            "min_delayed_wick_pct": 0.30,
            "max_delay_bars": 1,
        },
    }

    return params
