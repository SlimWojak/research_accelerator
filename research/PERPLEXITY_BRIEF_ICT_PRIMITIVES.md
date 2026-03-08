# PERPLEXITY COMPUTER BRIEF — ICT PRIMITIVES CODIFICATION

**"From intuition to algorithm. From ambiguity to precision."**

```yaml
PROJECT: ICT_PRIMITIVES_CODIFICATION
SCOPE: 6 Tier 1 (full treatment) + 6 Tier 2 (research only)
OUTPUT: Test Vectors + Visual Bible + One-Pagers + Algorithms + v0.5 Format Proposal
INSTRUMENT: EURUSD
BASE_DATA: 1-minute OHLCV candlesticks
```

---

## MISSION

We need deterministic, reproducible primitive detectors for EURUSD 1m OHLCV data (higher timeframes aggregated on-the-fly from 1m).

Our v0.4 methodology correctly encodes strategy hierarchy, but primitive definitions were underspecified — leading to inconsistent swing/FVG placement and VI flooding. The code faithfully executes the spec; the spec is the gap.

| Primitive | Detection Result | Issue |
|---|---|---|
| Session Boundaries | CORRECT | Times and DST accurate |
| Previous Day High/Low | CORRECT | 17:00 NY boundary, wick measurement |
| Asia Range | CORRECT | 19:00-00:00 NY, 30 pip threshold |
| Swing Points (HH/HL/LH/LL) | INCONSISTENT | Some real swings missed, some false |
| Fair Value Gap (FVG) | PARTIALLY CORRECT | Boundaries sometimes wrong, gaps misplaced |
| Volume Imbalance (VI) | FLOODING | Far too many detections |

**Your job:** Research how existing open-source algo trading systems codify these ICT primitives. Consolidate the best implementations into replayable visual examples, executable specs, and test vectors. Produce output that a human trader validates by looking at it, and a machine executes deterministically.

---

## EVIDENCE DISCIPLINE

Every primitive definition must include **at least 2 independent open references** (indicator repo, PineScript library, QuantConnect implementation, academic paper, or reputable quant blog).

Constrained sources:
- **TradingView PineScript indicators** — widely-used ICT detection scripts (link each)
- **GitHub repositories** — QuantConnect, Backtrader, pandas-based ICT implementations
- **Academic/quant literature** — for generic primitives (fractals, pivots, BOS/MSS)

**Rules:**
- Every claim about "standard practice" must cite a source link + code snippet reference
- If no consensus exists on a definition, label it explicitly as **VARIANT** and list all variants with tradeoffs
- Do not present guesses as standards
- Do not invent novel approaches — research what EXISTS in production

---

## DELIVERABLES

### Deliverable 0: Test Vector Pack (JSON)

For each Tier 1 primitive, produce 10–30 minimal OHLC sequences (50–300 bars each):

```yaml
format:
  input: Array of {timestamp, open, high, low, close, volume}
  expected: Array of {timestamp, type, direction, price_high, price_low, metadata}
  category: textbook | edge_case | false_positive | false_negative

per_primitive:
  - 5+ textbook examples (unambiguous, clean detection)
  - 3+ edge cases (boundary conditions, minimum gap, equal highs)
  - 3+ false positives (looks like it but is NOT — explain WHY)
  - 3+ false negatives (what naive algos miss — explain WHY)
```

This is the most important deliverable. It plugs directly into our 493-test automated suite.

---

### Deliverable 1: Visual Bible (Interactive HTML)

Per Tier 1 primitive, produce a standalone HTML page containing:

**A. Visual Reference Charts** — Annotated candlestick examples showing EXACTLY what the primitive looks like. Use realistic EURUSD data at 1m, 5m, 15m. Show: textbook example, edge case, false positive, missed detection. Annotate with arrows, boxes, labels, color coding. A trader should understand in 3 seconds.

Charts must be **replayable** — embed the OHLC sample data (inline JSON) so we can re-render and verify independently.

**B. Plain-English Logic** — Candle-by-candle walkthrough using precise terms:
- **wick** = high/low
- **body** = open/close
- **body_top** = max(open, close)
- **body_bottom** = min(open, close)

Specify EXACTLY which price points define boundaries. No ambiguity.

