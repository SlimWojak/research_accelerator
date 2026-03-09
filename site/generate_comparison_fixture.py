#!/usr/bin/env python3
"""Generate a 2-config comparison fixture for the Phase 3 comparison interface.

Creates a Schema 4A evaluation_run.json with two per_config entries
(current_locked vs candidate_relaxed) plus pairwise comparison data.

Config A (current_locked): Uses locked baseline params as-is.
Config B (candidate_relaxed): swing_points.N increased (5m: 3→5, 15m: 2→4)
    and mss.ltf.confirmation_window_bars increased (3→5), producing fewer
    composite/terminal detections while leaf counts remain closer.

Usage:
    python3 site/generate_comparison_fixture.py

Output:
    site/eval/evaluation_run.json — Schema 4A with 2 configs + pairwise
"""

import copy
import logging
import sys
import time
from pathlib import Path

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    from ra.config.loader import load_config
    from ra.data.csv_loader import load_csv
    from ra.data.tf_aggregator import aggregate
    from ra.evaluation.runner import _build_all_locked_params
    from ra.engine.cascade import CascadeEngine, build_default_registry
    from ra.output.json_export import serialize_evaluation_run, write_json

    config_path = ROOT / "configs" / "locked_baseline.yaml"
    data_path = ROOT / "data" / "eurusd_1m_2024-01-07_to_2024-01-12.csv"
    eval_dir = ROOT / "site" / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)

    # ── Load config ────────────────────────────────────────────────────
    config = load_config(config_path)
    logger.info("Loaded config: %s", config_path)

    # ── Load and aggregate bars ────────────────────────────────────────
    bars_1m = load_csv(data_path)
    logger.info("Loaded %d 1m bars from %s", len(bars_1m), data_path)

    bars_by_tf = {"1m": bars_1m}
    for tf in ["5m", "15m"]:
        bars_by_tf[tf] = aggregate(bars_1m, tf)
        logger.info("Aggregated to %s: %d bars", tf, len(bars_by_tf[tf]))

    bars_1m_count = len(bars_1m)

    # ── Infer date range ───────────────────────────────────────────────
    import pandas as pd
    ts = pd.to_datetime(bars_1m["timestamp_ny"])
    date_range = (ts.min().date().isoformat(), ts.max().date().isoformat())

    # ── Dependency graph ───────────────────────────────────────────────
    dep_graph = {
        name: node.upstream
        for name, node in config.dependency_graph.items()
    }

    # ── Build engines ──────────────────────────────────────────────────
    registry = build_default_registry()
    raw_dep_graph = {
        name: node.model_dump()
        for name, node in config.dependency_graph.items()
    }

    # ── Config A: current_locked (baseline) ────────────────────────────
    logger.info("=" * 60)
    logger.info("Running Config A: current_locked (baseline)")
    logger.info("=" * 60)

    base_params = _build_all_locked_params(config)
    engine_a = CascadeEngine(registry, raw_dep_graph, variant="a8ra_v1")

    t0 = time.time()
    results_a = engine_a.run(bars_by_tf, base_params)
    t1 = time.time()
    logger.info("Config A done in %.1fs", t1 - t0)

    # ── Config B: candidate_relaxed ────────────────────────────────────
    #
    # Modify swing_points.N (makes swing detection stricter → fewer swings)
    # and mss.ltf.confirmation_window_bars (requires more bars → fewer MSS).
    # These changes cascade through MSS → order_block → ote → liquidity_sweep.
    logger.info("=" * 60)
    logger.info("Running Config B: candidate_relaxed (N↑, conf_window↑)")
    logger.info("=" * 60)

    variant_params = copy.deepcopy(base_params)

    # Increase swing_points N for 5m and 15m (stricter → fewer swings)
    sp_params = variant_params["swing_points"]
    if isinstance(sp_params.get("N"), dict):
        sp_params["N"]["5m"] = 5   # was 3
        sp_params["N"]["15m"] = 4  # was 2
        logger.info("  Set swing_points.N: 5m=5 (was 3), 15m=4 (was 2)")

    # Increase MSS confirmation window (needs more confirming bars)
    mss_params = variant_params["mss"]
    if "ltf" in mss_params:
        mss_params["ltf"]["confirmation_window_bars"] = 5  # was 3
        logger.info("  Set mss.ltf.confirmation_window_bars = 5 (was 3)")

    engine_b = CascadeEngine(registry, raw_dep_graph, variant="a8ra_v1")

    t0 = time.time()
    results_b = engine_b.run(bars_by_tf, variant_params)
    t1 = time.time()
    logger.info("Config B done in %.1fs", t1 - t0)

    # ── Compare detection counts ───────────────────────────────────────
    def _count_detections(results, prim, tf):
        r = results.get(prim, {}).get(tf)
        return len(r.detections) if r else 0

    check_prims = ["swing_points", "displacement", "fvg", "mss",
                    "order_block", "liquidity_sweep"]
    for prim in check_prims:
        for tf in ["5m", "15m"]:
            cnt_a = _count_detections(results_a, prim, tf)
            cnt_b = _count_detections(results_b, prim, tf)
            diff = "SAME" if cnt_a == cnt_b else f"DIFF({cnt_b - cnt_a:+d})"
            logger.info("  %s/%s: A=%d, B=%d  [%s]", prim, tf, cnt_a, cnt_b, diff)

    # ── Serialize to Schema 4A ─────────────────────────────────────────
    logger.info("Serializing to Schema 4A with 2 configs...")

    results_by_config = {
        "current_locked": results_a,
        "candidate_relaxed": results_b,
    }

    output = serialize_evaluation_run(
        results_by_config=results_by_config,
        dataset_name=str(data_path),
        bars_1m_count=bars_1m_count,
        date_range=date_range,
        dep_graph=dep_graph,
        run_id="eval_comparison_2config",
    )

    # ── Write output ───────────────────────────────────────────────────
    out_path = eval_dir / "evaluation_run.json"
    write_json(output, out_path)
    logger.info("Wrote Schema 4A to %s", out_path)

    # ── Verify ─────────────────────────────────────────────────────────
    import json
    with open(out_path) as f:
        data = json.load(f)

    configs = data.get("configs", [])
    per_config = data.get("per_config", {})
    pairwise = data.get("pairwise", {})

    logger.info("Verification:")
    logger.info("  schema_version: %s", data.get("schema_version"))
    logger.info("  configs: %s", configs)
    logger.info("  per_config keys: %s", list(per_config.keys()))
    logger.info("  pairwise keys: %s", list(pairwise.keys()))
    logger.info("  pairwise has divergence_index: %s",
                any("divergence_index" in v for v in pairwise.values()))

    # Summarize detection count differences
    for cfg in configs:
        pc = per_config.get(cfg, {})
        total = 0
        for prim_data in pc.get("per_primitive", {}).values():
            for tf_data in prim_data.get("per_tf", {}).values():
                total += tf_data.get("detection_count", 0)
        logger.info("  %s total detections: %d", cfg, total)

    return 0


if __name__ == "__main__":
    sys.exit(main())
