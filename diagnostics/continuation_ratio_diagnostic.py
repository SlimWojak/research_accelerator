#!/usr/bin/env python3
"""Diagnostic: Sweep vs Continuation ratio investigation.

Instruments _detect_base_sweeps() to capture WHY each continuation fired
(failure mode breakdown), then packages results as YAML for CTO/Olya review.

Usage:
    cd ~/research_accelerator
    python3 diagnostics/continuation_ratio_diagnostic.py

Output:
    diagnostics/continuation_ratio_2025-09-29_10-03.yaml
"""

import copy
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ra.config.loader import load_config
from ra.data.csv_loader import load_csv
from ra.data.river_adapter import RiverAdapter
from ra.data.tf_aggregator import aggregate
from ra.detectors._common import PIP, bar_time_str, compute_atr, map_session
from ra.detectors.liquidity_sweep import (
    _build_level_pool,
    _compute_session_levels,
    _consume_dwelling_levels,
    _count_session_boundaries,
    _detect_base_sweeps,
    _extract_displacements,
    _extract_htf_pools,
    _extract_pdh_pdl,
    _extract_pwh_pwl,
    _extract_session_boxes,
    _extract_swings,
    _qualify_sweeps,
)
from ra.engine.cascade import CascadeEngine, build_default_registry
from ra.evaluation.param_extraction import extract_params

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _run_cascade_locked(config, bars_by_tf):
    """Run the full cascade with locked params and return results."""
    all_prims = [
        "fvg", "ifvg", "bpr", "swing_points", "displacement",
        "session_liquidity", "asia_range", "mss", "order_block",
        "liquidity_sweep", "htf_liquidity", "ote", "reference_levels",
        "equal_hl",
    ]
    params = {}
    for prim in all_prims:
        params[prim] = extract_params(config, prim, mode="locked")

    registry = build_default_registry()
    dep_graph = {
        name: node.model_dump()
        for name, node in config.dependency_graph.items()
    }
    engine = CascadeEngine(registry, dep_graph, variant="a8ra_v1")
    results = engine.run(bars_by_tf, params)
    return results, params