**C. Algorithmic Specification** — Pseudocode AND Python. Every comparison explicit:
`candle_A.high < candle_C.low` not "there is a gap."

**D. Parameter Guide** — Standard values, sensitivity analysis, recommended defaults for EURUSD 1m.

**E. Variant Matrix** — Per primitive:

| Variant | Source (link) | What it changes | Pros | Cons | Recommended? |
|---|---|---|---|---|---|

This gives us a controlled choice surface instead of "one true algorithm."

**F. Common Pitfalls** — Data source differences (Dukascopy, IBKR, FXCM), tick aggregation artifacts, sub-pip gaps, minimum thresholds used in production.

---

### Deliverable 2: One-Pager Per Primitive

```yaml
PRIMITIVE: [Name]
ALSO_KNOWN_AS: [Alternative names in ICT and broader trading]
CATEGORY: [Market Structure | Session Reference | Liquidity | Imbalance]
WHAT_IT_IS: [2-3 sentences plain English]
WHAT_IT_IS_NOT: [Common confusions]
DETECTION_RULE: [Exact algorithmic rule in one sentence]
CANDLE_LOGIC: [Which candles, which price points, which comparisons]
PARAMETERS: [name: default_value (range)]
MINIMUM_VIABLE_DETECTION: [Simplest correct algorithm]
TIMEFRAMES: [Where it applies, how multi-TF works]
DATA_REQUIREMENTS: [OHLCV? Volume needed? Tick data?]
SANITY_BAND:
  per_day_median: [expected count on EURUSD 1m]
  per_day_5th_95th: [range]
  flooding_signal: "If >N detections/day, likely cause is X"
KNOWN_ISSUES: [What breaks automated detection]
```

---

### Deliverable 3: Production-Grade Python Per Primitive

- Standalone function per primitive
- Input: OHLCV array (list of dicts or numpy structured array)
- Output: detections with metadata (timestamp, direction, price bounds, confidence tags)
- Deterministic — same input = same output
- Handles edge cases: market gaps, zero-volume bars, DST transitions, session boundaries
- Docstring with plain-English logic
- Inline comments explaining every comparison
- No dependencies beyond numpy
- Tested against test vectors from Deliverable 0

---

### Deliverable 4: v0.5 Methodology Format Proposal

Our v0.4 mixes strategy with primitives — that is the root cause of our detection issues. Propose a v0.5 format with clean separation:

**Layer 1 — Primitive Definitions** (what the system detects):
- Each primitive self-contained
- Detection algorithm with parameters and defaults
- Expected detection density per timeframe (sanity bands)
- Visual reference pointer
- This layer is **industry-standard building blocks** — borrowed, not invented

**Layer 2 — Strategic Logic** (how the trader uses primitives):
- Which primitives gate which decisions
- Hierarchy and combination rules (e.g., FVG + Sweep + MSS = engine event)
- This is the **strategist's unique edge** — not in scope for this research

**Layer 3 — Execution Rules** (how trades are managed):
- Entry types, position sizing, stop placement, exits
- Also strategist-specific — not in scope

Include a **template using FVG** as the worked example showing the new format.

---

## TIER 1 PRIMITIVES — Full Treatment (All 5 Deliverables)

### 1. Fair Value Gap (FVG)

**Current v0.4 definition:** "Three-candle imbalance (wick-to-wick). Candle A wick high < Candle C wick low (bullish) or Candle A wick low > Candle C wick high (bearish)."

**Strategist feedback on our detection:**
> "Sometimes picks up the top correctly but cuts it randomly"
> "Sometimes places gaps next to candle on empty space, not over the candle"

**Strategist verbal description:** "3 candle formation, number 2 candle is where the gap sits. Bearish example: First candle is a run of some kind of old high. First candle high, second candle is an extended low that goes below it. Third candle, another continuation candle that does not trade back into candle number one low. It means price is only being offered on the sell side."

**Research must resolve:**
- Candle indexing convention (A/B/C = first/middle/last) — confirm standard
- Zone bounds: exactly which highs/lows define top and bottom of the gap
- Where candle B fits — does the gap exist "in B's space" (visual) or is B uninvolved in boundary definition?
- Wick-to-wick always, or body-to-body variant when?
- Minimum gap size (pips) — default + rationale. Is 0.1 pip noise?
- Merge/overlap rules: two adjacent gaps become one zone? Yes/no?
- Invalidation rules: what constitutes "filled"?
- Zone respect rule from v0.4: "Candle BODIES must stay inside zone — wicks can breach it"

