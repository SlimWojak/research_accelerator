# ICT Tier 2 Primitives: Comprehensive Research Report
**For: ICT Forex Algo Trading System — Research Phase**
**Date: March 2026**
**Scope: 6 Tier 2 Primitives (research-only, no implementation)**

---

## Overview: Tier 2 Dependency Map

The following diagram shows how Tier 2 primitives depend on Tier 1 building blocks:

```
TIER 1 FOUNDATIONS
├── Swing Points (HH, HL, LH, LL)
├── Fair Value Gap (FVG) [3-candle imbalance]
├── Session Levels (Asian H/L, PDH/PDL, NY Open)
└── Candlestick OHLCV

TIER 2 PRIMITIVES (require Tier 1 context)
│
├── Displacement ──────────────── depends on: FVG (created by), Swing Points (broken by)
│       │
├── Market Structure Shift (MSS) ─ depends on: Swing Points + Displacement (required)
├── Break of Structure (BOS) ───── depends on: Swing Points (+ Displacement preferred)
│       │
├── Order Block (OB) ──────────── depends on: Displacement (validates), FVG (confirms)
├── Optimal Trade Entry (OTE) ──── depends on: Swing Points (anchor), BOS (confirms structure)
│                                             OB + FVG (confluence)
├── Liquidity Sweep/Judas ──────── depends on: Session Levels, Swing Points (equal H/L)
│                                             MSS (confirms reversal)
└── Market Maker Model (MMXM) ──── depends on: ALL above (meta-pattern)
                                              OB, FVG, BOS, MSS, Sweep, OTE
```

---

## Primitive 1: Market Structure Shift (MSS) / Break of Structure (BOS)

### 1.1 Standard Definition

**Break of Structure (BOS):**
A BOS occurs when price breaks a swing high in an uptrend or a swing low in a downtrend — confirming trend **continuation**. The prior swing being broken must be in the direction of the prevailing trend.

- Bullish BOS: Price closes above previous external swing high (HH formation in uptrend)
- Bearish BOS: Price closes below previous external swing low (LL formation in downtrend)

**Market Structure Shift (MSS):**
An MSS occurs when price breaks a swing high or low **against** the prevailing trend — signaling a potential **reversal**. It is the first indication that the order flow may be changing direction.

- Bullish MSS: In a downtrend, price breaks above a previous lower high (the last structural high before the trend low)
- Bearish MSS: In an uptrend, price breaks below a previous higher low (the last structural low before the trend high)

**The Key Distinction:**
| Feature | BOS | MSS | CHoCH |
|---|---|---|---|
| Direction | With the trend | Against the trend | Against the trend (stronger) |
| Signal type | Continuation | Early reversal warning | Major reversal confirmation |
| Scope | External swings | Internal swings (intraday) | External key swings |
| Inducement | After liquidity sweep | Can occur directly | After significant liquidity |
| Displacement | Preferred | **Required per most sources** | Required |