def _diagnostic_detect_sweeps(bars, levels, atrs, params, tf_label):
    """Re-run sweep detection with diagnostic capture for each continuation.

    Returns (sweeps, continuations, diagnostics) where diagnostics is a list
    of per-continuation failure-mode records.
    """
    min_breach_cfg = params.get("min_breach_pips", {}).get("per_tf", {})
    min_reclaim_cfg = params.get("min_reclaim_pips", {}).get("per_tf", {})

    tf_floors = {
        "1m": {"min_breach": 0.5, "min_reclaim": 0.5},
        "5m": {"min_breach": 0.5, "min_reclaim": 0.5},
        "15m": {"min_breach": 1.0, "min_reclaim": 1.0},
    }
    floors = tf_floors.get(tf_label, tf_floors["5m"])
    if tf_label in min_breach_cfg:
        floors["min_breach"] = min_breach_cfg[tf_label]
    if tf_label in min_reclaim_cfg:
        floors["min_reclaim"] = min_reclaim_cfg[tf_label]

    MIN_BREACH = floors["min_breach"] * PIP
    MIN_RECLAIM = floors["min_reclaim"] * PIP
    MAX_ATR_MULT = params.get("max_sweep_size_atr_mult", 1.5)
    MIN_REJ_WICK = params.get("rejection_wick_pct", {}).get("locked", 0.40)
    SWING_STALENESS = params.get("level_sources", {}).get("promoted_swing", {}).get("staleness_bars", 20)

    se_cfg = params.get("level_sources", {}).get("sweep_event_levels", {})
    SE_ENABLED = se_cfg.get("enabled", False)
    SE_MAX_DEPTH = se_cfg.get("max_recursion_depth", 2)
    SE_MAX_AGE = se_cfg.get("max_age_sessions", 3)

    probe_cfg = params.get("level_exhaustion", {}).get("probe_rule", {})
    PROBE_ENABLED = probe_cfg.get("enabled", True)
    PROBE_THRESHOLD = probe_cfg.get("threshold", 5)
    PROBE_RESET_BARS = probe_cfg.get("reset_bars", 3)

    rw_cfg = params.get("return_window_bars", {})
    if isinstance(rw_cfg, dict) and "per_tf" in rw_cfg:
        rw_map = rw_cfg["per_tf"]
    elif isinstance(rw_cfg, dict):
        rw_map = rw_cfg
    else:
        rw_map = {}
    rw_defaults = {"1m": 2, "5m": 3, "15m": 4}
    RETURN_WINDOW = rw_map.get(tf_label, rw_defaults.get(tf_label, 3))

    n = len(bars)
    tf_minutes = {"1m": 1, "5m": 5, "15m": 15}.get(tf_label, 5)

    swept_levels = set()
    cont_seen = set()
    diagnostics = []

    probe_counts = {}
    last_breach_bar = {}

    for i in range(n):
        row = bars.iloc[i]
        if row.get("is_ghost", False):
            continue
        atr_val = atrs[i] if i < len(atrs) and atrs[i] is not None else None
        if atr_val is None:
            continue
        max_breach = MAX_ATR_MULT * atr_val
        bar_time = bar_time_str(row["timestamp_ny"], tf_minutes)

        levels_snapshot = list(levels)
        for lv in levels_snapshot:
            lv_key = (lv["id"], lv["side"])
            if lv_key in swept_levels:
                continue

            # Temporal gate — mirrors production logic exactly
            if lv["source"] == "PROMOTED_SWING":
                if lv["bar_index"] >= i:
                    continue
                if i - lv["bar_index"] > SWING_STALENESS:
                    continue
                bar_fd = row.get("forex_day", "")
                if bar_fd and lv.get("forex_day", "") and lv["forex_day"] != bar_fd:
                    continue
            elif lv["source"] == "SWEEP_EVENT":
                vf = lv.get("valid_from", "")
                if vf and bar_time <= vf:
                    continue
                if SE_MAX_AGE > 0 and _count_session_boundaries(vf, bar_time) > SE_MAX_AGE:
                    continue
            else:
                vf = lv.get("valid_from", "")
                if vf and bar_time < vf:
                    continue

            if PROBE_ENABLED and lv_key in last_breach_bar:
                gap = i - last_breach_bar[lv_key]
                if gap >= PROBE_RESET_BARS:
                    probe_counts.pop(lv_key, None)
                    last_breach_bar.pop(lv_key, None)

            # Check both sides (production processes them sequentially with `continue`)
            for side_check, direction in [("high", "BEARISH"), ("low", "BULLISH")]:
                if lv["side"] != side_check:
                    continue

                if side_check == "high":
                    if not (row["high"] > lv["price"]):
                        continue
                    breach = row["high"] - lv["price"]
                else:
                    if not (row["low"] < lv["price"]):
                        continue
                    breach = lv["price"] - row["low"]

                if breach < MIN_BREACH:
                    continue

                # ── MIRROR PRODUCTION CONTROL FLOW EXACTLY ──
                # Production: find FIRST close-back bar, then check reclaim+wick
                # on that single bar. Break on first close-back regardless of quality.

                closed_back = False
                return_bar_idx = i
                for j in range(i, min(i + RETURN_WINDOW, n)):
                    if side_check == "high":
                        if bars.iloc[j]["close"] < lv["price"]:
                            closed_back = True
                            return_bar_idx = j
                            break
                    else:
                        if bars.iloc[j]["close"] > lv["price"]:
                            closed_back = True
                            return_bar_idx = j
                            break

                resolved = False
                diag_reclaim_pips = 0.0
                diag_wick = 0.0
                diag_failure = "NO_RETURN"

                if closed_back:
                    actual_rw = return_bar_idx - i + 1
                    confirm_bar = bars.iloc[return_bar_idx]
                    if side_check == "high":
                        reclaim = lv["price"] - confirm_bar["close"]
                    else:
                        reclaim = confirm_bar["close"] - lv["price"]

                    diag_reclaim_pips = round(reclaim / PIP, 2)

                    if reclaim < MIN_RECLAIM:
                        diag_failure = "INSUFFICIENT_RECLAIM"
                    else:
                        # Compute wick ratio (same formula as production)
                        if actual_rw == 1:
                            cr = row["high"] - row["low"]
                            if side_check == "high":
                                wick = (row["high"] - max(row["open"], row["close"])) / cr if cr > 0 else 0.0
                            else:
                                wick = (min(row["open"], row["close"]) - row["low"]) / cr if cr > 0 else 0.0
                        else:
                            if side_check == "high":
                                peak = row["high"] - lv["price"]
                                reclaim_below = lv["price"] - confirm_bar["close"]
                                total = peak + reclaim_below
                            else:
                                peak = lv["price"] - row["low"]
                                reclaim_above = confirm_bar["close"] - lv["price"]
                                total = peak + reclaim_above
                            wick = reclaim / total if total > 0 else 0.0

                        diag_wick = round(wick, 4)

                        if wick >= MIN_REJ_WICK:
                            # SWEEP confirmed
                            resolved = True
                        else:
                            diag_failure = "WEAK_WICK"

                if resolved:
                    swept_levels.add(lv_key)
                    continue

                # No valid sweep — check ATR cap for continuation
                if breach > max_breach:
                    cont_key = (lv["id"], direction)
                    if cont_key not in cont_seen:
                        cont_seen.add(cont_key)

                        reclaim_detail = None
                        if closed_back:
                            confirm_bar = bars.iloc[return_bar_idx]
                            confirm_time = bar_time_str(confirm_bar["timestamp_ny"], tf_minutes)
                            reclaim_detail = {
                                "bar_index": int(return_bar_idx),
                                "bar_time": confirm_time,
                                "reclaim_distance_pips": diag_reclaim_pips,
                                "wick_ratio": diag_wick,
                                "failure_reason": diag_failure,
                            }

                        diagnostics.append({
                            "level_id": lv["id"],
                            "level_price": round(lv["price"], 6),
                            "level_source": lv["source"],
                            "direction": direction,
                            "breach_bar_index": int(i),
                            "breach_time": bar_time,
                            "breach_pips": round(breach / PIP, 2),
                            "atr_14_pips": round(atr_val / PIP, 2),
                            "atr_multiple": round(breach / atr_val, 3),
                            "return_window_bars_checked": RETURN_WINDOW,
                            "had_close_back": closed_back,
                            "reclaim_detail": reclaim_detail,
                            "ultimate_failure_mode": diag_failure,
                            "tf": tf_label,
                            "forex_day": row.get("forex_day", ""),
                        })

                    swept_levels.add(lv_key)
                    continue

                # Probe exhaustion path
                if PROBE_ENABLED:
                    last_breach_bar[lv_key] = i
                    probe_counts[lv_key] = probe_counts.get(lv_key, 0) + 1
                    if probe_counts[lv_key] >= PROBE_THRESHOLD:
                        swept_levels.add(lv_key)
                        probe_counts.pop(lv_key, None)
                        last_breach_bar.pop(lv_key, None)

    return diagnostics


