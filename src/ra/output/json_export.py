"""JSON export module for structured evaluation output (Phase 2).

Serializes evaluation results to JSON conforming to Schemas 4A-4E
as defined in .factory/library/output_schemas.md.

Key features:
- Custom JSON encoder for numpy/pandas types (int64→int, float64→float, NaN→null)
- Schema 4A: Evaluation run envelope
- Schema 4B: Per-config detection results with cascade funnel
- Schema 4C: Pairwise comparison with divergence index
- Schema 4D: Grid sweep with 2D heatmap data (supports 1D degenerate)
- Schema 4E: Walk-forward validation results
- All outputs include schema_version field
- Round-trip fidelity: write→read preserves all fields
- Detection arrays sorted by time
- Cascade funnel levels ordered: leaf → composite → terminal
"""

import json
import logging
import math
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from ra.engine.base import Detection, DetectionResult
from ra.evaluation.comparison import compute_stats, compare_pairwise
from ra.evaluation.cascade_stats import cascade_funnel
from ra.evaluation.scoring import score_labels

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"


class RAJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder handling numpy/pandas types.

    Conversion rules:
    - numpy.int64 → int
    - numpy.float64 → float (NaN → None)
    - numpy.bool_ → bool
    - numpy.ndarray → list
    - pandas.Timestamp → ISO 8601 string
    - pandas.NaT → None
    - float('nan') → None
    - datetime → ISO 8601 string
    - date → ISO 8601 string
    """

    def default(self, obj: Any) -> Any:
        # numpy integer types
        if isinstance(obj, (np.integer,)):
            return int(obj)

        # numpy floating types
        if isinstance(obj, (np.floating,)):
            val = float(obj)
            if math.isnan(val):
                return None
            return val

        # numpy boolean
        if isinstance(obj, (np.bool_,)):
            return bool(obj)

        # numpy array
        if isinstance(obj, np.ndarray):
            return obj.tolist()

        # pandas Timestamp
        if isinstance(obj, pd.Timestamp):
            if pd.isna(obj):
                return None
            return obj.isoformat()

        # pandas NaT
        if obj is pd.NaT:
            return None

        # Python datetime
        if isinstance(obj, datetime):
            return obj.isoformat()

        # Python date
        if isinstance(obj, date):
            return obj.isoformat()

        return super().default(obj)

    def encode(self, o: Any) -> str:
        """Override encode to handle NaN at the top level."""
        return super().encode(self._sanitize(o))

    def _sanitize(self, obj: Any) -> Any:
        """Recursively sanitize NaN/NaT values in nested structures."""
        if isinstance(obj, float) and math.isnan(obj):
            return None
        if isinstance(obj, (np.floating,)):
            val = float(obj)
            return None if math.isnan(val) else val
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return [self._sanitize(v) for v in obj.tolist()]
        if isinstance(obj, pd.Timestamp):
            return None if pd.isna(obj) else obj.isoformat()
        if obj is pd.NaT:
            return None
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date) and not isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: self._sanitize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._sanitize(v) for v in obj]
        return obj


def _deep_sanitize(obj: Any) -> Any:
    """Recursively sanitize numpy/pandas/NaN types for JSON serialization.

    This must be called before json.dump because the standard JSON encoder
    handles Python float (including NaN) before our custom encoder sees it.
    """
    if obj is None:
        return None
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.floating,)):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [_deep_sanitize(v) for v in obj.tolist()]
    if isinstance(obj, pd.Timestamp):
        return None if pd.isna(obj) else obj.isoformat()
    if obj is pd.NaT:
        return None
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date) and not isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _deep_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_deep_sanitize(v) for v in obj]
    return obj


def write_json(data: Any, filepath: str | Path) -> None:
    """Write data to a JSON file using the RA encoder.

    Args:
        data: Data structure to serialize.
        filepath: Output file path.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _deep_sanitize(data)
    with open(filepath, "w") as f:
        json.dump(sanitized, f, cls=RAJSONEncoder, indent=2)
    logger.info("Wrote JSON output to %s", filepath)


def read_json(filepath: str | Path) -> Any:
    """Read a JSON file back into a Python structure.

    Args:
        filepath: Input file path.

    Returns:
        Parsed JSON data.
    """
    with open(filepath) as f:
        return json.load(f)


