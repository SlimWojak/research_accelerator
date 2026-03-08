# ICT Primitives Research Pack — Phase 1 Synthesis
## a8ra Algo Trading System | EURUSD 1-Minute

**Version:** 1.0 — Master Synthesis  
**Date:** 2026-03-03  
**Prepared for:** Craig (Sovereign Operator) · Olya (ICT Strategist)  
**Status:** Phase 1 Research Complete — Ready for Joint Review

---

# 1. EXECUTIVE SUMMARY

## What Was Researched

12 ICT primitives were investigated across 5 parallel research streams, covering canonical ICT definitions, TradingView PineScript implementations (20+ scripts surveyed), GitHub repositories (8+), community consensus, and academic/quantitative parallels. Every claim in this document is sourced.

## Data Used

- **7,177 bars** of EURUSD 1m OHLCV data (2024-01-07 22:04 UTC to 2024-01-12 21:59 UTC)
- 5 complete forex days (Mon–Fri), January EST (UTC-5), no DST
- Forex day boundary: 17:00 NY = 22:00 UTC
- All three kill zone sessions fully covered (~99.7% of theoretical bars)

## Key Findings

1. **FVG has 2 rendering bugs** (off-by-one boundary + zone anchor time), but the detection condition itself (`low[C] > high[A]`) is **correct and universally agreed** across all 8+ implementations surveyed. Fixes are straightforward. ([research_fvg_vi.md](research_fvg_vi.md))

2. **Volume Imbalance must be REMOVED.** ICT's VI is a 2-candle body-gap concept; v0.4 uses a non-standard 3-candle definition. Empirically, VI floods at **765 detections/day** (median) — 1.9–3.1× worse than FVG at every threshold. No production algo system found treating VI as a standalone primitive. ([research_fvg_vi.md](research_fvg_vi.md), [sanity_band_results.md](sanity_band_results.md))

3. **Session boundaries (Asia, LOKZ, NYOKZ), PDH/PDL, Midnight Open, and Day Boundary are ALL CONFIRMED correct** against primary ICT sources and 5 TradingView indicator implementations. ([research_sessions_pdh_asia.md](research_sessions_pdh_asia.md))

4. **Swing Points N=5 is correct in concept but 3 bugs cause inconsistent detection:** strict `>` silently drops equal highs, no minimum size filter allows sub-pip noise through, and no session noise filter lets Asian session noise contaminate HH/HL classification. Empirically, N=5 unfiltered produces **148 swings/day** — flooding. With a 2–3 pip filter, this drops to 15–30/day (usable). ([research_swing_points.md](research_swing_points.md), [sanity_band_results.md](sanity_band_results.md))

5. **Asia Range 30-pip threshold is a VARIANT** — no published ICT standard exists. Empirical data shows **0/5 days exceeded 30 pips** (median 12.7 pips). A system using this threshold would have been inactive all week. Needs Olya's input. ([research_sessions_pdh_asia.md](research_sessions_pdh_asia.md), [sanity_band_results.md](sanity_band_results.md))

6. **Tier 2 primitives (MSS, BOS, OTE, Displacement, OB, Sweep) are all PARTIALLY deterministic** — core detection logic can be coded, but each requires threshold parameters with no canonical values. Best community defaults: ATR 1.5× + body/range 65% for displacement; close-beyond (not wick) for MSS/BOS. ([research_tier2_primitives.md](research_tier2_primitives.md))

7. **MMXM is NOT a primitive — it is a retrospective meta-pattern** composed of all other primitives. Real-time phase classification is not possible. Build last, use only for retrospective labeling. ([research_tier2_primitives.md](research_tier2_primitives.md))

8. **The 2-pip FVG threshold is the empirically validated sweet spot** for EURUSD 1m: produces ~15 FVGs/day (median), with stable day-to-day variance [11–27]. ([sanity_band_results.md](sanity_band_results.md))

## Critical Action Items

| Priority | Action | Why |
|----------|--------|-----|
| **P0** | Fix FVG zone boundary (off-by-one) | Zones render on wrong candle |
| **P0** | Fix FVG zone anchor time (use candle A time) | Zones float in empty space |
| **P0** | Remove VI as standalone primitive | 765/day flooding; non-standard definition |
| **P1** | Add `>=` on left side for swing equal highs | Silent swing drops; most likely cause of "some work, some don't" |
| **P1** | Add 2–3 pip minimum swing height filter | 148 swings/day without filter → 15–30 with |
| **P1** | Add 2-pip minimum FVG gap filter | 400/day without filter → ~15/day with |
| **P2** | Revisit Asia Range 30-pip threshold with Olya | 0/5 days triggered — too restrictive for quiet weeks |
| **P2** | Resolve NY reversal window (08:00–09:00 vs Silver Bullet 10:00–11:00) | Current window doesn't match canonical Silver Bullet |

---

# 2. v0.4 DIAGNOSIS — What's Broken and What Works

