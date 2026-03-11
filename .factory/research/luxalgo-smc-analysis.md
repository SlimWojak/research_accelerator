# LuxAlgo Smart Money Concepts — BOS/CHoCH & Order Block Deep-Dive

**Date:** 2026-03-10  
**Source:** [GitHub Gist — niquedegraaff](https://gist.github.com/niquedegraaff/8c2f45dc73519458afeae14b0096d719) (PineScript v5, ~1250 lines)  
**License:** CC BY-NC-SA 4.0 (© LuxAlgo)

---

## 1. Source Code Overview

The LuxAlgo SMC indicator is a single PineScript v5 file (~1250 lines of logic, excluding display helpers). It implements:

| Module | Approx Lines | Description |
|--------|-------------|-------------|
| Swing detection | ~15 | N-bar pivot using `ta.highest`/`ta.lowest` |
| BOS/CHoCH (internal) | ~30 | 5-bar pivot crossover → structure shift |
| BOS/CHoCH (swing) | ~30 | User-configurable N-bar pivot crossover → structure shift |
| Order Block coord | ~25 | Finds highest/lowest candle in structure interval |
| Order Block lifecycle | ~50 | Mitigation tracking + break invalidation |
| FVG, EQH/EQL, Zones | ~200 | Separate modules |
| Display/Alerts | ~400 | Drawing, box management, alertcondition |

---

## 2. BOS/CHoCH Module (Market Structure Shift)

### 2.1 Swing Point Logic

```pinescript
swings(len)=>
    var os = 0

    upper = ta.highest(len)
    lower = ta.lowest(len)

    os := high[len] > upper ? 0 : low[len] < lower ? 1 : os[1]

    top = os == 0 and os[1] != 0 ? high[len] : 0
    btm = os == 1 and os[1] != 1 ? low[len] : 0

    [top, btm]
```

**How it works:**
- Uses a rolling window comparison: `ta.highest(len)` returns the highest high of the last `len` bars (bars 0 to len-1)
- `high[len]` is the bar `len` bars back
- If `high[len] > ta.highest(len)` → that bar is higher than all subsequent `len` bars → swing high
- This is essentially an **N-bar right-side pivot** (checks if bar[len] > all N bars to its right)
- The `os` state variable prevents re-firing: a swing high only fires on the *transition* from state 1→0

**Two scale levels:**
- **Internal structure:** `swings(5)` — 5-bar pivot (fast, captures minor swings)
- **Swing structure:** `swings(length)` — user input, default 50 bars (slow, captures major swings)

### 2.2 BOS vs CHoCH Classification

```pinescript
// Global trend state
var trend = 0    // swing-level trend
var itrend = 0   // internal trend

// Bullish break — close crosses over prior swing high
if ta.crossover(close, top_y) and top_cross
    bool choch = na
    
    if trend < 0
        choch := true       // trend WAS bearish → this break REVERSES it → CHoCH
    else
        choch := false       // trend WAS bullish → break CONTINUES it → BOS
    
    txt = choch ? 'CHoCH' : 'BOS'
    top_cross := false       // consume the swing (one-shot)
    trend := 1               // update trend to bullish

// Bearish break — close crosses under prior swing low  
if ta.crossunder(close, btm_y) and btm_cross
    bool choch = na
    
    if trend > 0
        choch := true       // trend WAS bullish → this break REVERSES it → CHoCH
    else
        choch := false       // trend WAS bearish → break CONTINUES it → BOS
    
    txt = choch ? 'CHoCH' : 'BOS'
    btm_cross := false       // consume the swing (one-shot)
    trend := -1              // update trend to bearish
```

**Key definitions:**
- **BOS (Break of Structure):** Close beyond prior swing point *in the same direction as existing trend*. E.g., close > swing high when trend is already bullish.
- **CHoCH (Change of Character):** Close beyond prior swing point *against the existing trend*. E.g., close > swing high when trend was bearish. This is the *first* break that flips the trend.

**Confirmation logic:**
- Uses `ta.crossover(close, level)` — meaning the **close** must cross above/below the level
- No displacement requirement whatsoever
- No confirmation window — fires on the exact bar where close crosses
- Each swing is consumed once via the `top_cross`/`btm_cross` flags

**Confluence filter (internal only):**
```pinescript
if ifilter_confluence
    bull_concordant := high - math.max(close, open) > math.min(close, open - low)
```
Optional filter requiring the upper wick to be larger than the lower wick for bullish breaks (and vice versa). This is a weak candle-shape filter, not a displacement filter.

### 2.3 Properties per Detection

The LuxAlgo BOS/CHoCH outputs are minimal — only visual:
- Line from swing point bar to current bar at the swing price level
- Label "BOS" or "CHoCH"
- Direction (bullish/bearish) via color
- No numeric metadata, no displacement data, no FVG tagging, no break_type classification beyond BOS/CHoCH

---

## 3. Order Block Module

### 3.1 OB Identification

```pinescript
ob_coord(use_max, loc, target_top, target_btm, ...)=>
    min = 99999999.
    max = 0.
    idx = 1

    ob_threshold = ob_filter == 'Atr' ? atr : cmean_range

    // For bearish OB (use_max=true): find highest high in interval
    if use_max
        for i = 1 to (n - loc)-1
            if (high[i] - low[i]) < ob_threshold[i] * 2
                max := math.max(high[i], max)
                min := max == high[i] ? low[i] : min
                idx := max == high[i] ? i : idx
    // For bullish OB (use_max=false): find lowest low in interval
    else
        for i = 1 to (n - loc)-1
            if (high[i] - low[i]) < ob_threshold[i] * 2
                min := math.min(low[i], min)
                max := min == low[i] ? high[i] : max
                idx := min == low[i] ? i : idx
```

**How it works:**
1. Triggered by a BOS/CHoCH event (order blocks are created at the same time as structure breaks)
2. Scans backward from current bar to the structure break bar (`loc`)
3. Filters candles: only considers candles where `range < ATR * 2` (or cumulative mean range * 2) — this removes volatile candles
4. For **bullish OB**: finds the candle with the **lowest low** → zone = [low, high] of that candle
5. For **bearish OB**: finds the candle with the **highest high** → zone = [low, high] of that candle
6. Zone uses **full candle range** (wick to wick), not just body

### 3.2 OB Lifecycle / Invalidation

```pinescript
// Mitigation: price touches the OB zone
if element == 1 and low[1] > array.get(iob_top, index) and low <= array.get(iob_top, index)
    array.set(iob_mit, index, array.get(iob_mit, index) + 1)  // increment mit counter

// Invalidation/Break: close penetrates through the OB
if close < array.get(iob_btm, index) and element == 1
    // Remove the OB entirely
    array.remove(iob_top, index)
    ...
```

**Mitigation:** price *touches* the OB zone boundary (low taps bullish OB top, high taps bearish OB bottom). The OB is NOT removed — just re-colored. Can be mitigated multiple times.

**Break/Invalidation:** close *penetrates through* the opposite side of the OB. For bullish OB: close < OB bottom. For bearish OB: close > OB top. The OB is permanently removed.

### 3.3 Two levels of Order Blocks:
- **Internal OBs:** Created on internal structure breaks (5-bar swings)
- **Swing OBs:** Created on swing structure breaks (50-bar swings)

---

## 4. Algorithm Comparison: LuxAlgo vs a8ra

### 4.1 MSS / BOS+CHoCH Comparison

| Aspect | LuxAlgo SMC | a8ra MSS Detector |
|--------|-------------|-------------------|
| **Swing detection** | `ta.highest/lowest(N)` — right-side only pivot | N-bar pivot: high >= N left AND > N right |
| **Swing N values** | Internal: 5, Swing: 50 (user input) | Per-TF: 1m→5, 5m→3, 15m→2 |
| **Break condition** | `ta.crossover(close, level)` — close crosses above/below | `close > swing_high.price` or `close < swing_low.price` |
| **Displacement requirement** | ❌ NONE | ✅ Required — must find displacement candle (ATR×1.5 + body ratio 0.6) within confirmation window |
| **Confirmation window** | None — fires on crossover bar | LTF: 3 bars, HTF: 1 bar |
| **Break classification** | BOS (same trend) vs CHoCH (reversal) | CONTINUATION (same trend) vs REVERSAL (counter-trend) |
| **Conceptual mapping** | **BOS ≈ a8ra CONTINUATION, CHoCH ≈ a8ra REVERSAL** | Same concept, different names |
| **FVG tagging** | ❌ No | ✅ Tags whether displacement created an FVG |
| **Impulse suppression** | ❌ No — can fire repeatedly | ✅ Pullback-reset, opposite-displacement-reset, new-day-reset |
| **Swing consumption** | ✅ Each swing consumed once (`top_cross` flag) | ✅ Each swing consumed once (`broken_swings` set) |
| **Trend state** | Simple: `var trend = 0` (flip on each break) | Inferred from prior swing sequence (HH/HL vs LH/LL) |
| **Two scale levels** | ✅ Internal (5-bar) + Swing (50-bar) | ❌ Single level per timeframe |
| **Height filter** | ❌ No minimum swing height | ✅ height_filter_pips per TF (0.5–3.0 pips) |
| **Output metadata** | Minimal: label + line | Rich: direction, break_type, window_used, displacement details, fvg_created, session, forex_day |
| **Lines of code** | ~60 (structure detection) | ~260 (core logic, excluding imports/dataclass) |

### 4.2 Order Block Comparison

| Aspect | LuxAlgo SMC | a8ra OB Detector |
|--------|-------------|------------------|
| **Trigger** | Any BOS or CHoCH event | MSS event (which already requires displacement) |
| **Anchor candle selection** | Scan backward from break, find extreme high/low candle with range < 2×ATR | Last opposing candle before MSS bar (fallback: scan 3 bars back) |
| **Direction filter** | None — just finds extreme candle in interval | ✅ Must be opposing direction (bearish candle for bullish OB) |
| **Thin candle filter** | Range < 2×ATR (removes volatile candles) | body_pct >= 0.10 (removes doji/spinning tops) |
| **Zone definition** | Full candle range: [low, high] (wick-to-wick) | Execution zone: body only [min(O,C), max(O,C)]; Invalidation: full wick |
| **Mitigation** | Price touches zone → re-color (keeps OB alive) | Retest tracking within look-ahead window (30-100 bars) |
| **Invalidation** | Close penetrates opposite side → remove entirely | State machine: ACTIVE → MITIGATED → INVALIDATED → EXPIRED |
| **Displacement qualifier** | ❌ No (OB itself isn't qualified) | ✅ Inherited from MSS upstream (displacement required) |
| **Two scale levels** | ✅ Internal OBs + Swing OBs | ❌ Single level |
| **Lines of code** | ~75 (coord + lifecycle) | ~200 (core logic) |

---

## 5. Detection Output Mapping

### 5.1 LuxAlgo BOS/CHoCH → a8ra Detection Schema

```
LuxAlgo Field              → a8ra Detection Field
─────────────────────────────────────────────────
structure type (BOS/CHoCH) → properties.break_type (CONTINUATION/REVERSAL)
direction (bull/bear)      → direction ("bullish"/"bearish")
swing price (top_y/btm_y)  → price (broken swing price)
swing bar (top_x/btm_x)    → properties.broken_swing.bar_index
structure bar (current n)   → properties.bar_index
trend state (trend var)     → inferred from break_type
internal vs swing level     → ❌ NOT MAPPED (a8ra has single level)
                            → properties.displacement: NOT AVAILABLE (would be null)
                            → properties.fvg_created: NOT AVAILABLE
                            → properties.session: need to add
                            → properties.forex_day: need to add
```

### 5.2 LuxAlgo OB → a8ra Detection Schema

```
LuxAlgo Field              → a8ra Detection Field
─────────────────────────────────────────────────
ob zone [low, high]        → properties.zone_wick.top/bottom (wick-to-wick)
                            → properties.zone_body: NOT AVAILABLE (LuxAlgo uses full candle)
ob bar (idx)               → properties.ob_bar_index
ob direction (type ±1)     → direction ("bullish"/"bearish")
mit counter                → properties.total_retests (conceptually similar)
break/invalidation         → state transitions (simpler in LuxAlgo: just removed)
internal vs swing          → ❌ NOT MAPPED
```

---

## 6. Transpilation Assessment

### 6.1 Can LuxAlgo BOS/CHoCH be a PrimitiveDetector?

**Yes.** It fits the `PrimitiveDetector` interface cleanly:

```python
class LuxAlgoBOSCHoCHDetector(PrimitiveDetector):
    primitive_name = "luxalgo_structure"
    variant_name = "luxalgo_v1"
    version = "1.0.0"

    def required_upstream(self) -> list[str]:
        return ["swing_points"]  # Could use a8ra swings OR its own
    
    def detect(self, bars, params, upstream, context) -> DetectionResult:
        # ... transpiled logic
```

### 6.2 Upstream Dependencies

**Option A: Use a8ra's swing_points detector**
- Pros: Reuses existing infrastructure, consistent with other detectors
- Cons: Different swing algorithm (N-bar left+right pivot vs N-bar right-only). Would produce different swing points, therefore different structure breaks.
- Mapping: a8ra N=3 on 5m ≈ LuxAlgo 5-bar internal. But a8ra has no 50-bar swing equivalent.

**Option B: Implement LuxAlgo's own swing detection inline**
- Pros: Exact behavioral match to LuxAlgo indicator
- Cons: Duplicates swing logic, cannot reuse a8ra swing_points
- Implementation: ~15 lines of Python for the `swings()` function equivalent

**Recommendation: Option B** for faithful transpilation (behavioral match matters for comparison). Can expose both internal (5-bar) and swing (50-bar) swings.

### 6.3 Mapping Summary

| LuxAlgo Concept | a8ra Equivalent | Exact Match? |
|-----------------|-----------------|:---:|
| BOS | MSS with break_type=CONTINUATION | ⚠️ Conceptual match, different trigger (no displacement gate) |
| CHoCH | MSS with break_type=REVERSAL | ⚠️ Same concept, different trigger |
| Internal Structure (5-bar) | swing_points N=5 on 1m, N=3 on 5m | ⚠️ Close but different pivot algo |
| Swing Structure (50-bar) | No equivalent | ❌ Would need new upstream |
| Order Block | order_block | ⚠️ Different anchor selection |

### 6.4 Estimated Transpilation Effort

| Component | Estimated Python Lines | Complexity |
|-----------|:---------------------:|:----------:|
| LuxAlgo swing detection (inline) | ~30 | Low |
| BOS/CHoCH detection + trend state | ~80 | Medium |
| Order Block coord + lifecycle | ~100 | Medium |
| Detection schema mapping | ~50 | Low |
| Config/params handling | ~30 | Low |
| **Total** | **~290** | **Medium** |

Compare: a8ra MSS ~260 lines + OB ~200 lines = ~460 lines. LuxAlgo is simpler because:
- No displacement gate
- No impulse suppression
- No FVG tagging
- Simpler trend state machine
- No confirmation window

### 6.5 Key Behavioral Differences (What Olya Would See)

1. **LuxAlgo fires MORE structure breaks.** Without displacement requirement, every close beyond a swing is a valid break. a8ra filters ~40-60% of these out by requiring displacement.

2. **LuxAlgo has TWO levels of structure.** Internal (5-bar = minor swings) and Swing (50-bar = major swings). a8ra only has one level per timeframe. On a chart, LuxAlgo shows both minor BOS and major CHoCH simultaneously.

3. **LuxAlgo BOS/CHoCH fires earlier.** No confirmation window means the signal is on the crossover bar itself. a8ra may delay up to 3 bars waiting for displacement.

4. **LuxAlgo Order Blocks are positioned differently.** They find the extreme candle in the entire structure interval (with ATR filter), not the last opposing candle before the break. This means:
   - LuxAlgo OBs may be further from the break point
   - LuxAlgo OBs use full wick range; a8ra uses body for execution zone
   - LuxAlgo OBs can be located at any candle in the interval; a8ra always at MSS-1 (or up to MSS-3)

5. **LuxAlgo OB mitigation is visual-only.** Price touching = re-color but OB persists. a8ra tracks retests with bar counts and has explicit state transitions.

6. **No impulse suppression in LuxAlgo.** Same swing type can fire rapid BOS signals (each new swing consumed, but no cooldown). a8ra prevents re-fires until pullback/reset.

7. **LuxAlgo trend is simpler.** Pure toggle: trend flips to +1 on bullish break, -1 on bearish. a8ra infers trend from HH/HL vs LH/LL swing sequence.

---

## 7. Source References

| Resource | URL | Notes |
|----------|-----|-------|
| GitHub Gist (PineScript v5) | https://gist.github.com/niquedegraaff/8c2f45dc73519458afeae14b0096d719 | Full source, ~1250 lines. CC BY-NC-SA 4.0 |
| TradingView page | https://www.tradingview.com/script/CnB3fSph-Smart-Money-Concepts-SMC-LuxAlgo/ | Official listing, open source |
| LuxAlgo blog | https://www.luxalgo.com/blog/smart-money-concept-indicator-for-tradingview-free/ | Feature description, no code |
| eonfutures mirror | https://github.com/eonfutures/Pinescript-Indicators | Mirror with MQL5 port included |
| a8ra MSS detector | `src/ra/detectors/mss.py` | ~260 lines core logic |
| a8ra OB detector | `src/ra/detectors/order_block.py` | ~200 lines core logic |
| a8ra swing_points detector | `src/ra/detectors/swing_points.py` | N-bar left+right pivot |
| a8ra locked config | `configs/locked_baseline.yaml` | N per TF, displacement keys |
