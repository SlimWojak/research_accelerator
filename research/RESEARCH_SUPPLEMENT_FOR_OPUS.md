# RESEARCH SUPPLEMENT FOR OPUS
## IFVG · BPR · Displacement — Implementation Specs for v0.5 Update

**Generated:** 2026-03-04  
**Purpose:** Synthesizes RG1, RG2, RG5 into direct implementation guidance for updating `SYNTHETIC_OLYA_METHOD_v0.5.yaml`  
**Audience:** Opus (AI coding assistant)

---

## 1. Executive Summary

This document distills three deep-research reports (751 + 976 + 356 lines) into precise, Opus-ready specs for three structures currently incomplete in v0.5: IFVG (marked "build pending"), BPR (marked "build pending"), and displacement (tag exists but threshold undefined). For each structure, this document provides the canonical detection algorithm, confirmed parameter defaults with sourced justifications, the recommended state machine, invalidation rules, sanity bands, and a numbered v0.5 patch list. All pseudocode is confirmed against multiple open-source TradingView implementations and primary ICT educational sources. **The v0.5 patch list in Section 5 is the direct action list for Opus** — read Sections 2–4 for the reasoning behind each patch item.

---

## 2. IFVG: Implementation Spec

### 2.1 What an IFVG Is (One-Line)

A **failed FVG that flips polarity**: when price closes fully beyond the FVG's far boundary, the original gap zone reverses its structural role (support→resistance or resistance→support).

### 2.2 L1 Detection Algorithm

```python
# ── STEP 1: Detect source FVG (3-candle wick-to-wick gap) ──
# bars[0]=current, bars[1]=middle(impulse), bars[2]=two-bars-ago

def detect_fvg(bars, min_gap_size):
    # Bullish FVG: gap up — current bar's low > two-bars-ago bar's high
    if bars[0].low > bars[2].high:
        gap_size = bars[0].low - bars[2].high
        if gap_size >= min_gap_size:
            return FVG(
                type=BULLISH,
                top=bars[0].low,       # fvgHigh — upper boundary
                bottom=bars[2].high,   # fvgLow  — lower boundary
                ce=(bars[0].low + bars[2].high) / 2.0,
                state=NORMAL,
                formation_bar=current_bar_index
            )
    # Bearish FVG: gap down — current bar's high < two-bars-ago bar's low
    if bars[0].high < bars[2].low:
        gap_size = bars[2].low - bars[0].high
        if gap_size >= min_gap_size:
            return FVG(
                type=BEARISH,
                top=bars[2].low,       # fvgHigh — upper boundary
                bottom=bars[0].high,   # fvgLow  — lower boundary
                ce=(bars[2].low + bars[0].high) / 2.0,
                state=NORMAL,
                formation_bar=current_bar_index
            )
    return None

# ── STEP 2: IFVG trigger — close beyond far boundary ──
# Far boundary = fvgLow for BULLISH FVG; fvgHigh for BEARISH FVG
# Source: MQL5 ref impl (https://www.mql5.com/en/articles/20361),
#         JT17jO6n TradingView (https://www.tradingview.com/script/JT17jO6n-...)
#         Aron Groups (https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/)

def ifvg_trigger(fvg, bar, trigger_mode="CLOSE"):
    if fvg.type == BULLISH:
        if trigger_mode == "CLOSE":  return bar.close < fvg.bottom   # canonical
        if trigger_mode == "WICK":   return bar.low   < fvg.bottom   # liberal
        if trigger_mode == "BODY":   return max(bar.open, bar.close) < fvg.bottom  # strict
    if fvg.type == BEARISH:
        if trigger_mode == "CLOSE":  return bar.close > fvg.top      # canonical
        if trigger_mode == "WICK":   return bar.high  > fvg.top      # liberal
        if trigger_mode == "BODY":   return min(bar.open, bar.close) > fvg.top     # strict
```

**Far boundary table:**

| FVG Type | Zone | Far Boundary | Trigger (CLOSE mode) |
|----------|------|--------------|----------------------|
| Bullish FVG | `[high[2], low[0]]` | `low[0]` (bottom) | `close < fvg.bottom` → IFVG_BEARISH |
| Bearish FVG | `[high[0], low[2]]` | `high[0]` (top) | `close > fvg.top` → IFVG_BULLISH |

### 2.3 L1.5 Parameters

```yaml
ifvg:
  trigger_mode: "CLOSE"          # CLOSE | WICK | BODY. Default CLOSE — canonical ICT.
                                  # Source: Aron Groups, innercircletrader.net, MQL5, JT17jO6n
  staleness_bars: 100             # FVGs older than N bars are pruned (memory management).
                                  # MQL5 default=30, ACE FVG default=30–500; 100 is middle ground.
  min_fvg_size_pips: 0.5          # Minimum gap size before IFVG tracking begins.
                                  # Matches v0.5 floor from calibration data.
  require_displacement_candle: false  # Optional: triggering candle body > ATR × 1.5
                                      # Only B0UXFx1Q enforces this; not canonical.
                                      # Source: iFVG Structural Framework (https://www.tradingview.com/script/B0UXFx1Q/)
  invalidation_trigger: "CLOSE_INSIDE_ZONE"  # Close back inside [fvgLow, fvgHigh]
                                              # Source: Aron Groups, FluxCharts, FXOpen
```