def _get_upstream_results(config, bars_by_tf, params, tf_label):
    """Run upstream primitives to get the data needed for sweep detection."""
    registry = build_default_registry()
    dep_graph = {
        name: node.model_dump()
        for name, node in config.dependency_graph.items()
    }
    engine = CascadeEngine(registry, dep_graph, variant="a8ra_v1")
    results = engine.run(bars_by_tf, params)
    return results


def _run_diagnostic_for_tf(config, bars_by_tf, params, tf_label):
    """Run diagnostic for a single timeframe."""
    results = _get_upstream_results(config, bars_by_tf, params, tf_label)

    bars = bars_by_tf[tf_label]
    bars_1m = bars_by_tf.get("1m", bars)

    # Global primitives use "global" key, TF-specific use tf_label
    sess_result = results["session_liquidity"].get("global") or results["session_liquidity"].get(tf_label)
    ref_result = results["reference_levels"].get("global") or results["reference_levels"].get(tf_label)
    htf_result = results["htf_liquidity"].get("global") or results["htf_liquidity"].get(tf_label)
    swing_result = results["swing_points"][tf_label]
    disp_result = results["displacement"][tf_label]

    source_bars = bars_1m
    session_levels = _compute_session_levels(source_bars)
    session_boxes = _extract_session_boxes(sess_result)
    pdh_pdl = _extract_pdh_pdl(ref_result)
    pwh_pwl = _extract_pwh_pwl(ref_result)
    htf_pools = _extract_htf_pools(htf_result)
    swings = _extract_swings(swing_result)

    promoted_swings, merged_non_swing, all_levels, raw_levels = _build_level_pool(
        session_levels, session_boxes, pdh_pdl, htf_pools, pwh_pwl, swings, params["liquidity_sweep"],
    )

    # Sweep target tiering: exclude promoted swings on 1m/5m
    if tf_label in ("1m", "5m"):
        all_levels = [lv for lv in all_levels if lv["source"] != "PROMOTED_SWING"]

    atrs = compute_atr(bars, period=14)

    # Run diagnostic detection
    diagnostics = _diagnostic_detect_sweeps(
        bars, copy.deepcopy(all_levels), atrs, params["liquidity_sweep"], tf_label
    )

    return diagnostics


def _load_dataset_csv(csv_path):
    """Load Jan 2024 data from CSV."""
    bars_1m = load_csv(csv_path)
    bars_by_tf = {"1m": bars_1m}
    for tf in ["5m", "15m"]:
        bars_by_tf[tf] = aggregate(bars_1m, tf)
    return bars_by_tf


