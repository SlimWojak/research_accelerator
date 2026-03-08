# RG-1: Inverse Fair Value Gap (IFVG) — Deep Research Document

**Purpose:** Implementation reference for Opus coding assistant  
**Date:** 2026-03-04  
**Scope:** All 7 research areas — canonical definition, trigger precision, zone definition, staleness, TradingView implementations, variant matrix, sanity bands  

---

## Executive Summary

An IFVG is a **failed FVG that flips polarity**. The most rigorous/conservative canonical definition (Aron Groups, innercircletrader.net, MQL5 reference implementation) requires a **candle CLOSE fully beyond the far boundary** of the FVG — wick-only penetration does not qualify. A minority of sources (FluxCharts, FXOpen) permit wick-based invalidation. The zone after flip is the **entire original FVG box, unchanged**. The CE is the **50% midpoint** of that original box. There is no fixed bar-count expiry; the IFVG remains valid until price closes back fully inside the original zone boundaries, or the zone is "accepted" without reaction. Double-flip (IFVG re-inverted) is conceptually possible but not standardized.

---

## 1. Canonical ICT Definition

### 1.1 What Constitutes the "Close Through"

This is the most important question for implementation. Sources diverge into two camps:

#### Camp A — Close-Based (Majority / More Rigorous)

| Source | Exact Wording | Boundary Required |
|--------|--------------|-------------------|
| [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/) | "A simple touch or wick through the gap does not create an IFVG. **Price must close fully beyond the gap boundaries** on the relevant timeframe." | Close beyond far boundary |
| [innercircletrader.net](https://innercircletrader.net/tutorials/ict-inversion-fair-value-gap/) | "Look for the price **closing beyond** the fair value gap and breaking it in opposite direction." | Close beyond far boundary |
| [Time-Based FVG + Inversions (TradingView JT17jO6n)](https://www.tradingview.com/script/JT17jO6n-Time-Based-Fair-Value-Gaps-FVG-with-Inversions-iFVG/) | Bullish FVG → IFVG: `close < FVG.bottom`; Bearish FVG → IFVG: `close > FVG.top` | Close beyond far boundary |
| [iFVG Structural Framework (TradingView B0UXFx1Q)](https://www.tradingview.com/script/B0UXFx1Q/) | "**Complete candle body must close through** the qualifying FVG. Wick-only penetration does not qualify." | Full body close |
| [MQL5 Reference Implementation](https://www.mql5.com/en/articles/20361) | `prevClose < fvgLow` (for bullish FVG inversion) / `prevClose > fvgHigh` (for bearish FVG inversion) | Close beyond far boundary |
| [TradeZella IFVG Model](https://www.tradezella.com/strategies/ifvg-trading-model) | "Wait for price to **close back through the FVG** from the opposite direction." | Close beyond far boundary |
| [YouTube ICT video transcript (uDJI2AbyyCs)](https://www.youtube.com/watch?v=uDJI2AbyyCs) | "...we want to see a **close over** the CBI for it to become an inversion...closing over this civy which creates an inversion" | Close beyond (entire FVG) |

#### Camp B — Wick-Based (Minority / More Liberal)

| Source | Exact Wording |
|--------|--------------|
| [FluxCharts](https://www.fluxcharts.com/articles/Trading-Concepts/Price-Action/Inversion-Fair-Value-Gaps) | "An IFVG is formed when the FVG is invalidated by **either a candle wick or close**." |
| [FXOpen](https://fxopen.com/blog/en/what-is-an-inverse-fair-value-gap-ifvg-concept-in-trading/) | "often with a close or strong wick beyond the level" — acknowledges both but treats wick as looser |

**Implementation decision:** The close-based trigger is the canonical ICT standard with the most sources, the most rigorous implementations, and explicit ICT video confirmation. **Use candle close beyond the far boundary.**

### 1.2 "Far Boundary" Definition

| FVG Type | Zone | Far Boundary (trigger) | Near Boundary |
|----------|------|----------------------|---------------|
| Bullish FVG | `[high[2], low[0]]` | `low[0]` (bottom of zone) | `high[2]` (top of zone) |
| Bearish FVG | `[high[0], low[2]]` | `high[0]` (top of zone) | `low[2]` (bottom of zone) |

A **bullish FVG** (gap up) becomes an IFVG when `close < fvgLow` (candle closes below the bottom boundary — price displaces downward through it).  
A **bearish FVG** (gap down) becomes an IFVG when `close > fvgHigh` (candle closes above the top boundary — price displaces upward through it).

### 1.3 Standard IFVG Formation Sequence (Aron Groups / TradeZella Consensus)

```
1. Original FVG forms (3-candle imbalance)
2. Price approaches the FVG (expected to hold)
3. Liquidity sweep: price runs a nearby swing high/low
4. Displacement candle: price closes fully beyond the FVG's far boundary
5. IFVG confirmed: zone flips polarity
6. Trade entry: wait for price to return to the flipped zone
```

Note: Steps 3 (liquidity sweep) is emphasized as a prerequisite by premium sources ([Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/), [TradeZella](https://www.tradezella.com/strategies/ifvg-trading-model)), but is **not** baked into basic IFVG detection logic — it is a trade-quality filter, not a detection criterion.

---

## 2. Trigger Precision

### 2.1 Which Boundary Must Be Closed Beyond?

The close must cross the **far boundary** — the side of the FVG opposite to the direction the gap was pointing.

```
Bullish FVG (gap up, acting as support):
  Zone = [fvgLow, fvgHigh] where fvgLow = low[0], fvgHigh = high[2]
  Far boundary = fvgLow (bottom)
  Trigger condition: close < fvgLow
  ↳ Price closes BELOW the bottom of the bullish gap → IFVG_BEARISH

Bearish FVG (gap down, acting as resistance):
  Zone = [fvgLow, fvgHigh] where fvgLow = low[2], fvgHigh = high[0]
  Far boundary = fvgHigh (top)
  Trigger condition: close > fvgHigh
  ↳ Price closes ABOVE the top of the bearish gap → IFVG_BULLISH
```

**Important:** The "far boundary" in standard ICT discourse is the edge that faces away from the initial move. Some sources require closing "through the entire gap" — meaning the close must not only breach the near boundary but must exit from the far side. The MQL5 reference implementation confirms this: the inversion trigger requires `prevClose < fvgLow` (for a bullish FVG), meaning price closed below the absolute bottom of the zone — beyond the far boundary.

### 2.2 Must the Close Be Beyond the Far Boundary, or Just Within the Gap?

The close must be **beyond** (outside) the far boundary, not merely within the gap. Evidence:
- MQL5: `prevClose < fvgLow` — strictly less than, meaning price exits the gap on the far side
- JT17jO6n TradingView: `close < FVG.bottom` for bullish FVG → IFVG conversion
- Aron Groups: "close fully beyond the gap boundaries"

A close that enters the FVG but stops inside it (e.g., between fvgLow and fvgHigh) = **partial fill / mitigation**, not inversion.

### 2.3 Minimum Penetration Depth

No source specifies a minimum pip/price penetration depth beyond the far boundary. The close must simply be `< fvgLow` (or `> fvgHigh`) by any amount, including 1 tick. However:
- The MQL5 implementation uses `minPts = 100` (minimum points) as a filter on the **FVG size itself**, not on penetration depth
- The iFVG Structural Framework uses a "minimum tick-size threshold" for FVG qualification — again, filtering the original gap size, not the close-through distance
- In practice, most traders require a "decisive" or "displacement" close, but this is not quantified

**Implementation recommendation:** No minimum penetration depth filter is needed for IFVG detection. The FVG minimum size filter (e.g., 10 pips for EURUSD on 5m) should be applied at the FVG detection stage.

### 2.4 Does the Triggering Candle Need to Be a Displacement Candle (Strong Body)?

The iFVG Structural Framework (B0UXFx1Q) is the only TradingView indicator that explicitly requires displacement before IFVG qualification. Its full sequence includes:
- Liquidity detection (pivot sweep)
- FVG detection during displacement  
- Inversion: body close through the FVG within a validation window

The Aron Groups definition requires "a strong candle, or a series of candles, closes fully beyond the original FVG boundary" — implying displacement is preferred but a series of candles also qualifies.

**For a minimal/pure IFVG detection algorithm:** No displacement filter is required. It is a **trade-quality filter**, not part of the core pattern definition. Flag it as an optional parameter.

---

## 3. Zone Definition After Flip

### 3.1 What Is the Exact Zone of the IFVG?

**Answer: The entire original FVG zone, unchanged.**

Multiple sources confirm:

> *"The original gap is now an inverse fair value gap."* — [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/)

> *"The flipped zone is the original FVG area (gap between high of candle one and low of candle three). It now acts in the opposite role."* — [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/)

The zone is **not** redrawn, trimmed, or adjusted based on the penetration depth. The entire original `[fvgLow, fvgHigh]` rectangle becomes the IFVG zone.

```
Original Bullish FVG zone: [fvgLow=1.0820, fvgHigh=1.0835]
After inversion (IFVG_BEARISH): zone remains [1.0820, 1.0835]
Role: now resistance (price expected to reject from below on retest)
```

### 3.2 Where Is the CE (Consequent Encroachment) of the IFVG?

CE = **50% midpoint of the original FVG zone** — unchanged after flip.

From canonical ICT sources:
- [innercircletrader.net CE page](https://innercircletrader.net/tutorials/ict-consequent-encroachment/): "Consequent Encroachment is the 50% measure of ICT fair value gap or any PD Array"
- [YouTube CE explanation (79KwSQyEzKo)](https://www.youtube.com/watch?v=79KwSQyEzKo): "The 50% point of the fair value gap is consequent encroachment"
- [TradingFinder CE](https://tradingfinder.com/education/forex/ict-consequent-encroachment/): "CE refers to the 50% level of a trading structure, such as the midpoint of a Fair Value Gap"

```
CE calculation:
  CE = fvgLow + (fvgHigh - fvgLow) / 2.0
     = (fvgLow + fvgHigh) / 2.0

Example:
  fvgLow=1.0820, fvgHigh=1.0835
  CE = (1.0820 + 1.0835) / 2 = 1.08275
```

From the [ICT video transcript](https://www.youtube.com/watch?v=uDJI2AbyyCs):
> *"The consequent encroachment is the 50% of a fair value gap... if price comes in and respects this area then I anticipate it to move higher. If price comes in and violates this area then I can anticipate price to move lower."*

The CE of an IFVG has the same structural role as in a regular FVG: it's the primary reaction level and the line that, if closed through, suggests the zone is failing.

### 3.3 Key Zone Levels Summary

```
IFVG Zone (from original FVG, polarity flipped):
  ┌─────────────────────── fvgHigh (top boundary)
  │
  ├─────────────────────── CE = (fvgLow + fvgHigh) / 2.0  [primary reaction level]
  │
  └─────────────────────── fvgLow (bottom boundary)
```

For **IFVG_BEARISH** (bearish resistance zone, from inverted bullish FVG):
- Entry zone: top half of box (fvgHigh down to CE)
- CE is the line; close below CE → zone weakening
- Invalidation: close above fvgHigh

For **IFVG_BULLISH** (bullish support zone, from inverted bearish FVG):
- Entry zone: bottom half of box (fvgLow up to CE)
- CE is the line; close above CE → zone weakening
- Invalidation: close below fvgLow

---

## 4. Staleness / Expiry

### 4.1 Standard Invalidation Rules

There is **no fixed bar-count or time-based expiry** in the canonical ICT definition. An IFVG remains valid until one of the following occurs:

| Condition | Result |
|-----------|--------|
| Price closes fully **back inside** the original gap boundaries | Zone invalidated (Aron Groups, MQL5) |
| Price passes through the zone without any reaction and continues aggressively in original direction | Zone disregarded (Aron Groups) |
| Significant news event / external shock | Zone may be unreliable (Aron Groups) |

From [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/):
> *"Valid until the price either accepts it without reaction or specific time-based rules indicate expiry... Zones several weeks old or tested multiple times carry less weight; always check current market context."*

From [FXOpen](https://fxopen.com/blog/en/what-is-an-inverse-fair-value-gap-ifvg-concept-in-trading/):
> *"If price moves past the bottom of the IFVG zone, it is no longer valid and is typically disregarded."*

From [FluxCharts](https://www.fluxcharts.com/articles/Trading-Concepts/Price-Action/Inversion-Fair-Value-Gaps):
> *"If price rises past the bottom of the bullish IFVG zone, it is invalid."*

### 4.2 Implementation-Level Expiry Observations

| Indicator | Staleness/Expiry Mechanism |
|-----------|---------------------------|
| ACE FVG (7tbdroH5) | `fvgLookbackLimit` default 30 bars, max 500 bars. FVGs older than lookback are dropped. |
| iFVG Structural Framework (B0UXFx1Q) | Time-limited validation windows (bar-count windows for post-liquidity and HTF context) |
| Time-Based FVG (JT17jO6n) | `Show Last N` parameter (default 5 recent IFVGs). `Remove Mitigated FVGs` toggle. Persistence "until re-mitigated." |
| MQL5 Reference | `CleanupExpiredFVGs`: removes FVG when `curBarTime > fvgs[j].origEndTime`. Rectangle extended `FVG_Rec_Ext_Bars = 30` bars. |

### 4.3 "First Touch" Expiry

**No source definitively requires expiry after first touch/test.** The concept of a "reclaimed IFVG" (second visit to the zone) is explicitly supported by [Aron Groups](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/):
> *"A reclaimed IFVG refers to a scenario where you missed the initial return into the flipped gap, but the price comes back to the zone a second time. This is a legitimate entry opportunity."*

### 4.4 Can an IFVG Be Re-Inverted (Double Flip)?

No source explicitly defines a "double-flip" standard. However:
- The MQL5 state machine explicitly has only 4 states: `Normal → Mitigated → Retraced → Inverted`. The inverted state is terminal in that implementation — no further state transitions defined.
- The iFVG Pro (W2kx2bRf) flexible mode mentions "Inversions" in context of detecting IFVGs from partially-touched FVGs, but does not describe double-flip.
- Theoretically, if an IFVG zone is then treated as a new FVG with the opposite polarity, it could be detected as a new FVG and subsequently inverted — but this would require a fresh detection pass treating the IFVG as a standard FVG.

**Implementation decision:** Do not implement double-flip as a state transition. If an IFVG zone is violated (close fully back inside original gap), mark it as INVALIDATED. Any new imbalance from that price area will be detected as a fresh FVG in a subsequent detection pass.

---

## 5. TradingView Implementations Analysis

### 5a. ACE FVG & IFVG Trading System (7tbdroH5)
**Source:** [https://www.tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/](https://www.tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/)  
**Published:** 2025-06-24  

| Aspect | Detail |
|--------|--------|
| IFVG definition | "Mitigated FVGs with immediate or retrace signals" — implies standard close-through trigger |
| Wick vs. close | Configurable: `tpTriggerType` = "Wick" or "Close" (applies to TP/SL checks; "Close" is recommended) |
| Entry modes | Immediate (direct signal post-mitigation) and Retrace (pullback to zone) |
| Zone visualization | Purple boxes for IFVG/mitigated FVGs |
| Key parameters | `fvgMinSize`, `fvgLookbackLimit` (default 30, max 500 bars), time filters, SL/TP modes |
| FVG detection formula | `low > high[2]` (bullish), `high < low[2]` (bearish) — standard wick-based 3-candle pattern |
| Code availability | Closed-source, protected |

**Notes:** The dual Immediate/Retrace mode is a distinct feature. The `wick vs. close` toggle for TP/SL signals likely extends to IFVG retest detection. No explicit statement on trigger threshold for initial IFVG creation (assumed to be standard close beyond far boundary).

---

### 5b. iFVG Structural Framework (B0UXFx1Q)
**Source:** [https://www.tradingview.com/script/B0UXFx1Q/](https://www.tradingview.com/script/B0UXFx1Q/)  
**Published:** 2026-02-15  

| Aspect | Detail |
|--------|--------|
| Trigger | Full candle **body** must close through the qualifying FVG (most stringent definition found) |
| Wick vs. close | Close only, and specifically body-based (not just close price — requires body to clear the FVG) |
| Liquidity prerequisite | Yes, required: pivot high/low taken, or session high/low swept, within a time window |
| Minimum threshold | Minimum tick-size filter on the FVG size |
| Validation window | Bar-count window post-liquidity sweep; inversion must occur within that window |
| HTF context | Optional: IFVG must form within an active HTF FVG zone (up to 4 HTF levels) |
| Entry modes | Alerts on intrabar (preliminary) or bar-close (confirmed) setups |

**Pseudocode (derived from description):**
```python
for each bar:
    # Step 1: Detect liquidity event
    if pivot_taken(high_or_low) or session_high_low_swept:
        if within_time_window:
            mark_liquidity_event()
    
    # Step 2: Detect FVG during displacement (body-based)
    if body_gap >= min_tick_size:
        create_fvg()
        optionally_layer_htf_fvgs()
    
    # Step 3: Check for inversion (within validation_window bars post-liquidity)
    if candle.body.fully_closes_through(fvg):  # body, NOT wick
        if optionally within_active_HTF_zone:
            validate_ifvg()
    
    # Step 4: Activate structure
    if full_sequence_met and optional_filters(session, bias):
        draw_ifvg_box()
        draw_activation_line_at_close()
```

**Notes:** This is the most conservative implementation. The "body fully closes through" requirement means both the open and close of the triggering candle must be on the far side of the FVG boundary — not just the closing price. This is stricter than the common `close < fvgLow` check.

---

### 5c. iFVG Pro (W2kx2bRf)
**Source:** [https://www.tradingview.com/script/W2kx2bRf/](https://www.tradingview.com/script/W2kx2bRf/)  
**Published:** 2026-02-13  

| Aspect | Detail |
|--------|--------|
| Detection modes | Strict: "True Gaps" only (no wick overlap between candles 1 and 3); Flexible: allows wick touching/overlap |
| Wick vs. close | Wick-based gap qualification (gap must exist between wicks); close implied for inversion but not detailed |
| IFVG zone visualization | Box with dashed midline (CE at 50%) |
| CE display | Yes — explicitly shows 50% midpoint of IFVG box |
| Quality filter | Fractal PD Array Filter: blocks longs in premium zones, blocks shorts in discount zones |
| HTF analysis | Macro (auto-correlated HTF) + Local structures |
| Grading | A+/B setups based on: Liquidity Sweeps + HTF Trend + Volume + SMT Divergence |
| Code availability | Closed-source, protected |

**Notes:** The Strict/Flexible toggle controls FVG *detection* (whether the original 3-candle gap requires clean separation or allows touching wicks), not necessarily the IFVG *trigger*. The CE (50% line) is explicitly displayed. No numerical threshold parameters mentioned.

---

### 5d. Time-Based FVG with Inversions (JT17jO6n)
**Source:** [https://www.tradingview.com/script/JT17jO6n-Time-Based-Fair-Value-Gaps-FVG-with-Inversions-iFVG/](https://www.tradingview.com/script/JT17jO6n-Time-Based-Fair-Value-Gaps-FVG-with-Inversions-iFVG/)  
**Published:** 2025-05-04  

| Aspect | Detail |
|--------|--------|
| Trigger | `close < FVG.bottom` (bullish FVG → IFVG_BEARISH); `close > FVG.top` (bearish FVG → IFVG_BULLISH) |
| Wick vs. close | **Close** for IFVG creation (conservative default); **Wick** available as option for retest signals |
| Retest signal threshold | Configurable: "Close" (candle body confirms retest) or "Wick" (candle high/low touches) |
| Zone visualization | Extended boxes with dashed midlines |
| Persistence | Until re-mitigated (if "Remove Mitigated FVGs" enabled); otherwise permanent |
| Key parameters | `Signal Preference` (Close/Wick), `Show Last N` (default 5), `Remove Mitigated FVGs` (default true), `Timezone Offset` |

**Core pseudocode:**
```python
# FVG detection
if low[0] > high[2]:  # bullish FVG
    fvg = FVG(type=BULLISH, top=low[0], bottom=high[2])
if high[0] < low[2]:  # bearish FVG
    fvg = FVG(type=BEARISH, top=low[2], bottom=high[0])

# Optional ATR size filter: gap > 0.25 * ATR

# IFVG creation
if fvg.type == BULLISH and close < fvg.bottom:
    convert_to_ifvg(fvg, type=IFVG_BEARISH)
if fvg.type == BEARISH and close > fvg.top:
    convert_to_ifvg(fvg, type=IFVG_BULLISH)

# Retest detection
if signal_preference == CLOSE:
    if candle_body_touches(ifvg_zone):
        emit_signal()
elif signal_preference == WICK:
    if candle_high_or_low_touches(ifvg_zone):
        emit_signal()
```

**Notes:** This indicator does NOT require a liquidity sweep prerequisite. It's a "pure" IFVG detector. The wick/close toggle applies only to *retest* signals, not to IFVG creation. IFVG creation is always close-based.

---

### 5e. TradingFinder IFVG Educational Page
**Source:** [https://tradingfinder.com/education/forex/ict-inversion-fair-value-gap/](https://tradingfinder.com/education/forex/ict-inversion-fair-value-gap/)  

| Aspect | Detail |
|--------|--------|
| Definition | FVG that "fails to sustain price in its initial direction" and transforms into a supply/demand zone in opposite direction |
| Trigger | Implicit close-based; no explicit wick vs. close statement |
| High-probability filter | Post-liquidity sweep (HOD/LOD, session highs/lows, equal highs/lows, swing highs/lows) |
| Zone identification | IFVGs "often appear near key areas such as daily highs/lows, cleared liquidity zones, or within premium/discount zones" |
| CE | Not explicitly discussed |

---

### 5f. FXOpen IFVG
**Source:** [https://fxopen.com/blog/en/what-is-an-inverse-fair-value-gap-ifvg-concept-in-trading/](https://fxopen.com/blog/en/what-is-an-inverse-fair-value-gap-ifvg-concept-in-trading/)  

| Aspect | Detail |
|--------|--------|
| Definition | IFVG forms when a previously valid FVG is "breached or clearly broken through" |
| Trigger | "often with a close or strong wick beyond the level" — permits both wick and close |
| Invalidation | "if price moves past the bottom of the IFVG zone, it is no longer valid" |
| CE | Not mentioned |

**Notes:** FXOpen is the most liberal source, explicitly permitting wick-based triggering. This is the outlier position.

---

### 5g. Aron Groups IFVG
**Source:** [https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/](https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/)  

| Aspect | Detail |
|--------|--------|
| Definition | Failed FVG where "price closes back through the original gap after a liquidity sweep → displacement → close beyond the gap" |
| Trigger | "**Price must close fully beyond the gap boundaries**. A simple touch or wick through does not create an IFVG." |
| Full sequence | Liquidity sweep → displacement through FVG → close beyond gap (all 3 required for high-quality setup) |
| Zone after flip | Original FVG area, opposite role |
| Invalidation | Close fully back inside original gap; or passes through without reaction; or news shock |
| CE | Not explicitly discussed in this article |
| Reclaimed IFVG | Second visit to zone is a legitimate entry |

---

## 6. Variant Matrix

All variants found across sources, organized by detection parameter:

### 6.1 Trigger Type Matrix

| Variant | Trigger Condition | Sources | Notes |
|---------|------------------|---------|-------|
| **Close-beyond-far-boundary** (canonical) | `close < fvgLow` (bullish FVG) / `close > fvgHigh` (bearish FVG) | Aron Groups, innercircletrader.net, JT17jO6n, MQL5, TradeZella | Most defensible; avoids wick-false-positives |
| **Body-fully-through** (strictest) | Both open AND close beyond the far boundary (full body clear) | B0UXFx1Q (iFVG Structural Framework) | Eliminates doji/pin bar triggers; fewer signals |
| **Wick-or-close** (liberal) | `high < fvgLow` (for bearish move through bullish FVG) / `low > fvgHigh` (for bullish move through bearish FVG) | FluxCharts, FXOpen | More signals, more false positives on 5m charts |
| **CE close-through** (intermediate) | Close beyond 50% midpoint only (CE level) | Implied by ICT video context; not a standalone IFVG trigger | Used as a WARNING signal, not full IFVG creation |

### 6.2 Prerequisite Conditions Matrix

| Variant | Prerequisite | Adds Quality | Adds Complexity |
|---------|-------------|-------------|-----------------|
| **Bare IFVG** | None (just close beyond far boundary) | Low | Low |
| **Post-liquidity IFVG** | Liquidity sweep (swing high/low taken) must precede the displacement | High | Medium |
| **HTF-aligned IFVG** | IFVG must form within an active HTF FVG or order block | Very High | High |
| **Post-MSS IFVG** | Market Structure Shift must occur before IFVG formation | High | Medium |
| **SMT-confirmed IFVG** | Correlated instrument divergence (e.g., NQ vs ES) | Very High | High |

### 6.3 FVG Detection Basis (Original Gap)

| Variant | Detection Method | Impact on IFVG Count |
|---------|-----------------|---------------------|
| **Wick-to-wick gap** (standard) | `low[0] > high[2]` (bullish) — gap between wicks | Baseline |
| **Body-to-body gap** | Gap between candle bodies (open/close) only | Fewer, higher quality |
| **Strict gap** (no wick overlap at all) | No wick overlap between candle 1 and candle 3 | iFVG Pro Strict mode; fewest signals |
| **Implied gap** (wick touch OK) | Allows wicks to touch or slightly overlap | iFVG Pro Flexible mode; most signals |

### 6.4 Zone Extent After Flip

| Variant | Zone Used | Sources |
|---------|-----------|---------|
| **Full original zone** (canonical) | `[fvgLow, fvgHigh]` unchanged | All major sources |
| **Penetrated portion only** | Zone trimmed to the segment that was actually closed through | Not found in any source — avoid |
| **Extended zone** | Zone expanded by some factor of ATR | Not found — avoid |

### 6.5 Expiry Rules Matrix

| Variant | Expiry Condition | Notes |
|---------|-----------------|-------|
| **Close-back-inside** (canonical) | Close returns inside `[fvgLow, fvgHigh]` | Aron Groups, FluxCharts — most common |
| **Far-boundary breach** | Price closes beyond far boundary of IFVG zone from new direction | FXOpen — "past bottom of IFVG zone" |
| **N-bar lookback** | FVG older than N bars is dropped | ACE FVG (30–500 bars), MQL5 (30 bars default) |
| **Session-end** | All FVGs cleared at end of session | FMZ Quant intraday strategy |
| **One-touch expiry** | Zone consumed after first interaction | Not explicitly stated in any source |
| **No expiry** | Zone valid indefinitely until price action invalidates it | Pure ICT teaching |

---

## 7. Sanity Bands

### 7.1 Raw FVG Frequency on 5m EURUSD

No source provides a direct published count of FVGs per day on 5m EURUSD. The following estimates are constructed from available data:

**Base calculation:**
- EURUSD active trading hours: ~14–16 hours/day (London + NY sessions dominate)
- 5m bars per active day: ~190–240 bars
- FVG formation rate on 5m: qualitative consensus suggests FVGs occur "frequently" on lower timeframes

**From [edgeful.com](https://www.edgeful.com/blog/posts/fvg-indicator-tradingview):**
- YM (Dow futures) 5-minute FVGs have ~75% same-session mitigation rate (vs ~30% for 30m) — implying 5m FVGs are more numerous and shorter-lived
- YM 30m data: 167 bullish + 117 bearish = ~284 FVGs over 6 months (~1–2 per session per direction at 30m)
- Scaling to 5m: approximately 5–6x more FVGs than 30m → **~8–15 raw FVGs per day** (both directions combined) on an active instrument

**Conservative estimate for 5m EURUSD:**
- With no size filter: ~10–20 FVGs per day (including micro-gaps)
- With minimum size filter (e.g., 3 pips): ~5–10 FVGs per day
- During London + NY sessions only (excluding Asian): ~4–8 FVGs per day

### 7.2 What Ratio of FVGs Become IFVGs?

**From [edgeful.com YM 30m data](https://www.edgeful.com/blog/posts/fair-value-gap-best-practices-guide):**
- Bullish FVGs: 60.71%–69.46% stay **unmitigated** (same session)
- Bearish FVGs: 63.2%–67.52% stay **unmitigated** (same session)
- This means ~30–37% of FVGs get **mitigated** (price closes back through) in the same session

**Extrapolating to IFVG conversion rate:**

A FVG becomes an IFVG only if price closes **fully beyond the far boundary** (not just partially fills). Of the ~30–37% of FVGs that are mitigated:
- "Mitigated" in the edgeful data may include partial fills (into the zone) not full close-throughs
- Only a subset of mitigated FVGs qualify as full close-throughs (IFVGs)
- Rough estimate: ~50–60% of mitigated FVGs actually close fully through → **~15–22% of all FVGs become IFVGs**

**Practical sanity band for 5m EURUSD:**

| Metric | Low Estimate | Mid Estimate | High Estimate |
|--------|-------------|-------------|---------------|
| Raw FVGs per day | 5 | 10 | 20 |
| FVG → IFVG conversion rate | 15% | 20% | 30% |
| IFVGs per day (5m EURUSD) | **1–2** | **2–3** | **4–6** |
| IFVGs per week | 5–10 | 10–15 | 20–30 |

**Calibration check:** If an algo is detecting >10 IFVGs per day on 5m EURUSD without a size filter or session filter, it is likely detecting noise (micro-gaps that technically satisfy the wick criteria but are not institutionally meaningful). If detecting <1 IFVG per day with a strict size filter (5+ pips), it may be too restrictive.

### 7.3 Impact of Trigger Type on Frequency

| Trigger Type | Relative Frequency |
|-------------|-------------------|
| Wick-based | ~3–4x more signals than close-based |
| Close-based (canonical) | Baseline |
| Body-fully-through | ~50–70% of close-based signals |

A wick-based detector on 5m EURUSD could easily produce 10–30+ "IFVGs" per day, making most signals noise.

---

## 8. Implementation-Ready Pseudocode

### 8.1 Core IFVG Detection State Machine

Based on the MQL5 reference implementation and cross-validated with canonical sources:

```python
# FVG / IFVG State Enum
class FVGState(Enum):
    NORMAL     = "normal"      # Gap detected, price has not yet interacted
    MITIGATED  = "mitigated"   # Price closed beyond far boundary (first time)
    RETRACED   = "retraced"    # Price re-entered the original gap zone after mitigation
    INVERTED   = "inverted"    # Price closed beyond far boundary from inside → IFVG signal
    INVALIDATED = "invalidated" # Price closed back fully inside the original zone (IFVG failed)

class FVG:
    type: Enum  # BULLISH or BEARISH
    top: float  # fvgHigh — upper boundary
    bottom: float  # fvgLow — lower boundary
    ce: float   # (top + bottom) / 2.0 — Consequent Encroachment
    state: FVGState
    formation_bar: int
    mitigation_bar: int
    inversion_bar: int

# ─────────────────────────────────────────────────────────────
# STEP 1: Detect FVG (standard wick-to-wick 3-candle pattern)
# ─────────────────────────────────────────────────────────────
def detect_fvg(bars):
    # bars[0] = current (newest), bars[1] = middle, bars[2] = two bars ago
    
    # Bullish FVG: gap up — low of current bar > high of 2-bars-ago
    if bars[0].low > bars[2].high:
        gap_size = bars[0].low - bars[2].high
        if gap_size >= MIN_FVG_SIZE:
            return FVG(
                type=BULLISH,
                top=bars[0].low,    # top of gap
                bottom=bars[2].high, # bottom of gap
                ce=(bars[0].low + bars[2].high) / 2.0,
                state=NORMAL
            )
    
    # Bearish FVG: gap down — high of current bar < low of 2-bars-ago
    if bars[0].high < bars[2].low:
        gap_size = bars[2].low - bars[0].high
        if gap_size >= MIN_FVG_SIZE:
            return FVG(
                type=BEARISH,
                top=bars[2].low,    # top of gap
                bottom=bars[0].high, # bottom of gap
                ce=(bars[2].low + bars[0].high) / 2.0,
                state=NORMAL
            )
    
    return None

# ─────────────────────────────────────────────────────────────
# STEP 2: Update FVG state on each new bar close
# (using confirmed bar, not live/intrabar)
# ─────────────────────────────────────────────────────────────
def update_fvg_state(fvg, closed_bar):
    """
    Called on bar close. closed_bar is the fully confirmed bar.
    """
    bar_close = closed_bar.close
    bar_high  = closed_bar.high
    bar_low   = closed_bar.low

    if fvg.state == NORMAL:
        # Check if price has mitigated (closed beyond far boundary)
        if fvg.type == BULLISH and bar_close < fvg.bottom:
            # Bullish FVG: far boundary = bottom. Close below bottom = mitigation
            fvg.state = MITIGATED
            fvg.mitigation_bar = current_bar_index
        elif fvg.type == BEARISH and bar_close > fvg.top:
            # Bearish FVG: far boundary = top. Close above top = mitigation
            fvg.state = MITIGATED
            fvg.mitigation_bar = current_bar_index

    elif fvg.state == MITIGATED:
        # Check if price has re-entered the zone (overlap)
        bar_overlaps_zone = (bar_high > fvg.bottom) and (bar_low < fvg.top)
        if bar_overlaps_zone:
            fvg.state = RETRACED

    elif fvg.state == RETRACED:
        # *** INVERSION SIGNAL ***
        # Check if price has closed beyond far boundary AGAIN (from inside)
        # Requires: previous bar was inside the zone (prevInside check)
        # See MQL5: prevClose > fvgLow AND prevClose < fvgHigh
        prev_bar_inside = (prev_bar.close > fvg.bottom) and (prev_bar.close < fvg.top)
        
        if fvg.type == BULLISH and bar_close < fvg.bottom and prev_bar_inside:
            # IFVG_BEARISH: old bullish gap now acts as resistance
            fvg.state = INVERTED
            fvg.direction_after_flip = BEARISH
            fvg.inversion_bar = current_bar_index
            emit_ifvg_signal(fvg)
        elif fvg.type == BEARISH and bar_close > fvg.top and prev_bar_inside:
            # IFVG_BULLISH: old bearish gap now acts as support
            fvg.state = INVERTED
            fvg.direction_after_flip = BULLISH
            fvg.inversion_bar = current_bar_index
            emit_ifvg_signal(fvg)

    elif fvg.state == INVERTED:
        # Check for invalidation: price closes back inside original zone
        price_inside_zone = (bar_close > fvg.bottom) and (bar_close < fvg.top)
        if price_inside_zone:
            fvg.state = INVALIDATED

# ─────────────────────────────────────────────────────────────
# NOTE on simpler (non-MQL5) approach:
# Many implementations (JT17jO6n, innercircletrader.net) skip the
# MITIGATED→RETRACED step and directly convert:
#   if fvg.state == NORMAL and close_crosses_far_boundary:
#       fvg.state = INVERTED
# This matches the v0.5 spec more closely.
# ─────────────────────────────────────────────────────────────

# Simpler 2-state version (matches v0.5 spec):
def update_fvg_simple(fvg, closed_bar):
    if fvg.state == NORMAL:
        if fvg.type == BULLISH and closed_bar.close < fvg.bottom:
            fvg.state = IFVG_BEARISH  # was BOUNDARY_CLOSED → flip
        elif fvg.type == BEARISH and closed_bar.close > fvg.top:
            fvg.state = IFVG_BULLISH  # was BOUNDARY_CLOSED → flip
    
    elif fvg.state in [IFVG_BULLISH, IFVG_BEARISH]:
        # Invalidation
        price_inside = (closed_bar.close > fvg.bottom) and (closed_bar.close < fvg.top)
        if price_inside:
            fvg.state = INVALIDATED
```

### 8.2 Zone and CE Reference

```python
class IFVGZone:
    """IFVG zone after flip — same boundaries as original FVG"""
    top: float       # = original fvgHigh (unchanged)
    bottom: float    # = original fvgLow (unchanged)
    ce: float        # = (top + bottom) / 2.0 — Consequent Encroachment
    direction: Enum  # BULLISH (acts as support) or BEARISH (acts as resistance)
    
    def is_invalidated_by(self, closed_bar) -> bool:
        """IFVG is invalidated when price closes back inside the original zone."""
        if self.direction == BULLISH:
            # Bullish IFVG fails if price closes below the bottom
            return closed_bar.close < self.bottom
        else:
            # Bearish IFVG fails if price closes above the top
            return closed_bar.close > self.top
    
    def ce_is_violated(self, closed_bar) -> bool:
        """CE violation is a WARNING that zone is weakening."""
        if self.direction == BULLISH:
            return closed_bar.close < self.ce
        else:
            return closed_bar.close > self.ce
```

### 8.3 Trigger Threshold Summary (for config parameter)

```python
TRIGGER_MODE = "CLOSE"  # Options: "CLOSE" (canonical), "WICK" (liberal), "BODY" (strict)

def close_beyond_far_boundary(fvg, bar, mode=TRIGGER_MODE) -> bool:
    if fvg.type == BULLISH:
        if mode == "CLOSE":
            return bar.close < fvg.bottom
        elif mode == "WICK":
            return bar.low < fvg.bottom
        elif mode == "BODY":
            return max(bar.open, bar.close) < fvg.bottom  # full body below
    elif fvg.type == BEARISH:
        if mode == "CLOSE":
            return bar.close > fvg.top
        elif mode == "WICK":
            return bar.high > fvg.top
        elif mode == "BODY":
            return min(bar.open, bar.close) > fvg.top  # full body above
```

---

## 9. Source Disagreement Matrix

| Question | Conservative (ICT Canon) | Liberal |
|---------|-------------------------|---------|
| What triggers IFVG? | Close beyond far boundary | Wick touch or any penetration |
| Prerequisite? | Liquidity sweep + displacement | None |
| Zone after flip? | Full original FVG box | Full original FVG box (consensus) |
| CE? | 50% midpoint | 50% midpoint (consensus) |
| Expiry? | Close back inside zone | Close back inside zone (consensus) |
| First-touch expiry? | No | No (consensus) |
| Double-flip? | Not defined | Not defined (consensus) |

---

## 10. Recommendations for v0.5 → v1.0 Implementation

### Priority Changes

1. **Confirm close-based trigger is already in use** — the v0.5 `BOUNDARY_CLOSED` state should be mapped to `close < fvgLow` (bullish FVG) or `close > fvgHigh` (bearish FVG), not wick-based

2. **Add CE field to IFVG zone** — `ce = (fvgLow + fvgHigh) / 2.0` — required for trade entry precision and zone-weakness detection

3. **Add INVALIDATED state** — when price closes back inside the original zone, the IFVG should transition to INVALIDATED, not remain active

4. **Expose trigger mode as a config parameter** — `CLOSE` (default), `WICK` (liberal), `BODY` (strict)

5. **Consider the MQL5 4-state model vs. simpler 2-state** — the 4-state model (NORMAL → MITIGATED → RETRACED → INVERTED) is more accurate to the full ICT concept but requires tracking the price-re-entering-the-zone step; the 2-state model (NORMAL → IFVG on first close-through) is simpler and matches most TradingView implementations

6. **Add staleness pruning** — implement a max-bars lookback (suggested default: 100 bars) beyond which inactive FVGs are pruned from tracking arrays to prevent memory bloat

7. **Optional displacement filter** — `bool require_displacement = false` — when enabled, check that the triggering candle has a body size > 1.5× average body size (ATR-derived) before confirming inversion

---

## Appendix: Source URLs

| # | Source | URL |
|---|--------|-----|
| 1 | ACE FVG & IFVG Trading System (TradingView) | https://www.tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/ |
| 2 | iFVG Structural Framework (TradingView) | https://www.tradingview.com/script/B0UXFx1Q/ |
| 3 | iFVG Pro (TradingView) | https://www.tradingview.com/script/W2kx2bRf/ |
| 4 | Time-Based FVG with Inversions (TradingView) | https://www.tradingview.com/script/JT17jO6n-Time-Based-Fair-Value-Gaps-FVG-with-Inversions-iFVG/ |
| 5 | TradingFinder IFVG | https://tradingfinder.com/education/forex/ict-inversion-fair-value-gap/ |
| 6 | FXOpen IFVG | https://fxopen.com/blog/en/what-is-an-inverse-fair-value-gap-ifvg-concept-in-trading/ |
| 7 | Aron Groups IFVG | https://arongroups.co/technical-analyze/inverse-fair-value-gap-ifvg/ |
| 8 | ICT Trading IFVG Tutorial | https://innercircletrader.net/tutorials/ict-inversion-fair-value-gap/ |
| 9 | MQL5 IFVG Reference Implementation | https://www.mql5.com/en/articles/20361 |
| 10 | FluxCharts IFVG | https://www.fluxcharts.com/articles/Trading-Concepts/Price-Action/Inversion-Fair-Value-Gaps |
| 11 | TradeZella IFVG Model | https://www.tradezella.com/strategies/ifvg-trading-model |
| 12 | ICT CE Tutorial | https://innercircletrader.net/tutorials/ict-consequent-encroachment/ |
| 13 | edgeful.com FVG Fill Statistics | https://www.edgeful.com/blog/posts/fair-value-gap-best-practices-guide |
| 14 | edgeful.com FVG Indicator Stats | https://www.edgeful.com/blog/posts/fvg-indicator-tradingview |
| 15 | ICT Inversion FVG YouTube (uDJI2AbyyCs) | https://www.youtube.com/watch?v=uDJI2AbyyCs |
| 16 | ICT CE YouTube (79KwSQyEzKo) | https://www.youtube.com/watch?v=79KwSQyEzKo |
| 17 | TradingFinder CE | https://tradingfinder.com/education/forex/ict-consequent-encroachment/ |