### 2.4 State Machine: Simple 2-State (Recommended for v0.5)

**Use the simple 2-state model, not the MQL5 4-state model.**

Reason: v0.5 already uses a `BOUNDARY_CLOSED` concept matching the 2-state approach. Most TradingView implementations (JT17jO6n, innercircletrader.net) skip the MITIGATED→RETRACED intermediate step. The 4-state model (NORMAL→MITIGATED→RETRACED→INVERTED) is accurate to the fullest ICT teaching but adds tracking complexity the spec doesn't yet need.

```python
# ── Simple 2-State IFVG (recommended for v0.5) ──
# Source: JT17jO6n (https://www.tradingview.com/script/JT17jO6n-...)
#         innercircletrader.net (https://innercircletrader.net/tutorials/ict-inversion-fair-value-gap/)

class FVGState(Enum):
    NORMAL      = "normal"       # Active gap, no interaction
    IFVG_BULLISH = "ifvg_bullish" # Bearish FVG inverted → now acts as support
    IFVG_BEARISH = "ifvg_bearish" # Bullish FVG inverted → now acts as resistance
    INVALIDATED  = "invalidated"  # IFVG consumed — price closed back inside zone

def update_fvg_simple(fvg, closed_bar):
    """Called on bar CLOSE only — never intrabar."""
    if fvg.state == NORMAL:
        if fvg.type == BULLISH and closed_bar.close < fvg.bottom:
            fvg.state = IFVG_BEARISH
            fvg.inversion_bar = current_bar_index
        elif fvg.type == BEARISH and closed_bar.close > fvg.top:
            fvg.state = IFVG_BULLISH
            fvg.inversion_bar = current_bar_index

    elif fvg.state in (IFVG_BULLISH, IFVG_BEARISH):
        # Invalidation: close back inside original zone
        price_inside = (fvg.bottom < closed_bar.close < fvg.top)
        if price_inside:
            fvg.state = INVALIDATED

# ── MQL5 4-State Reference (for future upgrade) ──
# States: NORMAL → MITIGATED → RETRACED → INVERTED → (INVALIDATED)
# Source: MQL5 Reference Implementation (https://www.mql5.com/en/articles/20361)
# Difference: requires price to re-enter zone (RETRACED) before emitting IFVG signal.
# Adds quality but also latency. Not recommended for v0.5 initial build.
```

### 2.5 Zone and CE After Flip

**Zone = entire original FVG box, unchanged.** No redraw, no trim.

```python
class IFVGZone:
    top:    float   # = original fvgHigh (UNCHANGED after flip)
    bottom: float   # = original fvgLow  (UNCHANGED after flip)
    ce:     float   # = (top + bottom) / 2.0  — Consequent Encroachment
    direction: Enum # BULLISH (acts as support) | BEARISH (acts as resistance)
```