---

### 2. Swing Point Detection (HH / HL / LH / LL)

**Current detection:** `high[i] > max(high[i-N:i]) AND high[i] > max(high[i+1:i+N+1])` for swing HIGH. Inverted for LOW. Classification by comparing to previous swing of same polarity. N=5.

**Strategist:** "Some work, some don't — not all picked up consistently"

**Research must resolve:**
- Swing detection model comparison for EURUSD 1m — which is most stable:
  - Fractal/pivot (N-bar extremum) — our current approach
  - Zigzag (threshold-based)
  - ATR-scaled swing significance
- Is N=5 standard for 1m forex? Recommended N per timeframe?
- Equal highs/lows handling (within X pips = equal?)
- Noise filtering: 0.5 pip oscillation is not a real swing on 1m
- Robust HH/HL/LH/LL classification algorithm
- Multi-timeframe swing detection mechanics

**v0.4 context:** `order_flow_read = "HH+HL = bullish, LH+LL = bearish, mixed = no trade"`. Stop placement: "Beyond the swing that provided liquidity, usually 8-12 pips."

---

### 3. Volume Imbalance (VI)

**Current v0.4:** "Three-candle imbalance (body-to-body). Candle A body top < Candle C body bottom (bullish) or Candle A body bottom > Candle C body top (bearish). Wicks may overlap."

**Strategist feedback:**
> "Spewing examples all over the chart"
> "Added in v0.4 because in Interactive Brokers she occasionally sees body-to-body gaps"
> "Surprised Dukascopy finds so many — those IB gaps don't show on these charts"
> **Currently recommends REMOVING**

**Research must resolve:**
- Is VI a standard ICT primitive or a niche/derived concept?
- Difference from FVG in standard ICT teaching — are they distinct or is VI a sub-case?
- Under what **market microstructure conditions** do true body gaps exist on EURUSD 1m?
- How should we filter gaps at illiquid boundaries (session open, Sunday open, roll)?
- Is this broker-dependent? (Tick aggregation differences: Dukascopy vs IBKR vs FXCM)
- Minimum body gap size for meaningful detection on EURUSD 1m
- Do production algo systems detect VI separately from FVG?
- **Recommendation needed:** Keep as separate primitive, merge into FVG with variant flag, or remove?

---

### 4. Session Boundaries (WORKING — validate)

Asia 19:00-00:00 NY, LOKZ 02:00-05:00 NY, NYOKZ 07:00-10:00 NY. Kill zone reversals: London 03:00-04:00, NY 08:00-09:00. Day boundary 17:00 NY. Midnight open 00:00 NY. Always NY time (EST/EDT).

**Research:** Do these match standard ICT teaching? Variant definitions in the community? How do production forex algo systems define session boundaries?

---

### 5. Previous Day High / Low (WORKING — validate)

Boundary: 17:00 NY (NOT midnight). Measurement: Wicks (NOT closes).

**Research:** Universal forex convention or ICT-specific? DST edge cases? Holidays/half-days?

---

### 6. Asia Range (WORKING — validate)

Window: 19:00-00:00 NY. Threshold: ≤30 pips for valid range.

**Research:** Standard ICT definition? Standard threshold? Variant thresholds in the community? Production implementations?

---

## TIER 2 PRIMITIVES — Research Only (No Code)

Per primitive provide: standard definition, detection logic, relation to Tier 1, variant matrix, complexity assessment (simple / moderate / requires ML), deterministic detectability assessment.

