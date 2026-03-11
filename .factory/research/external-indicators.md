# External ICT Indicators Research

**Research Date:** 2026-03-10  
**Purpose:** Investigate external ICT displacement and SMC indicators for potential transpilation to a8ra  
**Focus:** TradingFinder, LuxAlgo, FibAlgo, and other popular TradingView implementations

---

## 1. FibAlgo - ICT Displacement

**URL:** https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/  
**Source Availability:** ❌ PROTECTED SOURCE (Closed-source, cannot access PineScript)  
**Release Date:** Feb 25, 2025  
**Popularity:** High (12 favorites, 299 uses shown)

### Detection Logic

**Dual Detection Methods:**
1. **ATR Multiple Method:**
   - Default: Candle body must exceed ATR(14) × 1.5
   - Configurable multiplier range: 0.5–5.0
   - Adapts to current market volatility
   - A candle qualifying in low volatility needs proportionally more range in high volatility

2. **Body/Range Ratio Method:**
   - Default: Candle body must be ≥ 65% of total candle range (high to low)
   - Configurable range: 0.30–0.95 (30%–95%)
   - Identifies "institutional candles" with strong directional commitment
   - Filters out candles with large wicks (indecision)

3. **Combined Method (AND):**
   - Strictest filter: must satisfy BOTH conditions
   - Large body relative to ATR AND high body-to-range ratio
   - Most selective displacement detection

**Additional Features:**
- **Doji Filter:** Automatically excludes doji candles (close = open, zero body)
- **Glow Effect:** Semi-transparent box behind displacement candles (configurable transparency 50-95, default 85)
- **Bar Coloring:** Optional candle color override for displacement bars
- **Measurement Labels:** Shows body size in ticks + body-to-range percentage (e.g., "245.0t, 78.5%")
- **Streak Tracking:** Counts consecutive displacement candles in same direction
  - Alert fires at 3+ consecutive displacements
  - Label shows streak count at 2+
- **Displacement FVG Detection:**
  - 3-candle FVG where middle candle is displacement
  - Marks "higher significance" FVGs created by institutional momentum
  - Draws semi-transparent boxes with optional CE midline
  - Configurable history count (1-50, default 15)
- **Summary Statistics Table:**
  - Total displacement count & percentage
  - Bullish/bearish breakdown
  - Average displacement body size
  - Current ATR value
  - Lookback period: 50-5000 bars (default 500)

### Parameters vs a8ra_v1

| Feature | FibAlgo | a8ra_v1 |
|---------|---------|---------|
| ATR Multiplier | 1.5 (default) | 1.5 (locked) |
| Body/Range Ratio | 0.65 (default) | 0.6 (locked) |
| AND/OR Logic | Configurable | AND (locked) |
| Close Gate | ❌ Not mentioned | ✅ 0.25 |
| Decisive Override | ❌ Not mentioned | ✅ body≥0.75, close_max≤0.1 |
| Cluster Detection | ❌ Basic streak only | ✅ Cluster-2 (adjacent bars) |
| Quality Grades | ❌ None | ✅ STRONG/VALID/WEAK |
| FVG Tagging | ✅ FVG boxes | ✅ FVG creation tag |
| Per-TF Overrides | ❌ None | ✅ LTF vs HTF params |
| Streak Detection | ✅ Consecutive count | ❌ None |