def _serialize_detection(det: Detection) -> dict[str, Any]:
    """Serialize a single Detection to a JSON-compatible dict.

    Args:
        det: Detection object.

    Returns:
        Dict with id, time, direction, type, price, properties, tags, upstream_refs.
    """
    return {
        "id": det.id,
        "time": det.time.isoformat() if det.time else None,
        "direction": det.direction,
        "type": det.type,
        "price": float(det.price) if det.price is not None else None,
        "properties": dict(det.properties) if det.properties else {},
        "tags": dict(det.tags) if det.tags else {},
        "upstream_refs": list(det.upstream_refs) if det.upstream_refs else [],
    }


def _sort_detections_by_time(detections: list[Detection]) -> list[Detection]:
    """Sort detections by time ascending.

    Args:
        detections: List of Detection objects.

    Returns:
        Sorted list (new list, doesn't modify original).
    """
    return sorted(detections, key=lambda d: d.time if d.time else datetime.min)


def serialize_per_config_result(
    config_name: str,
    results: dict[str, dict[str, DetectionResult]],
    params: dict[str, Any],
    dep_graph: dict[str, list[str]],
    timeframe: str = "5m",
) -> dict[str, Any]:
    """Serialize per-config detection results to Schema 4B.

    Args:
        config_name: Name of the config.
        results: Cascade results dict (primitive -> tf -> DetectionResult).
        params: Parameter dict for this config.
        dep_graph: Dependency graph for cascade funnel computation.
        timeframe: Timeframe for cascade funnel (default "5m").

    Returns:
        Dict conforming to Schema 4B.
    """
    # Compute stats using comparison module
    stats = compute_stats(results)

    # Build per_primitive section
    per_primitive: dict[str, Any] = {}

    for prim_name, tf_dict in results.items():
        per_tf: dict[str, Any] = {}

        for tf, det_result in tf_dict.items():
            prim_stats = stats.get(prim_name, {}).get(tf, {})

            # Sort detections by time
            sorted_dets = _sort_detections_by_time(det_result.detections)
            serialized_dets = [_serialize_detection(d) for d in sorted_dets]

            per_tf[tf] = {
                "detection_count": prim_stats.get("detection_count", len(det_result.detections)),
                "detections_per_day": prim_stats.get("detections_per_day", 0.0),
                "detections_per_day_std": prim_stats.get("detections_per_day_std", 0.0),
                "by_session": prim_stats.get("by_session", {}),
                "by_direction": prim_stats.get("by_direction", {}),
                "detections": serialized_dets,
            }

        per_primitive[prim_name] = {"per_tf": per_tf}

    # Compute cascade funnel
    funnel = cascade_funnel(results, timeframe, dep_graph)

    return {
        "config_name": config_name,
        "params": params,
        "per_primitive": per_primitive,
        "cascade_funnel": funnel,
    }


def serialize_pairwise_comparison(
    comparison: dict[str, Any],
) -> dict[str, Any]:
    """Serialize pairwise comparison to Schema 4C.

    Takes the raw comparison dict from compare_pairwise() and ensures
    it conforms to Schema 4C structure.

    Args:
        comparison: Raw comparison dict from compare_pairwise() or manual build.

    Returns:
        Dict conforming to Schema 4C.
    """
    # The comparison module already produces Schema 4C-compatible output.
    # We just ensure all required fields are present.
    result: dict[str, Any] = {
        "config_a": comparison.get("config_a", ""),
        "config_b": comparison.get("config_b", ""),
        "per_primitive": comparison.get("per_primitive", {}),
        "divergence_index": comparison.get("divergence_index", []),
    }
    # Include variant names when present (variant comparison mode)
    if "variant_a" in comparison:
        result["variant_a"] = comparison["variant_a"]
    if "variant_b" in comparison:
        result["variant_b"] = comparison["variant_b"]
    return result


