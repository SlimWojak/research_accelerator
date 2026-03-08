# RG-5: Displacement Threshold Research
## ATR Multiplier × Body Ratio Grid for FVG Quality Filtering

**Purpose:** Provide Opus with the theoretical framework and empirical parameters for displacement-based FVG filtering.  
**Date:** 2026-03-04  
**Status:** Theoretical framework complete. Empirical 4×4 grid BLOCKED — requires EURUSD 1m CSV data (7,177 bars, 2024-01-07 to 2024-01-12) not currently in workspace. Grid spec is ready to execute.

---

## 1. What is Displacement in ICT Context?

Displacement refers to aggressive, directional price movement — typically one or more large-bodied candles that indicate institutional order flow. In ICT methodology, displacement is the mechanism that creates FVGs: the middle candle of the 3-bar pattern should ideally be a "displacement candle" to indicate genuine institutional activity.

**Canonical ICT definition** (from [ICT video transcripts](https://www.youtube.com/watch?v=0e1Wk2kTZeM)):
- "Strong break with clear displacement, meaning one or more large candles closing decisively past the swing point"
- "Displacement often leaves behind fair value gaps"
- A weak break (small candle barely closing past) is NOT displacement

---

## 2. Two Dimensions of Displacement

All reviewed implementations decompose displacement into two independent dimensions:

### Dimension 1: Body-to-Range Ratio (BRR)
**What it measures:** How much of the candle's total range (high-low) is body (|close-open|).

```
BRR = abs(close - open) / (high - low)
```

| BRR Value | Candle Character | Notes |
|-----------|-----------------|-------|
| < 0.30 | Doji / indecision | Not displacement |
| 0.30–0.50 | Moderate wicks | Possible but weak |
| 0.50–0.65 | Strong body, some wicks | Moderate displacement |
| 0.65–0.80 | Dominant body | **ICT standard: "institutional candle"** |
| > 0.80 | Near-full body (marubozu) | Very strong displacement |

**Source:** [FibAlgo ICT Displacement indicator](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/):
> "Institutional Candle — A candle whose body is at least 60–70% of the total candle range (high to low). This body-to-range ratio threshold separates candles with strong directional commitment from those with large wicks (indecision)."

Default in FibAlgo: **0.65** (65%), configurable 0.30–0.95.

### Dimension 2: ATR Multiplier (AM)
**What it measures:** Whether the candle's body is unusually large relative to recent volatility.

```
AM_condition = abs(close - open) > ATR(n) × multiplier
```

| ATR Mult | Meaning | Notes |
|----------|---------|-------|
| 0.5× | Half of average range | Very permissive |
| 1.0× | Body equals full ATR | Moderate: candle body = average range |
| 1.5× | Body 50% larger than average range | **FibAlgo default** |
| 2.0× | Body twice the average range | Aggressive filtering |
| 3.0× | Body triple the average range | Very rare events only |

**Source:** [FibAlgo ICT Displacement](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/):
> "ATR Multiple: Candle body must exceed ATR(14) × multiplier (default multiplier: 1.5). Adapts to current market volatility."

Default: ATR(14) × **1.5**, configurable 0.5–5.0.

### Combined Mode
FibAlgo offers three detection modes:
- **ATR Multiple only** — candle body > ATR × mult
- **Body/Range Ratio only** — body/range > threshold
- **Both (AND)** — must pass BOTH filters simultaneously (strictest)

---

## 3. How Displacement Relates to FVG Quality

The displacement check applies to the **middle candle (candle B)** of the 3-bar FVG pattern:
- Candle A: the "before" candle
- Candle B: the impulse/displacement candle (the one that creates the gap)
- Candle C: the "after" candle

**From [FibAlgo ICT Fair Value Gaps](https://www.tradingview.com/script/SoBOPZzT-FibAlgo-ICT-Fair-Value-Gaps/):**
> "Optional ATR filter that requires the middle candle's body to exceed ATR. Ensures only displacement-grade imbalances qualify."
> "Min Gap Size parameter: Minimum gap size (in ticks) to remove tiny noise gaps."

**From [ICT Gems video](https://www.youtube.com/watch?v=xzrLRyXHsjw):**
> ICT explicitly states not all FVGs are tradable. He uses displacement, dealing ranges, and quadrant levels to grade FVGs.

---

## 4. The ForexGuy Empirical Study (Body Size vs ATR)

The most rigorous public study on body-to-ATR ratios and candle follow-through was conducted by [TheForexGuy](https://www.theforexguy.com/forex-candlestick-patterns-strategy/). Key findings:

### Raw Results (no additional filters)
- **Body < 50% ATR:** Near-random directional prediction (~50% win rate)
- **Body 50–85% ATR:** Slight directional edge (52–55% win rate) but poor risk-reward
- **Body 85–120% ATR:** Clear edge identified ("profitability threshold" zone)
- **Body > 130% ATR:** Fewer opportunities, win rate peaks but sample size drops
- **Body > 160% ATR:** Only viable at 15m and above with additional filters

### With Swing Filter (bodies + swing significance ≥ 3)
- 10–20% performance boost across most body size ranges
- Profitability threshold met more consistently

### Time Frame Effects
- 15m: Minimum body 160% ATR needed to approach break-even
- 4H–6H: Only negligible improvements below 135% ATR
- Daily: Best edge at 85–120% ATR range
- **Implication for 5m:** Even more noise than 15m; expect minimum 120–160% ATR body threshold

### Key Quote
> "One correlation visible here is that the success chance increases as the body size of the candle gets higher."

---

## 5. v0.5 Current State

The v0.5 spec has `displacement_present` as a boolean tag on FVG objects (line ~144) but does NOT define the threshold for what constitutes "displacement." The gap analysis (RESEARCH_VS_V05_GAP_ANALYSIS.md) flagged this as a high-priority gap.

Current v0.5 displacement-related fields:
```yaml
# From FVG L1_detection:
displacement_present: bool  # candle B body/range check (threshold TBD)

# From constants (NOT defined):
# No ATR_MULT or BODY_RATIO constants exist yet
```

---

## 6. Proposed 4×4 Threshold Grid (Empirical — REQUIRES DATA)

### Grid Design

The grid tests 4 ATR multiplier values × 4 body ratio values on the EURUSD 1m dataset (7,177 bars). For each combination, we count how many FVGs pass the filter.

**ATR Multiplier values:** [0.5, 1.0, 1.5, 2.0]  
**Body Ratio values:** [0.50, 0.60, 0.70, 0.80]

### Expected Output Table

```
                  BRR=0.50  BRR=0.60  BRR=0.65  BRR=0.70  BRR=0.80
AM=0.5 (lax)     [count]   [count]   [count]   [count]   [count]
AM=1.0 (mod)     [count]   [count]   [count]   [count]   [count]  
AM=1.5 (std)     [count]   [count]   [count]   [count]   [count]
AM=2.0 (strict)  [count]   [count]   [count]   [count]   [count]

Each cell = number of FVGs on 5m bars where candle B passes both filters
```

### Grid Execution Script (Ready to Run)

```python
#!/usr/bin/env python3
"""
RG-5: Displacement threshold grid for FVG quality filtering.
Requires: EURUSD 1m CSV with columns [time, open, high, low, close, volume]
"""
import pandas as pd
import numpy as np

# ── Configuration ──
CSV_PATH = "/home/user/workspace/eurusd_1m_2024-01-07_to_2024-01-12.csv"
ATR_PERIOD = 14
TF_MINUTES = 5  # Resample to 5m bars

# Grid axes
ATR_MULTS = [0.5, 1.0, 1.5, 2.0]
BODY_RATIOS = [0.50, 0.60, 0.65, 0.70, 0.80]
MIN_GAP_PIPS = 0.5  # 0.5 pip = 0.00005 for EURUSD (matching v0.5 floor)
PIP = 0.0001

def load_and_resample(path, tf_min):
    df = pd.read_csv(path, parse_dates=['time'])
    df.set_index('time', inplace=True)
    ohlc = df.resample(f'{tf_min}min').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna()
    return ohlc

def compute_atr(df, period=14):
    tr = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    return tr.rolling(window=period).mean()

def detect_fvgs_with_grid(df, atr_series, atr_mults, body_ratios, min_gap_pips, pip):
    """
    Detect 5m FVGs and test each ATR_MULT × BODY_RATIO combination.
    Returns a dict of {(am, brr): count} and raw FVG list.
    """
    results = {(am, brr): 0 for am in atr_mults for brr in body_ratios}
    total_fvgs = 0
    min_gap = min_gap_pips * pip
    
    for i in range(2, len(df)):
        bar_a = df.iloc[i-2]  # Candle A (oldest)
        bar_b = df.iloc[i-1]  # Candle B (middle — displacement candle)
        bar_c = df.iloc[i]    # Candle C (newest)
        
        # Check for bullish FVG: C.low > A.high
        is_bull = bar_c['low'] > bar_a['high']
        gap_bull = bar_c['low'] - bar_a['high'] if is_bull else 0
        
        # Check for bearish FVG: C.high < A.low  
        is_bear = bar_c['high'] < bar_a['low']
        gap_bear = bar_a['low'] - bar_c['high'] if is_bear else 0
        
        if not (is_bull or is_bear):
            continue
        
        gap_size = gap_bull if is_bull else gap_bear
        if gap_size < min_gap:
            continue
        
        total_fvgs += 1
        
        # Compute candle B metrics
        body_b = abs(bar_b['close'] - bar_b['open'])
        range_b = bar_b['high'] - bar_b['low']
        brr_b = body_b / range_b if range_b > 0 else 0
        atr_val = atr_series.iloc[i-1] if not pd.isna(atr_series.iloc[i-1]) else None
        
        for am in atr_mults:
            for brr in body_ratios:
                passes_brr = brr_b >= brr
                passes_atr = (body_b >= atr_val * am) if atr_val else False
                if passes_brr and passes_atr:
                    results[(am, brr)] += 1
    
    return results, total_fvgs

# ── Main ──
if __name__ == "__main__":
    print("Loading and resampling data...")
    df = load_and_resample(CSV_PATH, TF_MINUTES)
    print(f"Resampled to {len(df)} bars at {TF_MINUTES}m")
    
    atr = compute_atr(df, ATR_PERIOD)
    
    print("Running grid...")
    grid, total = detect_fvgs_with_grid(df, atr, ATR_MULTS, BODY_RATIOS, MIN_GAP_PIPS, PIP)
    
    print(f"\nTotal FVGs (>= {MIN_GAP_PIPS} pip floor): {total}")
    print(f"Trading days in sample: ~5")
    print(f"FVGs per day: ~{total / 5:.1f}")
    print()
    
    # Print grid
    header = f"{'AM \\ BRR':>12}" + "".join(f"  BRR={brr:.2f}" for brr in BODY_RATIOS)
    print(header)
    print("-" * len(header))
    
    for am in ATR_MULTS:
        row = f"  AM={am:.1f}    "
        for brr in BODY_RATIOS:
            count = grid[(am, brr)]
            pct = (count / total * 100) if total > 0 else 0
            row += f"  {count:>4} ({pct:4.1f}%)"
        print(row)
    
    # Also print per-day rates
    print(f"\n── Per-Day Rates (÷ 5 days) ──")
    header2 = f"{'AM \\ BRR':>12}" + "".join(f"  BRR={brr:.2f}" for brr in BODY_RATIOS)
    print(header2)
    print("-" * len(header2))
    for am in ATR_MULTS:
        row = f"  AM={am:.1f}    "
        for brr in BODY_RATIOS:
            count = grid[(am, brr)]
            per_day = count / 5
            row += f"  {per_day:>8.1f}"
        print(row)
```

### News Contamination Filter (Extension)

The grid should also be run WITH a news-time exclusion filter. High-impact news events (NFP, FOMC, CPI) create extreme displacement candles that are outliers — they inflate counts at the high-AM end of the grid.

**Proposed news windows to exclude:**
```python
NEWS_EXCLUSION_WINDOWS = [
    # Date, Start (NY), End (NY), Event
    ("2024-01-10", "08:20", "08:45", "CPI Release"),
    ("2024-01-11", "08:20", "08:45", "PPI Release"),
    ("2024-01-12", "08:20", "08:45", "Import/Export Prices"),
    # NFP was Jan 5 (not in our window)
]
```

---

## 7. Theoretical Expectations (Before Empirical Run)

Based on the FibAlgo defaults, ForexGuy study, and v0.5 calibration context:

### Expected Sweet Spot
- **ATR Mult: 1.0–1.5** — body equals or exceeds average range; filters dojis and ranging candles
- **Body Ratio: 0.60–0.70** — ICT's "institutional candle" definition
- **Combined (AND):** The FibAlgo default of AM=1.5 + BRR=0.65 is a strong starting point

### Expected FVG Survival Rates (estimates for 5m EURUSD)
- **No displacement filter:** ~345 FVGs / week (from v0.5 calibration data: 5m, 0.5 pip floor)
- **AM=1.5 + BRR=0.65:** ~30–60% survival → ~100–210 FVGs / week → ~20–42 per day
- **AM=2.0 + BRR=0.70:** ~10–20% survival → ~35–70 FVGs / week → ~7–14 per day
- **AM=2.0 + BRR=0.80:** ~5–10% survival → ~17–35 FVGs / week → ~3–7 per day (likely too strict)

### Recommended Default for v0.5
```yaml
displacement:
  method: "BOTH"  # AND mode — candle B must pass both filters
  atr_period: 14
  atr_multiplier: 1.0  # Conservative start — body >= 1× ATR
  body_ratio: 0.60     # ICT minimum for "institutional candle"
  note: "Empirical calibration pending — run grid on EURUSD data to validate"
```

---

## 8. Relationship to v0.5 `displacement_present` Tag

The v0.5 spec has `displacement_present: bool` as a tag on each FVG. This tag should be populated using the displacement detection logic above:

```python
# For each FVG's candle B:
body_b = abs(candle_b.close - candle_b.open)
range_b = candle_b.high - candle_b.low
brr_b = body_b / range_b if range_b > 0 else 0
atr_val = atr[candle_b.index]

fvg.displacement_present = (
    brr_b >= constants.DISPLACEMENT_BODY_RATIO and
    body_b >= atr_val * constants.DISPLACEMENT_ATR_MULT
)
```

**Critical note:** `displacement_present` is a QUALITY TAG, not a detection gate. All FVGs that pass the 0.5-pip floor are detected. The `displacement_present` tag adds confluence weight. Whether it gates detection or just adds weight is an L2 decision.

---

## 9. Sources

| Source | URL | Relevance |
|--------|-----|-----------|
| FibAlgo ICT Displacement indicator | https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/ | Primary: dual ATR + BRR detection, default thresholds |
| FibAlgo ICT Fair Value Gaps indicator | https://www.tradingview.com/script/SoBOPZzT-FibAlgo-ICT-Fair-Value-Gaps/ | ATR filter for FVGs, min gap size, IFVG + BPR detection |
| TheForexGuy body-vs-ATR study | https://www.theforexguy.com/forex-candlestick-patterns-strategy/ | Empirical body-to-ATR analysis across multiple timeframes |
| ICT Displacement YouTube | https://www.youtube.com/watch?v=0e1Wk2kTZeM | Canonical displacement definition |
| ICT Gems: A+ FVG Selection | https://www.youtube.com/watch?v=xzrLRyXHsjw | ICT's FVG grading criteria using displacement |
| LuxAlgo IFVG + ATR multiplier | https://www.youtube.com/watch?v=TD2SJCBze6c | ATR multiplier in IFVG context |
| Candle Body Percentage (TradingView) | https://www.tradingview.com/script/fpnIQpqO-Candle-Body-Percentage-Indicator/ | BRR calculation reference |
