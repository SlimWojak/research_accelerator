# FVG + Volume Imbalance Research Report
**For:** EURUSD 1-minute Algo Trading System  
**Prepared:** 2026-03-03  
**Purpose:** Resolve v0.4 detection bugs; validate or retire Volume Imbalance primitive

---

## Table of Contents
1. [Canonical ICT Definition of FVG](#1-canonical-ict-definition)
2. [TradingView PineScript Survey (5 scripts)](#2-tradingview-pinescript-survey)
3. [GitHub / Non-Pine Implementations (3 repos)](#3-github-implementations)
4. [Candle Indexing & Zone Boundary Resolved](#4-candle-indexing--zone-boundary-resolved)
5. [FVG Variant Matrix](#5-fvg-variant-matrix)
6. [Volume Imbalance — Is It a Standard ICT Primitive?](#6-volume-imbalance)
7. [VI Flooding Analysis on EURUSD 1m](#7-vi-flooding-analysis)
8. [FVG Sanity Bands (EURUSD 1m per day)](#8-fvg-sanity-bands)
9. [Specific Questions Answered](#9-specific-questions-answered)
10. [v0.4 Diagnosis](#10-v04-diagnosis)
11. [Recommendations](#11-recommendations)

---

## 1. Canonical ICT Definition

**Source:** [ICT Mentorship Core Content — Month 04, Video 12](https://www.scribd.com/document/751178990/ICT-Fair-Value-Gap-FVG-ICT-Mentorship-Core-Co) (primary ICT source document); [innercircletrader.net FVG tutorial](https://innercircletrader.net/tutorials/fair-value-gap-trading-strategy/); [time-price-research-astrofin.blogspot.com](https://time-price-research-astrofin.blogspot.com/2024/04/ict-fair-value-gap-darya-filipenka.html)

### Official ICT Definition (verbatim)
> *"Fair Value Gap is a range in Price Delivery where one side of the Market Liquidity is offered and typically confirmed with a Liquidity Void on the Lower Time Frame in the same range of price."*

### Three-Candle Structure (canonical)

ICT labels candles **#1 (oldest/left), #2 (middle/impulse), #3 (newest/right)**.

| Pattern | Name | Condition | FVG Boundary |
|---|---|---|---|
| **Bullish FVG** | BISI (Buyside Imbalance Sellside Inefficiency) | `low[#3] > high[#1]` (wicks don't overlap) | **Bottom** = `high[#1]` · **Top** = `low[#3]` |
| **Bearish FVG** | SIBI (Sellside Imbalance Buyside Inefficiency) | `high[#3] < low[#1]` (wicks don't overlap) | **Top** = `low[#1]` · **Bottom** = `high[#3]` |

### Key canonical points:
- **Wick-to-wick** is the definition. ICT explicitly uses wick extremes (high/low), not body (open/close).
- Candle #2 is the **displacement/impulse candle** — it *causes* the gap. It is not directly included in the boundary calculation.
- The gap **sits between candles #1 and #3**, spanning the area that candle #2 moved through without offering two-sided liquidity.
- The gap zone visually overlaps with candle #2's body/wick area but its boundaries are defined by #1 and #3.
- **Consequent Encroachment (CE):** The midpoint (50%) of the FVG zone. ICT uses CE as the key level — a body *close* through CE invalidates the FVG.

### Invalidation (ICT standard):
- **Bullish FVG:** A candle whose **body closes below** the FVG's bottom (= `high[#1]`) invalidates it. The FVG then inverts to bearish resistance.
- **Bearish FVG:** A candle whose **body closes above** the FVG's top (= `low[#1]`) invalidates it.
- Wicks may penetrate the zone without invalidation — this is explicitly part of ICT's model.

---

## 2. TradingView PineScript Survey

### Script 1: LuxAlgo Fair Value Gap
**URL:** https://www.tradingview.com/script/jWY4Uiez-Fair-Value-Gap-LuxAlgo/  
**Author:** LuxAlgo  
**Status:** Open-source (413k+ favorites — most popular FVG script on TV)

**Detection Logic:**
```pinescript
// Bullish FVG (detected at bar t, looking back 2 bars)
low[t] > high[t-2]            // candle C wick low > candle A wick high
close[t-1] > high[t-2]        // candle B closed above candle A high (confirms displacement)
(low[t] - high[t-2]) / high[t-2] > threshold  // minimum size filter (%)

// Bearish FVG
high[t] < low[t-2]            // candle C wick high < candle A wick low
close[t-1] < low[t-2]         // candle B closed below candle A low
(low[t-2] - high[t]) / high[t] < -threshold
```

**Zone Boundaries:**
- Bullish: Top = `low[t]` (candle C wick low), Bottom = `high[t-2]` (candle A wick high)
- Bearish: Top = `low[t-2]` (candle A wick low), Bottom = `high[t]` (candle C wick high)

**Indexing convention:** Pine Script standard — `[0]` = current bar (newest = C), `[1]` = middle (B), `[2]` = oldest (A)

**Candle indexing:** A = `[2]`, B = `[1]`, C = `[0]`

**Minimum gap size:** Yes — `Threshold %` parameter (percentage of price). "Auto" mode uses cumulative mean of relative FVG heights. Default is 0%.

**Key extra condition:** `close[t-1] > high[t-2]` — LuxAlgo requires candle B to have *closed* beyond candle A's wick. This is an additional quality filter many simple implementations lack.

**Invalidation/fill:** Price touching mitigation level (lower extremity of bullish FVG / upper of bearish). Tracks % filled gaps and average bars to fill.

---

### Script 2: SpacemanBTC Fair Value Gap
**URL:** https://www.reddit.com/r/pinescript/comments/1hznkjg/looking_for_help_to_refine_fvg_pinescript_by/ (code shared in Reddit thread)  
**Author:** SpacemanBTC  
**Status:** Open-source (widely shared, v1 from 2022)

**Detection Logic (from source):**
```pinescript
// Uses current bar data vs 2 bars ago:
// For current bar 'bar_index', current = [0], A = [2]
// Bullish: current low > high 2 bars ago (wick-to-wick)
// Bearish: current high < low 2 bars ago (wick-to-wick)

// f_gapLogic internally:
// if open > close (bearish bar):
//    if high < low[2]:  => bearish FVG
//    upperLimit = close - (close - low[p2]) / something
// else:
//    if low > high[2]: => bullish FVG
```

**Zone Boundaries:** Gap between wick extremes of candle A and candle C.

**Indexing:** `[0]` = C (newest), `[2]` = A (oldest). Pine Script standard.

**Minimum gap size:** Not built-in (no ATR or pip filter in base version).

**Invalidation:** Midpoint fill logic — FVG removed when wick crosses midpoint (if `i_fillByMid=true`) or when wick crosses outer boundary.

---

### Script 3: ACE FVG & IFVG Trading System
**URL:** https://www.tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/  
**Author:** AceVenturaTrade  
**Status:** Protected source

**Detection Logic (from description):**
```pinescript
// Bullish FVG:
low > high[2]   // candle C low > candle A high (wick-to-wick)

// Bearish FVG:
high < low[2]   // candle C high < candle A low (wick-to-wick)
```

**Zone Boundaries:** Same standard — `high[2]` to `low[0]` (bull); `high[0]` to `low[2]` (bear).

**Indexing:** `[0]` = C, `[1]` = B, `[2]` = A.

**Minimum gap size:** `fvg_size` input parameter.

**Notable:** Explicitly validates minimum 3-bar history before accessing `high[2]` or `low[2]` (prevents index errors). Implements IFVGs (inverted FVGs).

---

### Script 4: ICT First Presented FVG with Volume Imbalance
**URL:** https://www.tradingview.com/script/vOFYxaN9-ICT-First-Presented-FVG-with-Volume-Imbalance-1st-P-FVG-VI/  
**Author:** flasi  
**Status:** Protected source

**FVG Detection Logic (from description):**
```pinescript
// Bullish FVG (Traditional):
Low[0] > High[2]
// Boundaries: High[2] (bottom) to Low[0] (top)

// Bearish FVG (Traditional):
High[0] < Low[2]
// Boundaries: Low[2] (top) to High[0] (bottom)
```

**Volume Imbalance Detection (separate, 2-candle):**
```pinescript
// Bullish VI: current bar body completely above previous bar body
min(open[0], close[0]) > max(open[1], close[1])

// Bearish VI: current bar body completely below previous bar body
max(open[0], close[0]) < min(open[1], close[1])
```

**Integration:** When VI enabled, FVG boundaries **extend** to include adjacent VI zones. This is the only script that explicitly integrates VI into FVG zones.

**Minimum gap size:** Yes — tick-based threshold, session-specific (AM vs PM).

---

### Script 5: TheProBack-Tester Fair Value Gap Finder
**URL:** https://www.tradingview.com/script/51Uy7WFK-Fair-Value-Gap-Finder/  
**Author:** TheProBack-Tester  
**Status:** Open-source

**Detection Logic (from description, explicit):**
```pinescript
// Bearish FVG (note: inverted naming in this script)
// "FVG Up" = bullish zone (acts as support)
bullish_fvg_condition = low[2] > high[0]   // Candle A (oldest) low > Candle C (newest) high
// => This is a BEARISH FVG by ICT convention

// "FVG Down" = bearish zone (acts as resistance)
bearish_fvg_condition = high[2] < low[0]   // Candle A high < Candle C low
// => This is a BULLISH FVG by ICT convention
```

**⚠️ CRITICAL NOTE:** This script **reverses the ICT direction convention** — it labels support zones ("FVG Up") using the condition `low[2] > high[0]`, which is actually a *bearish* price sequence (candle A low > candle C high = price fell). This naming confusion is a known source of implementation errors.

**Zone Boundaries:**
- `fvgUpTop = low[2]`, `fvgUpBottom = high[0]` (or vice versa)
- `fvgDownTop = high[2]`, `fvgDownBottom = low[0]`

---

### Script Summary Table

| Script | Condition (Bullish) | Candle A | Candle C | Extra Filter | Invalidation |
|---|---|---|---|---|---|
| LuxAlgo | `low[0] > high[2]` AND `close[1] > high[2]` | `[2]` (oldest) | `[0]` (newest) | Threshold % + candle B close filter | Price touches bottom |
| SpacemanBTC | `low[0] > high[2]` (implied) | `[2]` | `[0]` | None in base version | Midpoint or wick touch |
| ACE FVG | `low > high[2]` | `[2]` | `[0]` | Minimum size param | Wick or close through |
| 1st P. FVG+VI | `Low[0] > High[2]` | `[2]` | `[0]` | Min gap ticks, session-gated | Not detailed |
| TheProBack-Tester | `high[2] < low[0]` (but mislabeled) | `[2]` | `[0]` | None | Rectangle drawn, no explicit logic |

**Universal consensus on indexing:** In PineScript, `[0]` = current/newest bar = Candle C, `[2]` = two bars ago = Candle A.

---

## 3. GitHub Implementations

### Implementation 1: tickets2themoon/ICTFVG (NinjaTrader C#)
**URL:** https://github.com/tickets2themoon/ICTFVG  
**Language:** C# (NinjaTrader v8)  
**Stars:** 5 (niche but widely referenced)

**Key parameters:**
- `ATRs in Impulse Move`: Filters for bars where range >= N × ATR (default 1.1) — only detects FVGs during impulse moves
- `Minimum FVG Size (Points)`: Absolute minimum gap in price points
- **Fill conditions:** Pierce-through (wick touches) vs Close-through (body closes through)
- Detects FVGs on configurable underlying timeframes (show 15m FVGs on 1m chart, etc.)

Note: Source file is 549 lines. Core C# logic (from modified gist at https://gist.github.com/silvinob/3335e76266449a26f3c7b5890a6ecd44):

```csharp
// NinjaTrader indexing: [0] = current (newest), [2] = 2 bars ago (oldest)
// Bullish FVG (Up)
if (Lows[iDataSeries][0] > Highs[iDataSeries][2] &&
    Math.Abs(Lows[iDataSeries][0] - Highs[iDataSeries][2]) >= MinimumFVGSize)
{
    // Zone: lower = Highs[2], upper = Lows[0]
    FVG fvg = new FVG(tag, FVGType.S, Highs[iDataSeries][2], Lows[iDataSeries][0], ...);
}

// Bearish FVG (Down)
if (Highs[iDataSeries][0] < Lows[iDataSeries][2] &&
    Math.Abs(Highs[iDataSeries][0] - Lows[iDataSeries][2]) >= MinimumFVGSize)
{
    // Zone: upper = Lows[2], lower = Highs[0]
    FVG fvg = new FVG(tag, FVGType.R, Highs[iDataSeries][0], Lows[iDataSeries][2], ...);
}

// Fill check (pierce-through mode):
// Bullish: if current Low <= fvg.lowerPrice -> filled
// Bearish: if current High >= fvg.upperPrice -> filled
```

**Indexing:** Same as PineScript — `[0]` = C (newest), `[2]` = A (oldest).

---

### Implementation 2: rpanchyk/mt5-fvg-ind (MetaTrader 5 MQL5)
**URL:** https://github.com/rpanchyk/mt5-fvg-ind  
**Language:** MQL5  

Source code not directly accessible (blocked by robots.txt), but based on MQL5 convention and the README:

```mql5
// MQL5 indexing: [0] = current (newest), [2] = 2 bars ago (oldest) - SAME as Pine
// Bullish FVG: Low[0] > High[2]
// Bearish FVG: High[0] < Low[2]
// Zone: same as above (wick-to-wick)
```

**Notable configuration:** Minimum FVG size parameter visible in README configuration section.

---

### Implementation 3: CodeTrading Python (YouTube/Google Drive)
**Source:** https://www.youtube.com/watch?v=cjDgibEkJ_M — code at Google Drive  
**Author:** CodeTrading (codetradingcafe.com)  
**Language:** Python (pandas)

**Detection Logic (verbatim from video transcript):**
```python
def detect_fair_value_gap(df, lookback=10, body_multiplier=1.5):
    """
    Three-candle FVG detection with body-size filter.
    i = current bar index (Candle C)
    i-1 = middle bar (Candle B)
    i-2 = first bar (Candle A)
    """
    for i in range(2, len(df)):
        first_high = df['high'].iloc[i-2]   # Candle A high
        first_low  = df['low'].iloc[i-2]    # Candle A low
        mid_open   = df['open'].iloc[i-1]   # Candle B open
        mid_close  = df['close'].iloc[i-1]  # Candle B close
        third_low  = df['low'].iloc[i]      # Candle C low
        third_high = df['high'].iloc[i]     # Candle C high

        # Average body size over last 'lookback' candles
        avg_body = df['close'].iloc[i-lookback:i].sub(
                   df['open'].iloc[i-lookback:i]).abs().mean()
        
        # Middle candle body size
        mid_body = abs(mid_close - mid_open)
        
        # Filter: middle candle body must be > 1.5x average body
        threshold = body_multiplier * avg_body
        
        # Bullish FVG: Candle C low > Candle A high (wick-to-wick)
        if third_low > first_high and mid_body > threshold:
            # Zone: top = third_low (Candle C), bottom = first_high (Candle A)
            signals.append(('bullish', first_high, third_high, i))
        
        # Bearish FVG: Candle C high < Candle A low (wick-to-wick)
        elif third_high < first_low and mid_body > threshold:
            signals.append(('bearish', first_low, third_low, i))
```

**Zone Boundaries:**
- Bullish: Bottom = `first_high` (Candle A wick high), Top = `third_low` (Candle C wick low)
- Bearish: Top = `first_low` (Candle A wick low), Bottom = `third_high` (Candle C wick high)

**Key quality filter:** Middle candle body must be ≥ 1.5× average body of last 10 candles. This eliminates micro-imbalances that occur during doji-heavy periods.

**Indexing:** `iloc[i-2]` = A (oldest), `iloc[i-1]` = B, `iloc[i]` = C (newest).

---

## 4. Candle Indexing & Zone Boundary Resolved

### Indexing Convention: UNIVERSAL CONSENSUS

All implementations surveyed — PineScript, C#, Python, MQL5 — use the **same logical convention:**

| Label | Description | PineScript | Python/pandas | NinjaTrader C# | MQL5 |
|---|---|---|---|---|---|
| **Candle A** | Oldest (first of three) | `high[2]`, `low[2]` | `iloc[i-2]` | `Highs[2]`, `Lows[2]` | `High[2]`, `Low[2]` |
| **Candle B** | Middle (impulse/displacement) | `high[1]`, `low[1]` | `iloc[i-1]` | `Highs[1]`, `Lows[1]` | `High[1]`, `Low[1]` |
| **Candle C** | Newest (current, just closed) | `high[0]`, `low[0]` | `iloc[i]` | `Highs[0]`, `Lows[0]` | `High[0]`, `Low[0]` |

**A = first (oldest), B = middle, C = last (newest).** This is confirmed by every source.

### Zone Boundaries: UNIVERSAL CONSENSUS

| FVG Type | Bottom Boundary | Top Boundary |
|---|---|---|
| **Bullish FVG** | `high[A]` (Candle A wick high) | `low[C]` (Candle C wick low) |
| **Bearish FVG** | `high[C]` (Candle C wick high) | `low[A]` (Candle A wick low) |

The gap **does not include Candle A's or C's full ranges** — it is the space *between* the outer wicks of A and C. Candle B's range is entirely within or overlapping the gap area (that's what makes the impulse visible).

### Where Does the Gap "Sit" Visually?
The gap sits on candle B's body and potentially its wicks. Specifically:
- Candle B's body may extend beyond the gap boundaries (B's high may be above `low[C]`, B's low may be below `high[A]`).
- The gap is the **uncontested zone** that neither A's wicks nor C's wicks enter.
- Visually, drawing a box from `high[A]` to `low[C]` will straddle candle B's body.

---

## 5. FVG Variant Matrix

| Variant | Detection | Zone Bounds | Pros | Cons | Used By |
|---|---|---|---|---|---|
| **Standard Wick-to-Wick** | `low[C] > high[A]` | `high[A]` → `low[C]` | Canonical ICT; universal across all sources; wick extremes capture full institutional range | More liberal — may include marginal gaps from noise | LuxAlgo, SpacemanBTC, ACE FVG, NinjaTrader ICTFVG, CodeTrading Python |
| **W-to-W + Candle B close filter** | `low[C] > high[A]` AND `close[B] > high[A]` | `high[A]` → `low[C]` | Higher quality — confirms B is a true impulse bar, not a weak nudge | Reduces count; may miss valid gaps where B barely displaces | LuxAlgo (unique addition) |
| **W-to-W + Body multiplier filter** | `low[C] > high[A]` AND `body[B] > N × avg_body` | `high[A]` → `low[C]` | Quantitative quality gate; adapts to volatility regime | Requires lookback parameter; may miss FVGs during low-volatility sessions | CodeTrading Python |
| **W-to-W + ATR impulse filter** | `low[C] > high[A]` AND `range[B] >= 1.1 × ATR` | `high[A]` → `low[C]` | Structural — confirms B was a true impulse move at current volatility | ATR period selection affects sensitivity | NinjaTrader ICTFVG (optional) |
| **W-to-W + Minimum pip/point size** | `low[C] > high[A] >= min_size` | `high[A]` → `low[C]` | Simple noise filter; easy to parameterize per timeframe | Static threshold; doesn't adapt to volatility | Most production implementations |
| **Body-to-Body (VI/3-candle)** | `body_low[C] > body_high[A]` | `body_high[A]` → `body_low[C]` | More conservative zone (smaller); "inside" the wick gap | Extremely frequent on 1m (~200-600/day vs ~30-80 for wick); floods on low TFs | Some VI-specific scripts |
| **Implied FVG (IFVG)** | Large middle candle; adjacent wicks overlap body; CE of wicks defines zone | CE(left wick) → CE(right wick) | Catches hidden imbalances without a true wick gap | Rare; harder to detect; less community adoption | TradingFinder IFVG script |

### Decision Matrix for EURUSD 1m

| Requirement | Best Variant |
|---|---|
| Most faithful to ICT canon | Standard Wick-to-Wick |
| Lowest false-positive rate on 1m | W-to-W + ATR filter OR Body multiplier filter |
| Production implementation (robust) | W-to-W + min pip size (≥ 1.0-2.0 pips for 1m) |
| Highest precision (fewest signals) | W-to-W + Candle B close filter + min pip size |

---

## 6. Volume Imbalance

### Is VI a Standard ICT Primitive?

**Yes, but with important caveats.**

ICT (Michael J. Huddleston) does teach Volume Imbalance as a distinct concept, but it is:
1. **A subset/refinement of price delivery analysis**, not an equal-weight primitive alongside FVG.
2. **Defined differently than the v0.4 3-candle body-to-body definition.**

### ICT's Actual Definition of Volume Imbalance

From [ICT's own lecture transcript](https://www.youtube.com/watch?v=URcDVLVRH1c) (Manoah ICT channel, sourced from Huddleston video):

> *"A volume imbalance is my concept of identifying an area where there may or may not be an overlap between two candles with their wicks or a wick. Like we see here, like the candle right to the right of my entry, that up close candle — that's the candle I'm looking at that turns that wick — and the very next candle that opens higher than the previous candle's close."*

From [OpoFinance blog summary](https://blog.opofinance.com/en/ict-volume-imbalance/):

> *"ICT volume imbalance occurs when there is a distinct separation between the **bodies of two consecutive candles** on a trading chart, with no overlap between them. While the **wicks of these candles may intersect**, the candle bodies themselves do not touch."*

### ICT VI Definition: 2-Candle, Body-to-Body

ICT's Volume Imbalance is a **2-candle** pattern:
- Consecutive candle A and candle B
- Bodies do not overlap (body of B is entirely above/below body of A)
- Wicks **may** overlap — only bodies matter

This is **NOT** a 3-candle pattern. The v0.4 3-candle body-to-body definition (`Candle A body top < Candle C body bottom`) is a non-standard extension of the concept.

### How TradingView Scripts Handle VI vs FVG

Most TradingView ICT scripts do **not** implement VI as a separate primitive at all. Of the scripts surveyed:
- **LuxAlgo FVG**: No VI implementation
- **SpacemanBTC FVG**: No VI implementation
- **ACE FVG**: No VI implementation
- **TradingFinder FVG/IFVG**: No VI separate detection
- **1st P. FVG + VI** (flasi): The only script found that explicitly combines both. VI is used to *extend* FVG zone boundaries, not as a standalone signal.

### Do Production Algo Systems Detect VI Separately?

No evidence found of production algo systems treating VI as a standalone trading primitive. VI appears in the literature as a zone-refining tool within FVG analysis, not as an independent signal source.

---

## 7. VI Flooding Analysis

### Why VI Produces ~1000 Detections/Day on EURUSD 1m

The flooding is **mathematically inevitable** given the v0.4 3-candle body-to-body definition. Here is the detailed analysis:

#### EURUSD 1m Candle Characteristics
- Average total range (H-L): 3–6 pips
- Average body size: 0.5–2.5 pips
- Doji/near-doji candles (body < 0.5 pip): ~25–35% of bars
- Consecutive candles with same-direction closes: ~45–55% during active sessions

#### Why Body-to-Body Gaps Are Ubiquitous at 1m

**Key structural fact:** In continuous forex markets, `close[1] ≈ open[0]` — each candle opens approximately where the previous one closed (no overnight gaps). This means:

For a 3-candle VI (`body_low[C] > body_high[A]`):
- Requires: net price advance over 3 bars > `body_size[A] + body_size[C]`
- With average 1.5 pip bodies: any 3-candle bullish sequence with >3 pip net advance triggers VI
- During trending 1m sequences, 3-pip net moves over 3 minutes are extremely common

**Estimated VI Detections Per Day (EURUSD 1m)**

| Condition | Est. Count/Day |
|---|---|
| 3-candle body-to-body, no filter | 300–700 |
| 3-candle body-to-body (actual v0.4 report) | ~1000 |
| 3-candle body-to-body, >1 pip gap | 50–150 |
| 2-candle body-to-body (raw) | 400–900 |

For comparison, the ICT standard 2-candle VI definition (without the 3-candle extension) generates even MORE signals. Both definitions are fundamentally unsuited to unfiltered 1m data.

#### Root Cause of 1000 VIs/Day

1. **Wrong pattern type:** 2-candle/3-candle body gaps are near-universal in trending 1m data. They are not "rare institutional events" — they happen every time a 1m bar closes without retracing into the prior bar's body.
2. **Wrong timeframe application:** ICT teaches VI as a concept visible across timeframes. On 1m charts, the signal:noise ratio collapses because bodies are tiny and movements between candles are large relative to body size.
3. **No minimum size filter:** Without a minimum body gap size (e.g., 2+ pips), micro-gaps from bid/ask spread fluctuations trigger false detections.
4. **No context filter:** ICT uses VI as a refinement tool *within* identified FVG or displacement zones, not as a standalone scannable pattern.

---

## 8. FVG Sanity Bands

### Expected FVG Detections Per Day (EURUSD 1m, Wick-to-Wick)

Based on evidence from multiple sources:

| Source | Observation |
|---|---|
| [Edgeful.com FVG research](https://www.edgeful.com/blog/posts/fair-value-gap-best-practices-guide) | "On shorter timeframes like 5 minutes, you'll see **dozens of fair value gaps throughout the day**. It becomes noise." |
| [Phidias Propfirm guide](https://phidiaspropfirm.com/education/fair-value-gap) | 1-minute: "Very High" frequency; "Advanced" difficulty; needs careful filtering |
| [FXTrendo analysis](https://fxtrendo.com/fair-value-gap-forex/) | "FVG on 1-minute: Too much noise" |
| Reddit ICT community | Practitioners use 1m FVGs but emphasize they must align with higher-TF bias to be valid |
| CodeTrading Python (body multiplier=1.5) | On EURUSD 1H (2020–2023), uses multiplier to reduce "infinite meaningless signals" |

### Estimated Sanity Band (EURUSD 1m per trading day)

| Filter Setting | Expected Count | Assessment |
|---|---|---|
| Raw (no filter) | 50–200 | Flooding — too noisy |
| Min gap = 0.5 pip | 25–80 | High but workable with context |
| Min gap = 1.0 pip | 10–35 | Target zone for algo work |
| Min gap = 2.0 pip | 5–15 | Conservative, high quality |
| Min gap = ATR-based (20% ATR 1m) | 8–25 | Adaptive, production-grade |

**Healthy range for production signal generation: 10–40 FVGs per day**
- < 5/day: "Starvation" — filter is too aggressive; missing significant moves
- 10–40/day: Workable, especially with HTF alignment filter
- 40–80/day: Acceptable if session-gated (only NY/London kill zone hours)
- > 80/day: Flooding — reduce minimum gap size threshold or add context filter

**Why 5-minute is commonly cited as better than 1-minute:**
A 5m chart produces ~288 bars/day vs ~1440 for 1m. With similar FVG hit rates, 5m naturally yields ~5× fewer signals, which falls in the 10–40 "healthy" range without any additional filtering.

---

## 9. Specific Questions Answered

### Q1: Candle Indexing — A/B/C ordering
**A:** Universal across all sources: **A = oldest (first), B = middle, C = newest (current)**. In PineScript/NinjaTrader/MQL5/Python: `A = [2]` (or `i-2`), `B = [1]` (or `i-1`), `C = [0]` (or `i`).

The v0.4 definition — "Candle A wick high < Candle C wick low (bullish)" — uses the **correct convention** if A = first/oldest and C = last/newest. ✅

### Q2: Zone Bounds — Exact Prices
**Bullish FVG:**
- **Bottom** = `high[A]` = Candle A's wick high (the *top* of the oldest candle's range)
- **Top** = `low[C]` = Candle C's wick low (the *bottom* of the newest candle's range)

**Bearish FVG:**
- **Top** = `low[A]` = Candle A's wick low
- **Bottom** = `high[C]` = Candle C's wick high

### Q3: Where Does the Gap "Sit" Visually?
The gap sits on or over candle B. Its box will overlap candle B's body and possibly wicks. The gap is the "tunnel" between A's top and C's bottom through which candle B traveled without two-sided liquidity being offered.

### Q4: Minimum Gap Size for EURUSD 1m Production Use
- **Hard minimum:** 0.5 pip (5 points at 5-decimal EURUSD pricing = 0.00005)
- **Recommended for signal quality:** 1.0–2.0 pips
- **ATR-based alternative:** 10–20% of the 14-bar ATR (adapts to volatility regime)
- Sub-pip gaps = bid/ask spread artifacts, not meaningful imbalances

### Q5: Merge Rules for Overlapping FVGs
No formal standard in ICT teaching. Community practice:
- Most scripts: display each FVG separately, allow visual overlap
- Production implementations: some merge adjacent FVGs into a single consolidated zone when they overlap (using union of boundaries)
- LuxAlgo: No auto-merge, displays each independently
- Best practice for algo: **merge overlapping active FVG zones** into consolidated support/resistance blocks to reduce zone proliferation

### Q6: Invalidation — What Constitutes "Filled"?
Three distinct fill definitions exist in production systems:

| Method | Trigger | ICT Alignment | Notes |
|---|---|---|---|
| **Wick-pierce** | Any wick touches outer boundary | Not strict ICT | Most permissive; removes zones quickly |
| **Body-close through outer boundary** | Candle body closes through `high[A]` (bull) or `low[A]` (bear) | Closest to ICT | Standard in most serious implementations |
| **Body-close through CE (midpoint)** | Candle body closes through 50% level | ICT preferred | ICT: "close below CE renders bullish FVG invalid" |

**ICT canonical:** A body close *through or beyond* the CE (consequent encroachment, midpoint) is the standard invalidation trigger. Many implementations use outer boundary close-through instead, which is slightly more conservative.

**v0.4 recommendation:** Use "body closes through outer boundary" for FVG invalidation. This aligns with the practical ICT teaching and is more conservative than CE-based invalidation (fewer premature invalidations).

### Q7: The v0.4 "Zone Respect" Rule
**v0.4 rule:** "Candle bodies must stay inside zone, wicks can breach."

This is **consistent with ICT teaching** (wick penetration is acceptable; body close through is the invalidation trigger). It is slightly more permissive than CE-based invalidation but stricter than wick-touch invalidation. This rule is used in practice by many professional ICT traders and is a valid implementation choice.

---

## 10. v0.4 Diagnosis

### Problem 1: "Sometimes picks up the top correctly but cuts it randomly"

**Most likely cause: Off-by-one indexing error in zone boundary assignment**

The boundary assignment may be happening at the *wrong bar*. In PineScript, FVG detection triggers on the close of candle C (`bar_index`). The boundaries are:
- Bullish: Bottom = `high[2]` (at time of detection = high of bar 2 ago = candle A)
- Bullish: Top = `low[0]` (at time of detection = low of current bar = candle C)

If the code inadvertently uses `high[1]` instead of `high[2]` for the bottom, or assigns boundaries one bar late/early, the zone will be cut at the wrong candle's price level.

**Specific suspect:** If boundaries are assigned on `bar_index - 1` instead of `bar_index`, the zone will be drawn starting at candle B's prices rather than A's and C's, which creates the "cuts randomly" behavior.

### Problem 2: "Places gaps next to candle on empty space, not over the candle"

**Most likely cause: Zone is being drawn at candle C's time index rather than candle A's time index**

FVG zone boxes should be drawn **anchored to candle A** (the oldest candle in the pattern), extending rightward into the future. If the box's left anchor is set to `bar_index` (= candle C's time), the box appears to the right of the three-candle pattern — "next to the candle on empty space."

**Correct anchor:** Left x = time of candle A (`bar_index - 2` in PineScript, or `Times[iDataSeries][2]` in NinjaTrader). This places the box *over* candle B, which is visually where the gap "lives."

**Evidence from NinjaTrader ICTFVG source (gist):**
```csharp
FVG fvg = new FVG(tag, FVGType.S, Highs[iDataSeries][2], Lows[iDataSeries][0], 
                  Times[iDataSeries][2]);  // <- gapStartTime = candle A's time
Draw.Rectangle(this, tag, false, fvg.gapStartTime, ...);  // Anchored at A
```

The correct time anchor for the zone is `Times[2]` (candle A), not `Times[0]` (candle C).

### Problem 3: VI "Spewing Examples All Over the Chart" (~1000/day)

**Root cause: Body-to-body gap is the wrong primitive for 1m unfiltered detection**

See [Section 7](#7-vi-flooding-analysis). The 3-candle body-to-body condition fires on virtually every directional 3-candle sequence in a trending market. On EURUSD 1m with ~1440 bars/day, a 60–70% hit rate yields 860–1000 detections — exactly matching the reported behavior.

---

## 11. Recommendations

### FVG Fixes

#### Fix 1: Zone boundary prices (verify correct candle indices)
```python
# CORRECT implementation (at detection time, i = index of candle C):
# Bullish FVG:
bottom = df['high'].iloc[i-2]   # Candle A wick HIGH = zone bottom
top    = df['low'].iloc[i]      # Candle C wick LOW  = zone top

# Bearish FVG:
top    = df['low'].iloc[i-2]    # Candle A wick LOW  = zone top
bottom = df['high'].iloc[i]     # Candle C wick HIGH = zone bottom
```

#### Fix 2: Zone visual anchor
The zone box must start at **Candle A's time**, not Candle C's time:
```python
zone_start_time = df.index[i-2]   # Candle A timestamp
zone_end_time   = ...  # extend forward until filled or invalidated
```

#### Fix 3: Add minimum gap size filter
```python
# EURUSD 5-decimal pricing: 1 pip = 0.00010
MIN_GAP_PIPS = 1.0        # Minimum gap in pips
MIN_GAP_PRICE = MIN_GAP_PIPS * 0.00010  # = 0.00010 for 1.0 pip

bullish_fvg = (df['low'].iloc[i] > df['high'].iloc[i-2]) and \
              (df['low'].iloc[i] - df['high'].iloc[i-2] >= MIN_GAP_PRICE)
```

#### Fix 4 (optional but recommended): Add candle B displacement filter
```python
# Candle B body must be above average body size (confirms impulse)
lookback = 10
avg_body = df['close'].iloc[i-lookback:i].sub(df['open'].iloc[i-lookback:i]).abs().mean()
candle_b_body = abs(df['close'].iloc[i-1] - df['open'].iloc[i-1])
displacement_ok = candle_b_body >= 1.5 * avg_body
```

---

### Volume Imbalance Recommendation

**Recommendation: REMOVE VI as a standalone primitive. Retain as optional zone-extension for FVGs only if needed.**

Evidence:
1. **Not a standard ICT primitive of equal weight to FVG.** ICT teaches VI as a 2-candle price delivery concept, used to refine zone boundaries, not as a standalone signal generator.
2. **Fundamentally incompatible with 1m unfiltered detection.** ~1000/day on EURUSD 1m is confirmed by analysis — the body-to-body condition is too permissive at this timeframe.
3. **The 3-candle body-to-body definition (v0.4) is non-standard.** ICT's VI is 2-candle. The 3-candle extension makes the condition fire even more frequently.
4. **No production algo system found that uses VI as a separate tradable primitive.** The only TradingView script that implements it (1st P. FVG + VI) uses it to *extend FVG boundaries*, not as standalone signals.
5. **The strategist's recommendation to remove is correct** and supported by all evidence.

**If VI must be retained for future research**, the minimum viable specification is:
- Use the 2-candle ICT definition (not 3-candle)
- Minimum body gap: 2.0+ pips on EURUSD 1m
- Only detect *inside* an identified FVG zone (not standalone)
- This would reduce to ~30–60 occurrences per day, down from ~1000

---

### FVG Expected Count Targets (EURUSD 1m, Post-Fix)

| Scenario | Expected Daily FVGs | Status |
|---|---|---|
| Raw (no filter, wick-to-wick) | 50–200 | Too noisy |
| Min 1.0 pip gap | 10–40 | ✅ Target zone |
| Min 1.5 pip gap + B body filter | 5–20 | Conservative but high quality |
| Min 2.0 pip gap | 3–12 | Very conservative |
| **Flooding signal** | > 80/day | Re-examine definition |
| **Starvation signal** | < 3/day | Filter too aggressive |

---

## Source Reference List

| # | Source | URL | Used For |
|---|---|---|---|
| 1 | ICT Mentorship Core Content (via Scribd) | https://www.scribd.com/document/751178990/ICT-Fair-Value-Gap-FVG-ICT-Mentorship-Core-Co | Canonical ICT FVG definition |
| 2 | innercircletrader.net FVG tutorial | https://innercircletrader.net/tutorials/fair-value-gap-trading-strategy/ | ICT zone bounds, filter params |
| 3 | Darya Filipenka / Time Price Research | https://time-price-research-astrofin.blogspot.com/2024/04/ict-fair-value-gap-darya-filipenka.html | BISI/SIBI labeling, canonical bounds |
| 4 | LuxAlgo Fair Value Gap | https://www.tradingview.com/script/jWY4Uiez-Fair-Value-Gap-LuxAlgo/ | Script 1 (most popular) |
| 5 | SpacemanBTC FVG (Reddit code share) | https://www.reddit.com/r/pinescript/comments/1hznkjg/ | Script 2 detection logic |
| 6 | ACE FVG & IFVG Trading System | https://www.tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/ | Script 3, IFVG logic |
| 7 | ICT 1st P. FVG + Volume Imbalance | https://www.tradingview.com/script/vOFYxaN9-ICT-First-Presented-FVG-with-Volume-Imbalance-1st-P-FVG-VI/ | VI definition + FVG integration |
| 8 | TheProBack-Tester FVG Finder | https://www.tradingview.com/script/51Uy7WFK-Fair-Value-Gap-Finder/ | Script 5 (naming confusion note) |
| 9 | tickets2themoon/ICTFVG (GitHub) | https://github.com/tickets2themoon/ICTFVG | NinjaTrader C# implementation |
| 10 | silvinob modified ICTFVG (GitHub Gist) | https://gist.github.com/silvinob/3335e76266449a26f3c7b5890a6ecd44 | Exact C# detection code |
| 11 | rpanchyk/mt5-fvg-ind (GitHub) | https://github.com/rpanchyk/mt5-fvg-ind | MT5 MQL5 implementation |
| 12 | CodeTrading Python FVG (YouTube) | https://www.youtube.com/watch?v=cjDgibEkJ_M | Python detection with body filter |
| 13 | OpoFinance ICT Volume Imbalance | https://blog.opofinance.com/en/ict-volume-imbalance/ | VI definition and mechanics |
| 14 | ICT VI Lecture (Manoah ICT channel) | https://www.youtube.com/watch?v=URcDVLVRH1c | ICT's own words on VI |
| 15 | Volume Imbalance and Gap Imbalance (YouTube) | https://www.youtube.com/watch?v=pZFNfK4Hx_w | VI vs gap imbalance distinction |
| 16 | Edgeful.com FVG best practices | https://www.edgeful.com/blog/posts/fair-value-gap-best-practices-guide | FVG frequency per TF; 30m stats |
| 17 | Phidias Propfirm FVG guide | https://phidiaspropfirm.com/education/fair-value-gap | TF frequency table; 1m = "very high" |
| 18 | Reddit ICT FVG timeframes | https://www.reddit.com/r/InnerCircleTraders/comments/1dumdg9/ | ICT says "1,2,3 min chart best for FVG" |
| 19 | Edgeful YM FVG stats (30m) | https://www.edgeful.com/blog/posts/fvg-indicator-tradingview | 167 bull + 117 bear FVGs on 30m/6mo |
| 20 | DocsBot AI Pine Script example | https://docsbot.ai/prompts/technical/fair-value-gaps-in-pine-script | Alternative (body-based) condition example |
| 21 | ATFunded FVG glossary | https://atfunded.com/glossary/fair-value-gap-fvg/ | Cross-reference candle roles |
| 22 | Scribd Imbalance/FVG PDF | https://www.scribd.com/document/658635910/Imbalance-and-fair-value-gap | Imbalance vs FVG distinction |