| # | Primitive | v0.4 Status | Bug / Issue | Fix Required | Priority |
|---|-----------|-------------|-------------|--------------|----------|
| 1 | **FVG** | BUGGY | (a) Off-by-one in zone boundary price — uses `high[1]` instead of `high[2]` for bottom ([research_fvg_vi.md §10](research_fvg_vi.md)); (b) Zone anchor time set to candle C's time instead of candle A's — box floats in empty space | Fix boundary to `high[i-2]`/`low[i]`; anchor box at candle A time (`bar_index - 2`) | **P0** |
| 2 | **Volume Imbalance** | REMOVE | ICT's VI is 2-candle body-gap; v0.4 uses non-standard 3-candle. Floods at 765/day median on EURUSD 1m. No production system uses VI standalone. ([research_fvg_vi.md §6–7](research_fvg_vi.md)) | Remove from detector; optionally retain as FVG zone-extension only | **P0** |
| 3 | **Swing Points** | BUGGY | (a) Strict `>` drops equal highs silently ([research_swing_points.md §10](research_swing_points.md)); (b) No min height filter → 148 swings/day; (c) Asian session noise contaminates HH/HL | (a) `>=` on left side; (b) Add 2–3 pip min height; (c) Session noise filter | **P1** |
| 4 | **Session: Asia** | CONFIRMED | Window 19:00–00:00 NY matches primary ICT source ([innercircletrader.net](https://innercircletrader.net/tutorials/ict-asian-range/)) | None | — |
| 5 | **Session: LOKZ** | CONFIRMED | 02:00–05:00 NY — universal consensus across all 5 TradingView implementations ([research_sessions_pdh_asia.md §1.3B](research_sessions_pdh_asia.md)) | None | — |
| 6 | **Session: NYOKZ** | CONFIRMED | 07:00–10:00 NY — standard. 08:00–11:00 exists as extended variant. ([research_sessions_pdh_asia.md §1.3C](research_sessions_pdh_asia.md)) | None | — |
| 7 | **PDH/PDL** | CONFIRMED | 17:00 NY boundary + wicks — universal forex standard ([OANDA](https://www.oanda.com/bvi-en/cfds/hours-of-operation/), [Dukascopy](https://www.dukascopy.com/swiss/english/fx-market-tools/forex-market-hours/)) | None | — |
| 8 | **Asia Range** | VARIANT | Window CONFIRMED (19:00–00:00 NY). 30-pip threshold is VARIANT — no published ICT standard; 0/5 days exceeded 30 pips in sample. ([research_sessions_pdh_asia.md §3.2](research_sessions_pdh_asia.md)) | Revisit threshold with Olya; consider 15–20 pips | **P2** |
| 9 | **Midnight Open** | CONFIRMED | 00:00 NY open price — well-documented ICT concept ([edgeful.com](https://www.edgeful.com/blog/posts/ICT-trading-strategy-midnight-open-retracement-report)) | None | — |
| 10 | **MSS/BOS** | NOT YET BUILT | Moderate complexity, partially deterministic. Close-beyond required; displacement for MSS. ([research_tier2_primitives.md §1](research_tier2_primitives.md)) | Build after swing fix | **P2** |
| 11 | **OTE** | NOT YET BUILT | Moderate — Fibonacci 62%/70.5%/79%. Anchor swing selection is the hard part. ([research_tier2_primitives.md §2](research_tier2_primitives.md)) | Build after BOS | **P3** |
| 12 | **Liquidity Sweep / Judas** | NOT YET BUILT | Wick-beyond + close-back-inside. 30–40 pip limit is VARIANT. ([research_tier2_primitives.md §3](research_tier2_primitives.md)) | Build after session levels stable | **P3** |
| 13 | **Displacement** | NOT YET BUILT | No canonical thresholds. Best: ATR 1.5× + body/range 65%. ([research_tier2_primitives.md §4](research_tier2_primitives.md)) | Build first among Tier 2 | **P2** |
| 14 | **Order Block** | NOT YET BUILT | Last opposing candle before displacement. Body-only zone, mean threshold 50%. ([research_tier2_primitives.md §5](research_tier2_primitives.md)) | Build after displacement | **P3** |
| 15 | **MMXM** | NOT A PRIMITIVE | Meta-pattern. Retrospective labeling problem. Requires all other Tier 2 primitives. ([research_tier2_primitives.md §6](research_tier2_primitives.md)) | Build last; retrospective only | **P4** |

---

# 3. ONE-PAGERS

---

## 3.1 Fair Value Gap (FVG)

**Definition:** A three-candle price imbalance where the wick extremes of candle A (oldest) and candle C (newest) do not overlap, leaving a gap of one-sided liquidity in the range that candle B (the impulse) traveled through. ICT calls bullish FVGs "BISI" (Buyside Imbalance Sellside Inefficiency) and bearish FVGs "SIBI." ([ICT Mentorship Core Content via Scribd](https://www.scribd.com/document/751178990/ICT-Fair-Value-Gap-FVG-ICT-Mentorship-Core-Co), [innercircletrader.net](https://innercircletrader.net/tutorials/fair-value-gap-trading-strategy/))

**v0.4 Assessment:** BUGGY — Detection condition correct, 2 rendering bugs (zone boundary + anchor time)

**Detection Logic:**
```
Bullish FVG:  low[C] > high[A]          → Zone: bottom=high[A], top=low[C]
Bearish FVG:  high[C] < low[A]          → Zone: bottom=high[C], top=low[A]
Anchor box at candle A's timestamp, extend rightward until invalidated.
Invalidation: body close through outer boundary (ICT: through CE midpoint).
```

**Variant Matrix:**

| Variant | Filter | Used By | Pros | Cons |
|---------|--------|---------|------|------|
| Standard wick-to-wick | None | All canonical sources | Faithful to ICT | Floods on 1m (~400/day) |
| + Candle B close filter | `close[B] > high[A]` | [LuxAlgo (413k+ favorites)](https://www.tradingview.com/script/jWY4Uiez-Fair-Value-Gap-LuxAlgo/) | Higher quality | May miss valid gaps |
| + Body multiplier | `body[B] > 1.5× avg_body` | [CodeTrading Python](https://www.youtube.com/watch?v=cjDgibEkJ_M) | Adaptive to volatility | Requires lookback param |
| + ATR impulse filter | `range[B] >= 1.1× ATR` | [NinjaTrader ICTFVG](https://github.com/tickets2themoon/ICTFVG) | Structural confirmation | ATR period sensitivity |
| + Minimum pip size | `gap >= N pips` | Most production systems | Simple, effective | Static threshold |

**Sanity Band (EURUSD 1m empirical, [sanity_band_results.md](sanity_band_results.md)):**

| Threshold | Median/Day | Assessment |
|-----------|-----------|------------|
| Any gap | 400 | 🔴 FLOODING |
| ≥ 0.5 pip | 177 | 🔴 FLOODING |
| ≥ 1 pip | 75 | 🟡 HIGH |
| **≥ 2 pips** | **15** | **🟢 USABLE** |
| ≥ 5 pips | 0 | 🔵 STARVATION |

**Key Implementation Note:** The zone box must be **anchored at candle A's time** (not candle C's). The [NinjaTrader ICTFVG source](https://gist.github.com/silvinob/3335e76266449a26f3c7b5890a6ecd44) confirms: `gapStartTime = Times[iDataSeries][2]` (candle A).

**Recommendation:** Fix the 2 rendering bugs. Add ≥ 2-pip minimum gap filter. Optionally add candle B close filter (LuxAlgo approach) for higher precision. Target: ~15 FVGs/day.

---

## 3.2 Volume Imbalance (VI)

**Definition:** ICT's Volume Imbalance is a **2-candle** pattern where consecutive candle bodies do not overlap (wicks may intersect). ICT: *"A volume imbalance occurs... that up close candle — the very next candle that opens higher than the previous candle's close."* ([OpoFinance](https://blog.opofinance.com/en/ict-volume-imbalance/), [ICT YouTube lecture](https://www.youtube.com/watch?v=URcDVLVRH1c))

**v0.4 Assessment:** REMOVE — Uses non-standard 3-candle body-to-body definition. Floods at 765/day.

**Detection Logic (v0.4 — incorrect):**
```
Bullish VI (v0.4): body_top[A] < body_bottom[C]    ← 3-candle, NOT ICT standard
ICT actual:        body_top[0] < body_bottom[1]     ← 2-candle consecutive
```

**Variant Matrix:**

| Definition | Candles | Source | Detections/Day (1m) |
|-----------|---------|--------|-------------------|
| v0.4 (3-candle body) | 3 | Non-standard | 765 (median) |
| ICT standard (2-candle body) | 2 | [ICT YouTube](https://www.youtube.com/watch?v=URcDVLVRH1c) | 400–900 (worse) |
| FVG zone extension | 2 (within FVG) | [TradingView 1st P. FVG+VI](https://www.tradingview.com/script/vOFYxaN9-ICT-First-Presented-FVG-with-Volume-Imbalance-1st-P-FVG-VI/) | N/A (modifier) |

**Sanity Band (EURUSD 1m empirical, [sanity_band_results.md](sanity_band_results.md)):**

| Threshold | VI Median/Day | FVG Median/Day | VI÷FVG Ratio |
|-----------|-------------|---------------|-------------|
| Any gap | 765 | 400 | 1.91× |
| ≥ 1 pip | 177 | 75 | 2.36× |
| ≥ 2 pips | 47 | 15 | 3.13× |

**Key Implementation Note:** VI is fundamentally unsuited to unfiltered 1m detection. Bodies are tiny (0.5–2.5 pips average), making body-gaps near-universal in any trending sequence.

**Recommendation:** REMOVE as standalone primitive. The only production script integrating VI ([1st P. FVG+VI by flasi](https://www.tradingview.com/script/vOFYxaN9-ICT-First-Presented-FVG-with-Volume-Imbalance-1st-P-FVG-VI/)) uses it to *extend FVG boundaries*, not as standalone signals. Retain as optional zone-extension only if needed.

---

## 3.3 Swing Points

**Definition:** A swing high at bar `i` exists when bar `i`'s high is the maximum over a symmetric 2N+1 bar window — equivalent to TradingView's `ta.pivothigh(high, N, N)`. Swing lows are the symmetric minimum. ([TradingView Market Structure script](https://www.tradingview.com/script/3qHfkvHG-Market-Structure-HH-HL-LH-LL-with-Trendlines-Alerts/), [StackOverflow Python pivot](https://stackoverflow.com/questions/64019553/how-pivothigh-and-pivotlow-function-work-on-tradingview-pinescript))

**v0.4 Assessment:** BUGGY — N=5 correct in principle; 3 bugs cause inconsistency

**Detection Logic (corrected):**
```
Swing High: high[i] >= max(high[i-N:i])    # >= on left (allows equal highs)
        AND high[i] >  max(high[i+1:i+N+1]) # strict > on right
        AND height >= max(min_pips, ATR * factor)  # size filter

Swing Low:  low[i]  <= min(low[i-N:i])     # <= on left
        AND low[i]  <  min(low[i+1:i+N+1])  # strict < on right
        AND depth >= max(min_pips, ATR * factor)
```

**Variant Matrix:**

| Method | Mechanism | Repaints? | Suited to 1m Live? | Sources |
|--------|-----------|-----------|-------------------|---------|
| Fractal/N-bar (current) | Symmetric window, N-bar lag | No | Yes (with filters) | [TradingView](https://www.tradingview.com/script/3qHfkvHG-Market-Structure-HH-HL-LH-LL-with-Trendlines-Alerts/), [StackOverflow](https://stackoverflow.com/questions/64019553/how-pivothigh-and-pivotlow-function-work-on-tradingview-pinescript) |
| Zigzag (threshold) | Min reversal (5–10 pips) | **YES** | No (repaints) | [forex-connect GitHub](https://github.com/gehtsoft/forex-connect/blob/master/samples/Python/Indicators.py) |
| ATR-scaled fractal | N-bar + min size in ATR units | No | **Best** | [MQL5 ATR article](https://www.mql5.com/en/articles/21443) |

**Sanity Band (EURUSD 1m empirical, [sanity_band_results.md](sanity_band_results.md)):**

| N | Median Swings/Day | Assessment |
|---|------------------|------------|
| 3 | 242 | 🔴 FLOODING |
| **5 (current)** | **148** | **🔴 FLOODING (unfiltered)** |
| 10 | 77 | 🟡 HIGH |
| 15 | 51 | 🟢 USABLE |
| 20 | 39 | 🟢 USABLE |

With 2–3 pip height filter applied to N=5: estimated **15–30/day** (🟢 USABLE). ([research_swing_points.md §9.2](research_swing_points.md))

**Key Implementation Note:** The `>=` on the left side (allowing equal values) is how TradingView's `ta.pivothigh` handles ties — the leftmost bar in a tie wins. This is the single most likely fix for "some swings work, some don't." ([research_swing_points.md §10](research_swing_points.md))

**Recommendation:** Keep N=5, add `>=` on left side, add 2.5-pip minimum height (or 0.8× ATR adaptive), add 1.5-pip equal-high tolerance for EQH/EQL labeling, add session noise filter for Asian session.

---

## 3.4 Session Boundaries (Asia, LOKZ, NYOKZ)

**Definition:** ICT-defined time windows in New York local time where institutional algorithmic activity is concentrated. ICT anchors all session times to NY local time regardless of DST. ([innercircletrader.net Kill Zones](https://innercircletrader.net/tutorials/master-ict-kill-zones/))

**v0.4 Assessment:** ALL CONFIRMED

**Detection Logic:**
```
is_asia(ny_hour):  19 <= ny_hour < 24       # 19:00–00:00 NY
is_lokz(ny_hour):   2 <= ny_hour < 5        # 02:00–05:00 NY
is_nyokz(ny_hour):  7 <= ny_hour < 10       # 07:00–10:00 NY
Convert UTC→NY via America/New_York timezone (handles DST automatically)
```

**Variant Matrix:**

| Session | v0.4 | Variant 1 | Variant 2 | Sources |
|---------|------|-----------|-----------|---------|
| Asia Range | 19:00–00:00 | 20:00–00:00 | 19:00–22:00 (KZ only) | [innercircletrader.net](https://innercircletrader.net/tutorials/ict-asian-range/), [ICT YouTube 2017](https://www.youtube.com/watch?v=JA0mLNJeytY) |
| LOKZ | 02:00–05:00 | 01:00–05:00 (older ICT) | 03:00–05:00 | [ICT Kill Zone PDF](https://innercircletrader.net/wp-content/uploads/2023/12/ICT-Kill-Zone-PDF.pdf) |
| NYOKZ | 07:00–10:00 | 08:00–11:00 | 07:00–09:00 | [innercircletrader.net](https://innercircletrader.net/tutorials/master-ict-kill-zones/) |
| London Reversal | 03:00–04:00 | — | — | = [ICT Silver Bullet](https://innercircletrader.net/tutorials/ict-silver-bullet-strategy/) ✓ |
| NY Reversal | 08:00–09:00 | **10:00–11:00 (Silver Bullet)** | 08:50–09:10 (Macro) | **v0.4 ≠ canonical Silver Bullet** |

**Sanity Band:** All sessions fully covered in empirical data — 299–300 Asia bars, 180 LOKZ bars, 180 NYOKZ bars per day ([sanity_band_results.md §4](sanity_band_results.md)).

**Key Implementation Note:** During the 2–3 week US/EU DST mismatch (March: US springs forward before EU; October: EU falls back before US), London open shifts by 1 hour in NY terms. Use `America/New_York` timezone — never hardcode UTC offsets. ([research_sessions_pdh_asia.md §4](research_sessions_pdh_asia.md))

**Recommendation:** Sessions are correct. The NY reversal window (08:00–09:00) needs Olya's input — it does not match the canonical NY AM Silver Bullet (10:00–11:00).

---

## 3.5 PDH/PDL (Previous Day High/Low)

**Definition:** The highest wick high and lowest wick low of the previous forex trading day, bounded by the 17:00 NY daily candle close. ([capital.com](https://capital.com/en-au/analysis/day-traders-toolbox-previous-days-high-and-low-pdh-pdl), [Daily Price Action](https://dailypriceaction.com/blog/new-york-close-charts-forex-market/))

**v0.4 Assessment:** CONFIRMED — 17:00 NY boundary, wick-based measurement

**Detection Logic:**
```
forex_day_start = 17:00 NY (America/New_York)
PDH = max(high) for all bars in previous forex day
PDL = min(low) for all bars in previous forex day
```

**Variant Matrix:** No variants found. Universal standard across all brokers ([OANDA](https://www.oanda.com/bvi-en/cfds/hours-of-operation/), [Dukascopy](https://www.dukascopy.com/swiss/english/fx-market-tools/forex-market-hours/), [Daily Price Action](https://dailypriceaction.com/blog/new-york-close-charts-forex-market/)).

**Sanity Band (EURUSD 1m empirical):** PDH–PDL range: median 58 pips, range [50–70 pips] — normal for EURUSD. ([sanity_band_results.md §6](sanity_band_results.md))

| Condition | Daily Range | Action |
|-----------|------------|--------|
| Holiday/suspect | < 30 pips | Flag |
| Normal | 30–100 pips | OK |
| Elevated | 100–150 pips | OK (news days) |
| Extreme | > 150 pips | Flag |

**Key Implementation Note:** Convert all UTC timestamps using `America/New_York` timezone to correctly handle EST/EDT transitions. The 17:00 boundary shifts between 21:00 UTC (summer) and 22:00 UTC (winter).

**Recommendation:** No changes needed. Consider adding a holiday calendar to flag anomalous PDH/PDL days (Christmas Eve, Thanksgiving Friday).

---

## 3.6 Asia Range

**Definition:** The high-to-low price range during the Asian session (19:00–00:00 NY). A tight consolidation within this range signals an impending shift to a trending algorithm during London. ([innercircletrader.net](https://innercircletrader.net/tutorials/ict-asian-range/), [ICT YouTube 2017](https://www.youtube.com/watch?v=JA0mLNJeytY))

**v0.4 Assessment:** Window CONFIRMED; 30-pip threshold is VARIANT

**Detection Logic:**
```
asia_high = max(high) for bars in [19:00, 00:00) NY
asia_low  = min(low)  for bars in [19:00, 00:00) NY
asia_range = asia_high - asia_low
is_tight = asia_range <= threshold
```

**Variant Matrix:**

| Parameter | v0.4 | ICT Teaching | Empirical Data |
|-----------|------|-------------|---------------|
| Window | 19:00–00:00 NY ✓ | 19:00–00:00 ([innercircletrader.net](https://innercircletrader.net/tutorials/ict-asian-range/)) | 299–300 bars/session |
| Threshold | 30 pips | "Narrow consolidated range" — no specific pips ([ICT YouTube 2017](https://www.youtube.com/watch?v=JA0mLNJeytY)) | Median 12.7 pips, max 22.4 pips (0/5 > 30) |
| ICT's own range comments | — | "Ranging could go from 10 to 20 pips. Trending could go from 20 to 30 pips." ([YouTube 2024](https://www.youtube.com/watch?v=GfxScm82JHM)) | — |

**Sanity Band (EURUSD 1m empirical, [sanity_band_results.md §5](sanity_band_results.md)):**

| Day | Asia Range (pips) |
|-----|------------------|
| 2024-01-08 | 22.4 |
| 2024-01-09 | 17.0 |
| 2024-01-10 | 10.3 |
| 2024-01-11 | 11.7 |
| 2024-01-12 | 12.7 |
| **Median** | **12.7** |

**Key Implementation Note:** The 30-pip threshold fired 0/5 days in the sample week. ICT's own words suggest "ranging = 10–20 pips, trending = 20–30 pips" — a 20-pip threshold better separates these regimes.

**Recommendation:** Lower threshold to 15–20 pips (Olya's call). Alternatively, use an ATR-relative threshold (e.g., 30–40% of trailing ADR). The 30-pip value may be appropriate for volatile regimes but starves the system during quiet weeks.

---

## 3.7 Midnight Open

**Definition:** The opening price of the 00:00 NY candle — a key intraday reference level in ICT's model. ICT calls it "the beginning of the true day." Price retraces to the midnight open 58–69% of the time during the NY session. ([edgeful.com study](https://www.edgeful.com/blog/posts/ICT-trading-strategy-midnight-open-retracement-report), [TradingView indicator](https://www.tradingview.com/script/y5sLA4Ls-ICT-New-York-NY-Midnight-Open-and-Divider/))

**v0.4 Assessment:** CONFIRMED

**Detection Logic:**
```
midnight_open = open price of bar at 00:00 NY (America/New_York)
```

**Variant Matrix:** No variants. Universal definition.

**Sanity Band:** Exactly 1 level per day. Static reference.

**Key Implementation Note:** The midnight open is an *intraday reference level*, not a day boundary. The forex day boundary is 17:00 NY. These are distinct concepts.

**Recommendation:** No changes needed.

---

## 3.8 MSS / BOS (Market Structure Shift / Break of Structure)

**Definition:** **BOS** = price closes beyond a swing high (bullish) or swing low (bearish) in the **direction** of the prevailing trend (continuation). **MSS** = price closes beyond a swing point **against** the trend (reversal signal). MSS requires displacement; BOS prefers it. ([Equiti Guide](https://www.equiti.com/sc-en/news/trading-ideas/mss-vs-bos-the-ultimate-guide-to-mastering-market-structure/), [LuxAlgo MSS](https://www.luxalgo.com/blog/market-structure-shifts-mss-in-ict-trading/), [innercircletrader.net BOS](https://innercircletrader.net/tutorials/break-of-structure-bos/))

**v0.4 Assessment:** NOT YET BUILT — Moderate complexity, partially deterministic

**Detection Logic:**
```
Track trend_direction (BULL/BEAR) and last swing high (pH), last swing low (pL).

Bullish BOS:  trend == BULL AND close > pH.price → continuation
Bearish MSS:  trend == BULL AND close < pL.price → reversal, flip to BEAR
Bullish MSS:  trend == BEAR AND close > pH.price → reversal, flip to BULL
Bearish BOS:  trend == BEAR AND close < pL.price → continuation

MSS quality filter: require displacement (ATR 1.5× + body/range 65%)
Break trigger: CLOSE beyond swing (not wick). "A wick break is not enough."
```
Source: [Strike Money BOS](https://www.strike.money/technical-analysis/break-of-structure), [ICT Breakers PineScript on Scribd](https://www.scribd.com/document/902397983/Explanation-of-Pine-Script-Code)

**Variant Matrix:**

| Source | Break Trigger | Displacement Required? | Internal vs External |
|--------|-------------|----------------------|---------------------|
| ICT (original) | Close beyond | Yes (for MSS) | MSS = internal; BOS = external |
| [PineScript ICTProTools](https://www.scribd.com/document/902397983/Explanation-of-Pine-Script-Code) | Configurable (body/wick) | Optional | Single-level |
| [Strike Money](https://www.strike.money/technical-analysis/break-of-structure) | Close beyond | Strong momentum | Close decisive |
| [tsunafire GitHub SMC](https://github.com/tsunafire/PineScript-SMC-Strategy) | Close beyond | Implied | Structural shifts |

**Sanity Band:** Dependent on swing N and displacement thresholds. Expected: 3–8 BOS/MSS per session during trending periods.

**Key Implementation Note:** MSS/BOS directly require swing point detection. Without fixed Tier 1 swings, MSS/BOS cannot be computed. The same price break can be BOS by one system and MSS by another depending on higher-timeframe context.

**Recommendation:** Build after swing point fix is validated. Use close-beyond (body) as break trigger. Require displacement for MSS only.

---

## 3.9 OTE (Optimal Trade Entry)

**Definition:** A Fibonacci retracement zone (62%–79% of a confirmed structural swing) where institutional participants re-enter during pullbacks. The 70.5% level is ICT's "sweet spot" — unique to ICT, not found in standard Fibonacci theory. ([GrandAlgo](https://grandalgo.com/blog/ict-optimal-trade-entry-ote), [innercircletrader.net OTE](https://innercircletrader.net/tutorials/ict-optimal-trade-entry-ote-pattern/), [TradingFinder](https://tradingfinder.com/education/forex/ict-optimal-trade-entry-pattern/))

**v0.4 Assessment:** NOT YET BUILT — Moderate complexity

**Detection Logic:**
```
After BOS confirmed from swing_low to swing_high:
  range = swing_high - swing_low
  ote_62  = swing_high - (range * 0.62)    # Upper boundary
  ote_705 = swing_high - (range * 0.705)   # Sweet spot
  ote_79  = swing_high - (range * 0.79)    # Lower boundary

Entry: price enters [ote_79, ote_62] + confluence with FVG/OB in zone
Invalidation: close below swing_low (bullish) / above swing_high (bearish)
```

**Variant Matrix:**

| Source | Lower | Sweet Spot | Upper | Notes |
|--------|-------|-----------|-------|-------|
| ICT Standard | 62% | **70.5%** | 79% | ICT-specific levels |
| [TradingView Script (yLKbFuXN)](https://www.tradingview.com/script/yLKbFuXN-OTE-optimal-trade-entry-ICT-visible-chart-only-Dynamic/) | 61.8% | — | 78.6% | Standard Fibonacci |
| [GrandAlgo](https://grandalgo.com/blog/ict-optimal-trade-entry-ote) | 62% | 70.5% | 79% | BOS + OB confluence |

**Sanity Band:** OTE is a zone, not a detection. Activates 1–3× per trading session after BOS events.

**Key Implementation Note:** The hard part is **anchor swing selection** — which swing do you draw the Fibonacci on? Multiple candidates exist simultaneously. Systems typically use the swing that caused the most recent BOS.

**Recommendation:** Build after BOS implementation. Use ICT levels (62%, 70.5%, 79%). Require BOS preceding the swing. Gate to kill zone hours.

---

## 3.10 Liquidity Sweep / Judas Swing

**Definition:** **Liquidity Sweep:** Price probes beyond a significant high or low (stop-loss cluster) then returns inside the range. **Judas Swing:** A time-specific sweep between midnight and 05:00 NY that sets the day's false extreme before the main directional move. ([innercircletrader.net Judas Swing](https://innercircletrader.net/tutorials/ict-judas-swing-complete-guide/), [innercircletrader.net Sweep vs Run](https://innercircletrader.net/tutorials/ict-liquidity-sweep-vs-liquidity-run/))

**v0.4 Assessment:** NOT YET BUILT — Moderate complexity

**Detection Logic:**
```
# SWEEP
for each key_level (equal H/L, session H/L, PDH/PDL):
  if high > level AND close < level → BEARISH SWEEP
  if low  < level AND close > level → BULLISH SWEEP

# JUDAS SWING (time-filtered sweep)
if 0 <= ny_hour < 5:
  if low < asian_low AND close > midnight_open → BULLISH JUDAS
  if high > asian_high AND close < midnight_open → BEARISH JUDAS
```

**Variant Matrix:**

| Feature | v0.4 Rule | Community Consensus | Sources |
|---------|-----------|-------------------|---------|
| Pip limit | 30–40 pips | No fixed limit; ATR-relative or context-based | [Zeiierman](https://www.zeiierman.com/blog/liquidity-sweeps-in-trading/), [Phidias](https://phidiaspropfirm.com/education/liquidity-sweep) |
| Return window | Not specified | 1–5 bars | [Phidias](https://phidiaspropfirm.com/education/liquidity-sweep): 1–4 candles |
| Volume filter | Not specified | ≥ 1.5× 20-bar avg | [Zeiierman](https://www.zeiierman.com/blog/liquidity-sweeps-in-trading/), [TradingView ICT Concepts](https://fr.tradingview.com/script/KL0iqOX2-ICT-Concepts-Liquidity-FVG-Liquidity-Sweeps/) |
| Judas window | 00:00–05:00 NY | 00:00–05:00 NY | [innercircletrader.net](https://innercircletrader.net/tutorials/ict-judas-swing-complete-guide/) |

**Sanity Band:** Expected: 1–3 sweeps per key session (LOKZ, NYOKZ) on active days. Dependent on number of tracked levels.

**Key Implementation Note:** Sweep vs. BOS is only distinguishable **in retrospect** — the same candle that probes beyond a level could be either. The close-back-inside criterion is the only real-time differentiator.

**Recommendation:** Build after session levels and equal H/L detection are stable. Use ATR-relative thresholds instead of fixed 30–40 pip limit (Olya's call).

---

## 3.11 Displacement

**Definition:** An aggressive, rapid, one-directional price move characterized by large candle bodies, structure removal (BOS/MSS), and FVG creation. ICT's qualitative criteria: forceful exit, structure removed, FVG created, one-sided, no rotation. ([Aron Groups](https://arongroups.co/technical-analyze/displacement-in-ict/), [SimpleICT](https://thesimpleict.com/ict-displacement-explained-2025/))

**v0.4 Assessment:** NOT YET BUILT — No canonical thresholds exist

**Detection Logic (best composite approach):**
```
body = abs(close - open)
range = high - low
atr_14 = ATR(14)

# Dual detection (FibAlgo "Both" mode):
displacement = (body > atr_14 * 1.5) AND (body / range > 0.65)

# Optional: consecutive bars check
displacement_sequence = 2+ consecutive displacement candles same direction

# Quality: FVG should be created by the move
```
Source: [FibAlgo ICT Displacement](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/), [ArunKBhaskar GitHub](https://github.com/ArunKBhaskar/PineScript/blob/main/%5BScreener%5D%20ICT%20Retracement%20to%20Order%20Block%20with%20Screener.txt)

**Variant Matrix:**

| Method | Threshold | Source | Deterministic? |
|--------|-----------|--------|---------------|
| ATR multiple | 1.5× ATR(14) | [FibAlgo](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/) | Yes |
| Body/range ratio | ≥ 65% | [ArunKBhaskar](https://github.com/ArunKBhaskar/PineScript/blob/main/%5BScreener%5D%20ICT%20Retracement%20to%20Order%20Block%20with%20Screener.txt) | Yes |
| Dual (ATR + ratio) | Both conditions | [FibAlgo "Both" mode](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/) | Yes |
| Combined + volume + FVG | ATR 1.2× + vol 1.5× + CLV 25% | [Zeiierman](https://www.zeiierman.com/blog/liquidity-sweeps-in-trading/) | Yes |
| % price change | User-defined | [TehThomas](https://www.tradingview.com/script/1rld7nWE-TehThomas-Displacement-Candles/) | Yes |

**Sanity Band:** No direct empirical count available; expected 5–15 displacement candles per active session on 1m EURUSD based on ATR 1.5× threshold.

**Key Implementation Note:** There is **no canonical threshold**. The ATR multiplier (1.5×? 2.0×?) and body ratio (65%? 70%?) are arbitrary. News-driven spikes have identical candle metrics to institutional displacement. Context (was liquidity swept first?) is the ICT differentiator.

**Recommendation:** Build first among Tier 2 — everything else depends on it. Start with dual detection (ATR 1.5× AND body/range 65%). Validate thresholds against empirical data. Olya should confirm thresholds.

---

## 3.12 Order Block (OB)

**Definition:** The **last opposing candle** immediately before an impulsive displacement move. Bullish OB = last bearish candle before bullish displacement. Zone defined by the candle's **body** (open to close), with the **mean threshold** at 50% as a refined entry point. ([Strike Money](https://www.strike.money/technical-analysis/order-block), [Phidias Prop Firm](https://phidiaspropfirm.com/education/order-blocks))

**v0.4 Assessment:** NOT YET BUILT — Moderate complexity

**Detection Logic:**
```
# Bullish OB: last bearish candle before bullish displacement
if close[i-2] < open[i-2]:                  # candle is bearish
  if displacement_present(i-1):              # next candle displaces up
    ob_zone = {
      high: open[i-2],                       # body top
      low:  close[i-2],                      # body bottom
      mid:  (open[i-2] + close[i-2]) / 2     # mean threshold (50%)
    }

Invalidation: close < ob_low (bullish) or close > ob_high (bearish)
Staleness: 5–10 bars without retest → OB becomes "stale"
```
Source: [joshuaburton096 TradingView OB v2](https://www.tradingview.com/script/1M4FG5X2-ICT-Order-Blocks-v2-Debug/)

**Variant Matrix:**

| Feature | Standard ICT | Alternative | Source |
|---------|-------------|-------------|--------|
| Zone boundary | Body only (open/close) | Full candle (high/low) for buffer | [Phidias](https://phidiaspropfirm.com/education/order-blocks) |
| Entry level | Mean threshold (50% of body) | Full zone entry | [GrandAlgo](https://grandalgo.com/blog/ict-propulsion-block-explained) |
| FVG required? | Preferred (not required) | Required by some | [joshuaburton096](https://www.tradingview.com/script/1M4FG5X2-ICT-Order-Blocks-v2-Debug/) |
| Multiple candidates | Use "last" candle | Mark all consecutive opposing | YouTube implementations |
| Staleness timeout | 5 bars (YouTube) | 10 bars or no timeout | Varies |

**Sanity Band:** Expected 3–8 OBs per active session; heavily dependent on displacement threshold.

**Key Implementation Note:** Without a displacement filter, **any** candle before a modest move qualifies as an OB. Displacement validation is the critical gate. The "last" candle convention needs a firm rule when 3 consecutive opposing candles precede the move.

**Recommendation:** Build after displacement detector is validated. Use body-only zone boundaries. Mean threshold (50%) for refined entry. Require FVG creation as quality confirmation.

---

## 3.13 MMXM (Market Maker Model)

**Definition:** A meta-pattern — the complete institutional price delivery cycle composed of all other primitives in sequence: Original Consolidation → Manipulation/Sweep → Smart Money Reversal (displacement + MSS) → Accumulation (FVG/OB retracement) → Re-accumulation → Expansion to terminus. ([YouTube MMXM](https://www.youtube.com/watch?v=MM-vHn6TBck), [Scribd MMXM](https://www.scribd.com/document/715412777/ICT-MMXM-Iteration-a11b40c4725c48ae9cc72f6a8aba9caf-3))

**v0.4 Assessment:** NOT A PRIMITIVE — Meta-pattern with retrospective labeling problem

**Detection Logic (state machine sketch):**
```
States: IDLE → CONSOLIDATION → MANIPULATION → SMR → ACCUMULATION_1 → ACCUMULATION_2 → EXPANSION

CONSOLIDATION: equal H/L forming, ATR contracting
MANIPULATION:  sweep of SSL/BSL (Judas Swing)
SMR:           displacement + MSS + FVG created
ACCUMULATION:  retracement to FVG/OB
EXPANSION:     BOS toward terminus (HTF PD Array)

⚠️ Phase labels are RETROSPECTIVE — "is this consolidation or accumulation?"
   is only knowable after the fact.
```

**Variant Matrix:**

| Source | Phases | Phase Names | Real-Time? |
|--------|--------|-------------|-----------|
| ICT (original) | 4 | Accum/Manip/Distrib/Rebalance | No |
| [YouTube 6-stage](https://www.youtube.com/watch?v=MM-vHn6TBck) | 6 | OC/Range/Return/Stage1/Stage2/Terminus | No |
| [TradingFinder TV](https://www.tradingview.com/script/4eQPT3aC-MMXM-ICT-TradingFinder-Market-Maker-Model-PO3-CHoCH-CSID-FVG/) | 5 | OC/PriceRun/SMR/Accum/Completion | Partial |
| [LinkedIn critique (Pranay Gaurav)](https://www.linkedin.com/posts/pranay-gaurav-290a30150_mmxm-ictconcepts-liquiditytrading-activity-7320004504219734016-_83o) | N/A | "Phases are unidentifiable — only labeled after price has made a full move" | No |

**Sanity Band:** N/A — meta-pattern, not a countable detection.

**Key Implementation Note:** MMXM phase labels are **retrospective by nature**. Phase 2 (manipulation) looks identical to a continuation BOS until Phase 3 (SMR) confirms the reversal. There is no way to label Phase 2 in real time.

**Recommendation:** Build last. Use only for retrospective labeling and trade quality scoring. Do not attempt real-time phase classification.

---

# 4. MASTER VARIANT MATRIX

| # | Primitive | v0.4 Definition | Community Consensus | Alignment | Action |
|---|-----------|----------------|-------------------|-----------|--------|
| 1 | FVG condition | `low[C] > high[A]` (wick-to-wick) | Universal: identical condition across [LuxAlgo](https://www.tradingview.com/script/jWY4Uiez-Fair-Value-Gap-LuxAlgo/), [NinjaTrader](https://github.com/tickets2themoon/ICTFVG), [CodeTrading](https://www.youtube.com/watch?v=cjDgibEkJ_M) | ✅ Aligned | Fix rendering bugs only |
| 2 | FVG min size | No filter | Production systems use ≥ 1–2 pip minimum | ❌ Missing | Add ≥ 2 pip filter |
| 3 | FVG invalidation | Body stays inside zone | ICT: body close through CE (50%) invalidates; [LuxAlgo](https://www.tradingview.com/script/jWY4Uiez-Fair-Value-Gap-LuxAlgo/): touch of outer boundary | ⚠️ Acceptable variant | Keep current (conservative) |
| 4 | VI definition | 3-candle body-to-body | ICT: 2-candle body-to-body ([OpoFinance](https://blog.opofinance.com/en/ict-volume-imbalance/)); no standalone usage found | ❌ Wrong definition | REMOVE |
| 5 | Swing detection | N=5, strict `>` both sides | N=5 standard; `>=` left, `>` right per [TradingView ta.pivothigh](https://stackoverflow.com/questions/64019553/how-pivothigh-and-pivotlow-function-work-on-tradingview-pinescript) | ⚠️ Bug in equality | Fix `>=` on left side |
| 6 | Swing size filter | None | 2–3 pip min recommended by [MQL5 ATR article](https://www.mql5.com/en/articles/21443) | ❌ Missing | Add 2.5 pip or 0.8×ATR |
| 7 | Equal H/L tolerance | Not implemented | 1–2 pips on 1m per [practitioner consensus](https://www.litefinance.org/blog/for-beginners/trading-strategies/ict-trading-strategy/) | ❌ Missing | Add 1.5 pip tolerance |
| 8 | Asia Range window | 19:00–00:00 NY | 19:00–00:00 primary ([innercircletrader.net](https://innercircletrader.net/tutorials/ict-asian-range/)); 20:00 secondary | ✅ Aligned | None |
| 9 | Asia Range threshold | 30 pips | No published ICT standard; empirical median 12.7 pips | ⚠️ VARIANT (too restrictive) | Olya review: 15–20 pips? |
| 10 | LOKZ | 02:00–05:00 NY | Universal ([5 TV indicators](https://www.tradingview.com/script/nW5oGfdO-ICT-Killzones-Pivots-TFO/)) | ✅ Aligned | None |
| 11 | NYOKZ | 07:00–10:00 NY | Standard. 08:00–11:00 extended variant exists. | ✅ Aligned | None |
| 12 | London Reversal | 03:00–04:00 NY | = [ICT Silver Bullet London](https://innercircletrader.net/tutorials/ict-silver-bullet-strategy/) | ✅ Aligned | None |
| 13 | NY Reversal | 08:00–09:00 NY | **NY Silver Bullet = 10:00–11:00** ([innercircletrader.net](https://innercircletrader.net/tutorials/ict-silver-bullet-strategy/)); 08:50–09:10 = "Macro" | ⚠️ Different from Silver Bullet | Olya review |
| 14 | PDH/PDL | 17:00 NY, wicks | Universal standard | ✅ Aligned | None |
| 15 | Midnight Open | 00:00 NY | Universal ([edgeful.com](https://www.edgeful.com/blog/posts/ICT-trading-strategy-midnight-open-retracement-report)) | ✅ Aligned | None |
| 16 | Day boundary | 17:00 NY | Universal ([OANDA](https://www.oanda.com/bvi-en/cfds/hours-of-operation/), [Dukascopy](https://www.dukascopy.com/swiss/english/fx-market-tools/forex-market-hours/)) | ✅ Aligned | None |
| 17 | MSS/BOS trigger | Close beyond swing | Community consensus: close beyond, not wick ([Strike Money](https://www.strike.money/technical-analysis/break-of-structure)) | ✅ Aligned (concept) | Build |
| 18 | Displacement threshold | Not defined | ATR 1.5× + body/range 65% ([FibAlgo](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/)) | N/A (not built) | Build with dual threshold |
| 19 | OB zone | Not defined | Body-only, mean threshold 50% ([Strike Money](https://www.strike.money/technical-analysis/order-block), [Phidias](https://phidiaspropfirm.com/education/order-blocks)) | N/A (not built) | Build body-only |
| 20 | OTE levels | Not defined | 62%, 70.5%, 79% ICT-specific ([GrandAlgo](https://grandalgo.com/blog/ict-optimal-trade-entry-ote)) | N/A (not built) | Build ICT levels |
| 21 | Sweep pip limit | 30–40 pips | No fixed limit in community; ATR-relative preferred ([Zeiierman](https://www.zeiierman.com/blog/liquidity-sweeps-in-trading/)) | ⚠️ VARIANT | Olya review: ATR-relative? |
| 22 | MMXM | Planned | Retrospective meta-pattern, not real-time detectable ([LinkedIn critique](https://www.linkedin.com/posts/pranay-gaurav-290a30150_mmxm-ictconcepts-liquiditytrading-activity-7320004504219734016-_83o)) | N/A | Build last, retrospective only |

---

# 5. EMPIRICAL SANITY BANDS

All data from 7,177 bars EURUSD 1m, 2024-01-07 to 2024-01-12 ([sanity_band_results.md](sanity_band_results.md)).

## Traffic-Light Key
- 🔴 **FLOODING** — Signal-to-noise ratio collapsed; unusable without heavy filtering
- 🟡 **HIGH** — Borderline; needs session or confluence filtering to be actionable
- 🟢 **USABLE** — Actionable density for algo decision-making
- 🔵 **STARVATION** — Too few detections; filter is too aggressive or data is atypical

## Master Density Table

| Primitive | Parameter Setting | Median/Day | Range [Min–Max] | Status |
|-----------|------------------|-----------|-----------------|--------|
| FVG (any gap) | wick-to-wick, 0 pip | 400 | [384–429] | 🔴 FLOODING |
| FVG (≥ 0.5 pip) | wick-to-wick | 177 | [151–192] | 🔴 FLOODING |
| FVG (≥ 1 pip) | wick-to-wick | 75 | [69–91] | 🟡 HIGH |
| **FVG (≥ 2 pips)** | **wick-to-wick** | **15** | **[11–27]** | **🟢 USABLE** |
| FVG (≥ 5 pips) | wick-to-wick | 0 | [0–5] | 🔵 STARVATION |
| VI (any gap) | body-to-body, 0 pip | 765 | [731–790] | 🔴 SEVERE FLOODING |
| VI (≥ 0.5 pip) | body-to-body | 387 | [333–403] | 🔴 FLOODING |
| VI (≥ 1 pip) | body-to-body | 177 | [144–217] | 🔴 FLOODING |
| VI (≥ 2 pips) | body-to-body | 47 | [32–83] | 🟡 HIGH (high variance) |
| VI (≥ 5 pips) | body-to-body | 1 | [0–11] | 🔵 STARVATION |
| Swing (N=3) | strict `>` both sides | 242 | [224–266] | 🔴 FLOODING |
| Swing (N=5) — current | strict `>` both sides | 148 | [138–162] | 🔴 FLOODING |
| Swing (N=7) | strict `>` both sides | 110 | [99–130] | 🟡 HIGH |
| Swing (N=10) | strict `>` both sides | 77 | [69–93] | 🟡 HIGH |
| Swing (N=15) | strict `>` both sides | 51 | [43–63] | 🟢 USABLE |
| Swing (N=20) | strict `>` both sides | 39 | [33–52] | 🟢 USABLE |
| Asia Range | 19:00–00:00 NY | 12.7 pips | [10.3–22.4] | All < 30 pip threshold |
| PDH/PDL range | 17:00 NY | 58 pips | [50–70] | Normal for EURUSD |

## Recommended Working Thresholds

| Primitive | Recommended Filter | Expected Rate | Notes |
|-----------|-------------------|:------------:|-------|
| FVG | ≥ 2 pips (0.0002) | ~15/day | Session filter → ~5–8/session |
| Swing Points | N=5 + 2.5-pip height filter | ~15–30/day | Or N=15–20 unfiltered for HTF |
| Asia Range trigger | ≤ 15–20 pips | Most days | 30-pip starves quiet weeks |
| PDH/PDL | No filter | 2 levels/day | Always usable |

---

# 6. RECOMMENDED BUILD ORDER

Build in dependency order. Each phase validates before the next begins.

```
PHASE A — Tier 1 Fixes (Critical Path)
├─ A1: Swing Points — fix >= on left, add 2.5-pip height filter, add EQH/EQL
├─ A2: FVG — fix boundary + anchor bugs, add 2-pip min gap
├─ A3: Remove VI (standalone)
└─ A4: Sessions — already working (no changes)

PHASE B — Tier 2 Foundations
├─ B1: Displacement — ATR 1.5× + body/range 65% (dual filter)
│       Everything in Phase C depends on this.
└─ B2: MSS / BOS — swing break + trend state machine + displacement filter

PHASE C — Tier 2 Zones & Events
├─ C1: Order Block — last opposing candle + displacement + FVG confirmation
├─ C2: Liquidity Sweep — wick-beyond + close-back-inside at key levels
└─ C3: OTE — Fibonacci 62%/70.5%/79% zone after BOS, gated to kill zones

PHASE D — Meta-Pattern
└─ D1: MMXM — retrospective labeling ONLY. State machine over all above.
         Do NOT attempt real-time phase classification.
```

**Rationale:**
- Phase A fixes what's broken in the live system — highest ROI
- Phase B builds the foundational Tier 2 detector (displacement) that gates everything else
- Phase C builds the tradeable zones and events that compose the entry model
- Phase D wraps the narrative layer — useful for trade journaling and validation, not signal generation

---

# 7. OPEN QUESTIONS FOR OLYA

Items requiring the strategist's judgment — no community consensus exists, or the research found conflicting information.

1. **Asia Range threshold: 30 pips vs lower?** Empirical data shows 0/5 days exceeded 30 pips (median 12.7 pips). ICT's own words suggest "ranging = 10–20 pips, trending = 20–30 pips" ([YouTube 2024](https://www.youtube.com/watch?v=GfxScm82JHM)). A 30-pip threshold would have starved the system all week. **Should we lower to 15–20 pips, or use an ATR-relative threshold (e.g., 30–40% of trailing ADR)?**

2. **NY Reversal window: 08:00–09:00 vs Silver Bullet 10:00–11:00?** v0.4 uses 08:00–09:00, which captures the post-macro-release window (08:30 ET data drops). The canonical NY AM Silver Bullet per [innercircletrader.net](https://innercircletrader.net/tutorials/ict-silver-bullet-strategy/) is 10:00–11:00. These are different windows targeting different market mechanics. **Do we want the macro reversal (08:00–09:00), the Silver Bullet (10:00–11:00), or both?**

3. **Displacement thresholds: ATR 1.5× + body/range 65%? Both required or either-or?** The [FibAlgo "Both" mode](https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/) (AND condition) is the most restrictive and reduces false positives. The [Zeiierman approach](https://www.zeiierman.com/blog/liquidity-sweeps-in-trading/) uses a lower ATR multiple (1.2×) but adds volume and CLV checks. **Which parameter set should we start with?**

4. **OB zone: body-only or include wicks for low-probability setups?** Community overwhelmingly uses body-only for the OB zone ([Strike Money](https://www.strike.money/technical-analysis/order-block), [Phidias](https://phidiaspropfirm.com/education/order-blocks)). Some practitioners include the full candle range as a "low probability extension." **Body-only for v1, or configurable?**

5. **Equal highs/lows tolerance: 1.5 pips or 2 pips?** No universally agreed value. Practitioner consensus for 1m EURUSD is "1–2 pips" ([LiteFinance ICT guide](https://www.litefinance.org/blog/for-beginners/trading-strategies/ict-trading-strategy/)). **1.5 pips as default?**

6. **Swing N=5 with size filter vs N=10–15 without?** N=5 + 2.5-pip filter gives ~15–30 swings/day. N=15 unfiltered gives ~51/day. N=20 unfiltered gives ~39/day. **Which produces cleaner HH/HL sequences for order flow reads? Should we run both (micro N=5+filter for execution, macro N=15 for structure)?**

7. **Sweep pip limit: fixed 30–40 pips or ATR-relative?** The v0.4 30–40 pip limit is not found in community sources. [Zeiierman](https://www.zeiierman.com/blog/liquidity-sweeps-in-trading/) and [Phidias](https://phidiaspropfirm.com/education/liquidity-sweep) use context-based (close behavior, not size) or ATR-relative thresholds. **Remove the fixed limit and rely on close-back-inside + ATR-relative filter?**

8. **MSS displacement requirement: strict or preferred?** Most serious implementations require displacement for MSS quality ([Aron Groups](https://arongroups.co/technical-analyze/displacement-in-ict/)). Some ([PineScript ICTProTools](https://www.scribd.com/document/902397983/Explanation-of-Pine-Script-Code)) make it optional. **Require displacement for MSS, or make it a quality score?**

9. **OB staleness timeout: 5 bars, 10 bars, or no timeout?** YouTube source says "if it takes more than five [candles for retest], I'm not interested." Other implementations use no timeout. **Start with 10-bar timeout and tune?**

10. **FVG invalidation: outer boundary close-through (v0.4) vs CE midpoint close-through (ICT canonical)?** v0.4 uses outer boundary, which is more conservative (fewer premature invalidations). ICT teaches CE (50%) as the invalidation level. **Keep outer boundary for now?**

11. **Multi-timeframe swing hierarchy: dual N approach?** For live execution on 1m, should we run parallel swing detectors — N=5+filter for execution-level micro-structure and aggregated 5m/15m swings for structural bias? The [Market Structure HH/HL script](https://www.tradingview.com/script/3qHfkvHG-Market-Structure-HH-HL-LH-LL-with-Trendlines-Alerts/) uses dynamic N by timeframe. **Which timeframes to aggregate?**

---

# 8. SOURCE INDEX

## ICT Primary Sources

| Source | URL |
|--------|-----|
| ICT Mentorship Core Content (FVG) | https://www.scribd.com/document/751178990/ICT-Fair-Value-Gap-FVG-ICT-Mentorship-Core-Co |
| innercircletrader.net — FVG tutorial | https://innercircletrader.net/tutorials/fair-value-gap-trading-strategy/ |
| innercircletrader.net — Kill Zones | https://innercircletrader.net/tutorials/master-ict-kill-zones/ |
| innercircletrader.net — Kill Zone PDF | https://innercircletrader.net/wp-content/uploads/2023/12/ICT-Kill-Zone-PDF.pdf |
| innercircletrader.net — Asian Range | https://innercircletrader.net/tutorials/ict-asian-range/ |
| innercircletrader.net — Silver Bullet | https://innercircletrader.net/tutorials/ict-silver-bullet-strategy/ |
| innercircletrader.net — BOS Tutorial | https://innercircletrader.net/tutorials/break-of-structure-bos/ |
| innercircletrader.net — OTE Pattern | https://innercircletrader.net/tutorials/ict-optimal-trade-entry-ote-pattern/ |
| innercircletrader.net — Judas Swing | https://innercircletrader.net/tutorials/ict-judas-swing-complete-guide/ |
| innercircletrader.net — Sweep vs Run | https://innercircletrader.net/tutorials/ict-liquidity-sweep-vs-liquidity-run/ |
| innercircletrader.net — NDOG | https://innercircletrader.net/tutorials/ict-new-day-opening-gap-ndog/ |
| innercircletrader.net — Bread and Butter | https://innercircletrader.net/tutorials/ict-bread-and-butter-buy-setup/ |
| ICT YouTube — Asian Range (2017) | https://www.youtube.com/watch?v=JA0mLNJeytY |
| ICT YouTube — VI Lecture | https://www.youtube.com/watch?v=URcDVLVRH1c |
| ICT YouTube — 2024 Mentorship | https://www.youtube.com/watch?v=xw-mIOo3hds |
| ICT YouTube — Asian Sweep 2024 | https://www.youtube.com/watch?v=GfxScm82JHM |
| Scribd — Judas Swing Document | https://www.scribd.com/document/717809869/12-ICT-Forex-Understanding-The-ICT-Judas-Swing |
| Scribd — Asian Range Document | https://www.scribd.com/document/690531414/11-ICT-Forex-Implementing-The-Asian-Range |
| Scribd — MMXM Iteration | https://www.scribd.com/document/715412777/ICT-MMXM-Iteration-a11b40c4725c48ae9cc72f6a8aba9caf-3 |
| Scribd — MMXM PDF | https://www.scribd.com/document/776497721/ICT-Market-Maker-Model-MMXM-PDF |
| Scribd — Imbalance/FVG PDF | https://www.scribd.com/document/658635910/Imbalance-and-fair-value-gap |

## TradingView Scripts

| Script | URL | Used For |
|--------|-----|----------|
| LuxAlgo Fair Value Gap (413k+ favorites) | https://www.tradingview.com/script/jWY4Uiez-Fair-Value-Gap-LuxAlgo/ | FVG detection + B-close filter |
| ACE FVG & IFVG Trading System | https://www.tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/ | FVG + IFVG |
| ICT 1st P. FVG + Volume Imbalance | https://www.tradingview.com/script/vOFYxaN9-ICT-First-Presented-FVG-with-Volume-Imbalance-1st-P-FVG-VI/ | VI integration |
| TheProBack-Tester FVG Finder | https://www.tradingview.com/script/51Uy7WFK-Fair-Value-Gap-Finder/ | FVG (naming confusion) |
| Market Structure HH/HL/LH/LL | https://www.tradingview.com/script/3qHfkvHG-Market-Structure-HH-HL-LH-LL-with-Trendlines-Alerts/ | Swing + classification |
| Pivot-based Swing Highs and Lows | https://www.tradingview.com/script/ffRnXR2F-Pivot-based-Swing-Highs-and-Lows/ | Swing detection |
| Market Structure ZigZag (sufiyan1611) | https://www.tradingview.com/script/RHOeEnLm-Market-Structure-HH-HL-LH-and-LL/ | ZigZag variant |
| Fractals Custom Periods (DonkeyEmporium) | https://www.tradingview.com/script/F2vLpcxJ-Fractals-Swing-Points-Highs-Lows-Custom-Periods/ | Williams Fractal |
| ICT Killzones + Pivots [TFO] | https://www.tradingview.com/script/nW5oGfdO-ICT-Killzones-Pivots-TFO/ | Session boundaries |
| ICT Killzones Toolkit [LuxAlgo] | https://www.tradingview.com/script/9kY5NlHJ-ICT-Killzones-Toolkit-LuxAlgo/ | Session boundaries |
| ICT Killzones (enricoamato997) | https://www.tradingview.com/script/ehwcUFM8-ICT-Killzones/ | Session boundaries |
| ICT Killzones + Sessions w/ Silver Bullet | https://tw.tradingview.com/script/InMPCLO7-ICT-Killzones-and-Sessions-W-Silver-Bullet-Macros/ | Sessions + Silver Bullet |
| ICT NY Midnight Open | https://www.tradingview.com/script/y5sLA4Ls-ICT-New-York-NY-Midnight-Open-and-Divider/ | Midnight open |
| FibAlgo ICT Displacement | https://www.tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/ | Displacement detection |
| TehThomas Displacement Candles | https://www.tradingview.com/script/1rld7nWE-TehThomas-Displacement-Candles/ | Displacement (% change) |
| OTE Script (yLKbFuXN) | https://www.tradingview.com/script/yLKbFuXN-OTE-optimal-trade-entry-ICT-visible-chart-only-Dynamic/ | OTE zone |
| ICT Concepts Liquidity Sweeps (KL0iqOX2) | https://fr.tradingview.com/script/KL0iqOX2-ICT-Concepts-Liquidity-FVG-Liquidity-Sweeps/ | Sweep detection |
| joshuaburton096 OB v2 | https://www.tradingview.com/script/1M4FG5X2-ICT-Order-Blocks-v2-Debug/ | Order Block |
| MMXM TradingFinder | https://www.tradingview.com/script/4eQPT3aC-MMXM-ICT-TradingFinder-Market-Maker-Model-PO3-CHoCH-CSID-FVG/ | MMXM detection |
| FibAlgo ICT Market Maker Model | https://www.tradingview.com/script/AvZeEzkr-FibAlgo-ICT-Market-Maker-Model/ | MMXM (3-phase AMD) |

## GitHub Repositories

| Repository | URL | Used For |
|-----------|-----|----------|
| tickets2themoon/ICTFVG (NinjaTrader) | https://github.com/tickets2themoon/ICTFVG | FVG C# implementation |
| silvinob ICTFVG modified (Gist) | https://gist.github.com/silvinob/3335e76266449a26f3c7b5890a6ecd44 | FVG exact C# code |
| rpanchyk/mt5-fvg-ind (MT5) | https://github.com/rpanchyk/mt5-fvg-ind | FVG MQL5 |
| sheevv/find-swing-highs-swing-lows | https://github.com/sheevv/find-swing-highs-swing-lows | Lance Beggs swing |
| gehtsoft/forex-connect (zigzag) | https://github.com/gehtsoft/forex-connect/blob/master/samples/Python/Indicators.py | Zigzag Python |
| niquedegraaff ZigZagLib (Gist) | https://gist.github.com/niquedegraaff/4428558435f74cd30de1d9b95895af01 | HH/HL PineScript lib |
| tsunafire PineScript-SMC-Strategy | https://github.com/tsunafire/PineScript-SMC-Strategy | BOS/MSS + sweep |
| ArunKBhaskar PineScript ICT Screener | https://github.com/ArunKBhaskar/PineScript/blob/main/%5BScreener%5D%20ICT%20Retracement%20to%20Order%20Block%20with%20Screener.txt | OB + OTE screener |
| yusin99 Pivots and Killzones | https://github.com/yusin99/Tradingview-Indicator---Pivots-and-Killzones | Sessions PineScript |

## Community & Educational Sources

| Source | URL | Used For |
|--------|-----|----------|
| Darya Filipenka / Time Price Research | https://time-price-research-astrofin.blogspot.com/2024/04/ict-fair-value-gap-darya-filipenka.html | BISI/SIBI labeling |
| OpoFinance — ICT Volume Imbalance | https://blog.opofinance.com/en/ict-volume-imbalance/ | VI definition |
| SpacemanBTC FVG (Reddit) | https://www.reddit.com/r/pinescript/comments/1hznkjg/ | FVG code |
| Reddit — London Kill Zone variant | https://www.reddit.com/r/InnerCircleTraders/comments/1lea5mw/ | Session variant |
| Reddit — Daily candle open time | https://www.reddit.com/r/InnerCircleTraders/comments/1n3hw91/ | 17:00 vs 00:00 |
| Reddit — MMXM vs PO3 | https://www.reddit.com/r/InnerCircleTraders/comments/18wrwkk/ | MMXM relationship |
| Edgeful.com — FVG best practices | https://www.edgeful.com/blog/posts/fair-value-gap-best-practices-guide | FVG frequency |
| Edgeful.com — Midnight Open stats | https://www.edgeful.com/blog/posts/ICT-trading-strategy-midnight-open-retracement-report | 58–69% retracement |
| Phidias Propfirm — FVG guide | https://phidiaspropfirm.com/education/fair-value-gap | Timeframe frequency |
| Phidias Propfirm — Order Blocks | https://phidiaspropfirm.com/education/order-blocks | 8-point quality scoring |
| Phidias Propfirm — Liquidity Sweep | https://phidiaspropfirm.com/education/liquidity-sweep | 1–4 candle return |
| Equiti — MSS vs BOS Guide | https://www.equiti.com/sc-en/news/trading-ideas/mss-vs-bos-the-ultimate-guide-to-mastering-market-structure/ | MSS/BOS rules |
| LuxAlgo — MSS in ICT Trading | https://www.luxalgo.com/blog/market-structure-shifts-mss-in-ict-trading/ | MSS explainer |
| Strike Money — BOS Guide | https://www.strike.money/technical-analysis/break-of-structure | Close-beyond requirement |
| Strike Money — Order Block | https://www.strike.money/technical-analysis/order-block | OB definition |
| GrandAlgo — OTE Guide | https://grandalgo.com/blog/ict-optimal-trade-entry-ote | OTE levels |
| GrandAlgo — Propulsion Block | https://grandalgo.com/blog/ict-propulsion-block-explained | OB variants |
| TradingFinder — OTE | https://tradingfinder.com/education/forex/ict-optimal-trade-entry-pattern/ | OTE 70.5% |
| TradingFinder — Judas Swing | https://tradingfinder.com/education/forex/ict-judas-swing/ | Judas mechanics |
| TradingFinder — MSS vs CISD | https://tradingfinder.com/education/forex/mss-vs-cisd/ | MSS medium-term |
| TradingFinder — Asian Range | https://tradingfinder.com/education/forex/ict-asian-range-trading-strategy/ | Asia 19:00–00:00 |
| Zeiierman — Liquidity Sweeps | https://www.zeiierman.com/blog/liquidity-sweeps-in-trading/ | Quantified sweep criteria |
| Aron Groups — Displacement | https://arongroups.co/technical-analyze/displacement-in-ict/ | 5 criteria |
| SimpleICT — Displacement | https://thesimpleict.com/ict-displacement-explained-2025/ | BOS/FVG requirement |
| FXNX — OTE Guide | https://fxnx.com/en/blog/mastering-the-ict-fibonacci-retracement-a-traders-guide | ICT-modified Fib |
| Daily Price Action — Sweep Reversals | https://dailypriceaction.com/blog/liquidity-sweep-reversals/ | OTE combination |
| LinkedIn — MMXM Critique (Pranay Gaurav) | https://www.linkedin.com/posts/pranay-gaurav-290a30150_mmxm-ictconcepts-liquiditytrading-activity-7320004504219734016-_83o | Retrospective labeling |
| LiteFinance — ICT Strategy | https://www.litefinance.org/blog/for-beginners/trading-strategies/ict-trading-strategy/ | Equal H/L |
| FXOpen — ICT Concepts | https://fxopen.com/blog/en/what-are-the-inner-circle-trading-concepts/ | Equal H/L liquidity |
| FXOpen — Silver Bullet | https://fxopen.com/blog/en/what-is-the-ict-silver-bullet-strategy-and-how-does-it-work/ | Silver Bullet windows |
| CodeTrading Python FVG (YouTube) | https://www.youtube.com/watch?v=cjDgibEkJ_M | Python body filter |
| YouTube — MMXM Market Maker Models | https://www.youtube.com/watch?v=MM-vHn6TBck | 6-stage MMXM |
| YouTube — ICT MMXM Step-by-Step | https://www.youtube.com/watch?v=Rf_G-i1g22E | MMXM mechanics |

## Forex Data & Volatility References

| Source | URL | Used For |
|--------|-----|----------|
| OANDA — Trading Hours | https://www.oanda.com/bvi-en/cfds/hours-of-operation/ | Forex day boundary |
| Dukascopy — Forex Market Hours | https://www.dukascopy.com/swiss/english/fx-market-tools/forex-market-hours/ | Day boundary, DST |
| Dukascopy — DST Change Announcement | https://www.dukascopy.com/swiss/english/full-news/change-to-daylight-saving-time-dbl200533/ | UTC shift documentation |
| dukascopy-node — UTC documentation | https://www.dukascopy-node.app/custom-date-format-and-timezone-conversion | UTC timestamps |
| StrategyQuant — Dukascopy timezone | https://strategyquant.com/forum/topic/7377-handling-the-time-zone-issue-step-by-step/ | GMT+0 storage |
| Daily Price Action — NY Close Charts | https://dailypriceaction.com/blog/new-york-close-charts-forex-market/ | 17:00 standard |
| capital.com — PDH/PDL | https://capital.com/en-au/analysis/day-traders-toolbox-previous-days-high-and-low-pdh-pdl | PDH/PDL definition |
| TradethatSwing — EURUSD Volatility | https://tradethatswing.com/analyzing-eur-usd-volatility-for-day-trading-purposes/ | ADR, ATR context |
| OffbeatForex — ADR Table | https://offbeatforex.com/forex-average-daily-range-table/ | EURUSD ADR 2024 |
| BabyPips — Tokyo Session | https://www.babypips.com/learn/forex/can-trade-forex-tokyo-session | Asia hourly pips |
| MQL5 — ATR-Filtered Swings | https://www.mql5.com/en/articles/21443 | ATR swing detection |
| StackOverflow — PineScript Pivots | https://stackoverflow.com/questions/64019553/how-pivothigh-and-pivotlow-function-work-on-tradingview-pinescript | Python pivot implementation |

## Academic / Quantitative

| Source | URL | Used For |
|--------|-----|----------|
| IWSS Elliott Wave (algotrading-investment.com) | https://algotrading-investment.com/2020/06/04/impulse-wave-structural-score-and-corrective-wave-structural-score/ | Impulse scoring parallel |
| TradingWithUFOs — DMI Impulse | https://www.tradewithufos.com/impulse-or-correction/ | Quantitative impulse vs correction |

---

*Research Pack v1.0 — Phase 1 Complete. All claims cited. All variants explicitly labeled. No unsourced claims about "standard." Ready for Craig + Olya joint review.*