**Key Differences:**
- FibAlgo has **more flexible parameters** (user-configurable vs a8ra's locked thresholds)
- FibAlgo has **richer visualization** (glow effects, measurement labels, statistics table)
- FibAlgo has **streak tracking** (consecutive displacement count)
- a8ra has **more sophisticated logic**:
  - Close gate for confirming direction
  - Decisive override for very strong candles
  - Cluster-2 detection for adjacent displacement bars
  - Quality grading system (STRONG/VALID/WEAK based on ATR multiples)
  - Per-timeframe parameter overrides

### Transpilation Complexity: **HARD**

**Why Hard:**
- Cannot access source code (protected)
- Would need to reverse-engineer from description
- Rich visualization features (glow effects, labels) may not map to Python/HTML easily
- FVG detection integrated with displacement is non-trivial
- Statistics table requires historical lookback management

**What Could Be Learned:**
- Streak detection concept (consecutive displacement)
- FVG tagging by displacement candles
- Body size measurement display (ticks + percentage)
- Statistics dashboard idea

---

## 2. LuxAlgo - Smart Money Concepts (SMC)

**URL:** https://www.tradingview.com/script/CnB3fSph-Smart-Money-Concepts-SMC-LuxAlgo/  
**Source Availability:** ✅ OPEN SOURCE (PineScript v5 available on TradingView + GitHub Gist)  
**GitHub Gist:** https://gist.github.com/niquedegraaff/8c2f45dc73519458afeae14b0096d719  
**Release Date:** Oct 11, 2022  
**Popularity:** VERY HIGH (124.1K uses, 3.8M views, 1218 comments)  
**License:** CC BY-NC-SA 4.0 (Attribution-NonCommercial-ShareAlike)

### Scope: Comprehensive SMC Indicator (NOT Just Displacement)

This is a **full-featured Smart Money Concepts suite**, not a focused displacement detector. It includes:

**Features:**
1. **Market Structure:**
   - Internal & Swing Break of Structure (BOS)
   - Internal & Swing Change of Character (CHoCH)
   - Real-time labeling with dashed (internal) and solid (swing) lines
   - HH/HL/LH/LL swing point labels

2. **Order Blocks:**
   - Internal order blocks
   - Swing order blocks
   - ATR-based or Cumulative Mean Range filtering
   - Mitigation tracking (unmitigated vs mitigated color change)
   - Configurable display count (1-50, default 5)

3. **Equal Highs/Lows (EQH/EQL):**
   - Detects equal levels with configurable threshold (0-0.5, default 0.1)
   - Bars confirmation (default 3)
   - Labels with dotted lines

4. **Fair Value Gaps (FVG):**
   - Multi-timeframe FVG detection
   - Auto threshold filtering
   - Configurable extension (how many bars to extend boxes)
   - Bullish/bearish FVG boxes

5. **Previous High/Low:**
   - Daily, Weekly, Monthly highs/lows
   - Configurable line styles (solid/dashed/dotted)

6. **Premium/Discount Zones:**
   - Range-based premium, equilibrium, discount zones
   - Color-coded overlays

7. **Candle Coloring:**
   - Colors candles based on internal/swing trend

### Displacement-Relevant Code Insights

**Swings Detection (50-bar default):**
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

**Order Block Filtering (ATR-based):**
```pinescript
ob_threshold = ob_filter == 'Atr' ? atr : cmean_range
atr = ta.atr(200)
cmean_range = ta.cum(high - low) / n

// Search for highest/lowest high within structure interval
// Filter: (high[i] - low[i]) < ob_threshold[i] * 2
```

**Internal Structure Detection:**
- Uses 5-bar swings for internal structure
- Confluence filter option: bullish requires `high - max(close,open) > min(close,open-low)`
- Bearish requires opposite

**Order Block Coord Logic:**
```pinescript
// Finds candle with max/min within structure break
// Filters by: candle_range < ob_threshold * 2
// Records top, bottom, left, right, type, mitigation status
```

### Displacement vs a8ra_v1

LuxAlgo SMC does **NOT** have explicit displacement detection like a8ra or FibAlgo. However:

| Feature | LuxAlgo SMC | a8ra_v1 |
|---------|-------------|---------|
| Displacement Detection | ❌ None | ✅ ATR + body ratio + gates |
| Market Structure | ✅ BOS/CHoCH (internal & swing) | ❌ Not in detection module |
| Order Blocks | ✅ With ATR filtering | ❌ Not in detection module |
| FVG Detection | ✅ Multi-timeframe | ✅ Creation tagging only |
| Quality Grades | ❌ None | ✅ STRONG/VALID/WEAK |
| Cluster Detection | ❌ None | ✅ Cluster-2 |
| Close Gate | ❌ None | ✅ 0.25 |

**Key Differences:**
- LuxAlgo is a **comprehensive SMC suite** covering many ICT concepts
- a8ra_v1 displacement is **hyper-focused** on one primitive with sophisticated logic
- LuxAlgo's order block filtering could inform our order block detection module
- LuxAlgo's structure detection (BOS/CHoCH) is separate from displacement

### Transpilation Complexity: **MEDIUM** (for individual features)

**Why Medium:**
- ✅ Source code fully available (PineScript v5)
- ✅ Well-documented and readable
- ✅ Modular design (structure, OB, FVG, EQH/EQL separate)
- ❌ Very large (~2000+ lines of PineScript)
- ❌ Many interdependent features
- ❌ TradingView-specific drawing APIs (boxes, lines, labels)

**What Could Be Learned:**
- Order block detection and filtering logic
- ATR-based volatility filtering
- BOS/CHoCH market structure detection
- EQH/EQL detection algorithm
- FVG detection (3-candle pattern)
- Mitigation tracking patterns

**Recommended Modules to Port (if relevant to a8ra):**
1. **Order Blocks:** Could inform a future OB detection module
2. **BOS/CHoCH:** Could inform market structure shift detection
3. **EQH/EQL:** Useful for liquidity analysis

---

## 3. TradingFinder - ICT Indicators (Multiple)

**URL:** https://tradingfinder.com/products/indicators/tradingview/ict/  
**Source Availability:** ❌ MIXED (Some free, most paid; source not published on TradingView)  
**Pricing:** $50 for ICT Concepts (MT4/MT5), some TradingView indicators free temporarily

### Available Indicators

TradingFinder offers a **library of ICT indicators** rather than a single displacement tool:

1. **ICT Displacement** (implied, not found as standalone)
2. **ICT 2022 Model Entry Strategy** (Liquidity + FVG + MSS)
3. **One Trading Setup for Life ICT** (Sweep + Session + FVG)
4. **Premium & Discount ICT** (Zone identification)
5. **Immediate Rebalance ICT** (Supply/Demand zones)
6. **Silver Bullet ICT Strategy** (10-11 AM NY session + FVG)
7. **Market Structure ICT Screener** (BOS/CHoCH across symbols)

### Displacement References

From the web search results, TradingFinder's displacement logic (when mentioned):
- Uses ATR multiplier (specific values not disclosed in public descriptions)
- Likely includes body/range ratio
- Integrates with other ICT concepts (FVG, liquidity sweeps, MSS)

**No specific displacement indicator found on TradingFinder TradingView page.**

The closest match is their **ICT Concepts suite** which includes displacement as one component among many.

### Transpilation Complexity: **HARD TO IMPOSSIBLE**

**Why:**
- Source code not published
- Would require purchasing ($50+) and reverse-engineering
- Appears to be primarily MT4/MT5 focused
- TradingView versions may be invite-only or paid

**Value Assessment:**
- Not worth pursuing unless we can find open-source TradingView version
- Better to focus on FibAlgo's described logic or implement from ICT teaching materials

---

## 4. Other Notable ICT Indicators Found

### 4.1 Displacement by wilsonne14

**URL:** https://www.tradingview.com/script/5gzGR0Kh-Displacement/  
**Source Availability:** ❌ "Publication not found" (may be deleted or private)  
**From Search Description:**
- Detects "true price displacement" (momentum-driven moves beyond recent volatility)
- Body size exceeds multiple of ATR
- High close percentage, clear directional conviction
- Filters out indecisive or wick-heavy candles
- Open-source, customizable (ATR length, multiplier, min body %)
- Best on M5, M15, H1 during London/NY sessions

**Could not access:** Link returns 404 error.

### 4.2 TehThomas Displacement Candles

**URL:** https://www.tradingview.com/script/1rld7nWE-TehThomas-Displacement-Candles/  
**Source Availability:** ✅ OPEN SOURCE (but not fetched in this research)  
**From Search Description:**
- Identifies significant price movements by comparing current vs previous closing prices
- Calculates percentage changes
- Highlights bullish/bearish displacements based on user-defined threshold
- Does NOT directly use ATR multipliers (simpler % change approach)
- Customizable threshold, colors
- Useful for trend detection, volatility analysis

**Note:** This appears to be a **simpler percentage-based approach** rather than ATR+body ratio like FibAlgo or a8ra.

### 4.3 Displacement [QuantVue]

**URL:** https://www.tradingview.com/script/RUIo4bYt-Displacement-QuantVue/  
**Source Availability:** ✅ OPEN SOURCE (but not fetched in this research)  
**From Search Description:**
- Detects forceful price movements signaling trend shifts
- Combines candlestick analysis with ATR
- Focuses on large bodies + short wicks
- Confirmation through consecutive bullish/bearish candles
- Filters minor fluctuations using ATR-based volatility analysis
- Marks confirmed displacements with triangles

**Logic similarity to a8ra:** HIGH (ATR + body emphasis + consecutive confirmation)

---

## 5. General ICT Displacement Concepts (From Various Sources)

### Common Detection Criteria

From educational sources (Aron Groups, Inner Circle Trader Blog, ICT Trader):

1. **Body Size:**
   - Typically 60-70% of total candle range
   - FibAlgo default: 65%
   - a8ra_v1: 60%

2. **ATR Multiplier:**
   - Range: 1.25 to 2.0+
   - FibAlgo default: 1.5× ATR(14)
   - a8ra_v1: 1.5× (VALID), 2.0× (STRONG), 1.25× (WEAK)

3. **Consecutive Candles:**
   - 2-3+ consecutive displacement candles = stronger signal
   - FibAlgo: Streak tracking with alerts at 3+
   - a8ra_v1: Cluster-2 detection

4. **Minimal Wicks:**
   - High body-to-range ratio ensures minimal wicks
   - Indicates strong directional commitment
   - Filters out indecision

5. **Fair Value Gap Creation:**
   - Displacement often creates FVGs (3-candle gap pattern)
   - FibAlgo tags displacement FVGs separately
   - a8ra_v1 tags FVG creation but doesn't display boxes

### ICT Teaching Context

From sources referencing Michael Huddleston (ICT):
- Displacement is the "engine" behind institutional price delivery
- Validates Order Blocks
- Confirms Market Structure Shifts
- Creates Fair Value Gaps
- Typically seen during killzone sessions (London open, NY open)

---

## 6. GrandAlgo CHoCH/BOS Research

**Search Query:** GrandAlgo CHoCH BOS indicator TradingView source code  

### Findings:

No specific **"GrandAlgo"** branded indicator found. Search returned various CHoCH/BOS indicators:

1. **KeyAlgos BOS/CHoCH:**
   - https://www.tradingview.com/script/n2fKj3HU-Break-of-Structure-Change-of-Char...
   - Open source
   - Detects pivot highs/lows
   - Marks structural breaks (BOS) and counter-trend breaks (CHoCH)
   - Two-stage pivot detection with confirmation

2. **HH HL LH LL + BOS / CHoCH (kulangaa):**
   - https://es.tradingview.com/script/qT8NmovQ-HH-HL-LH-LL-BOS-CHoCH/
   - Open source
   - Labels HH, HL, LH, LL
   - Optional ATR-based adaptive swing lengths
   - BOS detection on pivot breaks
   - CHoCH as trend reversal signals

3. **UAlgo Internal/External Market Structure:**
   - https://www.tradingview.com/script/GHORKVuy-Internal-External-Market-Structur...
   - Open source
   - Internal (short-term) and external (long-term) structures
   - ChoCH (reversal) and BoS (continuation) labeling
   - Solid lines for internal, dashed for external

4. **LuxAlgo Market Structure CHoCH/BOS (Fractal):**
   - https://www.tradingview.com/script/ZpHqSrBK-Market-Structure-CHoCH-BOS-Fracta...
   - Open source
   - Uses fractal patterns instead of traditional swing points
   - More adaptive to market dynamics
   - Support/resistance levels from structures
   - Dashboard showing bullish/bearish fractal % breakdown

### No "GrandAlgo" Brand Found

**Conclusion:** "GrandAlgo" may be:
- A typo or misremembered name
- A private/paid indicator not published
- A discontinued indicator

**Available alternatives:** Multiple open-source BOS/CHoCH indicators exist (KeyAlgos, UAlgo, LuxAlgo Fractal version).

---

## 7. Summary & Recommendations

### Source Code Availability Matrix

| Indicator | Source Available | Quality | Complexity |
|-----------|-----------------|---------|------------|
| FibAlgo ICT Displacement | ❌ Protected | High | Hard |
| LuxAlgo SMC | ✅ Open (GitHub) | Very High | Medium |
| TradingFinder ICT | ❌ Paid/Closed | Unknown | Hard/Impossible |
| QuantVue Displacement | ✅ Open (TV) | Medium | Medium |
| TehThomas Displacement | ✅ Open (TV) | Low | Easy |
| KeyAlgos BOS/CHoCH | ✅ Open (TV) | Medium | Medium |

### Transpilation Recommendations

#### Priority 1: **None for Pure Displacement**

**Reasoning:**
- a8ra_v1 displacement is already **more sophisticated** than available open-source alternatives
- FibAlgo (the most feature-rich) is closed-source
- Other open-source displacement indicators are **simpler** than a8ra_v1

**What a8ra_v1 does better:**
- Close gate (directional confirmation)
- Decisive override (extreme candle handling)
- Cluster-2 detection (adjacent displacement bars)
- Quality grading system (STRONG/VALID/WEAK)
- Per-timeframe parameter overrides

**What external indicators do better (visualization):**
- FibAlgo: Glow effects, measurement labels, streak tracking, statistics dashboard
- Could inform **validation mode enhancements** (better visualization)

#### Priority 2: **LuxAlgo SMC Modules (For Future a8ra Primitives)**

If expanding a8ra beyond displacement, consider porting these LuxAlgo SMC modules:

1. **Order Blocks Detection & Filtering** (Medium complexity)
   - ATR-based filtering logic
   - Mitigation tracking
   - Useful for a future Order Block primitive

2. **BOS/CHoCH Market Structure** (Medium complexity)
   - Internal and swing structure breaks
   - Could inform Market Structure Shift primitive

3. **EQH/EQL Detection** (Easy-Medium complexity)
   - Equal highs/lows algorithm
   - Threshold-based matching
   - Useful for liquidity analysis

**Estimated Lines of PineScript per module:**
- Order Blocks: ~400 lines
- BOS/CHoCH: ~500 lines
- EQH/EQL: ~200 lines

#### Priority 3: **Skip Standalone Displacement Ports**

**Do NOT port:**
- TehThomas Displacement (too simple, percentage-based only)
- QuantVue Displacement (similar to a8ra but less sophisticated)
- TradingFinder (closed source, not worth $50 for reverse-engineering)

### Variant Recommendations for Porting

Given the research findings, **there is no superior open-source displacement variant to port**.

**Instead, recommend:**

1. **Enhance a8ra_v1 displacement visualization** (learning from FibAlgo):
   - Add streak detection (consecutive displacement count)
   - Add measurement labels (body size in ticks + body % of range)
   - Add statistics dashboard (total count, bull/bear ratio, avg body size)
   - Add displacement-specific FVG boxes (like FibAlgo)

2. **Consider LuxAlgo SMC modules for new primitives:**
   - Port Order Blocks as "a8ra_v2_order_blocks"
   - Port BOS/CHoCH as "a8ra_v2_market_structure"
   - Port EQH/EQL as "a8ra_v2_equal_levels"

3. **Build from ICT teaching materials directly:**
   - For concepts not well-represented in open-source indicators
   - Example: Breaker Blocks, Liquidity Sweeps, Optimal Trade Entry (OTE)

### Complexity Estimates

**If porting visualization enhancements to a8ra_v1 displacement:**
- Streak detection: **Easy** (1-2 hours)
- Measurement labels: **Easy** (2-3 hours for HTML output)
- Statistics dashboard: **Medium** (4-6 hours for HTML output)
- Displacement FVG boxes: **Medium** (8-12 hours, requires FVG detection + rendering)

**If porting LuxAlgo SMC modules:**
- Order Blocks: **Medium** (40-60 hours end-to-end with validation)
- BOS/CHoCH: **Medium** (50-70 hours end-to-end with validation)
- EQH/EQL: **Easy-Medium** (20-30 hours end-to-end with validation)

---

## 8. Key Takeaways

### What We Learned

1. **a8ra_v1 displacement is already competitive:**
   - More sophisticated logic than most open-source alternatives
   - Close gate, decisive override, cluster detection are unique
   - Quality grading system is a differentiator

2. **FibAlgo is the gold standard (but closed):**
   - Best visualization and UX
   - Streak tracking is novel
   - Statistics dashboard is useful
   - Cannot access source code

3. **LuxAlgo SMC is best open-source resource:**
   - Comprehensive suite of ICT concepts
   - Well-documented PineScript v5
   - Modular design allows selective porting
   - Not a displacement-focused tool

4. **No "GrandAlgo" found:**
   - Likely a misremembered name or private indicator
   - Many BOS/CHoCH alternatives exist (KeyAlgos, UAlgo, LuxAlgo)

5. **TradingFinder is a commercial platform:**
   - $50+ pricing for most tools
   - Primarily MT4/MT5 focused
   - Not worth purchasing for research purposes

### Next Steps

**For displacement variant porting:**
- ❌ **Do NOT port** any external displacement indicator (a8ra is already superior)
- ✅ **Consider enhancing** a8ra_v1 visualization with FibAlgo-inspired features
- ✅ **Document** a8ra_v1's unique features vs market (close gate, decisive override, cluster-2, quality grades)

**For new primitives:**
- ✅ **Consider LuxAlgo SMC** modules for Order Blocks, BOS/CHoCH, EQH/EQL
- ✅ **Use ICT teaching materials** for concepts not well-represented in open source
- ✅ **Maintain a8ra's philosophy:** sophisticated logic > flashy visualization

**For validation mode:**
- ✅ **Learn from FibAlgo UX:** measurement labels, statistics dashboard, glow effects
- ✅ **Prioritize clarity:** make displacement detection logic visually obvious
- ✅ **Add metrics:** streak detection, body size stats, quality grade distribution

---

## Appendices

### Appendix A: a8ra_v1 Displacement Logic (For Comparison)

```python
# Core detection (simplified)
atr_multiplier = 1.5  # locked
body_ratio_threshold = 0.6  # locked
close_gate = 0.25  # directional confirmation
decisive_override = {"body_min": 0.75, "close_max": 0.1}  # extreme candles

# Detection steps:
1. Calculate body_pct = body / candle_range
2. Calculate atr_ratio = candle_range / atr
3. Check AND gate: body_pct >= 0.6 AND atr_ratio >= 1.5
4. Check close_gate: close near high (bull) or low (bear) within 0.25
5. Check decisive_override: body >= 0.75 AND close_max <= 0.1 bypasses gates
6. Assign quality grade:
   - STRONG: atr_ratio >= 2.0
   - VALID: atr_ratio >= 1.5
   - WEAK: atr_ratio >= 1.25
7. Check cluster-2: adjacent displacement bars in same direction
8. Tag FVG creation (if displacement creates 3-candle gap)
9. Apply per-TF overrides (LTF vs HTF parameter adjustments)
```

### Appendix B: FibAlgo Detection Logic (Reconstructed from Description)

```pinescript
// Simplified reconstruction (not actual source code)
atr_length = input(14)
atr_multiplier = input(1.5)
body_range_ratio = input(0.65)
detection_method = input("ATR Multiple") // or "Body/Range Ratio" or "Both (AND)"

atr = ta.atr(atr_length)
body = math.abs(close - open)
candle_range = high - low
body_pct = body / candle_range

is_doji = (close == open)

if detection_method == "ATR Multiple":
    is_displacement = body > (atr * atr_multiplier) and not is_doji
else if detection_method == "Body/Range Ratio":
    is_displacement = body_pct >= body_range_ratio and not is_doji
else if detection_method == "Both (AND)":
    is_displacement = (body > (atr * atr_multiplier)) and (body_pct >= body_range_ratio) and not is_doji

// Streak tracking
var streak_count = 0
var prev_direction = 0
current_direction = close > open ? 1 : -1

if is_displacement:
    if current_direction == prev_direction:
        streak_count += 1
    else:
        streak_count = 1
    prev_direction = current_direction
else:
    streak_count = 0
    
if streak_count >= 3:
    alert("Displacement Streak 3+")

// FVG detection (3-candle pattern)
bullish_fvg = is_displacement[1] and (low > high[2])
bearish_fvg = is_displacement[1] and (high < low[2])

// Statistics (lookback loop, not shown)
```

### Appendix C: LuxAlgo SMC Swings & OB Logic (Excerpts)

```pinescript
// Swing detection (50-bar default)
swings(len)=>
    var os = 0
    upper = ta.highest(len)
    lower = ta.lowest(len)
    os := high[len] > upper ? 0 : low[len] < lower ? 1 : os[1]
    top = os == 0 and os[1] != 0 ? high[len] : 0
    btm = os == 1 and os[1] != 1 ? low[len] : 0
    [top, btm]

// Order block filtering
atr = ta.atr(200)
cmean_range = ta.cum(high - low) / bar_index
ob_threshold = (ob_filter == 'Atr') ? atr : cmean_range

// Search for highest/lowest candle within structure break interval
// that has candle_range < ob_threshold * 2
for i = 1 to (bar_index - structure_break_location) - 1:
    if (high[i] - low[i]) < ob_threshold[i] * 2:
        // Candidate for order block
        // Track: top, bottom, left, right, type, mitigation status
```

---

**End of Research Report**