def _load_dataset_river(pair, start_date, end_date):
    """Load data from River parquet."""
    adapter = RiverAdapter()
    bars_1m = adapter.load_bars(pair, start_date, end_date)
    bars_by_tf = {"1m": bars_1m}
    for tf in ["5m", "15m"]:
        bars_by_tf[tf] = aggregate(bars_1m, tf)
    return bars_by_tf


def _count_from_results(results, tf_label):
    """Extract sweep/continuation counts from cascade results."""
    sweep_result = results.get("liquidity_sweep", {}).get(tf_label)
    if sweep_result is None:
        return {"sweeps": 0, "continuations": 0}
    return {
        "sweeps": sweep_result.metadata.get("sweep_count", 0),
        "continuations": sweep_result.metadata.get("continuation_count", 0),
    }


def main():
    config_path = Path(__file__).resolve().parent.parent / "configs" / "locked_baseline.yaml"
    config = load_config(config_path)

    all_prims = [
        "fvg", "ifvg", "bpr", "swing_points", "displacement",
        "session_liquidity", "asia_range", "mss", "order_block",
        "liquidity_sweep", "htf_liquidity", "ote", "reference_levels",
        "equal_hl",
    ]
    params = {}
    for prim in all_prims:
        params[prim] = extract_params(config, prim, mode="locked")

    output = {
        "diagnostic": "continuation_ratio_investigation",
        "generated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "hypothesis": "Reclaim failing too often → borderline sweeps classified as continuations",
        "locked_params": {
            "rejection_wick_pct": 0.40,
            "max_sweep_size_atr_mult": 1.5,
            "return_window": {"M1": 2, "M5": 3, "M15": 4},
            "min_breach_pips": {"5m": 0.5, "15m": 1.0},
            "min_reclaim_pips": {"5m": 0.5, "15m": 1.0},
        },
    }

    # ── STEP 1: Raw counts ──────────────────────────────────────────────

    logger.info("=== STEP 1: Raw counts ===")

    # Sep 29 – Oct 3 2025
    logger.info("Loading Sep 29 – Oct 3 2025 EURUSD from River...")
    bars_oct = _load_dataset_river("EURUSD", "2025-09-29", "2025-10-03")
    logger.info("Loaded: 1m=%d, 5m=%d, 15m=%d", len(bars_oct["1m"]), len(bars_oct["5m"]), len(bars_oct["15m"]))

    results_oct, _ = _run_cascade_locked(config, bars_oct)
    counts_oct = {}
    for tf in ["5m", "15m"]:
        counts_oct[tf] = _count_from_results(results_oct, tf)
        sw = counts_oct[tf]["sweeps"]
        co = counts_oct[tf]["continuations"]
        ratio = round(co / sw, 3) if sw > 0 else "inf"
        logger.info("  Oct %s: sweeps=%d, continuations=%d, ratio=%.3f", tf, sw, co, ratio if isinstance(ratio, float) else float('inf'))

    # Jan 7–12 2024
    logger.info("Loading Jan 7–12 2024 EURUSD from CSV...")
    csv_path = Path(__file__).resolve().parent.parent / "data" / "eurusd_1m_2024-01-07_to_2024-01-12.csv"
    bars_jan = _load_dataset_csv(csv_path)
    logger.info("Loaded: 1m=%d, 5m=%d, 15m=%d", len(bars_jan["1m"]), len(bars_jan["5m"]), len(bars_jan["15m"]))

    results_jan, _ = _run_cascade_locked(config, bars_jan)
    counts_jan = {}
    for tf in ["5m", "15m"]:
        counts_jan[tf] = _count_from_results(results_jan, tf)
        sw = counts_jan[tf]["sweeps"]
        co = counts_jan[tf]["continuations"]
        ratio = round(co / sw, 3) if sw > 0 else "inf"
        logger.info("  Jan %s: sweeps=%d, continuations=%d, ratio=%.3f", tf, sw, co, ratio if isinstance(ratio, float) else float('inf'))

    output["step_1_raw_counts"] = {
        "sep_29_oct_03_2025": {
            "5m": counts_oct["5m"],
            "15m": counts_oct["15m"],
            "ratio_5m": round(counts_oct["5m"]["continuations"] / max(counts_oct["5m"]["sweeps"], 1), 3),
            "ratio_15m": round(counts_oct["15m"]["continuations"] / max(counts_oct["15m"]["sweeps"], 1), 3),
        },
        "jan_07_12_2024": {
            "5m": counts_jan["5m"],
            "15m": counts_jan["15m"],
            "ratio_5m": round(counts_jan["5m"]["continuations"] / max(counts_jan["5m"]["sweeps"], 1), 3),
            "ratio_15m": round(counts_jan["15m"]["continuations"] / max(counts_jan["15m"]["sweeps"], 1), 3),
        },
    }

    # ── STEP 2: Per-event failure mode diagnostics (Oct data) ───────────

    logger.info("=== STEP 2: Failure mode diagnostics (Oct 2025) ===")

    all_diagnostics = {}
    for tf in ["5m", "15m"]:
        logger.info("Running diagnostic for %s...", tf)
        diags = _run_diagnostic_for_tf(config, bars_oct, params, tf)
        all_diagnostics[tf] = diags
        logger.info("  %s: %d continuation diagnostics captured", tf, len(diags))

    output["step_2_per_event_diagnostics"] = {
        "dataset": "EURUSD Sep 29 – Oct 3 2025",
        "5m": all_diagnostics.get("5m", []),
        "15m": all_diagnostics.get("15m", []),
    }

    # ── STEP 3: Summary table ───────────────────────────────────────────

    logger.info("=== STEP 3: Summary table ===")

    summary = {}
    for tf in ["5m", "15m"]:
        diags = all_diagnostics.get(tf, [])
        mode_counts = {"NO_RETURN": 0, "INSUFFICIENT_RECLAIM": 0, "WEAK_WICK": 0}
        for d in diags:
            mode = d["ultimate_failure_mode"]
            if mode in mode_counts:
                mode_counts[mode] += 1
        total = sum(mode_counts.values())
        summary[tf] = {
            "total_continuations": total,
            "NO_RETURN": mode_counts["NO_RETURN"],
            "INSUFFICIENT_RECLAIM": mode_counts["INSUFFICIENT_RECLAIM"],
            "WEAK_WICK": mode_counts["WEAK_WICK"],
            "pct_NO_RETURN": round(100 * mode_counts["NO_RETURN"] / max(total, 1), 1),
            "pct_INSUFFICIENT_RECLAIM": round(100 * mode_counts["INSUFFICIENT_RECLAIM"] / max(total, 1), 1),
            "pct_WEAK_WICK": round(100 * mode_counts["WEAK_WICK"] / max(total, 1), 1),
        }
        logger.info("  %s: NO_RETURN=%d, INSUFFICIENT_RECLAIM=%d, WEAK_WICK=%d (total=%d)",
                     tf, mode_counts["NO_RETURN"], mode_counts["INSUFFICIENT_RECLAIM"],
                     mode_counts["WEAK_WICK"], total)

    output["step_3_summary_table"] = summary

    # ── STEP 4: Olya review package (WEAK_WICK events) ─────────────────

    logger.info("=== STEP 4: Olya review package (WEAK_WICK) ===")

    olya_review = []
    for tf in ["5m", "15m"]:
        for d in all_diagnostics.get(tf, []):
            if d["ultimate_failure_mode"] != "WEAK_WICK":
                continue
            rd = d.get("reclaim_detail")
            if rd is None:
                continue

            olya_review.append({
                "tf": d["tf"],
                "time": d["breach_time"],
                "level": f"{d['level_source']} {d['level_price']}",
                "level_id": d["level_id"],
                "direction": d["direction"],
                "breach_pips": d["breach_pips"],
                "atr_multiple": d["atr_multiple"],
                "reclaim_bar_time": rd["bar_time"],
                "reclaim_distance_pips": rd["reclaim_distance_pips"],
                "wick_ratio": rd["wick_ratio"],
                "wick_threshold": 0.40,
                "wick_shortfall": round(0.40 - rd["wick_ratio"], 4),
                "current_classification": "CONTINUATION",
                "question_for_olya": "Is this a sweep or a continuation?",
            })

    output["step_4_olya_review_weak_wick"] = {
        "count": len(olya_review),
        "events": olya_review,
    }

    if olya_review:
        logger.info("  %d WEAK_WICK events for Olya review", len(olya_review))
    else:
        logger.info("  No WEAK_WICK events found — ratio likely driven by NO_RETURN")

    # ── Write output ────────────────────────────────────────────────────

    def _sanitize(obj):
        """Convert numpy types to native Python for clean YAML."""
        import numpy as np
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return round(float(obj), 6)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    output = _sanitize(output)

    out_path = Path(__file__).resolve().parent / "continuation_ratio_2025-09-29_10-03.yaml"
    with open(out_path, "w") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)

    logger.info("=== DONE. Output: %s ===", out_path)


if __name__ == "__main__":
    main()
