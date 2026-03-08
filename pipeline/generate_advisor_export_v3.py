"""
Generate calibration_data_export.yaml v3 — Multi-TF Native Detection
Full event lists at DEFAULT thresholds per TF, summary counts at all others.
All timestamps in NY time (EST, UTC-5).
"""

import json
import os

# Paths relative to repo root (run from pipeline/ directory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(REPO_ROOT, "site")

def load_json(name):
    with open(os.path.join(DATA_DIR, name)) as f:
        return json.load(f)

def main():
    print("Loading data...")
    metadata = load_json("metadata.json")
    asia_data = load_json("asia_data.json")
    levels_data = load_json("levels_data.json")

    # Load per-TF detection data
    tf_data = {}
    for tf in ['1m', '5m', '15m']:
        tf_data[tf] = {
            'fvg': load_json(f"fvg_data_{tf}.json"),
            'swing': load_json(f"swing_data_{tf}.json"),
            'disp': load_json(f"displacement_data_{tf}.json"),
            'ob': load_json(f"ob_data_{tf}.json"),
            'ny': load_json(f"ny_windows_data_{tf}.json"),
        }

    forex_days = metadata["forex_days"]
    tf_config = metadata.get("tf_config", {})
    lines = []
    
    def w(text=""):
        lines.append(text)

    # ─── Header ───────────────────────────────────────────────
    w("# ═══════════════════════════════════════════════════════════")
    w("# a8ra Calibration Data Export v3 — Native Multi-TF")
    w("# For CTO + Advisor Panel — mirrors Calibration Visual Bible")
    w("# ═══════════════════════════════════════════════════════════")
    w()
    w("meta:")
    w("  purpose: Structured export of all detection results for advisor reference during Olya calibration session")
    w("  data_source: EURUSD 1m, 2024-01-07 to 2024-01-12 (7,177 bars)")
    w("  timezone: NY (EST, UTC-5)")
    w("  native_detection: true  # Detection runs natively on each TF's bars, NOT projected from 1m")
    w("  detection_timeframes: [1m, 5m, 15m]")
    w("  primary_timeframe: 5m  # Olya's default viewing TF")
    w(f"  forex_days: {forex_days}")
    w("  forex_day_boundary: '17:00 NY'")
    w("  pip_value: 0.0001")
    w("  sessions_ny:")
    w("    asia: '19:00-00:00 NY'")
    w("    lokz: '02:00-05:00 NY'")
    w("    nyokz: '07:00-10:00 NY'")
    w("  ny_reversal_windows:")
    w("    window_a: '08:00-09:00 NY'")
    w("    window_b: '10:00-11:00 NY'")
    w("  note: Full event lists at DEFAULT thresholds. Summary counts at all thresholds. 5m is primary, 1m and 15m for reference.")
    w()

    # ─── Levels ───────────────────────────────────────────────
    w("# ═══════════════════════════════════════════════════════════")
    w("# PDH / PDL / Day Extremes")
    w("# ═══════════════════════════════════════════════════════════")
    w("levels:")
    for day in forex_days:
        if day in levels_data:
            lv = levels_data[day]
            w(f"  {day}:")
            w(f"    day_high: {lv['day_high']:.5f}")
            w(f"    day_low: {lv['day_low']:.5f}")
            if "pdh" in lv:
                w(f"    pdh: {lv['pdh']:.5f}")
                w(f"    pdl: {lv['pdl']:.5f}")
            w(f"    midnight_open: {lv.get('midnight_open', 0):.5f}")
    w()

    # ─── FVG per TF ───────────────────────────────────────────
    for tf in ['5m', '1m', '15m']:
        fvg_d = tf_data[tf]['fvg']
        fvgs = fvg_d['fvgs']
        thresholds = fvg_d['thresholds']
        
        # Choose default threshold per TF
        default_t = thresholds[len(thresholds)//2] if thresholds else 2.0
        
        w("# ═══════════════════════════════════════════════════════════")
        w(f"# FVG — Fair Value Gap — NATIVE {tf} DETECTION")
        w("# Detection: low[C] > high[A] (bullish), high[C] < low[A] (bearish)")
        w(f"# A genuine {tf} FVG = gap exists across 3 consecutive {tf} candles")
        w("# ═══════════════════════════════════════════════════════════")
        w(f"fvg_{tf}:")
        w(f"  total_fvgs: {len(fvgs)}")
        w(f"  thresholds: {thresholds}")
        w(f"  default_threshold: {default_t}")

        w("  threshold_matrix:")
        for day in forex_days:
            day_fvgs = [f for f in fvgs if f["forex_day"] == day]
            w(f"    {day}:")
            for t in thresholds:
                filtered = [f for f in day_fvgs if f["gap_pips"] >= t]
                bull = sum(1 for f in filtered if f["type"] == "bullish")
                bear = sum(1 for f in filtered if f["type"] == "bearish")
                gaps = sorted([f["gap_pips"] for f in filtered])
                median = gaps[len(gaps)//2] if gaps else 0
                w(f"      {t}_pip: {{total: {len(filtered)}, bull: {bull}, bear: {bear}, median_gap: {median:.2f}}}")
        w()

        w(f"  events_at_{default_t}pip:")
        for day in forex_days:
            day_fvgs = [f for f in fvgs if f["forex_day"] == day and f["gap_pips"] >= default_t]
            w(f"    {day}: # {len(day_fvgs)} FVGs")
            for f in day_fvgs:
                if f.get("boundary_closed_time"):
                    inv = f"boundary_closed @ {f['boundary_closed_time']}"
                elif f.get("ce_touched_time"):
                    inv = f"ce_touched @ {f['ce_touched_time']}"
                else:
                    inv = "active"
                vi = ", vi: true" if f.get("vi_confluent") else ""
                w(f"      - {{time: '{f['detect_time']}', dir: {f['type']}, gap: {f['gap_pips']}pip, zone: [{f['bottom']:.5f}, {f['top']:.5f}], ce: {f['ce']:.5f}, session: {f['session']}, invalidation: '{inv}'{vi}}}")
        w()

    # ─── Swing Points per TF ──────────────────────────────────
    for tf in ['5m', '1m', '15m']:
        sw_d = tf_data[tf]['swing']
        swings = sw_d['swings']
        h_thresholds = sw_d['height_thresholds']
        eq_tol = sw_d['equal_tolerances']
        
        default_h = h_thresholds[len(h_thresholds)//2] if h_thresholds else 5.0

        w("# ═══════════════════════════════════════════════════════════")
        w(f"# SWING POINTS — NATIVE {tf} DETECTION — N=5")
        w("# Corrected equality: >= left, > right")
        w("# Strength = extra bars beyond N=5 that respect the extreme (capped at 20)")
        w("# ═══════════════════════════════════════════════════════════")
        w(f"swing_points_{tf}:")
        w(f"  total_swings: {len(swings)}")
        w(f"  height_thresholds: {h_thresholds}")
        w(f"  default_threshold: {default_h}")

        w("  threshold_matrix:")
        for day in forex_days:
            day_sw = [s for s in swings if s["forex_day"] == day]
            w(f"    {day}:")
            for t in h_thresholds:
                filt = [s for s in day_sw if s["height_pips"] >= t]
                highs = sum(1 for s in filt if s["type"] == "high")
                lows = sum(1 for s in filt if s["type"] == "low")
                strengths = [s["strength"] for s in filt]
                avg_str = round(sum(strengths)/len(strengths), 1) if strengths else 0
                w(f"      {t}_pip: {{total: {len(filt)}, highs: {highs}, lows: {lows}, avg_strength: {avg_str}}}")
        w()

        w(f"  events_at_{default_h}pip:")
        for day in forex_days:
            day_sw = [s for s in swings if s["forex_day"] == day and s["height_pips"] >= default_h]
            w(f"    {day}: # {len(day_sw)} swings")
            for s in day_sw:
                w(f"      - {{time: '{s['time']}', type: {s['type']}, price: {s['price']:.5f}, height: {s['height_pips']}pip, strength: {s['strength']}, session: {s['session']}}}")
        w()

        # Equal H/L (only for primary TF = 5m)
        if tf == '5m':
            w(f"  equal_hl:")
            eq_h = sw_d["equal_highs"]
            eq_l = sw_d["equal_lows"]
            w(f"    tolerances: {eq_tol}")
            w(f"    summary:")
            for tol in eq_tol:
                fh = sum(1 for e in eq_h if e["pip_diff"] <= tol)
                fl = sum(1 for e in eq_l if e["pip_diff"] <= tol)
                w(f"      {tol}_pip: {{equal_highs: {fh}, equal_lows: {fl}}}")
            w()
            default_eq = eq_tol[1] if len(eq_tol) > 1 else eq_tol[0]
            w(f"    pairs_at_{default_eq}pip:")
            w("      equal_highs:")
            fh1 = [e for e in eq_h if e["pip_diff"] <= default_eq]
            for e in fh1[:50]:
                w(f"        - {{a: '{e['swing1_time']}', b: '{e['swing2_time']}', pip_dist: {e['pip_diff']}, avg_price: {e['avg_price']:.5f}}}")
            if len(fh1) > 50:
                w(f"        # ... {len(fh1) - 50} more pairs truncated")
            w("      equal_lows:")
            fl1 = [e for e in eq_l if e["pip_diff"] <= default_eq]
            for e in fl1[:50]:
                w(f"        - {{a: '{e['swing1_time']}', b: '{e['swing2_time']}', pip_dist: {e['pip_diff']}, avg_price: {e['avg_price']:.5f}}}")
            if len(fl1) > 50:
                w(f"        # ... {len(fl1) - 50} more pairs truncated")
            w()

    # ─── Asia Range ───────────────────────────────────────────
    w("# ═══════════════════════════════════════════════════════════")
    w("# ASIA RANGE — 19:00-00:00 NY (session-level, TF-independent)")
    w("# ═══════════════════════════════════════════════════════════")
    w("asia_range:")
    a_thresholds = metadata["asia_thresholds"]
    w(f"  thresholds: {a_thresholds}")

    for ar in asia_data["ranges"]:
        day = ar["forex_day"]
        w(f"  {day}:")
        w(f"    asia_high: {ar['high']:.5f}")
        w(f"    asia_low: {ar['low']:.5f}")
        w(f"    range_pips: {ar['range_pips']}")
        w(f"    bars: {ar['bar_count']}")
        w(f"    start_time: '{ar['start_time']}'  # NY time")
        w(f"    end_time: '{ar['end_time']}'")
        tight = {str(t): ar["classifications"][str(t)] == "TIGHT" for t in a_thresholds}
        w(f"    tight_at: {{{', '.join(f'{k}: {v}' for k, v in tight.items())}}}")
    w()

    w("  classification_matrix:")
    for t in a_thresholds:
        days_tight = sum(1 for ar in asia_data["ranges"] if ar["classifications"][str(t)] == "TIGHT")
        days_wide = len(asia_data["ranges"]) - days_tight
        w(f"    {t}_pip: {{tight: {days_tight}, wide: {days_wide}}}")
    w()

    # ─── Displacement per TF ──────────────────────────────────
    for tf in ['5m', '1m', '15m']:
        disp_d = tf_data[tf]['disp']
        disps = disp_d['displacements']
        atr_mults = disp_d['atr_multipliers']
        body_ratios = disp_d['body_ratios']

        w("# ═══════════════════════════════════════════════════════════")
        w(f"# DISPLACEMENT — NATIVE {tf} DETECTION — ATR mult × body ratio")
        w("# ═══════════════════════════════════════════════════════════")
        w(f"displacement_{tf}:")
        w(f"  total_candidates: {len(disps)}")

        w("  heatmap_and:")
        for day in forex_days:
            day_disps = [d for d in disps if d["forex_day"] == day]
            w(f"    {day}:")
            for atr_m in atr_mults:
                row = {}
                for br in body_ratios:
                    key = f"atr{atr_m}_br{br}"
                    count = sum(1 for d in day_disps if d["qualifies"][key]["and"])
                    row[str(br)] = count
                w(f"      {atr_m}x: {{{', '.join(f'{k}: {v}' for k, v in row.items())}}}")
        w()

        w(f"  events_at_default:  # 1.5x ATR, 0.60 body, AND mode")
        default_key = "atr1.5_br0.6"
        for day in forex_days:
            day_d = [d for d in disps if d["forex_day"] == day and d["qualifies"][default_key]["and"]]
            with_fvg = sum(1 for d in day_d if d.get("created_fvg"))
            bull = sum(1 for d in day_d if d["direction"] == "bullish")
            bear = sum(1 for d in day_d if d["direction"] == "bearish")
            w(f"    {day}: # {len(day_d)} displacements ({bull}↑ {bear}↓, {with_fvg} FVG)")
            for d in day_d:
                fvg_mark = " ★FVG" if d.get("created_fvg") else ""
                win = ""
                if d.get("ny_window_a"): win = " [WinA]"
                elif d.get("ny_window_b"): win = " [WinB]"
                w(f"      - {{time: '{d['time']}', dir: {d['direction']}, body: {d['body_pips']}pip, range: {d['range_pips']}pip, atr_ratio: {d['atr_multiple']}, body_pct: {round(d['body_ratio']*100,1)}%, session: {d['session']}{fvg_mark}{win}}}")
        w()

    # ─── NY Windows per TF ────────────────────────────────────
    for tf in ['5m', '1m', '15m']:
        ny_d = tf_data[tf]['ny']

        w("# ═══════════════════════════════════════════════════════════")
        w(f"# NY REVERSAL WINDOWS — NATIVE {tf} DETECTION")
        w("# Window A: 08:00-09:00 NY  |  Window B: 10:00-11:00 NY")
        w("# ═══════════════════════════════════════════════════════════")
        w(f"ny_windows_{tf}:")

        for day in forex_days:
            day_a = [e for e in ny_d["window_a"] if e.get("time", "")[:10] == day]
            day_b = [e for e in ny_d["window_b"] if e.get("time", "")[:10] == day]
            w(f"  {day}:")
            w(f"    window_a: # {len(day_a)} events")
            for e in day_a:
                detail = ""
                if e["type"] == "fvg": detail = f", gap: {e.get('gap_pips','')}pip"
                elif e["type"] == "displacement": detail = f", range: {e.get('range_pips','')}pip"
                elif e["type"] == "swing": detail = f", price: {e.get('price','')}"
                w(f"      - {{type: {e['type']}, subtype: {e.get('subtype','')}, time: '{e['time']}'{detail}}}")
            w(f"    window_b: # {len(day_b)} events")
            for e in day_b:
                detail = ""
                if e["type"] == "fvg": detail = f", gap: {e.get('gap_pips','')}pip"
                elif e["type"] == "displacement": detail = f", range: {e.get('range_pips','')}pip"
                elif e["type"] == "swing": detail = f", price: {e.get('price','')}"
                w(f"      - {{type: {e['type']}, subtype: {e.get('subtype','')}, time: '{e['time']}'{detail}}}")
        w()

    # ─── OB Staleness per TF ──────────────────────────────────
    for tf in ['5m', '1m', '15m']:
        ob_d = tf_data[tf]['ob']
        obs = ob_d['order_blocks']
        staleness_thresholds = ob_d['staleness_bars']

        w("# ═══════════════════════════════════════════════════════════")
        w(f"# ORDER BLOCK STALENESS — NATIVE {tf} DETECTION")
        w("# OB = last opposing candle before displacement")
        w("# Retest = wick into zone | Immediate retests (b=1) excluded")
        w("# ═══════════════════════════════════════════════════════════")
        w(f"ob_staleness_{tf}:")
        w(f"  total_obs: {len(obs)}")

        w("  threshold_matrix:")
        for day in forex_days:
            day_obs = [ob for ob in obs if ob["forex_day"] == day]
            w(f"    {day}: # {len(day_obs)} OBs total")
            for thresh in staleness_thresholds:
                def meaningful(ob):
                    return [r for r in ob["retests"] if r["bars_since_ob"] > 1]
                active = sum(1 for ob in day_obs if any(r["bars_since_ob"] <= thresh for r in meaningful(ob)))
                stale = len(day_obs) - active
                w(f"      {thresh}_bars: {{active: {active}, stale: {stale}}}")
        w()

        # Full events only for 5m (primary TF)
        if tf == '5m':
            w(f"  events:")
            for day in forex_days:
                day_obs = [ob for ob in obs if ob["forex_day"] == day]
                w(f"    {day}: # {len(day_obs)} OBs")
                for ob in day_obs:
                    meaningful = [r for r in ob["retests"] if r["bars_since_ob"] > 1]
                    first_rt = meaningful[0]["bars_since_ob"] if meaningful else "none"
                    total_rt = len(meaningful)
                    w(f"      - {{ob_time: '{ob['ob_time']}', disp_time: '{ob['disp_time']}', dir: {ob['direction']}, zone_wick: [{ob['zone_wick']['bottom']:.5f}, {ob['zone_wick']['top']:.5f}], zone_body: [{ob['zone_body']['bottom']:.5f}, {ob['zone_body']['top']:.5f}], first_retest: {first_rt}, total_retests: {total_rt}}}")
            w()

    # ─── Write ────────────────────────────────────────────────
    output_path = os.path.join(DATA_DIR, "calibration_data_export.yaml")
    content = "\n".join(lines)
    with open(output_path, 'w') as f:
        f.write(content)

    size = os.path.getsize(output_path)
    print(f"Written: {output_path}")
    print(f"Size: {size / 1024:.0f} KB ({size / 1024 / 1024:.1f} MB)")
    print(f"Lines: {len(lines)}")

if __name__ == "__main__":
    main()