| # | Primitive | Key Research Question |
|---|---|---|
| 7 | **Market Structure Shift (MSS) / Break of Structure (BOS)** | How do production systems distinguish BOS vs MSS? Is displacement quantifiable or inherently subjective? Can MSS be detected deterministically on 1m OHLCV? |
| 8 | **Optimal Trade Entry (OTE)** | Fibonacci 61.8%-79% retracement of dealing range. Standard algo implementation? How to define expansion swing points programmatically? |
| 9 | **Liquidity Sweep / Judas Swing** | Price breaches liquidity pool and returns. How to distinguish sweep from breakout algorithmically? Max extent before it becomes trend? |
| 10 | **Displacement** | Can displacement be quantified (pip-per-bar velocity, consecutive directional bars)? Academic research on impulsive vs corrective moves? |
| 11 | **Order Block (OB)** | Last opposing candle before displacement. How to distinguish from random consolidation candles? Mark bodies only, NOT wicks. Quality criteria? |
| 12 | **Market Maker Model (MMXM)** | Is this a meta-pattern (combination of primitives) or its own primitive? Algorithmic detectability? |

---

## DATA QA REQUIREMENTS

Define preprocessing needed before detection. Research must address:

- Handling duplicate timestamps
- Missing minutes (gaps in 1m data)
- Sunday open / Friday close handling
- DST conversion strategy (source timestamps → NY time)
- Pip precision rules (5-digit brokers)
- Zero-volume bars (we have 66 in our EURUSD field — tag but don't discard)
- Output must be invariant to harmless float noise (define rounding policy)

---

## CONSTRAINTS — ABSOLUTE

| Constraint | Detail |
|---|---|
| **FOREX FOCUS** | EURUSD. Other pairs only if directly relevant to a definition. |
| **1-MINUTE BASE DATA** | Higher TFs (5m, 15m, 1H, 4H, Daily) aggregated from 1m on-the-fly. Algorithms must work on 1m bars. |
| **ALL TIMES NY TIMEZONE** | EST UTC-5 winter, EDT UTC-4 summer. Non-negotiable. |
| **NO PROPRIETARY INDICATORS** | Open, documented methods only. |
| **DETERMINISTIC** | Same input = same output. No randomness, no ML, no LLM. |
| **VISUAL OUTPUT PRIMARY** | Strategist validates by LOOKING at charts. 3-second recognition. |
| **DO NOT INVENT** | Research what EXISTS in production algo trading. Precise engineering, not novel approaches. |
| **SEPARATE PRIMITIVE FROM STRATEGY** | "What is an FVG" SEPARATE from "when to trade an FVG." Primitives are building blocks. How they combine is our strategist's edge — NOT in scope. |
| **CITE EVERYTHING** | No unsourced claims about "standard." Link or label as variant. |

---

## SANITY BANDS

For each Tier 1 primitive, provide expected detection density on EURUSD 1m:

```yaml
format:
  per_day_median: [count]
  per_day_5th_95th_percentile: [low, high]
  flooding_signal: "If >N detections/day, likely indicates [cause]"
  starvation_signal: "If <N detections/day, likely indicates [cause]"
```

This is critical. Our VI detector returned ~1,000/day. If the standard expectation is ~10/day, that immediately confirms a definition mismatch.

---

## OUTPUT FORMAT

| Deliverable | Format | Notes |
|---|---|---|
| D0: Test Vectors | JSON | Directly consumed by pytest. Most important deliverable. |
| D1: Visual Bible | Interactive HTML | Chart.js or Plotly. Embedded OHLC data for replay. Standalone in browser. |
| D2: One-Pagers | Markdown | One file per primitive. |
| D3: Python Algos | .py files | Standalone, numpy-only, documented. |
| D4: v0.5 Proposal | Markdown + YAML template | Worked example using FVG. |

---

## QUALITY BAR

- Strategist opens Visual Bible FVG page → says "YES, that is exactly what I look for" in under 10 seconds
- Developer runs Python on 1m EURUSD data → gets same detections strategist sees on TradingView
- Test vectors produce PASS/FAIL results when plugged into our detection code
- One-pager understood by new team member in 2 minutes
- Sanity bands match what we observe on our 1.9M bar EURUSD field
- v0.5 format makes us say "why didn't we structure it this way from the start"

---

```yaml
PROJECT: ICT_PRIMITIVES_CODIFICATION
TAGLINE: "From intuition to algorithm. From ambiguity to precision."
SCOPE: 6 Tier 1 (full treatment) + 6 Tier 2 (research only)
DELIVERABLES: Test Vectors + Visual Bible + One-Pagers + Algorithms + v0.5 Format
RUNTIME: Overnight — use the time. Be thorough. Be precise. Be visual.
```