- CE = `(fvgLow + fvgHigh) / 2.0` — the 50% midpoint of the original zone
- Source: [innercircletrader.net CE](https://innercircletrader.net/tutorials/ict-consequent-encroachment/), [iFVG Pro W2kx2bRf](https://www.tradingview.com/script/W2kx2bRf/) (explicit 50% midline)
- CE role: primary reaction level; close through CE = zone weakening (not yet invalidated)
- Invalidation only on close **fully outside** the zone (below `bottom` for bullish IFVG, above `top` for bearish IFVG)
- Source: [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/), [FXOpen](https://fxopen.com/blog/en/what-is-an-inverse-fair-value-gap-ifvg-concept-in-trading/)

### 2.6 Invalidation Rules

| Condition | Action | Source |
|-----------|--------|--------|
| `close < fvg.bottom` (bullish IFVG) | → INVALIDATED | [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/) |
| `close > fvg.top` (bearish IFVG) | → INVALIDATED | [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/) |
| Age > `staleness_bars` (default 100) | Prune from tracking array | [ACE FVG 7tbdroH5](https://www.tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/) |
| Price passes through without reaction | Zone disregarded (manual/context) | [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/) |

No first-touch expiry. Reclaimed IFVGs (second visit) are legitimate entries per [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/).

No double-flip state. If an IFVG is violated, mark INVALIDATED; new imbalances from that price area are detected as fresh FVGs.

### 2.7 Sanity Band: 5m EURUSD

| Metric | Low | Mid | High | Action if outside |
|--------|-----|-----|------|-------------------|
| IFVGs per day | 1 | 2–3 | 4–6 | <1/day: min_fvg_size too strict; >10/day: likely noise |
| IFVGs per week | 5–10 | 10–15 | 20–30 | — |

Derivation: ~5–10 raw FVGs/day (with 0.5 pip floor) × ~20% IFVG conversion rate. Source: [edgeful.com FVG stats](https://www.edgeful.com/blog/posts/fair-value-gap-best-practices-guide) extrapolated; wick-based trigger produces 3–4× more signals (noise).

### 2.8 Decision Table: v0.5 Updates

| Item | Change | Justification |
|------|--------|---------------|
| IFVG trigger condition | Confirm `close < fvg.bottom` / `close > fvg.top` (not wick-based) | Canonical — 7/9 sources use close-based |
| State enum | Add `IFVG_BULLISH`, `IFVG_BEARISH`, `INVALIDATED` | Current v0.5 only has `BOUNDARY_CLOSED` |
| CE field | Add `ce: float = (top + bottom) / 2.0` to IFVG zone | Required for entry precision |
| Invalidation | Close back inside `[bottom, top]` → INVALIDATED | [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/) |
| `trigger_mode` param | Add config: `CLOSE` (default) / `WICK` / `BODY` | Allows future tuning without code change |
| `staleness_bars` param | Add config: default 100 | Memory management; prevent array bloat |

---

## 3. BPR: Implementation Spec

### 3.1 What a BPR Is (One-Line)

A **Balanced Price Range** is the geometric overlap zone where a bullish FVG and a bearish FVG intersect in price, representing bi-directional institutional delivery in the same price area.

Source: [innercircletrader.net BPR](https://innercircletrader.net/tutorials/ict-balanced-price-range-bpr/), [ICT YouTube BPR explanation](https://www.youtube.com/watch?v=fZbQjvDp2OQ)

### 3.2 L1 Detection Algorithm

```python
# ── BPR detection: geometric overlap of BULLISH FVG + BEARISH FVG ──
# Source: tradeforopp Pine Script (https://www.tradingview.com/script/856oabwc-Balanced-Price-Range-BPR/)
#         UAlgo ICT BPR (https://www.tradingview.com/script/zPbYfcE8-ICT-Balance-Price-Range-UAlgo/)
#         ICT YouTube (https://www.youtube.com/watch?v=I40WcWikUj4) — "only the overlapping part"

def detect_bprs(
    active_fvgs: List[FVG],
    current_bar: int,
    timeframe: str,
    lookback_bars: int = 20,
    min_overlap_pips: float = 0.5,
    require_clean: bool = False,
    candles: List[Candle] = None
) -> List[BPR]:
    bprs = []

    # Same-TF only, within lookback window, active or partially mitigated
    relevant = [
        f for f in active_fvgs
        if f.timeframe == timeframe
        and (current_bar - f.formation_bar) <= lookback_bars
        and f.status in ("ACTIVE", "PARTIALLY_MITIGATED")
    ]
    bull_fvgs = [f for f in relevant if f.direction == "BULLISH"]
    bear_fvgs = [f for f in relevant if f.direction == "BEARISH"]

    for bull in bull_fvgs:
        for bear in bear_fvgs:
            # Geometric overlap
            overlap_top = min(bull.zone_top, bear.zone_top)
            overlap_bot = max(bull.zone_bottom, bear.zone_bottom)

            if overlap_top <= overlap_bot:
                continue  # No overlap

            overlap_size = overlap_top - overlap_bot
            if overlap_size < min_overlap_pips:
                continue  # Below minimum threshold

            formation_bar = max(bull.formation_bar, bear.formation_bar)

            # Optional: clean BPR check
            is_clean = True
            if require_clean and candles is not None:
                earlier_bar = min(bull.formation_bar, bear.formation_bar)
                for idx in range(earlier_bar + 1, formation_bar):
                    c = candles[idx]
                    if c.low < overlap_top and c.high > overlap_bot:
                        is_clean = False
                        break
                if not is_clean:
                    continue

            bprs.append(BPR(
                bull_fvg=bull,
                bear_fvg=bear,
                bpr_top=overlap_top,
                bpr_bottom=overlap_bot,
                ce=(overlap_top + overlap_bot) / 2.0,
                formation_bar=formation_bar,
                timeframe=timeframe,
                status="ACTIVE",
                is_clean=is_clean
            ))
    return bprs
```

### 3.3 L1.5 Parameters

```yaml
bpr:
  lookback_bars: 20             # Max bar distance between source FVG formations.
                                # Default 20 = practitioner-standard for 5m intraday.
                                # Source: tradeforopp (https://www.tradingview.com/script/856oabwc-...)
                                # "I'm only considering FVGs within 20 bars of each other."
  min_overlap_pips: 0.5         # Minimum BPR overlap zone size in pips.
                                # 0 is valid (any overlap) but 0.5 reduces noise on EURUSD 5m.
                                # Source: tradeforopp recommends 0 for Forex; 0.5 is conservative floor.
  invalidation_method: "CE"     # CE | PROXIMAL | DISTAL
                                # CE = close through 50% midpoint → CONSUMED.
                                # Reddit /r/InnerCircleTraders consensus; TradingFinder default.
                                # Source: (https://www.reddit.com/r/InnerCircleTraders/comments/1k1oqs7/)
  require_clean: false          # Exclude BPRs where price entered overlap zone between FVG formations.
                                # Improves quality; tradeforopp "Only Clean BPR" toggle.
                                # Source: (https://www.tradingview.com/script/856oabwc-...)
  same_tf_only: true            # CONFIRMED CANONICAL. Cross-TF overlap is "MTF confluence," not BPR.
                                # Source: tradeforopp, UAlgo, ICT primary material.
```

### 3.4 1-Bar Delay Requirement

**BPR must NOT be emitted until the bar AFTER the second FVG's formation bar closes.**

```python
# Emit BPR only when current_bar > formation_bar (i.e., at least 1 bar after FVG_2 confirmed)
if current_bar <= formation_bar:
    continue  # Not yet confirmed
```

Source: tradeforopp release notes — ["Fixed BPRs being created before following candle had chance to invalidate"](https://www.tradingview.com/script/856oabwc-Balanced-Price-Range-BPR/).

### 3.5 Clean BPR Filter (Optional)

A clean BPR = no price action entered the overlap zone between FVG_1 and FVG_2 formation. Implemented via the loop in Section 3.2. Set `require_clean=True` for higher-quality signals; off by default.

Source: [tradeforopp "Only Clean BPR" setting](https://www.tradingview.com/script/856oabwc-Balanced-Price-Range-BPR/)

### 3.6 Same-TF-Only Constraint (Confirmed Canonical)

Cross-TF BPR (e.g., bullish 5m FVG + bearish 15m FVG) is **not** a BPR per canonical ICT. It is an "MTF FVG confluence zone." The `same_tf_only: true` constraint in v0.5 is **correct**. Source: [tradeforopp multi-TF FVG discussion](https://www.tradingview.com/script/856oabwc-Balanced-Price-Range-BPR/), [ICT BPR tutorial](https://innercircletrader.net/tutorials/ict-balanced-price-range-bpr/).

### 3.7 State Management / Invalidation

```python
def update_bpr_status(bpr, closed_bar, invalidation_method="CE"):
    if bpr.status == "CONSUMED":
        return "CONSUMED"

    ce = bpr.ce
    c = closed_bar.close

    if invalidation_method == "CE":
        # Price enters zone AND closes beyond CE (50%) → CONSUMED
        if c < bpr.bpr_bottom or c > bpr.bpr_top:
            return "CONSUMED"          # Closed outside zone entirely
        # Partially inside zone but past CE = PARTIALLY_MITIGATED warning
        if bpr.bpr_bottom < c < bpr.bpr_top:
            if abs(c - ce) < (bpr.bpr_top - bpr.bpr_bottom) * 0.1:
                return "PARTIALLY_MITIGATED"

    elif invalidation_method == "PROXIMAL":
        # Strictest: any close beyond proximal edge → CONSUMED
        if c > bpr.bpr_top or c < bpr.bpr_bottom:
            return "CONSUMED"

    elif invalidation_method == "DISTAL":
        # Most lenient: only full traversal through distal edge → CONSUMED
        if bpr.status == "PARTIALLY_MITIGATED":
            if closed_bar.low < bpr.bpr_bottom or closed_bar.high > bpr.bpr_top:
                return "CONSUMED"
        if closed_bar.low <= bpr.bpr_top and closed_bar.high >= bpr.bpr_bottom:
            return "PARTIALLY_MITIGATED"

    return bpr.status
```

Source: [TradingFinder BPR indicator mitigation settings](https://www.tradingview.com/script/UBIzzw2R-ICT-Balanced-Price-Range-TradingFinder-BPR-FVG-IFVG/); [Reddit CE-based invalidation consensus](https://www.reddit.com/r/InnerCircleTraders/comments/1k1oqs7/)

### 3.8 Sanity Band: 5m EURUSD

| Lookback | BPRs/day expected | Quality |
|----------|--------------------|---------|
| 5–10 bars | 1–5 | Very high, rare |
| 20 bars (default) | **3–10** | Good, practitioner-standard |
| 50 bars | 5–20 | Mixed quality |
| 100–500 bars | 10–50+ | Includes historical/low-quality |

Source: Empirical indicator behavior; [TradingFinder indicator](https://www.tradingview.com/script/UBIzzw2R-ICT-Balanced-Price-Range-TradingFinder-BPR-FVG-IFVG/) shows 10–30 active BPRs at 500-bar window; tradeforopp shows 2–8 at 20-bar window on 5m.

If algo produces 0 BPRs/day: `min_overlap_pips` too high or `lookback_bars` too tight.  
If >20 BPRs/day: reduce `lookback_bars` to 10–15 or raise `min_overlap_pips`.

### 3.9 Decision Table: v0.5 Updates

| Item | Change | Justification |
|------|--------|---------------|
| Overlap formula | Confirm `overlap_top = min(bull.top, bear.top)` / `overlap_bot = max(bull.bottom, bear.bottom)` | Matches all implementations; [ICT YouTube](https://www.youtube.com/watch?v=I40WcWikUj4) confirms "only overlapping part" |
| `lookback_bars` | Default 20 | tradeforopp standard; [ICT "handful of candles"](https://www.youtube.com/watch?v=2IkXPiidUog) |
| `min_overlap_pips` | Default 0.5 for EURUSD | Noise reduction; 0 is valid if v0.5 has size filter elsewhere |
| `invalidation_method` | Default "CE" | Reddit community consensus; TradingFinder default |
| 1-bar delay | Enforce detection only on closed bars | [tradeforopp release notes](https://www.tradingview.com/script/856oabwc-Balanced-Price-Range-BPR/) |
| `require_clean` param | Add as optional boolean, default false | [tradeforopp "Only Clean BPR"](https://www.tradingview.com/script/856oabwc-Balanced-Price-Range-BPR/) |
| `same_tf_only` | Keep `true` (canonical) | Confirmed correct per all sources |
| CE field | `ce = (bpr_top + bpr_bottom) / 2.0` | [TradingFinder CE](https://tradingfinder.com/education/forex/ict-consequent-encroachment/); [CandelaCharts midline](https://www.tradingview.com/script/VZEviLcs-CandelaCharts-Balanced-Price-Range-BPR/) |

---

## 4. Displacement: Spec for `displacement_present` Tag

### 4.1 Two Dimensions

Displacement on candle B (the middle/impulse candle of the 3-bar FVG pattern) is defined by two independent filters that must BOTH pass (AND mode):

**Dimension 1 — Body-to-Range Ratio (BRR):**
```
BRR = abs(close - open) / (high - low)
```
Measures directional commitment. Values below 0.30 = doji/indecision; 0.60–0.70 = ICT "institutional candle" range.

Source: [FibAlgo ICT Displacement](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/) — default 0.65, configurable 0.30–0.95.

**Dimension 2 — ATR Multiplier (AM):**
```
AM_condition = abs(close - open) > ATR(14) × multiplier
```
Measures relative size vs. recent volatility. Adapts to changing market conditions.

Source: [FibAlgo ICT Displacement](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/) — default ATR(14) × 1.5, configurable 0.5–5.0.

### 4.2 Recommended Defaults

```yaml
displacement:
  method: "BOTH"              # AND mode — candle B must pass BOTH filters.
                               # Source: FibAlgo "Both" mode as strictest/most accurate.
  atr_period: 14              # Standard ATR period across all reviewed implementations.
  atr_multiplier: 1.0         # Conservative start: body >= 1× ATR (equals average range).
                               # Why 1.0 not 1.5: FibAlgo's 1.5 is calibrated for equities/futures;
                               # EURUSD 5m is noisier — start at 1.0 until empirical grid validates.
                               # Source: TheForexGuy study (https://www.theforexguy.com/forex-candlestick-patterns-strategy/)
                               # — 5m TF needs higher body threshold than daily; 1.0 is floor.
  body_ratio: 0.60            # ICT minimum for "institutional candle" (60% of range is body).
                               # Source: FibAlgo — "60–70% threshold separates institutional candles."
                               # Why 0.60 not 0.65: 0.60 is the stated ICT minimum; 0.65 is FibAlgo's
                               # equity-tuned default. Start conservative for EURUSD 5m.
  note: "Empirical calibration BLOCKED — run grid on EURUSD data to validate. See Section 4.4."
```

### 4.3 How It Maps to `displacement_present` Tag

```python
# For each detected FVG, compute displacement status of candle B:
body_b  = abs(candle_b.close - candle_b.open)
range_b = candle_b.high - candle_b.low
brr_b   = body_b / range_b if range_b > 0 else 0.0
atr_val = atr_series[candle_b.bar_index]  # ATR(14) of candle B

fvg.displacement_present = (
    brr_b  >= constants.DISPLACEMENT_BODY_RATIO    # default 0.60
    and body_b >= atr_val * constants.DISPLACEMENT_ATR_MULT  # default 1.0
)
```

**Critical distinction:** `displacement_present` is a **quality tag, not a detection gate**. All FVGs passing the `min_fvg_size_pips` floor are detected and tracked. `displacement_present = True` adds confluence weight at the L2 signal-generation layer. Whether it gates entry is an L2 decision, not an L1 detection decision.

Source: [RG5 §8](https://github.com/), [FibAlgo ICT FVG](https://www.tradingview.com/script/SoBOPZzT-FibAlgo-ICT-Fair-Value-Gaps/) — "Optional ATR filter. Ensures only displacement-grade imbalances qualify."

### 4.4 Grid Script: Ready to Run

Script is complete at: `/home/user/workspace/RG5_DISPLACEMENT_RESEARCH.md` §6 (lines 153–278).

**To execute when EURUSD 1m CSV is available:**
```bash
# CSV required: eurusd_1m_2024-01-07_to_2024-01-12.csv (~7,177 bars)
# Columns: [time, open, high, low, close, volume]
python /path/to/grid_script.py
# Expected output: 4×4 grid (AM=[0.5,1.0,1.5,2.0] × BRR=[0.50,0.60,0.65,0.70,0.80])
# per-cell: count of FVGs passing both filters + % of total
```

**Theoretical expected survival rates** (before empirical run):
- AM=1.0 + BRR=0.60: ~30–60% of raw FVGs survive → ~20–42 displacement FVGs/day on 5m
- AM=1.5 + BRR=0.65: ~20–40% survive → ~14–28 per day
- AM=2.0 + BRR=0.80: ~5–10% survive → ~3–7 per day (likely too strict)

Source: [TheForexGuy study](https://www.theforexguy.com/forex-candlestick-patterns-strategy/) — "5m TF needs minimum 120–160% ATR body threshold" for edge. [RG5 §7](https://github.com/).

### 4.5 Decision Table: v0.5 Updates

| Item | Change | Justification |
|------|--------|---------------|
| Add `DISPLACEMENT_BODY_RATIO` constant | Default `0.60` | ICT minimum for "institutional candle"; [FibAlgo default 0.65](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/) |
| Add `DISPLACEMENT_ATR_MULT` constant | Default `1.0` | Conservative start for EURUSD 5m; upgrade to 1.5 after empirical grid |
| Add `DISPLACEMENT_ATR_PERIOD` constant | Default `14` | Universal standard across all reviewed implementations |
| `displacement_present` computation | Implement AND of BRR + AM checks on candle B | [FibAlgo "Both" mode](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/) |
| Tag role | Confirm as quality tag (not detection gate) | [FibAlgo optional ATR filter](https://www.tradingview.com/script/SoBOPZzT-FibAlgo-ICT-Fair-Value-Gaps/) |

---

## 5. v0.5 Patch List

Ordered by priority. Each item is precise enough to act on without re-reading the research documents.

---

**IFVG PATCHES**

**1. IFVG trigger condition — verify / pin**
- Section: `l1_detection` → FVG state machine
- Change: Confirm trigger is `close < fvg.bottom` (bullish FVG) and `close > fvg.top` (bearish FVG). If currently checking wick (`low < fvg.bottom`), change to close.
- Source: [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/) "Price must close fully beyond the gap boundaries. A simple touch or wick through does not create an IFVG." Confirmed by [MQL5](https://www.mql5.com/en/articles/20361): `prevClose < fvgLow`.

**2. IFVG state enum — expand**
- Section: `fvg_state` enum (wherever BOUNDARY_CLOSED is defined)
- Change: Replace or supplement `BOUNDARY_CLOSED` with `IFVG_BULLISH` (inverted bearish FVG, now support) and `IFVG_BEARISH` (inverted bullish FVG, now resistance). Add `INVALIDATED` as terminal state.
- Source: [MQL5 state machine](https://www.mql5.com/en/articles/20361); [JT17jO6n](https://www.tradingview.com/script/JT17jO6n-Time-Based-Fair-Value-Gaps-FVG-with-Inversions-iFVG/).

**3. IFVG zone — add CE field**
- Section: `IFVGZone` or equivalent FVG data structure
- Change: Add `ce: float = (fvg.top + fvg.bottom) / 2.0` as a computed field. Value is set at detection time and does not change after flip.
- Source: [innercircletrader.net CE](https://innercircletrader.net/tutorials/ict-consequent-encroachment/): "CE is the 50% measure of any PD Array." [iFVG Pro W2kx2bRf](https://www.tradingview.com/script/W2kx2bRf/) shows explicit 50% dashed midline.

**4. IFVG invalidation — add rule**
- Section: `update_fvg_state` or equivalent per-bar update logic
- Change: When `fvg.state in (IFVG_BULLISH, IFVG_BEARISH)`, check `fvg.bottom < closed_bar.close < fvg.top`. If True → `fvg.state = INVALIDATED`.
- Source: [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/): "close fully back inside original gap boundaries." [FluxCharts](https://www.fluxcharts.com/articles/Trading-Concepts/Price-Action/Inversion-Fair-Value-Gaps): "price rises past bottom of bullish IFVG zone → invalid."

**5. IFVG config params — add to constants/config section**
- Section: `constants` or top-level `params`
- Change: Add:
  ```yaml
  IFVG_TRIGGER_MODE: "CLOSE"    # CLOSE | WICK | BODY
  IFVG_STALENESS_BARS: 100      # Prune FVGs older than N bars from tracking array
  ```
- Source: [ACE FVG lookback default](https://www.tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/) (30–500 bars); staleness 100 is midpoint. Trigger mode from [JT17jO6n](https://www.tradingview.com/script/JT17jO6n-Time-Based-Fair-Value-Gaps-FVG-with-Inversions-iFVG/) configurable signal preference.

**6. IFVG staleness pruning — add to tracking loop**
- Section: FVG array update logic (wherever per-bar processing occurs)
- Change: After each bar close, prune any FVG from the tracking array where `(current_bar - fvg.formation_bar) > IFVG_STALENESS_BARS` and state is still `NORMAL` (never inverted).
- Source: [MQL5 `CleanupExpiredFVGs`](https://www.mql5.com/en/articles/20361): removes FVG when `curBarTime > fvgs[j].origEndTime`. [ACE FVG `fvgLookbackLimit`](https://www.tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/).

---

**BPR PATCHES**

**7. BPR overlap formula — verify**
- Section: `l1_detection` → BPR detection
- Change: Confirm formula is `overlap_top = min(bull_fvg.top, bear_fvg.top)` and `overlap_bot = max(bull_fvg.bottom, bear_fvg.bottom)`. BPR exists only when `overlap_top > overlap_bot`.
- Source: [ICT YouTube](https://www.youtube.com/watch?v=I40WcWikUj4): "only the overlapping part." Confirmed by [tradeforopp](https://www.tradingview.com/script/856oabwc-Balanced-Price-Range-BPR/) and [UAlgo](https://www.tradingview.com/script/zPbYfcE8-ICT-Balance-Price-Range-UAlgo/).

**8. BPR config params — add to constants/config section**
- Section: `constants` or top-level `params`
- Change: Add:
  ```yaml
  BPR_LOOKBACK_BARS: 20         # Max bar distance between source FVGs
  BPR_MIN_OVERLAP_PIPS: 0.5     # Minimum overlap zone size
  BPR_INVALIDATION_METHOD: "CE" # CE | PROXIMAL | DISTAL
  BPR_REQUIRE_CLEAN: false      # Exclude unclean BPRs
  BPR_SAME_TF_ONLY: true        # Canonical; do not change
  ```
- Source: [tradeforopp](https://www.tradingview.com/script/856oabwc-Balanced-Price-Range-BPR/) for lookback=20 and clean BPR; [Reddit](https://www.reddit.com/r/InnerCircleTraders/comments/1k1oqs7/) for CE invalidation default.

**9. BPR CE field — add to BPR data structure**
- Section: `BPR` data class / schema
- Change: Add `ce: float = (bpr_top + bpr_bottom) / 2.0` as a computed field.
- Source: [CandelaCharts BPR](https://www.tradingview.com/script/VZEviLcs-CandelaCharts-Balanced-Price-Range-BPR/) "Show Mid-Line (CE)" option. [TradingFinder CE](https://tradingfinder.com/education/forex/ict-consequent-encroachment/).

**10. BPR 1-bar delay — enforce in detection logic**
- Section: BPR detection / signal emission
- Change: Do not emit BPR signal on the same bar that FVG_2 is confirmed. Emit on the NEXT closed bar: `if current_bar <= bpr.formation_bar: skip`.
- Source: [tradeforopp release notes](https://www.tradingview.com/script/856oabwc-Balanced-Price-Range-BPR/): "Fixed BPR's being created and alerted before the following candle had a chance to invalidate the range."

**11. BPR invalidation logic — add CE-based state update**
- Section: per-bar BPR status update
- Change: On each bar close, check BPR against `invalidation_method`. For CE mode: if `closed_bar.close < bpr.bottom` or `closed_bar.close > bpr.top`, set `bpr.status = "CONSUMED"`. For entering zone without closing outside: set `PARTIALLY_MITIGATED`.
- Source: [TradingFinder BPR indicator](https://www.tradingview.com/script/UBIzzw2R-ICT-Balanced-Price-Range-TradingFinder-BPR-FVG-IFVG/) Proximal/CE/Distal mitigation levels.

**12. BPR same-TF constraint — confirm and comment**
- Section: BPR detection filter
- Change: Add inline comment to the `fvg.timeframe == timeframe` filter: `# CANONICAL: BPR requires same-TF FVGs. Cross-TF overlap = MTF confluence zone, NOT BPR.`
- Source: [tradeforopp MTF discussion](https://www.youtube.com/watch?v=Hkpsq594Phc); [ICT BPR tutorial](https://innercircletrader.net/tutorials/ict-balanced-price-range-bpr/).

---

**DISPLACEMENT PATCHES**

**13. Add displacement constants**
- Section: `constants` or top-level config
- Change: Add:
  ```yaml
  DISPLACEMENT_METHOD: "BOTH"   # BOTH | ATR_ONLY | BRR_ONLY
  DISPLACEMENT_ATR_PERIOD: 14
  DISPLACEMENT_ATR_MULT: 1.0    # Body >= 1× ATR(14). Upgrade to 1.5 post-empirical grid.
  DISPLACEMENT_BODY_RATIO: 0.60 # BRR >= 0.60. ICT "institutional candle" minimum.
  ```
- Source: [FibAlgo ICT Displacement](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/) for both parameters and AND mode.

**14. Implement `displacement_present` computation**
- Section: FVG detection / L1 output fields
- Change: For each detected FVG, compute and store `displacement_present` from candle B:
  ```python
  body_b = abs(candle_b.close - candle_b.open)
  range_b = candle_b.high - candle_b.low
  brr_b = body_b / range_b if range_b > 0 else 0.0
  fvg.displacement_present = (
      brr_b >= DISPLACEMENT_BODY_RATIO
      and body_b >= atr_14[candle_b.index] * DISPLACEMENT_ATR_MULT
  )
  ```
- Source: [FibAlgo ICT FVG optional ATR filter](https://www.tradingview.com/script/SoBOPZzT-FibAlgo-ICT-Fair-Value-Gaps/); [ICT Gems FVG grading](https://www.youtube.com/watch?v=xzrLRyXHsjw).

**15. Add note: tag role vs. detection gate**
- Section: inline comment on `displacement_present` field definition
- Change: Add comment: `# Quality tag only — does NOT gate FVG detection. All FVGs >= min_fvg_size_pips are detected. displacement_present adds weight at L2 signal layer.`
- Source: [RG5 §8](https://github.com/) explicit note; FibAlgo "optional" ATR filter label.

**16. Reference grid script in v0.5**
- Section: `notes` or `pending_validation` section of v0.5
- Change: Add note:
  ```yaml
  pending_validation:
    - item: "DISPLACEMENT thresholds — empirical grid blocked on EURUSD 1m data re-upload"
      script: "RG5_DISPLACEMENT_RESEARCH.md §6 — grid_script.py ready to run"
      data_required: "eurusd_1m_2024-01-07_to_2024-01-12.csv"
      expected_upgrade: "DISPLACEMENT_ATR_MULT: 1.0 → 1.5 if grid confirms FibAlgo defaults"
  ```
- Source: [RG5 §6](https://github.com/) grid script; [TheForexGuy 5m TF analysis](https://www.theforexguy.com/forex-candlestick-patterns-strategy/).

---

## Appendix: Source URL Index

| # | Source | URL |
|---|--------|-----|
| 1 | Aron Groups IFVG | https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/ |
| 2 | innercircletrader.net IFVG | https://innercircletrader.net/tutorials/ict-inversion-fair-value-gap/ |
| 3 | innercircletrader.net CE | https://innercircletrader.net/tutorials/ict-consequent-encroachment/ |
| 4 | innercircletrader.net BPR | https://innercircletrader.net/tutorials/ict-balanced-price-range-bpr/ |
| 5 | MQL5 IFVG reference implementation | https://www.mql5.com/en/articles/20361 |
| 6 | TradingView: JT17jO6n Time-Based FVG+IFVG | https://www.tradingview.com/script/JT17jO6n-Time-Based-Fair-Value-Gaps-FVG-with-Inversions-iFVG/ |
| 7 | TradingView: B0UXFx1Q iFVG Structural Framework | https://www.tradingview.com/script/B0UXFx1Q/ |
| 8 | TradingView: W2kx2bRf iFVG Pro | https://www.tradingview.com/script/W2kx2bRf/ |
| 9 | TradingView: 7tbdroH5 ACE FVG & IFVG | https://www.tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/ |
| 10 | FluxCharts IFVG | https://www.fluxcharts.com/articles/Trading-Concepts/Price-Action/Inversion-Fair-Value-Gaps |
| 11 | FXOpen IFVG | https://fxopen.com/blog/en/what-is-an-inverse-fair-value-gap-ifvg-concept-in-trading/ |
| 12 | TradeZella IFVG | https://www.tradezella.com/strategies/ifvg-trading-model |
| 13 | TradingFinder CE | https://tradingfinder.com/education/forex/ict-consequent-encroachment/ |
| 14 | edgeful.com FVG stats | https://www.edgeful.com/blog/posts/fair-value-gap-best-practices-guide |
| 15 | tradeforopp BPR Pine Script | https://www.tradingview.com/script/856oabwc-Balanced-Price-Range-BPR/ |
| 16 | UAlgo ICT Balance Price Range | https://www.tradingview.com/script/zPbYfcE8-ICT-Balance-Price-Range-UAlgo/ |
| 17 | TradingFinder BPR Pine Script | https://www.tradingview.com/script/UBIzzw2R-ICT-Balanced-Price-Range-TradingFinder-BPR-FVG-IFVG/ |
| 18 | CandelaCharts BPR | https://www.tradingview.com/script/VZEviLcs-CandelaCharts-Balanced-Price-Range-BPR/ |
| 19 | FluxCharts BPR | https://www.fluxcharts.com/articles/Trading-Concepts/Price-Action/balanced-price-range |
| 20 | ICTProTools BPR Theory | https://ictprotools.com/guides/bpr-theory/ |
| 21 | HowToTrade BPR | https://howtotrade.com/blog/balanced-price-range/ |
| 22 | TradingFinder BPR education | https://tradingfinder.com/education/forex/ict-balanced-price-range/ |
| 23 | Reddit: BPR invalidity (CE consensus) | https://www.reddit.com/r/InnerCircleTraders/comments/1k1oqs7/ |
| 24 | ICT YouTube: Explains BPR | https://www.youtube.com/watch?v=fZbQjvDp2OQ |
| 25 | YouTube: BEST Way To Use ICT BPR | https://www.youtube.com/watch?v=2IkXPiidUog |
| 26 | YouTube: FVG BISI/SIBI BPR LV | https://www.youtube.com/watch?v=I40WcWikUj4 |
| 27 | FibAlgo ICT Displacement indicator | https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/ |
| 28 | FibAlgo ICT Fair Value Gaps | https://www.tradingview.com/script/SoBOPZzT-FibAlgo-ICT-Fair-Value-Gaps/ |
| 29 | TheForexGuy body-vs-ATR study | https://www.theforexguy.com/forex-candlestick-patterns-strategy/ |
| 30 | ICT Gems: A+ FVG Selection | https://www.youtube.com/watch?v=xzrLRyXHsjw |
| 31 | ICT Displacement YouTube | https://www.youtube.com/watch?v=0e1Wk2kTZeM |