def serialize_grid_sweep(
    grid_data: dict[str, Any],
) -> dict[str, Any]:
    """Serialize grid sweep to Schema 4D.

    Handles both 2D and 1D (degenerate y-axis) grids.
    Ensures schema_version is present.

    Args:
        grid_data: Raw grid sweep data dict.

    Returns:
        Dict conforming to Schema 4D with schema_version.
    """
    output = {
        "schema_version": SCHEMA_VERSION,
        "sweep_id": grid_data.get("sweep_id", ""),
        "primitive": grid_data.get("primitive", ""),
        "variant": grid_data.get("variant", ""),
        "dataset": grid_data.get("dataset", ""),
        "metric": grid_data.get("metric", ""),
        "axes": grid_data.get("axes", {}),
        "grid": grid_data.get("grid", []),
        "current_lock": grid_data.get("current_lock"),
        "plateau": grid_data.get("plateau"),
        "cliff_edges": grid_data.get("cliff_edges", []),
    }

    # Sanitize grid values (NaN → null)
    if output["grid"]:
        sanitized_grid = []
        for row in output["grid"]:
            sanitized_row = []
            for val in row:
                if isinstance(val, float) and math.isnan(val):
                    sanitized_row.append(None)
                elif isinstance(val, (np.floating,)):
                    fval = float(val)
                    sanitized_row.append(None if math.isnan(fval) else fval)
                elif isinstance(val, (np.integer,)):
                    sanitized_row.append(int(val))
                else:
                    sanitized_row.append(val)
            sanitized_grid.append(sanitized_row)
        output["grid"] = sanitized_grid

    return output


