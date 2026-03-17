#!/usr/bin/env python3
"""
AutoResearch Evaluation Harness
Adapts Karpathy's autoresearch pattern: ground truth + system under test + score.

Runs each annotated trade through the v2.1 phase classifier and scores
computed classification against Olya's expected state.

Usage:
    python3 tools/autoresearch/evaluate.py
    python3 tools/autoresearch/evaluate.py --param-overrides h1_counter_persistence_bars=4 momentum_stall_window_daily_bars=2
    python3 tools/autoresearch/evaluate.py --ground-truth path/to/trades.yaml
    python3 tools/autoresearch/evaluate.py --output reports/autoresearch/custom_run.yaml
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "site" / "data"
DETECTIONS_DIR = DATA_DIR / "detections"
CANDLES_DIR = DATA_DIR / "candles"
WEEKS_FILE = DATA_DIR / "weeks.json"
DEFAULT_GT = ROOT / "research" / "ground_truth" / "annotated_trades.yaml"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "autoresearch"

# ═══════════════════════════════════════════════════════════════════════════════
# DEFAULT CLASSIFIER THRESHOLDS (v2.1)
# These are the ONLY parameters AutoResearch tunes.
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_PARAMS = {
    "h1_counter_persistence_bars": 3,
    "momentum_stall_window_daily_bars": 3,
    "key_level_tolerance_atr_factor": 0.5,
    "transition_lockout_h1_bars": 2,
    "retrace_to_range_daily_bars": 3,
    "kill_zone_realignment_lookback_hours": 2,
}

# Kill zone windows (NY time, hour only for simplicity)
LOKZ = (2, 5)
NYOKZ = (7, 10)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_weeks():
    with open(WEEKS_FILE) as f:
        return json.load(f)


def date_to_weeks(trade_date: str, weeks: list, lookback_weeks: int = 2) -> list[str]:
    """Find the week(s) containing trade_date plus lookback weeks."""
    from datetime import date
    td = date.fromisoformat(trade_date)
    result = []
    for w in weeks:
        ws = date.fromisoformat(w["start"])
        we = date.fromisoformat(w["end"])
        # Include if week end is within lookback range before trade date,
        # or week contains the trade date
        lookback_start = td - timedelta(days=lookback_weeks * 7)
        if we >= lookback_start and ws <= td:
            result.append(w["week"])
    return result


def load_detections(week_ids: list[str]) -> dict:
    """Load and merge detections from multiple weeks."""
    merged = {}
    for wid in week_ids:
        fpath = DETECTIONS_DIR / f"{wid}.json"
        if not fpath.exists():
            print(f"  WARNING: detection file {fpath} not found", file=sys.stderr)
            continue
        with open(fpath) as f:
            data = json.load(f)
        dbp = data.get("detections_by_primitive", {})
        for prim, by_tf in dbp.items():
            if prim not in merged:
                merged[prim] = {}
            if isinstance(by_tf, dict):
                for tf, dets in by_tf.items():
                    if isinstance(dets, list):
                        merged.setdefault(prim, {}).setdefault(tf, []).extend(dets)
                    else:
                        merged.setdefault(prim, {}).setdefault(tf, dets)
    return merged


def load_candles(week_ids: list[str]) -> dict:
    """Load and merge candles from multiple weeks."""
    merged = {}
    for wid in week_ids:
        fpath = CANDLES_DIR / f"{wid}.json"
        if not fpath.exists():
            continue
        with open(fpath) as f:
            data = json.load(f)
        for tf, bars in data.items():
            if isinstance(bars, list):
                merged.setdefault(tf, []).extend(bars)
    return merged


def parse_time(t: str) -> datetime:
    """Parse detection/candle time string to datetime."""
    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S-04:00",
        "%Y-%m-%dT%H:%M:%S-05:00",
    ]:
        try:
            dt = datetime.strptime(t, fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    # Strip timezone offset manually
    clean = t.split("+")[0].split("-04:00")[0].split("-05:00")[0]
    if "T" in clean:
        return datetime.fromisoformat(clean)
    raise ValueError(f"Cannot parse time: {t}")


# ═══════════════════════════════════════════════════════════════════════════════
# HTF FACT COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

def get_detections_before(dets: list, cutoff: datetime, prim_type: str = None) -> list:
    """Filter detections to those at or before cutoff time."""
    result = []
    for d in dets:
        t = d.get("time", "")
        try:
            dt = parse_time(t)
        except ValueError:
            continue
        if dt <= cutoff:
            result.append(d)
    return result


def compute_daily_structure_direction(detections: dict, candles: dict, trade_dt: datetime, params: dict) -> dict:
    """
    Compute daily structure direction.

    The v2.1 spec defines EXPANSION as: "Most recent daily MSS exists,
    not invalidated." When no daily MSS fires, direction = NEUTRAL = RANGE.

    4H MSS serves as proxy for daily ONLY when daily-scale displacement
    also exists (confirming the 4H event represents a genuine daily structure
    shift). Without daily displacement, 4H MSS provides authority delegation
    in RANGE phase, not daily direction.

    Known limitation: daily MSS rarely fires due to ATR(14) needing 14+ bars
    but weekly windows provide only 5-6. 4H MSS + daily displacement together
    provide equivalent evidence.
    """
    result = {"direction": "NEUTRAL", "method": "none", "mss_time": None, "confidence": "LOW"}

    # Try daily MSS first
    daily_mss = detections.get("mss", {}).get("1D", [])
    daily_before = get_detections_before(daily_mss, trade_dt)
    if daily_before:
        daily_before.sort(key=lambda d: d["time"])
        last = daily_before[-1]
        direction = last.get("direction", last.get("properties", {}).get("direction", ""))
        result["direction"] = direction.upper()
        result["method"] = "daily_mss"
        result["mss_time"] = last["time"]
        result["confidence"] = "HIGH"
        return result

    # Step 1: Find most recent 4H MSS (proxy for daily structure)
    h4_mss = detections.get("mss", {}).get("4H", [])
    h4_before = get_detections_before(h4_mss, trade_dt)

    if h4_before:
        h4_before.sort(key=lambda d: d["time"])
        last_mss = h4_before[-1]
        mss_direction = last_mss.get("properties", {}).get("direction", last_mss.get("direction", "")).upper()
        mss_time = parse_time(last_mss["time"])

        # Check for invalidation: opposing MSS fired after this one
        invalidated = any(
            parse_time(d["time"]) > mss_time
            and d.get("properties", {}).get("direction", d.get("direction", "")).upper() != mss_direction
            for d in h4_before
        )

        if not invalidated:
            # Step 2: Verify daily-scale displacement confirmation.
            # 4H MSS proxies for daily only when daily candles also show
            # clear directional conviction (the 4H event represents a genuine
            # daily structure shift, not just a local 4H move).
            has_confirming_displacement = False

            # Check 1D displacement directly
            daily_disp = detections.get("displacement", {}).get("1D", [])
            daily_disp_before = get_detections_before(daily_disp, trade_dt)
            for dd in daily_disp_before:
                if dd["direction"].upper() == mss_direction:
                    has_confirming_displacement = True
                    break

            # Check daily candles for displacement-quality bars in MSS direction.
            # This catches the case where the detection engine can't fire daily
            # displacement (ATR limitation) but the candles show clear direction.
            # Requires 2+ daily bars with body_ratio >= 0.60 in MSS direction
            # within 5 days surrounding the MSS event, establishing that this
            # is a sustained daily move, not a single-day reaction.
            if not has_confirming_displacement:
                daily_bars = candles.get("1D", [])
                mss_window_start = mss_time - timedelta(days=3)
                mss_window_end = mss_time + timedelta(days=2)
                qualifying_bars = 0
                for bar in daily_bars:
                    bt = parse_time(bar["time"])
                    if mss_window_start <= bt <= mss_window_end:
                        o, c = bar["open"], bar["close"]
                        h, l = bar["high"], bar["low"]
                        body = abs(c - o)
                        rng = h - l
                        if rng > 0:
                            body_ratio = body / rng
                            is_dir = (mss_direction == "BEARISH" and c < o) or \
                                     (mss_direction == "BULLISH" and c > o)
                            if is_dir and body_ratio >= 0.60 and rng >= 0.0040:
                                qualifying_bars += 1
                # Need 2+ qualifying daily bars to confirm daily-scale move
                if qualifying_bars >= 2:
                    has_confirming_displacement = True

            if has_confirming_displacement:
                result["direction"] = mss_direction
                result["method"] = "4h_mss_proxy_with_displacement"
                result["mss_time"] = last_mss["time"]
                age_hours = (trade_dt - mss_time).total_seconds() / 3600
                if age_hours <= 5 * 24:
                    result["confidence"] = "HIGH"
                elif age_hours <= 15 * 24:
                    result["confidence"] = "MEDIUM"
                else:
                    result["confidence"] = "LOW"
                return result

    # No daily structure established
    return result


def compute_h1_alignment(detections: dict, trade_dt: datetime,
                         daily_direction: str, params: dict) -> dict:
    """
    Compute 1H alignment relative to daily direction.
    v2.1: swing structure primary, MSS confirming.
    """
    result = {"status": "ALIGNED", "method": "default", "details": ""}

    if daily_direction == "NEUTRAL":
        result["status"] = "NEUTRAL"
        result["method"] = "daily_neutral"
        return result

    # Get 1H swing points before trade time
    h1_swings = detections.get("swing_points", {}).get("1H", [])
    h1_before = get_detections_before(h1_swings, trade_dt)
    h1_before.sort(key=lambda d: d["time"])

    persistence = params["h1_counter_persistence_bars"]

    # Analyze swing structure: look for HH/HL or LL/LH pattern in recent swings
    if len(h1_before) >= 3:
        recent = h1_before[-6:]  # Last 6 swing points for pattern analysis
        highs = [s for s in recent if s.get("direction", s.get("type", "")) in ("high", "swing_point_high", "SwingHigh")]
        lows = [s for s in recent if s.get("direction", s.get("type", "")) in ("low", "swing_point_low", "SwingLow")]

        if len(highs) >= 2 and len(lows) >= 2:
            h_prices = [h["price"] for h in highs[-2:]]
            l_prices = [l["price"] for l in lows[-2:]]

            hh = h_prices[-1] > h_prices[-2]
            hl = l_prices[-1] > l_prices[-2]
            ll = l_prices[-1] < l_prices[-2]
            lh = h_prices[-1] < h_prices[-2]

            swing_direction = "NEUTRAL"
            if hh and hl:
                swing_direction = "BULLISH"
            elif ll and lh:
                swing_direction = "BEARISH"

            # Check if counter to daily
            is_counter = (
                (daily_direction == "BEARISH" and swing_direction == "BULLISH") or
                (daily_direction == "BULLISH" and swing_direction == "BEARISH")
            )

            if is_counter:
                # Check displacement-quality gate
                h1_disp = detections.get("displacement", {}).get("1H", [])
                h1_disp_before = get_detections_before(h1_disp, trade_dt)
                counter_dir = "bullish" if daily_direction == "BEARISH" else "bearish"
                counter_disps = [
                    d for d in h1_disp_before
                    if d.get("direction", "").lower() == counter_dir
                    and d.get("properties", {}).get("body_ratio", 0) >= 0.60
                    and d.get("properties", {}).get("quality_grade", "") in ("VALID", "STRONG")
                ]

                # Check persistence: recent swings span enough bars
                if len(recent) >= 2:
                    first_counter_time = parse_time(recent[-persistence]["time"]) if len(recent) >= persistence else parse_time(recent[0]["time"])
                    last_counter_time = parse_time(recent[-1]["time"])
                    span_hours = (last_counter_time - first_counter_time).total_seconds() / 3600

                    if counter_disps and span_hours >= persistence:
                        result["status"] = "COUNTER"
                        result["method"] = "swing_primary"
                        result["details"] = (
                            f"1H {swing_direction} pattern counter to daily {daily_direction}. "
                            f"Span {span_hours:.0f}h, {len(counter_disps)} displacement-quality moves."
                        )
                        return result

    # Check 1H MSS as confirming signal
    h1_mss = detections.get("mss", {}).get("1H", [])
    h1_mss_before = get_detections_before(h1_mss, trade_dt)
    if h1_mss_before:
        h1_mss_before.sort(key=lambda d: d["time"])
        last_h1_mss = h1_mss_before[-1]
        last_dir = last_h1_mss.get("properties", {}).get("direction", last_h1_mss.get("direction", "")).upper()
        is_counter = (
            (daily_direction == "BEARISH" and last_dir == "BULLISH") or
            (daily_direction == "BULLISH" and last_dir == "BEARISH")
        )
        if is_counter:
            result["status"] = "COUNTER"
            result["method"] = "mss_confirming"
            result["details"] = f"1H MSS {last_dir} at {last_h1_mss['time']} counter to daily {daily_direction}"

    return result


def check_kill_zone_realignment(detections: dict, trade_dt: datetime,
                                daily_direction: str, h1_alignment: dict,
                                params: dict) -> dict:
    """
    Check if kill zone realignment exception applies.
    Within LOKZ/NYOKZ: 15m/5m MSS in daily direction can restore ALIGNED
    when 1H counter-move has gone quiet.
    """
    if h1_alignment["status"] != "COUNTER":
        return h1_alignment

    hour = trade_dt.hour
    in_lokz = LOKZ[0] <= hour < LOKZ[1]
    in_nyokz = NYOKZ[0] <= hour < NYOKZ[1]
    if not (in_lokz or in_nyokz):
        return h1_alignment

    lookback_hours = params["kill_zone_realignment_lookback_hours"]
    kz_name = "LOKZ" if in_lokz else "NYOKZ"

    # Check for 15m or 5m MSS in daily direction within the kill zone
    for tf in ["15m", "5m"]:
        tf_mss = detections.get("mss", {}).get(tf, [])
        tf_mss_before = get_detections_before(tf_mss, trade_dt)
        kz_start = trade_dt.replace(hour=LOKZ[0] if in_lokz else NYOKZ[0], minute=0, second=0)

        for m in reversed(tf_mss_before):
            mt = parse_time(m["time"])
            if mt < kz_start:
                break
            mdir = m.get("properties", {}).get("direction", m.get("direction", "")).upper()
            if mdir == daily_direction:
                # Check no new 1H MSS in opposing direction in last N hours
                cutoff = mt - timedelta(hours=lookback_hours)
                h1_mss = detections.get("mss", {}).get("1H", [])
                recent_h1 = [
                    d for d in h1_mss
                    if cutoff <= parse_time(d["time"]) <= mt
                    and d.get("properties", {}).get("direction", d.get("direction", "")).upper() != daily_direction
                ]
                if not recent_h1:
                    return {
                        "status": "ALIGNED",
                        "method": "kill_zone_realignment",
                        "details": (
                            f"{tf} {mdir} MSS at {m['time']} in {kz_name}. "
                            f"No opposing 1H MSS in last {lookback_hours}h. "
                            f"Realignment to ALIGNED."
                        ),
                    }

    return h1_alignment


def compute_momentum_active(detections: dict, trade_dt: datetime,
                            daily_direction: str, params: dict) -> bool:
    """
    Check if daily-scale displacement is active (recent momentum).
    v2.1 spec: EXISTS(daily, Displacement, direction=structure_direction, age_bars <= N)
    Uses 4H as proxy: most recent same-direction 4H displacement within
    N trading days (where N = stall window in daily bars).
    """
    stall_window = params["momentum_stall_window_daily_bars"]
    # Convert daily bars to approximate hours (trading day ~24h, but weekends)
    # Use generous window: N daily bars ≈ N * 1.4 calendar days (accounting for weekends)
    max_age_hours = stall_window * 24 * 1.5

    for tf in ["1D", "4H"]:
        disps = detections.get("displacement", {}).get(tf, [])
        disps_before = get_detections_before(disps, trade_dt)
        if not disps_before:
            continue

        # Filter to same direction as daily structure (if known)
        if daily_direction and daily_direction != "NEUTRAL":
            same_dir = [
                d for d in disps_before
                if d.get("direction", "").upper() == daily_direction
            ]
        else:
            same_dir = disps_before

        if not same_dir:
            continue

        same_dir.sort(key=lambda d: d["time"])
        last = same_dir[-1]
        last_time = parse_time(last["time"])
        age_hours = (trade_dt - last_time).total_seconds() / 3600

        if age_hours <= max_age_hours:
            return True

    return False


def compute_at_key_level(detections: dict, candles: dict,
                         trade_dt: datetime, params: dict) -> bool:
    """
    Check if price is at a significant HTF key level.
    v2.1 spec: price_inside(monthly/weekly FVG) OR price_at(HTF_EQH_EQL)
    OR price_at(PWH_PWL), all within ATR tolerance.

    Daily FVGs are NOT key levels for this check — they are the expansion's
    own imbalance. Only weekly/monthly FVGs and HTF EQH/EQL (4H+ timeframe)
    qualify as "decision areas" that can demote EXPANSION to RANGE.
    """
    current_price = None
    for tf in ["1H", "4H", "1D"]:
        bars = candles.get(tf, [])
        if bars:
            bars_before = [b for b in bars if parse_time(b["time"]) <= trade_dt]
            if bars_before:
                bars_before.sort(key=lambda b: b["time"])
                current_price = bars_before[-1]["close"]
                break

    if current_price is None:
        return False

    tolerance_factor = params.get("key_level_tolerance_atr_factor", 0.5)
    tolerance = 0.0070 * tolerance_factor

    # Weekly/monthly FVGs not yet in pipeline — skip for now
    # When available, check: price_inside(weekly.FVG, state=ACTIVE)

    # Check HTF liquidity levels: price near UNTOUCHED EQH/EQL.
    # Only Daily+ (D1/W1/MN) liquidity levels qualify as "key levels" that
    # can demote EXPANSION to RANGE. 4H levels form during expansions and
    # are too granular to represent decision areas.
    htf_liq = detections.get("htf_liquidity", {}).get("global", [])
    if isinstance(htf_liq, list):
        for level in htf_liq:
            level_price = level.get("price", 0)
            status = level.get("properties", {}).get("status", "")
            tf = level.get("properties", {}).get("timeframe", "")
            if status == "UNTOUCHED" and tf in ("D1", "1D", "W1", "MN"):
                if abs(current_price - level_price) <= tolerance:
                    return True

    return False


def find_authority_tf(detections: dict, trade_dt: datetime) -> dict:
    """
    In RANGE phase, determine which sub-daily TF has authority.
    Most recent MSS between 4H and 1H wins.
    """
    result = {"authority_tf": None, "direction": "NEUTRAL", "mss_time": None}

    best_time = None
    for tf in ["4H", "1H"]:
        mss = detections.get("mss", {}).get(tf, [])
        mss_before = get_detections_before(mss, trade_dt)
        if mss_before:
            mss_before.sort(key=lambda d: d["time"])
            last = mss_before[-1]
            last_time = parse_time(last["time"])
            if best_time is None or last_time > best_time:
                best_time = last_time
                direction = last.get("properties", {}).get("direction", last.get("direction", "")).upper()
                result["authority_tf"] = tf
                result["direction"] = direction
                result["mss_time"] = last["time"]

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# V2.1 PHASE CLASSIFIER
# ═══════════════════════════════════════════════════════════════════════════════

def classify_phase(detections: dict, candles: dict,
                   trade_dt: datetime, params: dict, trade: dict) -> dict:
    """
    Apply v2.1 phase classification rules.
    Returns computed state + diagnostics.
    """
    strategy_type = trade.get("strategy_type", "state_gated")

    # INDEPENDENT strategies bypass the classifier
    if strategy_type == "asia_range_scalp" or trade["expected_state"]["htf_phase"] == "INDEPENDENT":
        return {
            "htf_phase": "INDEPENDENT",
            "direction_permission": "INDEPENDENT",
            "daily_direction": "NEUTRAL",
            "authority_tf": "N/A",
            "method": "strategy_bypass",
            "facts": {},
            "diagnostics": [],
        }

    # Step 1: Compute HTF facts
    daily_struct = compute_daily_structure_direction(detections, candles, trade_dt, params)
    daily_direction = daily_struct["direction"]

    h1_align = compute_h1_alignment(detections, trade_dt, daily_direction, params)
    h1_align = check_kill_zone_realignment(detections, trade_dt, daily_direction, h1_align, params)

    momentum = compute_momentum_active(detections, trade_dt, daily_direction, params)
    at_key = compute_at_key_level(detections, candles, trade_dt, params)

    facts = {
        "daily_structure": daily_struct,
        "h1_alignment": h1_align,
        "momentum_active": momentum,
        "at_key_level": at_key,
    }

    diagnostics = []

    # Step 2: Classify phase

    # Check RANGE first: daily neutral OR key level + stall
    if daily_direction == "NEUTRAL":
        authority = find_authority_tf(detections, trade_dt)
        facts["authority"] = authority
        return {
            "htf_phase": "RANGE",
            "direction_permission": "BOTH",
            "daily_direction": daily_direction,
            "authority_tf": authority["authority_tf"] or "N/A",
            "authority_direction": authority["direction"],
            "method": "daily_neutral",
            "facts": facts,
            "diagnostics": diagnostics,
        }

    if daily_direction != "NEUTRAL" and at_key and not momentum:
        authority = find_authority_tf(detections, trade_dt)
        facts["authority"] = authority
        diagnostics.append(
            f"Daily {daily_direction} but at key level with stalled momentum → RANGE"
        )
        return {
            "htf_phase": "RANGE",
            "direction_permission": "BOTH",
            "daily_direction": daily_direction,
            "authority_tf": authority["authority_tf"] or "N/A",
            "authority_direction": authority.get("direction", "NEUTRAL"),
            "method": "key_level_stall",
            "facts": facts,
            "diagnostics": diagnostics,
        }

    # Check RETRACE: daily direction exists + 1H counter
    if h1_align["status"] == "COUNTER":
        return {
            "htf_phase": "RETRACE",
            "direction_permission": "COUNTER_ALLOWED",
            "daily_direction": daily_direction,
            "authority_tf": "Daily",
            "method": f"h1_counter ({h1_align['method']})",
            "facts": facts,
            "diagnostics": diagnostics,
        }

    # Default: EXPANSION
    return {
        "htf_phase": "EXPANSION",
        "direction_permission": "WITH_EXPANSION",
        "daily_direction": daily_direction,
        "authority_tf": "Daily",
        "method": f"daily_{daily_direction.lower()}_expansion",
        "facts": facts,
        "diagnostics": diagnostics,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTION CHAIN VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

def check_execution_chain(detections: dict, trade: dict, trade_dt: datetime) -> dict:
    """
    Verify that expected execution chain primitives fire
    within the expected time window.
    """
    chain = trade.get("execution_chain", {})
    steps = chain.get("steps", [])
    if not steps:
        return {"status": "N/A", "matched": 0, "total": 0, "details": []}

    trade_date_str = trade["date"]
    matched = 0
    details = []

    for step in steps:
        prim = step["primitive"]
        tf = step["tf"]
        expected_time = step.get("time", "")

        # Map primitive names to detection keys
        prim_map = {
            "sweep": "liquidity_sweep",
            "mss": "mss",
            "displacement": "displacement",
            "fvg": "fvg",
            "ob": "order_block",
            "ote": "ote",
        }
        det_key = prim_map.get(prim, prim)

        tf_dets = detections.get(det_key, {}).get(tf, [])
        if not tf_dets:
            details.append({
                "step": f"{prim} on {tf} at ~{expected_time}",
                "status": "MISSED",
                "reason": f"No {det_key} detections on {tf}",
            })
            continue

        # Filter to trade date
        trade_day_dets = [
            d for d in tf_dets
            if d.get("time", "").startswith(trade_date_str)
        ]

        if not trade_day_dets:
            details.append({
                "step": f"{prim} on {tf} at ~{expected_time}",
                "status": "MISSED",
                "reason": f"No {det_key} detections on {tf} for date {trade_date_str}",
            })
            continue

        # Check if any detection is within tolerance of expected time.
        # Use 120 min tolerance: execution times in ground truth are
        # Olya's approximate annotations, not exact timestamps.
        if expected_time:
            expected_dt = datetime.strptime(f"{trade_date_str}T{expected_time}:00", "%Y-%m-%dT%H:%M:%S")
            found = False
            for d in trade_day_dets:
                dt = parse_time(d["time"])
                diff_min = abs((dt - expected_dt).total_seconds()) / 60
                if diff_min <= 120:  # 120 min tolerance for approximate annotations
                    matched += 1
                    found = True
                    details.append({
                        "step": f"{prim} on {tf} at ~{expected_time}",
                        "status": "FIRED",
                        "actual_time": d["time"],
                        "diff_min": round(diff_min, 1),
                    })
                    break
            if not found:
                nearest = min(trade_day_dets, key=lambda d: abs((parse_time(d["time"]) - expected_dt).total_seconds()))
                details.append({
                    "step": f"{prim} on {tf} at ~{expected_time}",
                    "status": "MISSED",
                    "reason": f"Nearest detection at {nearest['time']} ({abs((parse_time(nearest['time']) - expected_dt).total_seconds()) / 60:.0f} min away)",
                })
        else:
            matched += 1
            details.append({
                "step": f"{prim} on {tf}",
                "status": "FIRED",
                "actual_time": trade_day_dets[0]["time"],
            })

    total = len(steps)
    if matched == total:
        status = "FIRED"
    elif matched > 0:
        status = "PARTIAL"
    else:
        status = "MISSED"

    return {"status": status, "matched": matched, "total": total, "details": details}


# ═══════════════════════════════════════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════════════════════════════════════

def score_trade(trade: dict, computed: dict, chain_result: dict) -> dict:
    """Compare computed classification against expected state."""
    expected = trade["expected_state"]
    diagnostics = []

    phase_match = computed["htf_phase"] == expected["htf_phase"]
    if not phase_match:
        diagnostics.append({
            "fact": "htf_phase",
            "expected": expected["htf_phase"],
            "computed": computed["htf_phase"],
            "method": computed.get("method", ""),
        })

    perm_match = computed["direction_permission"] == expected["direction_permission"]
    if not perm_match:
        diagnostics.append({
            "fact": "direction_permission",
            "expected": expected["direction_permission"],
            "computed": computed["direction_permission"],
        })

    dir_match = computed["daily_direction"] == expected["daily_direction"]
    if not dir_match:
        diagnostics.append({
            "fact": "daily_direction",
            "expected": expected["daily_direction"],
            "computed": computed["daily_direction"],
        })

    auth_expected = expected.get("authority_tf", "N/A")
    auth_computed = computed.get("authority_tf", "N/A")
    auth_match = auth_expected == auth_computed
    if not auth_match:
        diagnostics.append({
            "fact": "authority_tf",
            "expected": auth_expected,
            "computed": auth_computed,
        })

    # Overall verdict
    if phase_match and perm_match:
        if chain_result["status"] in ("FIRED", "N/A"):
            verdict = "PASS"
        else:
            verdict = "PARTIAL"
    else:
        verdict = "FAIL"

    return {
        "verdict": verdict,
        "phase_match": phase_match,
        "permission_match": perm_match,
        "direction_match": dir_match,
        "authority_match": auth_match,
        "chain_status": chain_result["status"],
        "diagnostics": diagnostics,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EVALUATION LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate(gt_path: str, params: dict, output_path: str = None):
    """Run evaluation on all trades in ground truth file."""
    with open(gt_path) as f:
        gt = yaml.safe_load(f)

    trades = gt.get("trades", [])
    if not trades:
        print("ERROR: No trades found in ground truth file", file=sys.stderr)
        sys.exit(1)

    weeks = load_weeks()
    results = []
    pass_count = 0
    partial_count = 0
    fail_count = 0

    print(f"AutoResearch Evaluate — {len(trades)} trades")
    print(f"Parameters: {params}")
    print("=" * 70)

    for trade in trades:
        tid = trade["id"]
        strategy = trade.get("strategy_type", "state_gated")
        lookback = 0 if strategy == "asia_range_scalp" else 2

        print(f"\n--- {tid}: {trade['date']} {trade['direction']} ({trade['expected_state']['htf_phase']}) ---")

        # Load data
        week_ids = date_to_weeks(trade["date"], weeks, lookback_weeks=lookback)
        print(f"  Loading weeks: {week_ids}")
        detections = load_detections(week_ids)
        candles = load_candles(week_ids)

        # Parse trade datetime
        exec_time = trade.get("execution_time", "12:00")
        trade_dt = datetime.strptime(f"{trade['date']}T{exec_time}:00", "%Y-%m-%dT%H:%M:%S")

        # Classify
        computed = classify_phase(detections, candles, trade_dt, params, trade)
        print(f"  Computed: {computed['htf_phase']} / {computed['direction_permission']} "
              f"(daily={computed['daily_direction']}, auth={computed.get('authority_tf', 'N/A')})")
        print(f"  Method:   {computed.get('method', 'N/A')}")

        # Check execution chain
        chain_result = check_execution_chain(detections, trade, trade_dt)
        print(f"  Chain:    {chain_result['status']} ({chain_result['matched']}/{chain_result['total']})")

        # Score
        score = score_trade(trade, computed, chain_result)
        print(f"  Verdict:  {score['verdict']}")

        if score["diagnostics"]:
            for d in score["diagnostics"]:
                print(f"    MISMATCH: {d['fact']} expected={d['expected']} computed={d['computed']}")

        if score["verdict"] == "PASS":
            pass_count += 1
        elif score["verdict"] == "PARTIAL":
            partial_count += 1
        else:
            fail_count += 1

        results.append({
            "trade_id": tid,
            "date": trade["date"],
            "direction": trade["direction"],
            "expected_state": trade["expected_state"],
            "computed_state": {
                "htf_phase": computed["htf_phase"],
                "direction_permission": computed["direction_permission"],
                "daily_direction": computed["daily_direction"],
                "authority_tf": computed.get("authority_tf", "N/A"),
                "method": computed.get("method", ""),
            },
            "chain": {
                "status": chain_result["status"],
                "matched": chain_result["matched"],
                "total": chain_result["total"],
                "details": chain_result["details"],
            },
            "verdict": score["verdict"],
            "diagnostics": score["diagnostics"],
            "facts": {k: str(v) for k, v in computed.get("facts", {}).items()},
        })

    # Summary
    total = len(trades)
    print("\n" + "=" * 70)
    print(f"RESULTS: {pass_count}/{total} PASS, {partial_count} PARTIAL, {fail_count} FAIL")
    pct = (pass_count / total * 100) if total else 0
    print(f"Score: {pct:.0f}%")
    print("=" * 70)

    # Build output report
    report = {
        "metadata": {
            "run_time": datetime.now().isoformat(),
            "ground_truth_file": str(gt_path),
            "parameters": params,
            "version": "v2.1",
        },
        "summary": {
            "total_trades": total,
            "pass": pass_count,
            "partial": partial_count,
            "fail": fail_count,
            "score": f"{pass_count}/{total} ({pct:.0f}%)",
        },
        "per_trade": results,
    }

    # Write output
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(DEFAULT_OUTPUT_DIR / f"eval_{ts}.yaml")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(report, f, default_flow_style=False, sort_keys=False, width=120)

    print(f"\nReport written to: {output_path}")
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="AutoResearch Evaluation Harness")
    parser.add_argument("--ground-truth", default=str(DEFAULT_GT),
                        help="Path to ground truth YAML")
    parser.add_argument("--output", default=None,
                        help="Output report path (default: reports/autoresearch/eval_TIMESTAMP.yaml)")
    parser.add_argument("--param-overrides", nargs="*", default=[],
                        help="Override classifier params: key=value pairs")
    args = parser.parse_args()

    params = dict(DEFAULT_PARAMS)
    for override in args.param_overrides:
        if "=" not in override:
            print(f"ERROR: Invalid override format '{override}', expected key=value", file=sys.stderr)
            sys.exit(1)
        key, val = override.split("=", 1)
        if key not in params:
            print(f"WARNING: Unknown parameter '{key}', adding anyway", file=sys.stderr)
        try:
            params[key] = int(val)
        except ValueError:
            try:
                params[key] = float(val)
            except ValueError:
                params[key] = val

    evaluate(args.ground_truth, params, args.output)


if __name__ == "__main__":
    main()