Sources: [Equiti MSS vs BOS Guide](https://www.equiti.com/sc-en/news/trading-ideas/mss-vs-bos-the-ultimate-guide-to-mastering-market-structure/), [LuxAlgo MSS Explainer](https://www.luxalgo.com/blog/market-structure-shifts-mss-in-ict-trading/), [ICT Trading BOS Tutorial](https://innercircletrader.net/tutorials/break-of-structure-bos/)

**The v0.4 Methodology Alignment:**
The v0.4 definition of MSS (close beyond prior swing + displacement + FVG created or respected) is largely consistent with the community consensus. Displacement is treated as a **required** component by most serious implementations, not optional. [Aron Groups Displacement Article](https://arongroups.co/technical-analyze/displacement-in-ict/)

### 1.2 Detection Logic

**Prerequisite: Swing Point Detection**
Swing points must be established first (Tier 1). Common implementations use fractal detection: a pivot high is N bars where the middle bar has the highest high of the sequence (Williams Fractal logic, typically N=2 to N=5).

```pseudocode
// SWING POINT DETECTION (fractal, N=2)
isSwingHigh(i, N) = high[i] == highest(high, 2*N+1)[i+N]
isSwingLow(i, N) = low[i] == lowest(low, 2*N+1)[i+N]

// BOS/MSS CLASSIFICATION
// State: track current trend direction (bull/bear)
// Track last significant swing high (pH) and swing low (pL)

// BULLISH BOS (continuation)
if trend == BULL and close > pH.price:
    label "BOS Bull"
    trend remains BULL
    pH = new swing high

// BULLISH MSS (reversal)
if trend == BEAR and close > pH.price:
    label "MSS Bull"    // breaks against bear trend
    trend = BULL        // flip

// BEARISH BOS (continuation)
if trend == BEAR and close < pL.price:
    label "BOS Bear"
    trend remains BEAR
    pL = new swing low

// BEARISH MSS (reversal)
if trend == BULL and close < pL.price:
    label "MSS Bear"    // breaks against bull trend
    trend = BEAR        // flip

// DISPLACEMENT FILTER (for MSS only, optional/required depending on impl)
if require_displacement:
    mss_valid = mss_valid AND isDisplacement(current_candle)
```

**Key implementation found:**
Pine Script BOS/MSS Indicator `ICT Breakers (BOS / MSS - Market Structure) [ICTProTools]`:
```pinescript
// Core logic from Scribd document analysis:
breakHighCond = not na(pH) and highCond > pH.pp
breakLowCond = not na(pL) and lowCond < pL.pp

if breakHighCond:
    if bull:   bosBull := true     // trend was already bull → BOS
    else:      mssBull := true     // trend was bear → MSS (reversal)

if breakLowCond:
    if not bull:  bosBear := true  // trend was already bear → BOS
    else:         mssBear := true  // trend was bull → MSS (reversal)
```
Source: [ICT Breakers PineScript on Scribd](https://www.scribd.com/document/902397983/Explanation-of-Pine-Script-Code)

**Close vs. Wick Debate:**
- Most sources specify **close beyond** the swing point as the valid trigger (not wick)
- Some implementations offer both modes (body-only vs body/wick toggle)
- The Pine Script implementation above has a user input: `mssMode = ['Body Only', 'Body / Wick']`
- ICT community consensus: **close beyond** is required for high-quality BOS/MSS; wick-only is considered noise
- [Strike Money BOS Guide](https://www.strike.money/technical-analysis/break-of-structure): "A candle should give a decisive closing beyond the previous structural point. A wick break is not enough."

### 1.3 Relation to Tier 1 Primitives

| Tier 1 Dependency | How Used |
|---|---|
| Swing Points | Required — the structural high/low being broken |
| FVG | Created by MSS displacement; validates quality of the break |
| Sessions | Context only — higher TF sessions weight the significance |
| OHLCV | Close price is the break trigger (close > swing high) |

MSS/BOS directly require swing point detection. Without Tier 1 swing identification, MSS/BOS cannot be computed.

### 1.4 Variant Matrix

| Source | BOS Definition | MSS Definition | Break Trigger | Displacement Required? |
|---|---|---|---|---|
| ICT (original teaching) | Break of external swing in trend direction | Break of internal swing against trend | Close beyond | Yes (for MSS) |
| LuxAlgo / SMC community | Same as ICT | Same, but may include CHoCH as synonym | Close beyond | Preferred |
| TradingFinder | Medium-term trend change | Short-term trend change (internal structure) | Not specified | Not stated |
| PineScript ICTProTools | Price crosses pivot high/low with bull state = BOS, against = MSS | Same logic, flipped | Configurable (body/wick) | Optional |
| Strike Money | New high/low in trend direction with conviction | First counter-trend structural break | Close beyond | Strong momentum |
| Tsunafire GitHub SMC | Price closes beyond swing to trigger MSS | Identifies structural shifts | Close beyond | Implied |

Sources: [tsunafire GitHub](https://github.com/tsunafire/PineScript-SMC-Strategy), [TradingFinder MSS vs CISD](https://tradingfinder.com/education/forex/mss-vs-cisd/), [ICT Trading BOS](https://innercircletrader.net/tutorials/break-of-structure-bos/)

### 1.5 Complexity Assessment

**MODERATE** — Requires tracking stateful trend direction and maintaining a rolling list of recent swing points. The logic itself is rule-based but requires:
- Continuous swing point state management
- Trend direction tracking (bull/bear context)
- Multi-timeframe swing filtering

### 1.6 Deterministic Detectability

**PARTIAL**

The core structural break (close > swing high or close < swing low) is fully deterministic. However:
- **Swing point selection** is subjective (which N for fractals? Do you use 2-bar, 5-bar, Williams fractal?)
- **Internal vs. external swing** designation requires context that varies by timeframe and practitioner
- **Displacement requirement** for MSS introduces a second judgment call (is this strong enough?)
- The same price break can be called MSS by one system and BOS by another depending on higher-timeframe context

### 1.7 Key Implementation Challenges

1. **Which swing matters?** The choice of fractal lookback (N=2 vs N=5) dramatically changes which swings are "structural." Shorter lookbacks create many false MSS; longer lookbacks create lag.
2. **Internal vs. external swings**: MSS is meant to break an *internal* structural point (inducement/manipulation level), while BOS breaks an *external* structural point. Distinguishing them algorithmically requires multi-level swing hierarchy tracking.
3. **Displacement confirmation**: MSS is only considered "quality" when accompanied by displacement. Since displacement itself is partially subjective (see Primitive 4), this creates a nested subjectivity.
4. **Repainting**: On live data, swing points confirmed with N-bar lookbacks are only valid N bars after they form. Any real-time implementation must account for this lookahead bias.
5. **Timeframe dependency**: The same price action is MSS on the 1m but may be noise on the 15m. An algo system must specify which timeframe context governs classification.

---

## Primitive 2: Optimal Trade Entry (OTE)

### 2.1 Standard Definition

OTE is a Fibonacci retracement zone (62%–79% of a confirmed structural swing) used to identify where institutional participants are likely to re-enter the market during a pullback. It is not a standalone signal — it is a **zone** requiring structural confirmation and confluence.

The OTE zone consists of three key levels:
- **62% (0.618)**: Upper boundary; entry zone begins
- **70.5% (0.705)**: The "sweet spot" / midpoint; highest probability reversal level
- **79% (0.786)**: Lower boundary; last defensible point before trade invalidation

**What the Fibonacci is drawn on:**
The swing must be a **confirmed structural swing** — specifically one where a BOS has occurred. The Fibonacci tool is drawn from the **start of an impulsive/displacement move** to its endpoint (the swing that caused the BOS):
- Bullish OTE: Draw from swing low (start of impulse) to swing high (end of impulse where BOS was formed)
- Bearish OTE: Draw from swing high to swing low

Sources: [GrandAlgo OTE Guide](https://grandalgo.com/blog/ict-optimal-trade-entry-ote), [TradingFinder OTE](https://tradingfinder.com/education/forex/ict-optimal-trade-entry-pattern/), [FXNX OTE Guide](https://fxnx.com/en/blog/mastering-the-ict-fibonacci-retracement-a-traders-guide)

### 2.2 Fibonacci Level Variants Found

| Source | Lower Bound | Sweet Spot | Upper Bound | Notes |
|---|---|---|---|---|
| ICT (original YouTube) | 62% | 70.5% | 79% | Standard ICT levels |
| TradingView Script (yLKbFuXN) | 61.8% | — | 78.6% | Uses standard Fibonacci |
| TradingView India OTE Script | 61.8% | — | 78.6% | Same — standard fib |
| GrandAlgo/TradingFinder | 62% | 70.5% | 79% | ICT-specific levels |
| ICT Trading Tutorial | 0.62 | 0.705 | 0.79 | Three specific levels |
| Smart Risk YouTube | 61.8% | 70.5% | 78.6% | Mixed: ICT + standard |

**Verdict on level variants:** There is a minor discrepancy between practitioners using standard Fibonacci (61.8%, 78.6%) vs. ICT-specific levels (62%, 70.5%, 79%). The ICT-native levels are slightly adjusted from mathematical Fibonacci ratios. The 70.5% level is **unique to ICT** and not found in standard Fibonacci theory. [ICT Trading OTE Tutorial](https://innercircletrader.net/tutorials/ict-optimal-trade-entry-ote-pattern/)

### 2.3 Detection Logic

The OTE is a derived calculation, not a pattern to "detect" as such. It activates after a BOS/displacement is confirmed:

```pseudocode
// STEP 1: Detect confirmed structural swing
// Bullish OTE setup:
if BOS_bullish_confirmed:
    swing_low = price low at start of impulse move
    swing_high = price high where BOS occurred (current)
    
    // STEP 2: Calculate OTE zone
    range = swing_high - swing_low
    ote_high = swing_high - (range * 0.62)   // 62% retracement
    ote_mid  = swing_high - (range * 0.705)  // 70.5% retracement
    ote_low  = swing_high - (range * 0.79)   // 79% retracement
    
    // STEP 3: Activate zone — wait for price pullback
    ote_active = true
    
// STEP 4: Entry trigger (when price enters zone)
if ote_active and close >= ote_low and close <= ote_high:
    // Price is in OTE zone — look for confluence
    if has_fvg_in_zone or has_ob_in_zone:
        signal = BULLISH_OTE_ENTRY_CANDIDATE
    
// STEP 5: Invalidation
if close < swing_low:
    ote_active = false   // structure broken, OTE invalid

// Bearish OTE: mirror all logic (swing_high → swing_low direction)
```

**Anchor point identification (the hard part):**
The swing must be the start of a **displacement move** that caused a BOS. In practice:
- The swing low is the last significant low before the impulsive move up
- The swing high is where the BOS was confirmed (the pivot high broken by the move)
- Systems typically use the same fractal lookback as their swing point detection

Source implementations:
- [TradingView OTE Script (yLKbFuXN)](https://www.tradingview.com/script/yLKbFuXN-OTE-optimal-trade-entry-ICT-visible-chart-only-Dynamic/) — uses visible chart high/low
- [ArunKBhaskar GitHub ICT OTE](https://github.com/ArunKBhaskar/PineScript/blob/main/%5BScreener%5D%20ICT%20Retracement%20to%20Order%20Block%20with%20Screener.txt) — uses Donchian channel highest/lowest over N bars as anchor

### 2.4 Relation to Tier 1 Primitives

| Tier 1 Dependency | How Used |
|---|---|
| Swing Points | Required — define the anchor endpoints for Fibonacci |
| FVG | Confluence tool inside OTE zone (raises probability) |
| Sessions | Kill zones (London/NY) improve OTE reliability; ICT recommends 8:30-11:00 AM NY |
| BOS/MSS (Tier 2) | BOS must precede OTE setup — confirms the swing is structural |

### 2.5 Variant Matrix

| Approach | Anchor Logic | Fib Levels | Wick vs. Body | Confirmation Required |
|---|---|---|---|---|
| ICT Standard | Displacement swing: candle body start to move end | 62%, 70.5%, 79% | Wick-to-wick (highs/lows) | BOS preceding the swing |
| TradingView Script A | Visible chart high/low | 61.8%, 78.6% | Wick-to-wick | None (mechanical) |
| TradingView Script B | Dynamic auto-Fib (recent N-bar H/L) | Configurable | Wick-to-wick | Optional |
| GrandAlgo methodology | Confirmed structural swing (BOS required) | 62%, 70.5%, 79% | Wick-to-wick | BOS + OB/FVG confluence |
| DailyPriceAction | Most recent external high/low | 62%, 79% | Wick-to-wick | Session + sweep confirmation |

Source: [Daily Price Action OTE Strategy](https://dailypriceaction.com/blog/liquidity-sweep-reversals/)

### 2.6 Complexity Assessment

**MODERATE** — The calculation itself is pure arithmetic, but the complexity lies in:
- Correctly identifying the anchor swing (which swing to use)
- Determining when a BOS has occurred to trigger OTE activation
- Managing zone expiration (when is the OTE no longer valid?)

### 2.7 Deterministic Detectability

**PARTIAL**

- Zone calculation: **YES** — fully deterministic arithmetic once anchors are known
- Anchor identification: **PARTIAL** — requires BOS detection (itself partially subjective)
- Confluence confirmation: **PARTIAL** — requires FVG/OB overlap, which are deterministic individually
- "Is this the right swing?": **NO** — practitioner judgment on which displacement swing counts

### 2.8 Key Implementation Challenges

1. **Anchor swing selection**: Multiple potential swing candidates exist. The question of "which swing is the OTE anchor" depends on timeframe context and which BOS you're measuring from.
2. **Zone timing**: The OTE zone for a 4H swing will overlap with OTE zones from 1H and 15M swings. An algo must define TF hierarchy.
3. **Multiple BOS events**: After several consecutive BOS events, the "most recent structural swing" changes. Systems must decide how many historical swings to maintain.
4. **Invalidation logic**: If price drops below 79% but doesn't break the swing low, is the setup invalidated? Different practitioners have different rules.
5. **Session constraints**: ICT teaching says OTE is most effective during kill zones (8:30–11:00 AM NY). A systematic implementation needs time gating.

---

## Primitive 3: Liquidity Sweep / Judas Swing

### 3.1 Standard Definitions

**Liquidity Sweep:**
A price movement that probes **beyond** a significant high or low (where stop-loss orders cluster) and then **returns** back inside the prior range. The purpose is to trigger clustered stops, providing liquidity for institutional order fills, before reversing.

Key characteristics:
- Price spikes beyond a key level (equal highs/lows, swing H/L, session H/L)
- Price **returns** inside the level (either wick-only or close-back-inside)
- Often followed by a displacement move in the opposite direction
- Volume spike typically accompanies the sweep

**Liquidity Run (contrast):** Price breaks a level and **continues** in that direction — this is a BOS/continuation, not a sweep.

**Judas Swing:**
A **time-specific** liquidity sweep occurring between **midnight and 5:00 AM New York time** (London session). It is the daily false move that sets the day's low (bullish Judas) or high (bearish Judas) before the main directional move.

Specific mechanics of Judas Swing:
- Bullish Judas: Price makes a false move **below** the NY midnight open price and/or Asian session low, trapping short sellers, then reverses higher
- Bearish Judas: Price makes a false move **above** the NY midnight open price and/or Asian session high, trapping longs, then reverses lower
- Occurs 00:00–05:00 AM New York time
- Breaks Asian range to take stops, then MSS confirms reversal

Sources: [ICT Trading Judas Swing Guide](https://innercircletrader.net/tutorials/ict-judas-swing-complete-guide/), [TradingFinder Judas Swing](https://tradingfinder.com/education/forex/ict-judas-swing/), [ICT Scribd Judas Document](https://www.scribd.com/document/717809869/12-ICT-Forex-Understanding-The-ICT-Judas-Swing)

### 3.2 Sweep vs. Breakout Detection Logic

The critical algorithmic question: **when does a level break become a sweep vs. a breakout?**

| Indicator | Sweep | Breakout |
|---|---|---|
| Close location | Close returns INSIDE range | Close remains OUTSIDE range |
| Price velocity | Spike then snap-back | Continued directional close |
| Volume | Volume spike on probe | Volume may sustain |
| Candle signature | Long wick beyond level, small body | Large body closing beyond |
| Follow-through | None or reversal within N bars | Multiple closes beyond level |
| FVG | Displacement FVG forms in new direction | FVG forms in continuation direction |

```pseudocode
// SWEEP DETECTION (algorithmic)
// Track key levels (equal H/L, swing H/L, session H/L)
key_levels = detect_equal_highs_lows() ∪ detect_session_extremes()

for each candle:
    for each level in key_levels:
        // Wick violation (probe beyond)
        probed_above = high > level.price and level.type == BSL
        probed_below = low < level.price and level.type == SSL
        
        // Return inside (sweep confirmation)
        if probed_above and close < level.price:
            SWEEP_BEARISH detected at level
            sweep_valid = true
            
        if probed_below and close > level.price:
            SWEEP_BULLISH detected at level
            sweep_valid = true
            
        // Breakout (no return) — if close OUTSIDE level, it's a run/breakout
        if probed_above and close > level.price:
            BOS_BEARISH or BREAKOUT (wait N bars to confirm)

// SWEEP VALIDITY FILTERS (from community implementations)
// 1. Volume filter: volume > 1.5x average_volume(20) during sweep
// 2. Return speed: must return within 1-5 bars (implementation-specific)
// 3. Minimum wick penetration: wick beyond level ≥ 0.2 × ATR(14)
// 4. Context: sweep in premium zone → bearish; in discount zone → bullish
```

Source implementations:
- [TradingView ICT Concepts (KL0iqOX2)](https://fr.tradingview.com/script/KL0iqOX2-ICT-Concepts-Liquidity-FVG-Liquidity-Sweeps/) — bullish sweep: wick below equal lows + close above; volume ≥ 1.5×; cooldown period
- [tsunafire PineScript SMC](https://github.com/tsunafire/PineScript-SMC-Strategy) — liquidity sweep detection using wick beyond high/low followed by reversal
- [Zeiierman Sweep Criteria](https://www.zeiierman.com/blog/liquidity-sweeps-in-trading/): body ≥ 1.2×ATR; wick ≥ 0.2×ATR; close in top/bottom 25% of range; volume ≥ 1.5×20-bar average; CHoCH within ≤5 bars; FVG ≥ 0.5×ATR

### 3.3 The 30-40 Pip Limit Question

The v0.4 methodology states sweeps are bounded at 30-40 pips (beyond that = trend). This is **not universally adopted** in the community:

| View | Threshold | Rationale |
|---|---|---|
| v0.4 methodology | 30-40 pips for forex majors | Sweeps are surgical; beyond that = institutional intent changed |
| Most community sources | No pip limit; context-dependent | Sweep validity determined by close + follow-through, not size |
| ATR-based approaches | 0.2–1.5× ATR(14) | Adapts to current volatility; more robust than fixed pips |

**Evidence:** The [Zeiierman approach](https://www.zeiierman.com/blog/liquidity-sweeps-in-trading/) and [Phidias Prop Firm guide](https://phidiaspropfirm.com/education/liquidity-sweep) do not mention a pip limit. The concept is that context and the close-back-inside behavior define validity, not an absolute pip threshold.

### 3.4 Judas Swing Detection Logic

```pseudocode
// JUDAS SWING DETECTION
// Time filter: 00:00 to 05:00 New York time
in_judas_window = (ny_hour >= 0 and ny_hour < 5)

// Reference levels
ny_midnight_open = open at 00:00 NY
asian_high = highest(high, ASIA_SESSION)  // typically 17:00-02:00 NY prior day
asian_low = lowest(low, ASIA_SESSION)

if in_judas_window:
    // Bullish Judas: false drop below open/Asian low
    if low < asian_low or low < ny_midnight_open:
        if close > ny_midnight_open:  // returned above
            JUDAS_BULLISH = true
            judas_extreme = low  // stop level
    
    // Bearish Judas: false spike above open/Asian high        
    if high > asian_high or high > ny_midnight_open:
        if close < ny_midnight_open:  // returned below
            JUDAS_BEARISH = true
            judas_extreme = high  // stop level

// Entry: after MSS in direction of reversal, look for FVG or OB
```

### 3.5 Relation to Tier 1 Primitives

| Tier 1 Dependency | How Used |
|---|---|
| Swing Points (equal H/L) | Define the levels being swept |
| Session Levels (Asia H/L, PDH, PDL) | Primary sweep targets for Judas Swing |
| FVG | Created after sweep + displacement; entry tool |
| NY Open Time | Anchor for Judas Swing time constraint |

### 3.6 Variant Matrix

| Source | "Return" Criteria | Time Constraint | Level Types | Volume Req |
|---|---|---|---|---|
| ICT (original) | Close back inside range | None for sweep; 00:00–05:00 NY for Judas | Equal H/L, session extremes | Not specified |
| TradingView KL0iqOX2 | Close on opposite side of level (same bar) | Optional | Equal H/L | Yes (1.5×) |
| Phidias Prop Firm | Price returns through swept level + strong momentum | 1-4 candles | Any key level | Yes |
| Equiti | Close back inside prior range | Any candle | Swing H/L, sessions | Typical spike |
| Daily Price Action | Candle close below/above triggering low | Within same sequence | Swing in OTE zone | None specified |
| Zeiierman | Close, volume spike, displacement candle | ≤5 bars for CHoCH | Equal H/L, major swings | ≥1.5×20-bar avg |

### 3.7 Complexity Assessment

**MODERATE** — Core detection logic (wick beyond + close back inside) is deterministic. Complexity arises from:
- Level management (which levels to track, when they expire)
- Distinguishing genuine sweeps from low-quality probes
- Judas Swing requires session time management

### 3.8 Deterministic Detectability

**PARTIAL**

- Close-back-inside logic: **YES** — fully deterministic
- Level identification (equal H/L): **PARTIAL** — requires "how equal is equal?" threshold
- Volume confirmation: **YES** — if volume data available
- Judas Swing time filter: **YES** — deterministic time comparison
- Distinguishing sweep from early BOS: **PARTIAL** — the same candle can look like either until N bars later

### 3.9 Key Implementation Challenges

1. **Level identification**: "Equal highs/lows" requires a tolerance parameter — prices are never exactly equal. The typical implementation uses ATR-based proximity: `abs(high1 - high2) < atr * 0.1`.
2. **N-bar return window**: There is no canonical number of bars within which the return must happen. Implementations range from "same candle" (wick-only) to "within 5 bars."
3. **Sweep vs. BOS ambiguity**: A sweep that doesn't return is a BOS. The distinction is only confirmed in retrospect — real-time detection risks labeling a BOS as a pending sweep.
4. **Session level tracking**: PDH, PDL, Asian high/low, weekly open must all be tracked and managed as rolling values.
5. **The "30-40 pip" rule is controversial**: If implemented as a hard filter, it will reject large sweeps on volatile days. ATR-relative thresholds are more robust.

---

## Primitive 4: Displacement

### 4.1 Standard Definition

Displacement is an **aggressive, rapid, one-directional price move** characterized by:
1. Large candle bodies relative to wicks
2. Breaks a previous market structure (MSS or BOS)
3. Creates a Fair Value Gap (imbalance) in its wake
4. Occurs after a liquidity grab (stop hunt)
5. No "rotation" — one-sided, not back-and-forth

ICT's qualitative criteria (the "5 components"):
- **Forceful exit**: Large, decisive candles
- **Structure removed**: BOS or MSS confirmed
- **FVG created**: Imbalance left (gap between candle wicks)
- **One-sided**: No opposing candle bodies in the move
- **No rotation**: Consecutive closes in the same direction

Sources: [Aron Groups Displacement Guide](https://arongroups.co/technical-analyze/displacement-in-ict/), [SimpleICT Displacement](https://thesimpleict.com/ict-displacement-explained-2025/)

### 4.2 Quantification Attempts

**Can displacement be quantified?** Multiple approaches have been attempted:

**Approach 1: ATR Multiple (FibAlgo TradingView)**
```
body_size = abs(close - open)
candle_range = high - low
atr_14 = ta.atr(14)

displacement = body_size > (atr_14 * multiplier)   // default: 1.5×ATR
```
Source: [FibAlgo ICT Displacement](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/)

**Approach 2: Body-to-Range Ratio**
```
body_ratio = body_size / candle_range
displacement = body_ratio >= threshold   // default: 0.65 (65%)
```
Used by: [ArunKBhaskar PineScript](https://github.com/ArunKBhaskar/PineScript/blob/main/%5BScreener%5D%20ICT%20Retracement%20to%20Order%20Block%20with%20Screener.txt) uses `body / wick > 0.66`

**Approach 3: Dual Detection (AND condition)**
```
displacement = (body_size > atr * 1.5) AND (body_ratio > 0.65)
```
FibAlgo "Both" mode — most restrictive, reduces false positives.

**Approach 4: Consecutive Bars (ICT Displacement Scanner)**
```
// Count consecutive displacement candles in same direction
if bullish_displacement:
    bullCnt += 1
if bullCnt >= min_bars (default 2-3):
    displacement_sequence = true
```
Source: [Arun_K_Bhaskar ICT Displacement Candles](https://www.scribd.com/document/846180115/Indicator-ICT-Displacement-Candles)

**Approach 5: Percentage Change**
```
// TehThomas TradingView
percentage_change = abs(close - close[1]) / close[1] * 100
displacement = percentage_change > user_threshold
```
Source: [TehThomas Displacement Candles](https://www.tradingview.com/script/1rld7nWE-TehThomas-Displacement-Candles/)

**Approach 6: Combined Criteria (community consensus)**
From [Zeiierman](https://www.zeiierman.com/blog/liquidity-sweeps-in-trading/):
- Body ≥ 1.2× ATR(14)
- FVG created (gap ≥ 0.5× ATR)
- Volume ≥ 1.5× 20-bar average
- CLV (close location value) in top/bottom 25% of bar range

**Comparison of approaches:**
| Method | Pros | Cons | Deterministic? |
|---|---|---|---|
| ATR multiple | Adaptive to volatility | Threshold is arbitrary (1.5×?) | YES |
| Body/range ratio | Simple, universal | Doesn't capture magnitude | YES |
| Dual (ATR + ratio) | Reduces false positives | Still doesn't capture context | YES |
| Consecutive bars | Captures "forceful" quality | Arbitrary min_bars param | YES |
| % change | Simple | Not volatility-normalized | YES |
| Combined + FVG | Most holistic | Multiple arbitrary thresholds | MOSTLY YES |

**The 5 ICT qualitative criteria — are they codeable?**

| Criterion | Codeable? | How |
|---|---|---|
| Forceful exit (large candles) | YES | ATR multiple + body/range ratio |
| Structure removed (BOS/MSS) | PARTIAL | Requires swing detection (Tier 1) + break logic |
| FVG created | YES | 3-candle gap check: `low[0] > high[2]` (bullish) |
| One-sided (no rotation) | PARTIAL | Check that candles don't close in opposing direction; tricky for multi-bar sequences |
| No rotation | PARTIAL | Count opposing candle bodies > 50% body in wrong direction = fail |

**Academic parallel:**
Elliott Wave literature uses "Impulse Wave Structural Score (IWSS)" to quantify impulsive moves. The concept: score momentum, proportionality, and Fibonacci adherence. [Advanced Technical Analysis IWSS](https://algotrading-investment.com/2020/06/04/impulse-wave-structural-score-and-corrective-wave-structural-score/). The directional movement index (DMI) with ADX provides a quantitative distinction between impulse (trending) and corrective (choppy) markets. [TradeWithUFOs DMI Analysis](https://www.tradewithufos.com/impulse-or-correction/)

### 4.3 Relation to Tier 1 Primitives

| Tier 1 Dependency | How Used |
|---|---|
| FVG | Displacement creates FVG as a byproduct; FVG presence confirms displacement quality |
| Swing Points | Displacement must break a swing point (MSS/BOS) to be "structural" |
| OHLCV | Body, wick, range — all raw OHLCV calculations |
| Volume (if available) | Volume spike confirms institutional nature of move |

### 4.4 Variant Matrix

| Implementation | Method | Threshold | Volume? | FVG Check? |
|---|---|---|---|---|
| FibAlgo TV | ATR Multiple + Body/Range Ratio | 1.5× ATR, 65% ratio | No | Yes (auto-detect) |
| TehThomas TV | % price change | User-defined | No | No |
| ArunKBhaskar GitHub | Body/wick ratio | > 0.66 (66%) | ATR check | No |
| Zeiierman | Combined: ATR + volume + CLV + FVG | 1.2× ATR, 25% CLV, 1.5× vol | Yes | Yes |
| ICT (qualitative) | Context + feel + 5 criteria | None (discretionary) | Implied | Yes |
| FMZ.com Strategy | Body > wick × sensitivity | Default 1.2× | No | Implicit |

### 4.5 Complexity Assessment

**MODERATE to COMPLEX**

The candle-level detection (ATR + ratio) is simple. The full ICT definition that requires context (liquidity taken before, FVG created, structure broken) is MODERATE. The qualitative components ("one-sided, no rotation") become COMPLEX when trying to define them precisely.

### 4.6 Deterministic Detectability

**PARTIAL**

- Single-candle body/range ratio: **YES**
- ATR-normalized body size: **YES**
- FVG created by move: **YES**
- Structure broken (BOS/MSS): **PARTIAL** (see MSS section)
- "Institutional quality" (vs. news spike): **NO** — same candle metrics apply to both
- No rotation: **PARTIAL** — can count opposing candle bodies but threshold arbitrary

### 4.7 Key Implementation Challenges

1. **No canonical thresholds**: The ATR multiplier (1.5×? 2.0×?) and body ratio (65%? 70%?) are arbitrary. Different markets and timeframes may require different values.
2. **News-driven spikes look identical**: A 100-pip NFP spike has the same candle metrics as institutional displacement. Context (was liquidity swept first?) helps, but it's itself a judgment call.
3. **"One-sided" is hard to define**: A 3-candle sequence with two large bodies in one direction and one small opposing candle — is that "one-sided"? Requires a tolerance parameter.
4. **Timeframe sensitivity**: A displacement candle on 1m may be invisible on 15m. The same move may qualify as displacement on a lower TF but not on a higher TF.
5. **The fundamental ICT problem**: ICT explicitly says displacement requires liquidity to have been taken first. This makes the full detection dependent on sweep detection, creating circular dependency.

---

## Primitive 5: Order Block (OB)

### 5.1 Standard Definition

An Order Block is the **last opposing candle** immediately before an impulsive displacement move. It represents the final candle where institutional participants placed the directional orders that caused the subsequent aggressive move.

- **Bullish OB**: The last **bearish (down-close) candle** immediately before a bullish displacement/BOS move
- **Bearish OB**: The last **bullish (up-close) candle** immediately before a bearish displacement/BOS move

The zone is typically defined by the **body** (open to close) of that candle — not the full high-to-low range.

Sources: [Strike Money OB Guide](https://www.strike.money/technical-analysis/order-block), [GrandAlgo Propulsion Block](https://grandalgo.com/blog/ict-propulsion-block-explained), [Phidias Prop Firm OB](https://phidiaspropfirm.com/education/order-blocks)

### 5.2 Bodies Only vs. Wicks — The Debate

| View | Rationale | Sources |
|---|---|---|
| **Bodies only** (most common) | Body = institutional orders; wicks = liquidity grabs | ICT YouTube, community consensus |
| Wicks inclusive | Some implementations include full candle range for "buffer" | Some TradingView indicators |
| 50% midline (mean threshold) | Refined entry: only trade down to midpoint of OB body | GrandAlgo, multiple YouTube traders |
| Low probability: wick-to-open | When OB has small body/large wick, use wick bottom to open | YouTube trader (ICT Order Blocks Simplified) |

**Verdict**: The community overwhelmingly uses **bodies** (open-to-close range) as the OB zone, with the **mean threshold** at 50% as a refinement tool. Some implementations add the full range with reduced confidence for "low probability" setups.

### 5.3 Detection Logic

**Core Detection (3-candle pattern):**
```pseudocode
// BULLISH ORDER BLOCK DETECTION
// Candle indexing: [2] = 2 bars ago, [1] = 1 bar ago, [0] = current
for each new bar:
    // Check if candle[2] is a valid OB candidate
    if close[2] < open[2]:                    // candle[2] is bearish
        if high[1] > high[2]:                 // candle[1] breaks above [2]
            if displacement_present([1]):     // optional quality filter
                bullish_OB = {
                    high: open[2],            // body top (OB is defined by body)
                    low: close[2],            // body bottom
                    mid: (open[2]+close[2])/2 // mean threshold
                }

// BEARISH ORDER BLOCK DETECTION
for each new bar:
    if close[2] > open[2]:                    // candle[2] is bullish
        if low[1] < low[2]:                   // candle[1] breaks below [2]
            if displacement_present([1]):     // optional quality filter
                bearish_OB = {
                    high: close[2],           // body top
                    low: open[2],             // body bottom
                    mid: (close[2]+open[2])/2 // mean threshold
                }
```

Source: [joshuaburton096 TradingView OB v2](https://www.tradingview.com/script/1M4FG5X2-ICT-Order-Blocks-v2-Debug/)

**Optional FVG Confirmation:**
```pseudocode
// FVG check (candle [2] is OB, candle [0] current)
bullish_fvg = low[0] > high[2]   // gap between current and OB candle
bearish_fvg = high[0] < low[2]   // gap between current and OB candle

if require_fvg_confirmation:
    ob_valid = ob_valid AND fvg_present
```

**Multiple OB Candidates:**
```pseudocode
// Some implementations include ALL consecutive opposing candles before displacement
// Example: 3 consecutive bearish candles before bullish move
// → Mark ALL THREE as part of bullish OB zone
// This is the "3 consecutive candles" approach

ob_zone_high = max(open[2], open[3], open[4])  // highest body top of consecutive candles
ob_zone_low  = min(close[2], close[3], close[4]) // lowest body bottom
```

This broader approach is shown in YouTube implementations.

### 5.4 Quality Criteria / What Makes an OB "Valid"

| Criterion | Codeable? | Implementation |
|---|---|---|
| Last opposing candle | YES | Check `close[2]` direction, `high/low[1]` breaks out |
| Displacement follows | PARTIAL | Displacement detection (see Primitive 4) |
| FVG created | YES | `low[0] > high[2]` (bullish) check |
| Location at key PD Array | PARTIAL | Requires dealing range / premium-discount computation |
| Occurred in kill zone | YES | Time comparison |
| Volume spike | YES | Volume > avg_volume × N |
| Large body on OB candle | YES | body_ratio > threshold |
| Preceded by liquidity sweep | PARTIAL | Requires sweep detection |

**Phidias 8-point scoring system** — aim for 7+ points:
- Location at move origin (2 pts)
- Large body (1 pt)
- FVG follows (2 pts)
- Volume confirmation (1 pt)
- Session alignment (1 pt)
- LTF structure break (1 pt)

### 5.5 Invalidation: Mitigation vs. Invalidation

| Concept | Definition | Codeable? |
|---|---|---|
| **Mitigation** | Price returns to OB zone and reacts (institutional orders filled) | YES: `price enters [ob_low, ob_high]` |
| **Partial Mitigation** | Price enters but doesn't close through OB | YES: `low < ob_high and close > ob_low` |
| **Full Mitigation** | Price completely fills OB zone; orders exhausted | YES: `close < ob_low` (bullish) |
| **Invalidation** | Price trades decisively THROUGH the OB (structure fails) | YES: `close < ob_low` by N pips |
| **N-bar timeout** | OB expires after too many bars without retest | YES: `bar_count > N` |

**From joshuaburton096 implementation:**
```
Bullish OB invalidated: close < bull_ob_low
Bearish OB invalidated: close > bear_ob_high
```

**Community variance on invalidation:**
- Hard close beyond body → invalid (most common)
- Wick through 50% midline → questionable
- Full range violation → definitely invalid
- Timeout: 5 bars (per YouTube source), 10 bars (another), no timeout (static levels)

Source on 5-bar retest preference: YouTube "Ultimate ICT Order Block Strategy" transcript at {ts:1028-1037}: "if it takes more than five [candles for retest] and let's say 10 or 15, I'm not interested, this order block becomes stale."

### 5.6 Relation to Tier 1 Primitives

| Tier 1 Dependency | How Used |
|---|---|
| FVG | Confirms OB quality (FVG immediately after OB = higher probability) |
| Swing Points | OB must precede a swing break (BOS/displacement) |
| Displacement (Tier 2) | OB "activates" — displacement after OB is what validates it |
| Sessions | Kill zone OBs are higher quality |

### 5.7 Variant Matrix

| Source | OB Definition | Zone Boundaries | Invalidation | FVG Required? |
|---|---|---|---|---|
| ICT Standard | Last opposing candle before displacement | Body (open/close) | Close beyond body | Preferred |
| joshuaburton096 TradingView | Close[2] opposition + high/low[1] breakout | high[2]/low[2] (full candle) | close < ob_low | Optional |
| ArunKBhaskar GitHub | First candle breaking N-bar high/low (momentum candle) | High/Low of signal candle | Implied | Via FVG implication |
| Phidias Prop Firm | Last opposing candle + 8-point quality score | Body only | Score < 7/8 or close through | Points system |
| YouTube (ICT OB Simplified) | Last down candle before up move | Bodies (with optional wick for low-probability) | Stale after 5-10 bars | No (but helps) |
| GrandAlgo (Propulsion Block) | Candle that retraces INTO existing OB | Body of retrace candle | Mean threshold close beyond | N/A (different concept) |

### 5.8 Complexity Assessment

**MODERATE** — Core detection is a 3-candle pattern (deterministic), but quality validation requires displacement detection (PARTIAL) and multi-criteria scoring.

### 5.9 Deterministic Detectability

**PARTIAL**

- Last opposing candle before move: **YES** — `close[2]` direction + breakout at `[1]`
- FVG confirmation: **YES** — gap check
- Zone boundaries (body): **YES** — open/close of candle [2]
- Invalidation (close beyond): **YES** — simple price comparison
- "Quality" (was there displacement? was it at a key level?): **PARTIAL**
- "Last" candle (what if 3 consecutive opposing candles?): **PARTIAL** — need convention

### 5.10 Key Implementation Challenges

1. **"Last" is ambiguous with multiple candidates**: If 3 consecutive bearish candles precede the bullish move, which is the OB? ICT says "last" (most recent), but practitioners often mark all three, or use the one with the largest body.
2. **Distinguishing OB from random consolidation**: Without a displacement filter, any candle before a modest move qualifies. The displacement requirement is critical but introduces subjectivity.
3. **OB age management**: How many historical OBs to track? Older OBs accumulate rapidly. Most implementations limit to N most recent unmitigated OBs (default 5-10).
4. **Breaker blocks vs. OBs**: When an OB is violated and price uses it as resistance/support on the other side, it becomes a "breaker block." Tracking this state transition is algorithmically complex.
5. **Body vs. wick inconsistency**: When OBs have very large wicks (news candles), using body-only can create unrealistically tight zones. The 50% mean threshold is a common compromise.

---

## Primitive 6: Market Maker Model (MMXM)

### 6.1 Is MMXM a Primitive or Meta-Pattern?

**MMXM is definitively a meta-pattern** — a schematic framework composed of all other Tier 2 (and Tier 1) primitives arranged in a specific narrative sequence. It is not detected by a single rule but by recognizing the sequential composition of:

1. Original Consolidation (price range/balance)
2. Manipulation (false break / Judas / liquidity sweep)
3. Smart Money Reversal (displacement + MSS)
4. Accumulation / Distribution (retracement phases 1 and 2)
5. Expansion (directional move to terminus / opposite liquidity)

Sources: [YouTube MMXM Market Maker Models](https://www.youtube.com/watch?v=MM-vHn6TBck), [ICT MMXM Step-by-Step](https://www.youtube.com/watch?v=Rf_G-i1g22E), [MMXM Scribd](https://www.scribd.com/document/715412777/ICT-MMXM-Iteration-a11b40c4725c48ae9cc72f6a8aba9caf-3)

### 6.2 Standard Phases

**Market Maker Buy Model (MMBM):**
1. **Original Consolidation**: Price ranges; relatively equal lows/highs form (liquidity accumulates)
2. **Distribution/Manipulation** (Sell Side of Curve): Price drops, sweeps SSL, runs below previous consolidation low
3. **Smart Money Reversal (SMR)**: Displacement up with MSS; liquidity below old lows is collected
4. **First Stage Accumulation**: Price retraces to FVG/OB after MSS; first entry opportunity (20-30% of expected range)
5. **Second Stage Re-accumulation**: Price makes another short-term low after intermediate term low; consolidation (time distortion); second entry opportunity (>50% of expected range)
6. **Terminus/Expansion**: Price reaches premium HTF PD Array (old highs, FVG, OB)

**Market Maker Sell Model (MMSM):** Mirror image — sweeps BSL, SMR downward, redistribution phases.

Source: [YouTube MMXM MM Models Video](https://www.youtube.com/watch?v=MM-vHn6TBck)

**5-Phase Version (TradingFinder/TradingView indicator MMXM):**
1. Original Consolidation
2. Price Run (toward HTF level)
3. Smart Money Reversal (at HTF PD Array)
4. Accumulation/Distribution
5. Completion (expansion to terminus)

### 6.3 Relationship to Power of 3 (PO3)

| Feature | Power of 3 (PO3) | MMXM |
|---|---|---|
| Phases | 3: Accumulation → Manipulation → Distribution | 4-6 phases (more granular) |
| Timeframe | Intraday (daily session) | Fractal — applies to any TF |
| Entry focus | Kill zone entries (AMD model) | Two-stage accumulation entries |
| Relationship | PO3 is the conceptual framework | MMXM is the structural delivery of PO3 |
| Overlap | Near-identical stages conceptually | MMXM adds re-accumulation stages |

Reddit community perspective: "Power of 3 is the concept, MMXM is the way it delivers." [Reddit InnerCircleTraders](https://www.reddit.com/r/InnerCircleTraders/comments/18wrwkk/power_of_3_setups_are_similar_to_mmxm/)

One view: Understanding MMXM makes PO3 "redundant" — they model the same institutional behavior at different levels of granularity. Another view: they are distinct, with PO3 describing a daily session pattern and MMXM being any timeframe's institutional cycle.

### 6.4 The "MMXM IS the Liquidity Pool" Question

The v0.4 statement: "MMXM IS the liquidity pool — no sweep required at MMXM boundary."

**Evidence and analysis:**
- **Supporting**: The MMXM model describes HOW price delivers from one liquidity pool to the next. The model boundary (original consolidation / terminus) IS defined by where liquidity rests. In this sense, the MMXM itself is the liquidity cycle, not a pattern that requires a sweep before it.
- **Against**: The MMBM begins with a manipulation leg that IS a sweep (sweeps SSL). The sweep is internal to the model's Phase 2, not an external prerequisite.
- **Reconciliation**: The distinction is between an external sweep (required for MSS/OTE entry models) and the model's internal manipulation sweep (which is PART of the MMXM pattern, not a prerequisite). When you are observing a complete MMXM, the sweep already happened in Phase 2. You don't need an additional sweep "at the boundary."

From [Scribd MMXM Iteration document](https://www.scribd.com/document/715412777/ICT-MMXM-Iteration-a11b40c4725c48ae9cc72f6a8aba9caf-3): "We expect price to consolidate... then we want price to expand higher and stop just short of a HTF PD Array/Old High. After this accumulation we want to see it manipulate up into the PD Array or old high after which we want to see a violent correction back into the range..."

This confirms that the manipulation INTO the boundary IS the MMXM — the sweep is built in.

### 6.5 Algorithmic Detection — Can It Be Coded?

**Partial algorithmic detection exists** but is fundamentally a sequential state machine over composed primitives:

```pseudocode
// MMXM DETECTION (Buy Model)
// State machine with 6 states
enum MMBM_STATE {
    IDLE,
    ORIGINAL_CONSOLIDATION,
    MANIPULATION_SWEEP,
    SMART_MONEY_REVERSAL,
    ACCUMULATION_1,
    ACCUMULATION_2,
    EXPANSION
}

state = IDLE

// State transitions:
IDLE → ORIGINAL_CONSOLIDATION:
    condition: price range-bound (ATR contracting, equal H/L detected)
    
ORIGINAL_CONSOLIDATION → MANIPULATION_SWEEP:
    condition: price breaks BELOW consolidation low + sweep of SSL
    
MANIPULATION_SWEEP → SMART_MONEY_REVERSAL:
    condition: displacement UP + bullish MSS + FVG created
    
SMART_MONEY_REVERSAL → ACCUMULATION_1:
    condition: first retracement after MSS (into FVG/OB)
    condition: retracement < 30% of expected range
    
ACCUMULATION_1 → ACCUMULATION_2:
    condition: intermediary high formed, second pullback > 50% of expected range
    condition: "time distortion" (consolidation) present
    
ACCUMULATION_2 → EXPANSION:
    condition: BOS to upside of accumulation range
    condition: price targeting HTF PD Array (OB, FVG, equal H/L)
```

**TradingView implementations found:**
1. [MMXM ICT TradingFinder](https://www.tradingview.com/script/4eQPT3aC-MMXM-ICT-TradingFinder-Market-Maker-Model-PO3-CHoCH-CSID-FVG/) — detects 5 stages using SMT, liquidity sweep, HTF PD arrays, MSS, CISD, FVG
2. [FibAlgo ICT Market Maker Model](https://www.tradingview.com/script/AvZeEzkr-FibAlgo-ICT-Market-Maker-Model/) — three-phase institutional price cycle (Accumulation, Manipulation, Distribution)
3. [Advanced ICT Theory A-ICT](https://www.tradingview.com/script/FvAFGEsw-Advanced-ICT-Theory-A-ICT/) — MMXM phase lifecycle via element classification (PENDING → ORDER BLOCK → TRAP ZONE)
4. [Marketmaker TradingView](https://in.tradingview.com/scripts/marketmaker/) — anomaly candles + liquidity zone + stop hunt detection

**Critical assessment from LinkedIn (Pranay Gaurav, 2025):**
"MMXM phases are not mathematically defined, not observable via inference, and not backed by transition probabilities... MMXM phases are unidentifiable — they are only labeled after price has made a full move." [LinkedIn MMXM critique](https://www.linkedin.com/posts/pranay-gaurav-290a30150_mmxm-ictconcepts-liquiditytrading-activity-7320004504219734016-_83o)

This is the key algorithmic problem: MMXM phase labels are **retrospective by nature**. While the primitives that compose it can be detected (sweeps, MSS, FVG), the MMXM classification itself requires knowing what happens next.

### 6.6 Relation to Tier 1 and Tier 2 Primitives

| Component | Primitive Required |
|---|---|
| Original Consolidation | Swing Points (equal H/L), Session context |
| Manipulation / Sweep | Liquidity Sweep (Tier 2 Primitive 3) |
| Smart Money Reversal | Displacement (Tier 2 Primitive 4) + MSS (Tier 2 Primitive 1) |
| Accumulation entries | Order Block (Tier 2 Primitive 5) + FVG (Tier 1) |
| Re-accumulation entries | OTE (Tier 2 Primitive 2) + FVG within OTE |
| Terminus | HTF Swing Points + FVG/OB at destination |

MMXM **requires all 5 other Tier 2 primitives** plus Tier 1 foundations. It is the apex of the primitive hierarchy.

### 6.7 Variant Matrix

| Source | Phases | Entry Focus | Phase Names | Fractal? |
|---|---|---|---|---|
| ICT (original) | 4: Accumulation, Manipulation, Distribution, Rebalance | OTE + FVG in stages | Varies across ICT material | Yes |
| YouTube MM-vHn6TBck | 6: OC, Range, Return, Stage 1, Stage 2, Terminus | Stage 1 + 2 accumulation | Specific (see above) | Yes |
| TradingFinder TV | 5: OC, Price Run, SMR, Accum/Distrib, Completion | FVG pullback | MMBM/MMSM | Yes |
| FibAlgo TV | 3: Accumulation, Manipulation, Distribution | Post-phase signals | AMD | Yes |
| LinkedIn critique | N/A (no viable definition) | Not applicable | Labels retrospective | N/A |

### 6.8 Complexity Assessment

**COMPLEX** — MMXM requires:
- State machine tracking across multiple timeframes
- All other 5 Tier 2 primitives as sub-components
- Phase transitions that are only confirmable in retrospect
- "Expected range" calculations to determine stage percentages (30%, 50%)
- Fractal nature: the model applies at every timeframe simultaneously

### 6.9 Deterministic Detectability

**PARTIAL** (leaning toward NO for real-time)

- Individual components (sweep, MSS, FVG): **PARTIAL** (as assessed for each)
- Phase transitions in retrospect: **YES** — once all bars are known
- Real-time phase classification: **NO** — current phase label requires knowledge of future price
- "Is this the original consolidation or the accumulation phase?": **NO** — indistinguishable in real time
- Terminus detection: **PARTIAL** — target a HTF PD Array level

### 6.10 Key Implementation Challenges

1. **Retrospective labels**: The biggest challenge. Phase 2 (manipulation) looks identical to a continuation BOS until Phase 3 (SMR) confirms the reversal. There is no way to label Phase 2 in real time.
2. **"Expected range" calculation**: The MMXM model predicts stage 1 accumulation at 20-30% and stage 2 at >50% of the expected range. But the expected range itself requires knowing the terminus, which hasn't happened yet.
3. **Multi-timeframe fractal nature**: MMXM appears on every timeframe simultaneously. A 1m MMXM may be inside the accumulation phase of a 15m MMXM, which is inside the SMR of a 4H MMXM. Managing this hierarchy is extremely complex.
4. **"Time distortion" detection**: The second accumulation stage requires a "time distortion" (consolidation before the continuation). Detecting consolidation algorithmically (ATR contraction? range-bound definition?) introduces another threshold.
5. **SMT Divergence requirement**: Full MMXM quality assessment requires Smart Money Tool (SMT) divergence between correlated assets (e.g., EURUSD vs. GBPUSD), requiring multi-symbol data access.

---

## Summary Assessment Table

| Primitive | Complexity | Deterministic Detectability | Key Dependency |
|---|---|---|---|
| MSS / BOS | MODERATE | PARTIAL | Swing points + displacement context |
| OTE | MODERATE | PARTIAL | BOS confirmation + swing anchor selection |
| Liquidity Sweep | MODERATE | PARTIAL | Level identification + N-bar return window |
| Displacement | MODERATE–COMPLEX | PARTIAL | No canonical thresholds; context-dependent |
| Order Block | MODERATE | PARTIAL | "Last" candle + displacement validation |
| MMXM | COMPLEX | PARTIAL (real-time: near NO) | All other Tier 2 primitives + retrospective labeling |

---

## Cross-Primitive Dependencies and Execution Order

For a complete algo system, the primitives must be evaluated in dependency order:

```
EVALUATION ORDER:
1. Tier 1: Swing Points, FVG, Session Levels (prerequisites for everything)

2. Displacement (Tier 2, foundational):
   → ATR + body/range ratio + FVG created
   → Output: displacement_present(bar_i) = true/false

3. MSS / BOS (Tier 2, structural):
   → Requires: Swing Points + Displacement (for quality)
   → Output: mss_bull/bear or bos_bull/bear + swing_broken level

4. Order Block (Tier 2, zone):
   → Requires: Displacement (validation) + Swing break trigger
   → Output: ob_zone{high, low, mid, type}

5. Liquidity Sweep (Tier 2, event):
   → Requires: Session levels, equal H/L swing points
   → Output: sweep_event{level, direction, bar}

6. OTE (Tier 2, calculated zone):
   → Requires: BOS/MSS (to confirm structural swing)
   → Requires: Swing Points (anchor)
   → Output: ote_zone{high:62%, mid:70.5%, low:79%}

7. MMXM (Tier 2 meta-pattern):
   → Requires: All above as state machine inputs
   → Output: mmxm_phase{current_stage, buy/sell model}
```

---

## Implementation Recommendations for Algo System

Based on research findings:

### What Can Be Coded Deterministically (with acceptable threshold parameters)
- ✅ BOS detection (close > swing high / close < swing low)
- ✅ OTE zone calculation (arithmetic Fibonacci on confirmed swings)
- ✅ Sweep detection (wick beyond + close-back-inside)
- ✅ Displacement candle (ATR multiple + body/range ratio)
- ✅ Order Block identification (last opposing candle + FVG confirmation)
- ✅ Session time filtering for Judas Swing (00:00–05:00 NY)

### What Requires Threshold Parameters (tunable but not universal)
- ⚠️ Swing point lookback (N bars for fractal — typically 2–5)
- ⚠️ Displacement ATR multiplier (1.2×–2.0×; default community: 1.5×)
- ⚠️ Body/range ratio (60%–70%; default: 65%)
- ⚠️ Sweep return window (1–5 bars)
- ⚠️ Equal H/L tolerance (typically ATR × 0.1–0.15)
- ⚠️ OB invalidation method (wick touch vs. mean threshold vs. body close)

### What Cannot Be Fully Automated Without ML or Discretion
- ❌ MSS quality ("is this displacement strong enough to validate?")
- ❌ OTE anchor swing selection (multiple valid anchors exist)
- ❌ MMXM real-time phase classification (retrospective labeling problem)
- ❌ "Which OB among 3 candidates is the right one?"
- ❌ Distinguishing institutional displacement from news volatility

### Recommended Implementation Approach
1. Build displacement detector first — everything depends on it
2. Build swing point detector with configurable N (start N=3)
3. Build BOS/MSS on top of swing detector — classify by trend state
4. Build OB from displacement + BOS event (last opposing candle)
5. Build sweep detector using session levels + equal H/L tracking
6. Build OTE as post-BOS arithmetic zone
7. Treat MMXM as a quality label/filter, not a real-time detector — apply it retrospectively to validate trade setups

---

## Sources Index

1. [LuxAlgo MSS ICT Trading](https://www.luxalgo.com/blog/market-structure-shifts-mss-in-ict-trading/) — MSS vs BOS vs CHoCH comprehensive comparison
2. [Equiti MSS vs BOS Ultimate Guide](https://www.equiti.com/sc-en/news/trading-ideas/mss-vs-bos-the-ultimate-guide-to-mastering-market-structure/) — Rules of MSS and BOS
3. [ICT Trading BOS Tutorial](https://innercircletrader.net/tutorials/break-of-structure-bos/) — Primary source (innercircletrader.net)
4. [TradingFinder MSS vs CISD](https://tradingfinder.com/education/forex/mss-vs-cisd/) — MSS definition, medium-term trend
5. [Strike Money BOS Guide](https://www.strike.money/technical-analysis/break-of-structure) — Detection criteria (close vs wick)
6. [ATAS MSS Article](https://atas.net/blog/understanding-market-structure-and-market-structure-shift-mss/) — Reversal vs continuation definition
7. [Scribd ICT Breakers PineScript](https://www.scribd.com/document/902397983/Explanation-of-Pine-Script-Code) — Actual PineScript BOS/MSS implementation
8. [tsunafire GitHub PineScript SMC](https://github.com/tsunafire/PineScript-SMC-Strategy) — Open-source SMC implementation
9. [GrandAlgo OTE Guide](https://grandalgo.com/blog/ict-optimal-trade-entry-ote) — 62%, 70.5%, 79% with structural context
10. [TradingFinder OTE Pattern](https://tradingfinder.com/education/forex/ict-optimal-trade-entry-pattern/) — 0.705 sweet spot detail
11. [FXNX OTE Guide](https://fxnx.com/en/blog/mastering-the-ict-fibonacci-retracement-a-traders-guide) — ICT-modified Fibonacci levels
12. [ICT Trading OTE Tutorial](https://innercircletrader.net/tutorials/ict-optimal-trade-entry-ote-pattern/) — Primary source, dealing range definition
13. [TradingView OTE Script (yLKbFuXN)](https://www.tradingview.com/script/yLKbFuXN-OTE-optimal-trade-entry-ICT-visible-chart-only-Dynamic/) — 61.8%-78.6% implementation
14. [TradingView India OTE Scripts](https://in.tradingview.com/scripts/ote/) — 61.8%-78.6% OTE zone
15. [ArunKBhaskar GitHub ICT Screener](https://github.com/ArunKBhaskar/PineScript/blob/main/%5BScreener%5D%20ICT%20Retracement%20to%20Order%20Block%20with%20Screener.txt) — Order block + retracement screener
16. [ICT Trading Judas Swing Guide](https://innercircletrader.net/tutorials/ict-judas-swing-complete-guide/) — Primary source
17. [TradingFinder Judas Swing](https://tradingfinder.com/education/forex/ict-judas-swing/) — Midnight structure and time window
18. [Scribd Judas Swing Document](https://www.scribd.com/document/717809869/12-ICT-Forex-Understanding-The-ICT-Judas-Swing) — Detailed Judas mechanics
19. [ICT Trading Liquidity Sweep vs Run](https://innercircletrader.net/tutorials/ict-liquidity-sweep-vs-liquidity-run/) — Primary source on sweep vs run
20. [TradingFinder Liquidity Sweep](https://tradingfinder.com/education/forex/ict-liquidity-sweep-liquidity-run/) — Premium/discount sweep validation
21. [TradingView ICT Concepts Indicator (KL0iqOX2)](https://fr.tradingview.com/script/KL0iqOX2-ICT-Concepts-Liquidity-FVG-Liquidity-Sweeps/) — Volume-confirmed sweep implementation
22. [Daily Price Action Sweep Reversals](https://dailypriceaction.com/blog/liquidity-sweep-reversals/) — Acceptance concept, OTE combination
23. [Phidias Prop Firm Sweep Guide](https://phidiaspropfirm.com/education/liquidity-sweep) — 1-4 candle return, scoring matrix
24. [Equiti Sweep Guide](https://www.equiti.com/sc-en/news/trading-ideas/liquidity-sweeps-explained-how-to-identify-and-trade-them/) — Sweep vs grab distinction
25. [Zeiierman Sweep Guide](https://www.zeiierman.com/blog/liquidity-sweeps-in-trading/) — Quantified criteria (ATR, CLV, volume)
26. [ICT MSS vs Liquidity Sweep YouTube](https://www.youtube.com/watch?v=lMOxbNZKRg4) — Failure to displace = sweep
27. [Aron Groups Displacement Article](https://arongroups.co/technical-analyze/displacement-in-ict/) — 5 criteria, context vs. momentum
28. [SimpleICT Displacement](https://thesimpleict.com/ict-displacement-explained-2025/) — BOS/FVG creation requirement
29. [FibAlgo ICT Displacement TV](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/) — Dual detection: ATR×1.5 AND 65% ratio
30. [TehThomas Displacement Candles TV](https://www.tradingview.com/script/1rld7nWE-TehThomas-Displacement-Candles/) — % change implementation
31. [Scribd ICT Displacement Candles](https://www.scribd.com/document/846180115/Indicator-ICT-Displacement-Candles) — Body filter + consecutive bars scanner
32. [FMZ Advanced Displacement Strategy](https://www.fmz.com/lang/en/strategy/494055) — Body > wick × sensitivity parameter
33. [TradingWithUFOs DMI Impulse](https://www.tradewithufos.com/impulse-or-correction/) — DMI as quantitative impulse vs correction
34. [IWSS Elliott Wave](https://algotrading-investment.com/2020/06/04/impulse-wave-structural-score-and-corrective-wave-structural-score/) — Academic scoring of impulse quality
35. [joshuaburton096 OB v2 TradingView](https://www.tradingview.com/script/1M4FG5X2-ICT-Order-Blocks-v2-Debug/) — OB detection pseudocode
36. [Strike Money Order Block](https://www.strike.money/technical-analysis/order-block) — Last opposing candle definition
37. [GrandAlgo Propulsion Block](https://grandalgo.com/blog/ict-propulsion-block-explained) — OB vs propulsion block vs breaker
38. [Phidias Prop Firm OB Guide](https://phidiaspropfirm.com/education/order-blocks) — 8-point quality scoring
39. [TradingFinder OB FVG Strategy](https://tradingfinder.com/education/forex/trade-continuations-using-order-blocks/) — Invalidation conditions
40. [TradingView OB Search Results](https://www.tradingview.com/scripts/search/order%20block/) — Multiple OB indicator implementations
41. [Pineify OB Indicators Guide](https://pineify.app/resources/blog/best-smart-money-concept-indicators-on-tradingview-ultimate-guide) — SMC indicator comparison
42. [ICT Abbreviations TradingFinder](https://tradingfinder.com/education/forex/ict-abbreviation/) — MMXM, MMBM, MMSM definitions
43. [MMXM Scribd Iteration](https://www.scribd.com/document/715412777/ICT-MMXM-Iteration-a11b40c4725c48ae9cc72f6a8aba9caf-3) — MMXM iteration schematic with breaker blocks
44. [MMXM Scribd PDF](https://www.scribd.com/document/776497721/ICT-Market-Maker-Model-MMXM-PDF) — Accumulation/Manipulation/Distribution phases
45. [Reddit InnerCircleTraders MMXM vs PO3](https://www.reddit.com/r/InnerCircleTraders/comments/18wrwkk/power_of_3_setups_are_similar_to_mmxm/) — Community perspective on relationship
46. [YouTube MMXM Market Maker Models (MM-vHn6TBck)](https://www.youtube.com/watch?v=MM-vHn6TBck) — 6-stage model with stage percentages
47. [YouTube ICT MMXM Step-by-Step (Rf_G-i1g22E)](https://www.youtube.com/watch?v=Rf_G-i1g22E) — CISD + MSS + stages
48. [YouTube Advanced ICT MMXM (Ibw4saRtYMk)](https://www.youtube.com/watch?v=Ibw4saRtYMk) — Symmetry, two-stage accumulation
49. [TradingFinder MMXM TV Indicator](https://www.tradingview.com/script/4eQPT3aC-MMXM-ICT-TradingFinder-Market-Maker-Model-PO3-CHoCH-CSID-FVG/) — Open-source MMXM implementation
50. [FibAlgo Market Maker Model TV](https://www.tradingview.com/script/AvZeEzkr-FibAlgo-ICT-Market-Maker-Model/) — 3-phase AMD detection
51. [Advanced ICT Theory A-ICT TV](https://www.tradingview.com/script/FvAFGEsw-Advanced-ICT-Theory-A-ICT/) — Lifecycle: PENDING → OB → TRAP ZONE
52. [LinkedIn MMXM Critique (Pranay Gaurav)](https://www.linkedin.com/posts/pranay-gaurav-290a30150_mmxm-ictconcepts-liquiditytrading-activity-7320004504219734016-_83o) — Mathematical limitations of MMXM
53. [Headway ICT MMXM Guide](https://hw.online/faq/ict-in-forex-trading-a-comprehensive-guide-for-beginners-in-2024-2/) — Four-phase overview
54. [Forex Tester ICT Guide](https://forextester.com/blog/ict-trading/) — Multi-TF swing point identification
55. [LiteFinance ICT Strategy](https://www.litefinance.org/blog/for-beginners/trading-strategies/ict-trading-strategy/) — MSS + order block combined usage