def serialize_walk_forward(
    wf_data: dict[str, Any],
) -> dict[str, Any]:
    """Serialize walk-forward to Schema 4E.

    Ensures schema_version is present and all required fields are included.

    Args:
        wf_data: Raw walk-forward data from WalkForwardRunner.run().

    Returns:
        Dict conforming to Schema 4E with schema_version.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "config": wf_data.get("config", ""),
        "primitive": wf_data.get("primitive", ""),
        "metric": wf_data.get("metric", ""),
        "window_config": wf_data.get("window_config", {}),
        "windows": wf_data.get("windows", []),
        "summary": wf_data.get("summary", {}),
    }


def _collect_detection_ids_per_config(
    results_by_config: dict[str, dict[str, dict[str, DetectionResult]]],
) -> dict[str, set[str]]:
    """Collect all detection IDs per config name.

    Returns:
        Dict mapping config_name -> set of detection IDs.
    """
    per_config: dict[str, set[str]] = {}
    for config_name, results in results_by_config.items():
        ids: set[str] = set()
        for prim_name, tf_dict in results.items():
            for tf, det_result in tf_dict.items():
                for det in det_result.detections:
                    ids.add(det.id)
        per_config[config_name] = ids
    return per_config


def _score_per_config(
    labels: list[dict[str, str]],
    detection_ids: set[str],
    config_name: str,
) -> dict[str, Any]:
    """Score labels that match detections in a specific config.

    Returns per-primitive scoring with detection_count and labelled_count.
    """
    from collections import defaultdict

    # Filter labels to only those whose detection_id exists in this config
    matched_labels = [l for l in labels if l["detection_id"] in detection_ids]

    # Group by primitive
    by_primitive: dict[str, list[dict]] = defaultdict(list)
    for label in matched_labels:
        by_primitive[label["primitive"]].append(label)

    # Count detections per primitive in this config (for detection_count)
    # We need actual detection counts, not just labelled counts
    # detection_count comes from the results, labelled_count from matched labels

    per_primitive: dict[str, Any] = {}
    for primitive in sorted(by_primitive.keys()):
        prim_labels = by_primitive[primitive]
        correct = sum(1 for l in prim_labels if l["label"] == "CORRECT")
        noise = sum(1 for l in prim_labels if l["label"] == "NOISE")
        borderline = sum(1 for l in prim_labels if l["label"] == "BORDERLINE")
        missed = sum(1 for l in prim_labels if l["label"] == "MISSED")

        from ra.evaluation.scoring import compute_precision, compute_recall, compute_f1
        precision = compute_precision(correct, noise)
        recall = compute_recall(correct, missed)
        f1 = compute_f1(precision, recall)

        per_primitive[primitive] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "labelled_count": len(prim_labels),
            "correct": correct,
            "noise": noise,
            "borderline": borderline,
        }

    return per_primitive


def _compute_detection_counts_per_config(
    results: dict[str, dict[str, DetectionResult]],
) -> dict[str, int]:
    """Compute total detection count per primitive for a config."""
    counts: dict[str, int] = {}
    for prim_name, tf_dict in results.items():
        total = sum(len(dr.detections) for dr in tf_dict.values())
        counts[prim_name] = total
    return counts


def _compute_scoring_delta(
    scoring_a: dict[str, Any],
    scoring_b: dict[str, Any],
) -> dict[str, Any]:
    """Compute delta between two per-config scoring dicts.

    Delta = B - A for precision, recall, f1.
    Returns per_primitive and aggregate deltas.
    """
    all_primitives = set(scoring_a.keys()) | set(scoring_b.keys())
    per_primitive: dict[str, Any] = {}

    for prim in sorted(all_primitives):
        a = scoring_a.get(prim, {})
        b = scoring_b.get(prim, {})

        p_a = a.get("precision")
        p_b = b.get("precision")
        r_a = a.get("recall")
        r_b = b.get("recall")
        f1_a = a.get("f1")
        f1_b = b.get("f1")

        per_primitive[prim] = {
            "precision_delta": (p_b - p_a) if (p_a is not None and p_b is not None) else None,
            "recall_delta": (r_b - r_a) if (r_a is not None and r_b is not None) else None,
            "f1_delta": (f1_b - f1_a) if (f1_a is not None and f1_b is not None) else None,
            "detection_count_a": a.get("detection_count", 0),
            "detection_count_b": b.get("detection_count", 0),
        }

    return {"per_primitive": per_primitive}


def _build_scoring_section(
    labels: list[dict[str, str]],
    results_by_config: dict[str, dict[str, dict[str, DetectionResult]]],
) -> dict[str, Any]:
    """Build the scoring section for the evaluation run output.

    Computes:
    - Global scoring from score_labels()
    - Per-config scoring (labels matched to each config's detections)
    - Delta between first two configs (if 2+ configs)

    Args:
        labels: Canonical label list (non-empty).
        results_by_config: Config results.

    Returns:
        Scoring dict with per_primitive, aggregate, label_source,
        per_config, and optionally delta.
    """
    # Global scoring
    global_scores = score_labels(labels)

    # Per-config scoring
    detection_ids_per_config = _collect_detection_ids_per_config(results_by_config)
    detection_counts_per_config = {
        name: _compute_detection_counts_per_config(results)
        for name, results in results_by_config.items()
    }

    per_config_scoring: dict[str, dict[str, Any]] = {}
    config_names = sorted(results_by_config.keys())

    for config_name in config_names:
        ids = detection_ids_per_config.get(config_name, set())
        config_scoring = _score_per_config(labels, ids, config_name)
        counts = detection_counts_per_config.get(config_name, {})

        # Enrich with detection_count from actual results
        for prim, scores in config_scoring.items():
            scores["detection_count"] = counts.get(prim, 0)

        per_config_scoring[config_name] = config_scoring

    scoring: dict[str, Any] = {
        "schema_version": global_scores["schema_version"],
        "scored_at": global_scores["scored_at"],
        "label_source": global_scores["label_source"],
        "per_primitive": global_scores["per_primitive"],
        "aggregate": global_scores["aggregate"],
        "per_config": per_config_scoring,
    }

    # Delta between first two configs
    if len(config_names) >= 2:
        name_a = config_names[0]
        name_b = config_names[1]
        delta = _compute_scoring_delta(
            per_config_scoring.get(name_a, {}),
            per_config_scoring.get(name_b, {}),
        )
        # Add aggregate delta
        agg_a_scores = score_labels(
            [l for l in labels if l["detection_id"] in detection_ids_per_config.get(name_a, set())]
        )
        agg_b_scores = score_labels(
            [l for l in labels if l["detection_id"] in detection_ids_per_config.get(name_b, set())]
        )
        agg_a = agg_a_scores.get("aggregate", {})
        agg_b = agg_b_scores.get("aggregate", {})

        p_a = agg_a.get("precision")
        p_b = agg_b.get("precision")
        r_a = agg_a.get("recall")
        r_b = agg_b.get("recall")
        f1_a = agg_a.get("f1")
        f1_b = agg_b.get("f1")

        delta["aggregate"] = {
            "precision_delta": (p_b - p_a) if (p_a is not None and p_b is not None) else None,
            "recall_delta": (r_b - r_a) if (r_a is not None and r_b is not None) else None,
            "f1_delta": (f1_b - f1_a) if (f1_a is not None and f1_b is not None) else None,
        }
        delta["config_a"] = name_a
        delta["config_b"] = name_b
        scoring["delta"] = delta

    return scoring


def serialize_evaluation_run(
    results_by_config: dict[str, dict[str, dict[str, DetectionResult]]],
    dataset_name: str,
    bars_1m_count: int,
    date_range: tuple[str, str],
    dep_graph: dict[str, list[str]],
    grid_sweep: Optional[dict[str, Any]] = None,
    walk_forward: Optional[dict[str, Any]] = None,
    run_id: Optional[str] = None,
    variant_a: Optional[str] = None,
    variant_b: Optional[str] = None,
    labels: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
    """Serialize full evaluation run to Schema 4A.

    Args:
        results_by_config: Dict mapping config_name -> cascade results.
        dataset_name: Human-readable dataset name.
        bars_1m_count: Number of 1m bars in the dataset.
        date_range: Tuple of (start_date, end_date) strings.
        dep_graph: Dependency graph for cascade funnel computation.
        grid_sweep: Optional Schema 4D data (None if no sweep).
        walk_forward: Optional Schema 4E data (None if no walk-forward).
        run_id: Optional run ID. Auto-generated if None.
        variant_a: Optional variant name for first config (included in output).
        variant_b: Optional variant name for second config (included in output).
        labels: Optional list of canonical label dicts for scoring.
            When provided and non-empty, output includes a 'scoring' section
            with precision/recall/F1, per-config scoring, and delta.
            When None or empty, output has no scoring fields.

    Returns:
        Dict conforming to Schema 4A, optionally with scoring section.
    """
    config_names = sorted(results_by_config.keys())

    if run_id is None:
        run_id = f"eval_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}"

    # Build per_config (Schema 4B)
    per_config: dict[str, Any] = {}

    # Map config names to variant names when provided
    variant_map: dict[str, str] = {}
    if variant_a and variant_b and len(config_names) == 2:
        # Assign variant names to configs in sorted order
        # Convention: first sorted config gets variant_a, second gets variant_b
        for cname in config_names:
            if variant_a in cname:
                variant_map[cname] = variant_a
            elif variant_b in cname:
                variant_map[cname] = variant_b

    for config_name, results in results_by_config.items():
        config_entry = serialize_per_config_result(
            config_name=config_name,
            results=results,
            params={},  # Could be enriched with actual params
            dep_graph=dep_graph,
        )
        # Include variant field in config entries when variant info is provided
        if config_name in variant_map:
            config_entry["variant"] = variant_map[config_name]
        elif variant_a and not variant_b:
            config_entry["variant"] = variant_a
        per_config[config_name] = config_entry

    # Build pairwise (Schema 4C)
    pairwise: dict[str, Any] = {}
    if len(config_names) >= 2:
        import itertools
        for name_a, name_b in itertools.combinations(config_names, 2):
            comparison = compare_pairwise(
                results_by_config[name_a],
                results_by_config[name_b],
            )
            comparison["config_a"] = name_a
            comparison["config_b"] = name_b
            # Include variant names in pairwise comparison
            if name_a in variant_map:
                comparison["variant_a"] = variant_map[name_a]
            if name_b in variant_map:
                comparison["variant_b"] = variant_map[name_b]
            key = f"{name_a}__vs__{name_b}"
            pairwise[key] = serialize_pairwise_comparison(comparison)

    # Build Schema 4A envelope
    output: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "dataset": {
            "name": dataset_name,
            "bars_1m": bars_1m_count,
            "range": list(date_range),
        },
        "configs": config_names,
        "timestamp": datetime.now().isoformat(),
        "per_config": per_config,
        "pairwise": pairwise,
        "grid_sweep": serialize_grid_sweep(grid_sweep) if grid_sweep else None,
        "walk_forward": serialize_walk_forward(walk_forward) if walk_forward else None,
    }

    # Add scoring section when labels are provided and non-empty
    if labels:
        output["scoring"] = _build_scoring_section(labels, results_by_config)

    return output
