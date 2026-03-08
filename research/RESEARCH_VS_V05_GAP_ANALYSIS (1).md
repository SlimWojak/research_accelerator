# Research Pack vs v0.5 — Systematic Gap Analysis
## a8ra Algo Trading System | EURUSD 1m
**Prepared:** 2026-03-04  
**Source A:** `ICT_PRIMITIVES_RESEARCH_PACK.md` (813 lines, "RP" hereafter)  
**Source B:** `SYNTHETIC_OLYA_METHOD_v0.5.yaml` (779 lines, "v0.5" hereafter)  
**Purpose:** Identify what is carried forward, what is missing, what is resolved, and what is new — primitive by primitive.

---

## HOW TO READ THIS DOCUMENT

For each primitive:
- **A) Already Incorporated** — Research findings that v0.5 already encodes (with specific line refs)
- **B) Not Yet in v0.5 — Should Be** — Research findings useful for an Opus instance building from v0.5 but currently absent
- **C) Open Questions: Resolved vs Pending** — Which of RP Section 7's 11 questions has the Olya session answered
- **D) New in v0.5 Not in Research Pack** — Learnings added by the calibration session itself

Section references: `RP §3.1` = Research Pack Section 3.1; `v0.5 L84` = v0.5 line 84.

---

## CALIBRATION STATUS QUICK REFERENCE

| Primitive | v0.5 L1 | v0.5 L1.5 | v0.5 L2 | Calibrated? |
|-----------|---------|----------|---------|-------------|
| FVG | LOCKED | LOCKED | PARTIAL | YES (2026-03-04) |
| IFVG | LOCKED | INHERITED | NOTED | YES (2026-03-04) |
| BPR | LOCKED | TBD | NOTED | PARTIAL (2026-03-04) |
| Swing Points | PARTIAL | PENDING | PENDING | NO |
| Equal H/L | PARTIAL | PENDING | PENDING | NO |
| Asia Range | LOCKED | PENDING | PENDING | NO (fast expected) |
| Displacement | PARTIAL | PENDING | PENDING | NO |
| MSS | PARTIAL | PENDING | PENDING | NO |
| Order Block | PARTIAL | PENDING | PENDING | NO |
| Liquidity Sweep | PARTIAL | PENDING | PENDING | NO |
| OTE | LOCKED | LOCKED | PENDING | PARTIAL |
| PDH/PDL | LOCKED | N/A | N/A | YES |
| Midnight Open | LOCKED | N/A | N/A | YES |
| BOS | — | — | — | NOT IN v0.5 |
| MMXM | — | — | — | REMOVED |
| VI (standalone) | — | — | — | REMOVED |

---

# PRIMITIVE-BY-PRIMITIVE ANALYSIS

---

## 1. FVG (Fair Value Gap)
**RP Section:** §3.1 (lines 83–121), §4 rows 1–3, §5 (lines 590–593), §7 Q10  
**v0.5 Section:** lines 82–178, calibration_status lines 725–729

### A) Already Incorporated into v0.5

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| Bullish condition: `low[C] > high[A]`, zone top = `low[C]`, zone bottom = `high[A]` | RP §3.1 L91–92 | v0.5 L88–91 |
| Bearish condition: `high[C] < low[A]`, zone top = `low[A]`, zone bottom = `high[C]` | RP §3.1 L92 | v0.5 L95–98 |
| CE midpoint: `(zone_top + zone_bottom) / 2` | RP §3.1 L94 | v0.5 L92, L99 |
| Anchor time: candle A's timestamp (not candle C) | RP §3.1 L93, L117 | v0.5 L93–94, L100 |
| v0.4 bug fix: boundary used `high[1]` → corrected to `high[i-2]` | RP §2 L61 | v0.5 L113 |
| v0.4 bug fix: anchor time at candle C → corrected to candle A | RP §2 L61 | v0.5 L114 |
| Native timeframe detection (5m FVG ≠ 1m FVG projected to 5m) | RP §3.1 (implied) | v0.5 L104–110 |
| FVG state machine: ACTIVE → CE_TOUCHED → BOUNDARY_CLOSED | RP §3.1 L94 (invalidation logic) | v0.5 L116–138 |
| VI as FVG attribute, not standalone primitive | RP §3.2 L153 | v0.5 L143 (`vi_confluent` tag), L706–707 |
| MMXM removed as real-time primitive | RP §3.13, §2 L75 | v0.5 L712–713 |
| 5m FVG count context (calibration data: 345 FVGs vs 2017 on 1m same week) | RP §5 (density data) | v0.5 L110 |

**Bug fixes: Both P0 bugs from RP §2 are fully resolved in v0.5.**

### B) Not Yet in v0.5 — Should Be Added

**1. Full variant matrix with source citations**  
RP §3.1 lines 99–105 documents five distinct FVG filter variants (standard wick-to-wick, LuxAlgo B-close filter, CodeTrading body multiplier, NinjaTrader ATR impulse, minimum pip size) with named sources. v0.5 carries the *result* (0.5-pip floor, confluence-first) but drops the reasoning trail. An Opus instance that needs to justify the parameter choice or extend to different regimes has no source citations to reference.

**Specific gap:** The LuxAlgo `close[B] > high[A]` candle-B-close filter (RP L102, 413k favorites) is not represented in v0.5 as a candidate quality tag. The `displacement_present` tag in v0.5 L144 partially covers this, but the LuxAlgo approach is more granular and has been empirically validated at production scale.

**2. Full sanity band table**  
RP §5 / §3.1 provides the complete empirical density table (0 pip → 400/day, 0.5 pip → 177/day, 1 pip → 75/day, 2 pips → 15/day, 5 pips → starvation). v0.5 L110 records only one data point ("5m: 345 FVGs vs 2017 on 1m same week"). The full threshold-vs-count table is not present. An Opus instance recalibrating the floor parameter has no benchmark to compare against.

**Specific gap:** The day-by-day variance range `[11–27]` at the 2-pip threshold (RP L592) is not in v0.5. This is operationally important: if Opus sets a filter and sees 3 FVGs one day and 40 the next, it needs to know whether that's expected variance or a bug.

**3. FVG invalidation variant: outer boundary vs CE midpoint**  
RP §3.1 L94 notes that ICT teaches CE (50%) as the invalidation level while v0.4 used outer boundary (more conservative). v0.5 L174–177 correctly notes the distinction ("CE_TOUCHED = partial fill, BOUNDARY_CLOSED = invalid") but does not record that ICT's canonical invalidation trigger is CE, not outer boundary. RP Q10 (line 675) frames this explicitly. v0.5 is internally consistent but Opus doesn't know which is *canonical* vs which is a deliberate conservative deviation.

**4. Source citations for NinjaTrader anchor-time implementation**  
RP L117 provides the primary source confirming the `anchor_time = candle A` fix: the NinjaTrader ICTFVG source (`gist.github.com/silvinob/3335e76266449a26f3c7b5890a6ecd44`), with exact code reference `gapStartTime = Times[iDataSeries][2]`. v0.5 states the fix is correct but does not cite the confirmatory source. If the fix is ever questioned, the chain of evidence is broken.

**5. FVG retracement statistics from Edgeful**  
RP §8 cites `edgeful.com` study showing price retraces to FVG zones a specific percentage of the time (same domain that cited 58–69% midnight open retracement stats for the Midnight Open section, RP L759). This quantitative backing for FVG utility is absent from v0.5.

### C) Open Questions: Status

| RP Q# | Question | Status |
|-------|----------|--------|
| Q10 (L675) | FVG invalidation: outer boundary (v0.4) vs CE midpoint (ICT canonical)? | **PARTIALLY RESOLVED** — v0.5 L174–177 retains outer boundary language ("BOUNDARY_CLOSED") but acknowledges "Decision on which state invalidates = L2 context." Still pending Olya's L2 preference in a subsequent session. |

### D) New in v0.5 Not in Research Pack

1. **0.5-pip floor (not 2.0-pip):** The research pack's empirically validated sweet spot was **2 pips** (RP L40, L51, L114). The Olya calibration session specifically overrode this to **0.5 pip** with explicit provenance: "Jan 9 09:30 bullish FVG was sub-1-pip on 5m, meaningful in context. Previous 1.0 pip floor missed it." (v0.5 L155–157). This is a direct reversal of the research pack's recommendation — driven by Olya's visual review, not quantitative analysis.

2. **Confluence-first philosophy:** The research pack recommended size filtering as the primary quality gate ("≥ 2 pips"). v0.5 L162–167 replaces this with "CONFLUENCE_FIRST, not SIZE_FIRST" — a fundamental methodological shift. Pip size is explicitly demoted; context tags (session, displacement, swing proximity, HTF alignment) are the quality gate. This came from the calibration session.

3. **`bpr_zone` tag on FVG (v0.5 L145):** FVGs are now tagged whether they overlap with an opposite-direction FVG (creating a Balanced Price Range). This cross-primitive tagging is not in the research pack at all — it emerged from the Olya session introducing BPR as a new concept.

4. **`displacement_present` tag (v0.5 L144):** Each FVG is tagged whether candle B meets displacement criteria. This links FVG quality to displacement detection at the time of FVG formation — not in the research pack.

5. **State lifecycle tracking with timestamps (v0.5 L137–138):** Full audit log of state transitions (`state_change_time`, `state_history[]`) is an architectural addition not discussed in the research pack.

---

## 2. Volume Imbalance (VI)

**RP Section:** §3.2 (lines 123–154), §4 rows 3–4  
**v0.5 Section:** REMOVED block lines 704–707; `vi_confluent` tag at L143

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| VI removed as standalone primitive | RP L28, L127, L153 | v0.5 L705–707 |
| Reason: wrong definition (3-candle body-to-body vs ICT 2-candle) | RP L131–133 | v0.5 L706 |
| Reason: 765/day flooding | RP L28, L147 | v0.5 L706 |
| VI retained as FVG attribute only | RP L153 | v0.5 L143, L707 |

### B) Not Yet in v0.5 — Should Be Added

**1. The VI÷FVG ratio table (RP L145–149):** The quantitative case for removal includes the VI/FVG ratio at each threshold (1.91× at any gap, 2.36× at ≥1 pip, 3.13× at ≥2 pips). This ratio data, showing VI is systematically worse than FVG at every threshold, is the strongest argument for the removal decision. v0.5's removal justification is accurate but terse — an Opus instance defending the decision to a new Olya session lacks this quantitative backing.

**2. The single production integration pattern:** RP L153 identifies the one serious TradingView production use of VI: the "1st P. FVG+VI" script by `flasi` (`tradingview.com/script/vOFYxaN9-ICT-First-Presented-FVG-with-Volume-Imbalance-1st-P-FVG-VI/`) which uses VI to *extend FVG boundaries*. This is the *only* meaningful VI production use case found, and it's the model for the `vi_confluent` tag. The source citation is absent from v0.5.

**3. ICT's exact 2-candle definition (RP L125):** ICT's verbatim quote on VI ("A volume imbalance occurs... that up close candle — the very next candle that opens higher than the previous candle's close") and the source (ICT YouTube `youtube.com/watch?v=URcDVLVRH1c`) are not in v0.5. The `vi_confluent` tag's detection logic is undefined in v0.5 — an Opus instance implementing it has no specification for what "body-to-body gap also exists" means precisely.

**Critical gap:** v0.5 L143 declares `vi_confluent: "bool — body-to-body gap also exists (FVG + VI overlap)"` but does **not specify whether this uses the ICT 2-candle definition or the v0.4 3-candle definition.** This is an implementation ambiguity that could reintroduce the flooding problem.

### C) Open Questions
No RP Section 7 questions covered VI directly (VI removal was a research finding, not an open question).

### D) New in v0.5 Not in Research Pack
Nothing genuinely new — the `vi_confluent` tag design is a direct execution of RP's recommendation.

---

## 3. Swing Points

**RP Section:** §3.3 (lines 157–197), §4 rows 5–7, §5 (lines 599–604), §7 Q1, Q5, Q6, Q11  
**v0.5 Section:** lines 256–325, calibration_status lines 740–743

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| N=5 lookback window | RP L161, L187 | v0.5 L303 |
| `>=` on left side (equality fix) | RP L165, L194 | v0.5 L264–265, L272–276 |
| `>` strict on right side | RP L166 | v0.5 L265–266 |
| Bug: v0.4 strict `>` both sides — drops equal highs | RP L161, L194 | v0.5 L297 |
| Bug: no height filter — sub-pip noise | RP L192 | v0.5 L298 |
| Bug: no session noise filter | RP L196 | v0.5 L299 |
| Equal H/L detection as liquidity concept | RP L196 (1.5-pip tolerance) | v0.5 L318–319 (`is_equal_high`, `is_equal_low` tags) |
| Native TF detection principle | RP §3.3 (implied), §3.4 | v0.5 L294 |
| Height filter pending calibration | RP L192, L196 | v0.5 L307–311 |

### B) Not Yet in v0.5 — Should Be Added

**1. Full sanity band for swing count vs N (RP L184–192):**  
The complete empirical table (N=3 → 242/day, N=5 → 148/day, N=7 → 110/day, N=10 → 77/day, N=15 → 51/day, N=20 → 39/day) is absent from v0.5. v0.5 knows "148 swings/day is too many" (from the bugs_fixed note) but an Opus instance running calibration sessions needs the full curve to understand the trade-off of changing N.

**2. Estimated count with height filter applied (RP L192):**  
"N=5 + 2.5-pip filter → estimated 15–30/day" is not in v0.5. The `height_filter` candidates are listed (v0.5 L308: `[1.0, 1.5, 2.0, 2.5, 3.0, 4.0]`) but there's no expected count at any candidate value. Olya's calibration session will ask "what does 2.0 pips give me?" — the answer is available in RP but not in v0.5.

**3. The specific TradingView `ta.pivothigh` tie-breaking rule (RP L194):**  
"The leftmost bar in a tie wins — this is how TradingView handles it." This is the definitive reason for `>=` on the left side (not `>` on both, not `>=` on both), sourced from StackOverflow analysis of `ta.pivothigh`. v0.5 L272–276 describes the behavior correctly but drops the rationale. An Opus instance asked "why not `>=` on both sides?" has no answer.

**4. Zigzag alternative: repaints flag (RP L179):**  
The research explicitly documents that Zigzag methods REPAINT (v0.5 reference: none). This is important because Zigzag approaches appear frequently when searching for Python swing detection. v0.5 does not document that the current fractal approach is the *non-repainting* choice.

**5. ATR-scaled fractal recommendation (RP L180):**  
"ATR-scaled fractal (N-bar + min size in ATR units) = Best for live execution." Rated higher than static pip filter. v0.5 L307–311 has height_filter candidates in static pips only; ATR-adaptive sizing is not among the candidates.

**6. Session noise filter specification (RP L196):**  
RP recommends "add session noise filter for Asian session." v0.5 L317 adds a `session` tag to swing points, but the session noise filter (suppressing Asian session swings from contaminating HH/HL structural classification) is not specified as an L1 or L1.5 rule. It's a tag that's been added, but no L1 rule says "Asian session swings are not valid structural reference points for LOKZ/NY context."

**7. Dual-N micro/macro structure concept (RP §7 Q11, L677):**  
The research proposes running parallel swing detectors: N=5+filter for execution-level micro-structure and N=15+ for structural bias. v0.5 L303–304 says "N=10 reserved as test oracle only" — it acknowledges a second N exists but doesn't frame it as a dual-N architecture for different structural purposes.

**8. Equal highs tolerance candidates not in v0.5 (RP §7 Q5, L665):**  
RP cites LiteFinance ICT guide for 1–2 pip tolerance on 1m EURUSD. v0.5 L359 has `candidates: [0.5, 1.0, 1.5, 2.0, 2.5]` — range is correct but the source isn't cited, and the community guidance (1–2 pip) isn't flagged as the most likely landing zone.

### C) Open Questions: Status

| RP Q# | Question | Status |
|-------|----------|--------|
| Q5 (L665) | Equal H/L tolerance: 1.5 pips or 2 pips? | **PENDING** — v0.5 L359 lists candidates but no default locked |
| Q6 (L667) | Swing N=5+filter vs N=10–15 unfiltered? Also dual-N architecture? | **PENDING** — v0.5 L303–304 notes N=10 as test oracle but doesn't resolve the production question |
| Q11 (L677) | Multi-TF swing hierarchy: dual N approach? Which TFs? | **PENDING** — v0.5 L294 states "native detection per TF" but doesn't define execution vs structural swing separation |

### D) New in v0.5 Not in Research Pack

1. **Strength metric (v0.5 L280–292):** A `strength` score counting extra bars beyond the N-window that continue to respect the swing extreme (capped at 20, graded dim/mid/vivid). This is entirely absent from the research pack and appears to be a CTO architectural addition. This is a significant quality dimension — potentially more useful than height alone. No empirical data on its distribution.

2. **`strength_grade` tag (v0.5 L320):** `dim (0-5) | mid (6-12) | vivid (13-20)` — classification schema for swing quality. Novel.

3. **CTO hypothesis: "strength filter matters more than height" (v0.5 L310–311):** This claim has no backing in the research pack. It's an architectural opinion that will need empirical validation.

---

## 4. Equal Highs / Equal Lows (EQUAL_HL)

**RP Section:** §4 row 7, §7 Q5 (indirectly in §3.3 L196)  
**v0.5 Section:** lines 327–367, calibration_status lines 744–747

**Note:** EQUAL_HL was not a standalone one-pager in the research pack — it was treated as a swing points sub-feature. In v0.5, it has been promoted to its own primitive.

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| EQH/EQL as liquidity pool concept | RP L196, L557 | v0.5 L333–334 |
| 1.5-pip tolerance candidate for 1m EURUSD | RP L196, Q5 L665 | v0.5 L359 (`candidates: [0.5, 1.0, 1.5, 2.0, 2.5]`) |
| Pairs require matching type (both highs or both lows) | RP (implied) | v0.5 L339 |

### B) Not Yet in v0.5 — Should Be Added

**1. LiteFinance source citation for 1–2 pip tolerance (RP L665, L779):**  
v0.5 has the candidates but no source. An Opus instance justifying the tolerance needs the citation.

**2. FXOpen citation for EQL/EQH as liquidity magnet (RP L780):**  
`fxopen.com/blog/en/what-are-the-inner-circle-trading-concepts/` specifically discusses equal H/L as liquidity. Not cited in v0.5.

**3. The temporal filter rationale needs more specificity (v0.5 L350–354):**  
v0.5 L351–354 correctly warns about sub-5-minute pairs being noise. The CTO note is good. But the calibration data showing "hundreds of sub-5-minute pairs = noise" is referenced in general — there's no empirical count backing this. RP didn't generate this specific data either (it was implicit in the swing flooding numbers). A specific sanity band for EQUAL_HL detections is entirely absent from both documents.

**4. ICT's description of EQL as "resting stops" (not cited anywhere):**  
The mechanism — EQH/EQL marks stop clusters that ICT calls "buy-side liquidity" (BSL) and "sell-side liquidity" (SSL) respectively — is implicit in both documents but never explicitly cited from an ICT primary source. This is a gap in both RP and v0.5.

### C) Open Questions
| RP Q# | Question | Status |
|-------|----------|--------|
| Q5 (L665) | Equal H/L tolerance 1.5 pip or 2 pip? | **PENDING** — v0.5 L359 lists candidates, none locked |

### D) New in v0.5 Not in Research Pack

1. **Primitive promoted to standalone:** EQUAL_HL is its own YAML block in v0.5 (lines 327–367). In RP it was a bullet point in the swing section. The promotion reflects architectural clarity but introduces a new scoping question: does EQUAL_HL emit its own bead, or is it a tag on SWING_POINTS beads?

2. **`min_separation` parameter (v0.5 L361–363):** The 30-minute minimum time gap between qualifying swing pairs — with CTO note "Not in original Phase 2 spec. Added after data review." This is new and important.

---

## 5. Session Boundaries (Asia, LOKZ, NYOKZ)

**RP Section:** §3.4 (lines 200–229), §4 rows 10–13, §5 L605  
**v0.5 Section:** constants block lines 58–62, NY_WINDOWS lines 650–662

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| Asia: 19:00–00:00 NY | RP L208 | v0.5 L59 |
| LOKZ: 02:00–05:00 NY | RP L209 | v0.5 L60 |
| NYOKZ: 07:00–10:00 NY | RP L210 | v0.5 L61 |
| Always use NY local time (America/New_York tz) | RP L211, L226 | v0.5 L56 (`dst_rule`) |
| Gap periods tagged "other" | RP (implied) | v0.5 L62 |
| All sessions confirmed correct in v0.4 | RP §2 L64–66 | v0.5 (status: confirmed, no explicit flag needed) |

### B) Not Yet in v0.5 — Should Be Added

**1. Session bar counts / sanity band (RP L224, §5 L605):**  
"299–300 Asia bars, 180 LOKZ bars, 180 NYOKZ bars per day" — these are the expected bar counts for validation. If a system detects 50 Asia bars instead of 300, there's a DST bug. v0.5 has no such sanity check.

**2. DST mismatch window (RP L226):**  
"During the 2–3 week US/EU DST mismatch (March: US springs forward before EU; October: EU falls back before US), London open shifts by 1 hour in NY terms." RP L226 documents this explicitly. v0.5 L56 only says "Always NY local (auto-adjusts EST/EDT)" — the DST mismatch edge case and its operational impact on LOKZ timing is not mentioned.

**3. Variant list for each session (RP §3.4 variant matrix L218–222):**  
RP documents known variants: Asia 19:00–00:00 (primary) vs 20:00–00:00; LOKZ 02:00–05:00 (universal) vs older 01:00–05:00; NYOKZ 07:00–10:00 (standard) vs 08:00–11:00 extended. None of these variants are in v0.5. An Opus instance implementing for a different pair or dealing with "why isn't this matching my chart?" has no reference.

**4. Source citations for session validation (RP §8):**  
`innercircletrader.net/wp-content/uploads/2023/12/ICT-Kill-Zone-PDF.pdf` — the primary ICT Kill Zone PDF. Not cited in v0.5.

**5. London Reversal = Silver Bullet correlation (RP L221):**  
"London Reversal 03:00–04:00 NY = ICT Silver Bullet London." This equivalence (a session window in v0.4 maps to the named Silver Bullet strategy) is in the RP variant matrix but not in v0.5. Important for an Opus instance that might need to implement the Silver Bullet as a strategy layer.

### C) Open Questions

| RP Q# | Question | Status |
|-------|----------|--------|
| Q2 (L659) | NY Reversal: 08:00–09:00 (macro) vs Silver Bullet 10:00–11:00, or both? | **PARTIALLY RESOLVED** — v0.5 L650–661 reframes this as "Window A (08:00–09:00) = reversal energy, Window B (10:00–11:00) = continuation energy" with empirical FVG/displacement count data. However, Olya's L2 preference (which window she trades) remains PENDING. |

### D) New in v0.5 Not in Research Pack

1. **Empirical per-window characterisation (v0.5 L654–656):** "Window A: more FVGs, displacement, swing formation. Window B: lower event count, directional." This is a new empirical finding from the calibration session — the two windows were previously just treated as time ranges. The calibration added behavioral characterization.

2. **`other` category for gap periods (v0.5 L62):** Explicit tagging of bars in 00:00–02:00, 05:00–07:00, 10:00+ as "other." RP didn't categorize these gaps.

---

## 6. PDH/PDL (Previous Day High/Low)

**RP Section:** §3.5 (lines 232–259), §4 row 14, §5 L606  
**v0.5 Section:** REFERENCE_LEVELS block lines 626–636

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| 17:00 NY forex day boundary | RP L239 | v0.5 L633 |
| Wick-based (not close-based) measurement | RP L236, L241–242 | v0.5 L634 |
| Status: CONFIRMED correct | RP §2 L67 | v0.5 L635 |

### B) Not Yet in v0.5 — Should Be Added

**1. Full PDH/PDL sanity band (RP L247–255):**  
Median 58 pips range [50–70 pips] for EURUSD, plus the traffic-light table (< 30 pip = flag holiday, 30–100 = OK, 100–150 = news day, > 150 = flag extreme). v0.5 has no validation range. An Opus instance running production has no way to detect a corrupted PDH/PDL value.

**2. Holiday calendar consideration (RP L258):**  
"Consider adding a holiday calendar to flag anomalous PDH/PDL days (Christmas Eve, Thanksgiving Friday)." Not in v0.5.

**3. UTC timezone handling specifics (RP L256):**  
"17:00 boundary shifts between 21:00 UTC (summer) and 22:00 UTC (winter)." v0.5 says "Always NY local" but doesn't document the UTC equivalent for systems storing data in UTC (which Dukascopy data uses, per RP §8 L793–795).

**4. Source citations (RP §8 L790–796):**  
OANDA, Dukascopy, Daily Price Action — all confirming 17:00 NY as the universal standard. Not in v0.5.

### C) Open Questions
None — PDH/PDL had no open questions in RP Section 7.

### D) New in v0.5 Not in Research Pack
Nothing new. PDH/PDL is a confirmed, locked primitive in both documents.

---

## 7. Asia Range

**RP Section:** §3.6 (lines 262–298), §4 row 8, §5 L605, §7 Q1  
**v0.5 Section:** lines 372–415, calibration_status lines 748–751

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| Asia window: 19:00–00:00 NY (confirmed) | RP L271 | v0.5 L381 |
| 30-pip threshold is VARIANT (too restrictive) | RP L34, L68, L295 | v0.5 L396 (`v04_value: 30 # too restrictive`) |
| 0/5 days exceeded 30 pips in sample week | RP L34 | v0.5 L396 (implicit in "too restrictive") |
| Threshold candidates: 15–20 pip range suggested | RP L296–297 | v0.5 L395 (candidates: [12, 15, 18, 20, 25, 30]) |
| TIGHT classification = clean LOKZ setup expected | RP L264 (implied) | v0.5 L410–412 |
| WIDE classification = direction already expressed | RP (implied) | v0.5 L413–415 |
| Pending Olya calibration | RP L297 | v0.5 L394, calibration L750 |

### B) Not Yet in v0.5 — Should Be Added

**1. ICT's own words on ranging vs trending pips (RP L282):**  
ICT YouTube 2024 (`youtube.com/watch?v=GfxScm82JHM`): "Ranging could go from 10 to 20 pips. Trending could go from 20 to 30 pips." This is the primary source justifying the 15–20 pip candidate range. v0.5 L397 says "CTO prediction: 15-18 pip range" without citing ICT's own statement.

**2. Day-by-day empirical data (RP §3.6 L284–293):**  
The exact per-day data (Mon 22.4, Tue 17.0, Wed 10.3, Thu 11.7, Fri 12.7 pips) is not in v0.5. v0.5 L399–403 shows updated data (Mon 20.7, Tue 17.7, Wed 10.3, Thu 12.0, Fri 22.2) — there are slight numerical differences suggesting the v0.5 calibration session used a revised dataset or updated calculation. **This discrepancy between RP L287–292 and v0.5 L399–403 should be investigated** (e.g., 2024-01-08 shows 22.4 in RP vs 20.7 in v0.5; 2024-01-12 shows 12.7 in RP vs 22.2 in v0.5). The ordering also differs (RP is Mon-Fri, v0.5 appears reordered).

**3. ATR-relative threshold alternative (RP L297):**  
"Alternatively, use an ATR-relative threshold (e.g., 30–40% of trailing ADR)." This adaptive approach isn't in v0.5's candidates list (which is all static pip values).

**4. Janki-week caveat (RP L34):**  
"The 30-pip threshold would have been inactive all week — but Jan 8–12 2024 was a quiet EURUSD week." The qualification that the sample week may be atypically quiet is present in RP but absent from v0.5.

**5. innercircletrader.net Asia Range source URL (RP L691):**  
`innercircletrader.net/tutorials/ict-asian-range/` — not cited in v0.5.

### C) Open Questions

| RP Q# | Question | Status |
|-------|----------|--------|
| Q1 (L657) | Asia Range threshold: 30 pips vs lower? ATR-relative? | **PENDING** — v0.5 `L15: PENDING` (calibration_status L750). Calibration data updated but Olya hasn't locked threshold. |

### D) New in v0.5 Not in Research Pack

1. **Updated calibration data with slightly different values (v0.5 L399–403):** The per-day range values differ from RP. v0.5 shows Mon 20.7, Fri 22.2 where RP showed 22.4 and 12.7 respectively. This may reflect a corrected data pipeline or boundary fix. The discrepancy is not explained.

2. **`timeframe_note` (v0.5 L387–391):** Explicit statement that Asia Range correctly uses 1m bars for session extreme detection (unlike FVG/Swing which detect natively per TF). This architectural clarity note is not in RP.

---

## 8. Midnight Open

**RP Section:** §3.7 (lines 301–319), §4 row 9  
**v0.5 Section:** REFERENCE_LEVELS block lines 637–640

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| Midnight open = open price of 00:00 NY bar | RP L309 | v0.5 L638 |
| Status: CONFIRMED correct | RP §2 L69 | v0.5 L639 |
| Midnight open is intraday reference, NOT day boundary | RP L316 | Not explicitly in v0.5, but day boundary is clearly 17:00 NY (constants L54) |

### B) Not Yet in v0.5 — Should Be Added

**1. Edgeful.com retracement statistics (RP L303):**  
"Price retraces to the midnight open 58–69% of the time during the NY session" — from a specific Edgeful study (`edgeful.com/blog/posts/ICT-trading-strategy-midnight-open-retracement-report`). v0.5 L639 just says "CONFIRMED correct." This stat is the quantitative case for treating midnight open as a reference level worth tracking.

**2. ICT characterisation (RP L303):**  
ICT's phrase "the beginning of the true day" for midnight open — not in v0.5.

**3. TradingView indicator reference (RP L303, L725):**  
`tradingview.com/script/y5sLA4Ls-ICT-New-York-NY-Midnight-Open-and-Divider/` — not in v0.5.

### C) Open Questions
None from RP Section 7.

### D) New in v0.5 Not in Research Pack
Nothing new. Minimal entry in both documents — correctly reflects that this is a simple, fully-defined primitive.

---

## 9. Displacement

**RP Section:** §3.11 (lines 429–466), §4 row 18, §7 Q3  
**v0.5 Section:** lines 422–470, calibration_status lines 752–755

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| Dual detection: ATR multiple AND body/range ratio | RP L441–442 | v0.5 L436–441 |
| ATR period = 14 | RP L439 | v0.5 L430 |
| Body = abs(close - open) | RP L437 | v0.5 L431 |
| Range = high - low | RP L438 | v0.5 L432 |
| body_pct = body/range | RP L441 | v0.5 L433 |
| atr_ratio = range/atr_14 | RP (implicit) | v0.5 L434 |
| AND vs OR combination mode | RP L462 (implicit: "AND condition is most restrictive") | v0.5 L438, L456–458 |
| ATR multiplier candidates: 1.5× recommended | RP L442, L462 | v0.5 L452 (candidates: [1.0, 1.25, 1.5, 2.0]) |
| Body ratio candidates: 65% recommended | RP L442 | v0.5 L455 (candidates: [0.55, 0.60, 0.65, 0.70]) |
| FVG should be created by displacement (ICT rule) | RP L447 | v0.5 L443–447 |
| `created_fvg` tag | RP L447 | v0.5 L463 |
| No canonical thresholds — all parameters pending Olya | RP L463 | v0.5 calibration L753–755 |
| Displacement needed by MSS as dependency | RP L337, L355 | v0.5 L497 |

### B) Not Yet in v0.5 — Should Be Added

**1. Source citations for ATR 1.5× + 65% combination (RP L449):**  
`tradingview.com/script/9OYOAKNU-FibAlgo-ICT-Displacement/` (FibAlgo "Both" mode) and `github.com/ArunKBhaskar/PineScript/blob/main/...` are the sources for these specific values. v0.5 lists the same numerical candidates without sourcing them.

**2. Zeiierman's alternative approach (RP L458):**  
ATR 1.2× + volume ≥ 1.5× + CLV ≥ 25% — a three-factor approach (`zeiierman.com/blog/liquidity-sweeps-in-trading/`). This is a meaningful alternative that adds volume and close-location-value as confirmation. Not in v0.5 candidates.

**3. News spike disambiguation (RP L463):**  
"News-driven spikes have identical candle metrics to institutional displacement. Context (was liquidity swept first?) is the ICT differentiator." v0.5 doesn't include this warning. An Opus building a displacement detector will find it fires aggressively on news events — the research pack's note explains why.

**4. ~54% FVG creation rate provenance:**  
v0.5 L446 states "Calibration data: ~54% created FVG at default params." This is new data from the Olya session, but the default params it refers to are not specified (since ATR mult + body ratio are PENDING). An Opus running future calibration sessions needs to know what "default params" produced 54%.

**5. Variant matrix: TehThomas % price change method (RP L459):**  
`tradingview.com/script/1rld7nWE-TehThomas-Displacement-Candles/` — user-defined % price change as threshold. Not in v0.5. This approach is TF-independent (unlike ATR which is regime-dependent) and might be relevant for calibration on higher timeframes.

**6. Build-order rationale (RP §6 L631):**  
"Build displacement first among Tier 2 — everything in Phase C depends on it." v0.5 doesn't include build-order rationale.

### C) Open Questions

| RP Q# | Question | Status |
|-------|----------|--------|
| Q3 (L661) | Displacement thresholds: ATR 1.5× + body 65%? Both required (AND) or either-or (OR)? Start with Zeiierman (1.2× + vol + CLV)? | **PENDING** — v0.5 L453–458 lists candidates but all `PENDING OLYA CALIBRATION`. `combination_mode: AND` is set as default but explicitly marked pending. |

### D) New in v0.5 Not in Research Pack

1. **`ny_window` tag (v0.5 L464):** Displacement events tagged as occurring in WinA (08:00–09:00) or WinB (10:00–11:00). The RP treated these windows separately for sessions; tagging displacement events by NY window is a new cross-primitive architectural decision.

2. **~54% FVG creation rate (v0.5 L446):** This empirical calibration measurement (54% of displacement candles created an FVG at default params) is a new finding. It implies 46% of displacement candles don't create FVGs — which means displacement + FVG-created is a higher-quality filter than displacement alone.

---

## 10. MSS / BOS (Market Structure Shift / Break of Structure)

**RP Section:** §3.8 (lines 322–356), §4 row 17, §7 Q8  
**v0.5 Section:** lines 477–506 (MSS only), calibration_status lines 756–759

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| MSS = close beyond swing WITH displacement | RP L337–338 | v0.5 L481–482, L486–488 |
| Dependency on SWING_POINTS and DISPLACEMENT | RP L353 | v0.5 L497 |
| FVG creation optional on MSS | RP §7 Q8 L672 | v0.5 L501 |
| Close-beyond (not wick) as break trigger | RP L338 | v0.5 L486 (`bar.close > prior_swing_high.price`) |
| Displacement required for MSS quality | RP L337, Q8 L671 | v0.5 L487 (`if is_displacement(bar)`) |

### B) Not Yet in v0.5 — Should Be Added

**1. BOS is completely absent from v0.5:**  
RP §3.8 defines both MSS and BOS, with BOS = break in the direction of the prevailing trend (continuation) and MSS = break against the trend (reversal). v0.5 only defines MSS. BOS is not present as a primitive, derived primitive, or placeholder. This is the most significant structural omission between the two documents.

The BOS state machine from RP (RP L331–336) — tracking trend_direction (BULL/BEAR), last swing high (pH), last swing low (pL), and correctly classifying breaks as BOS vs MSS depending on direction — is entirely absent. An Opus building from v0.5 would implement MSS without knowing what BOS is or that it's a distinct signal with different L2 implications.

**2. Trend direction state machine (RP L331–336):**  
The full 4-case state machine (Bullish BOS, Bearish MSS, Bullish MSS, Bearish BOS) depending on current trend_direction is in RP but not in v0.5. v0.5 L484–495 only shows the bullish MSS case.

**3. Variant matrix: close-beyond vs wick (RP L344–350):**  
Sources that allow configurable wick vs body trigger (PineScript ICTProTools) vs those that require close (Strike Money, ICT). Not in v0.5.

**4. "A wick break is not enough" canonical statement (RP L338):**  
This is cited in RP from Strike Money and labeled as close-beyond doctrine. v0.5 uses close-beyond in pseudocode but doesn't document the canonical principle or why wick-only is wrong.

**5. Expected sanity band: 3–8 BOS/MSS per session (RP L351):**  
No expected detection rate in v0.5. An Opus instance has no benchmark.

**6. Source citations (RP L340):**  
`strike.money/technical-analysis/break-of-structure`, `equiti.com/sc-en/news/trading-ideas/mss-vs-bos-the-ultimate-guide-to-mastering-market-structure/`, `luxalgo.com/blog/market-structure-shifts-mss-in-ict-trading/` — none in v0.5.

**7. `require_fvg` parameter in v0.5 L501 is undefined:**  
v0.5 says `require_fvg: "PENDING — v0.4 said 'FVG created OR respected'"` but RP §7 Q8 (L671) asked about displacement requirement, not FVG requirement. The FVG requirement discussion is absent from RP entirely. This is an untracked open question introduced in v0.5 with no research backing.

### C) Open Questions

| RP Q# | Question | Status |
|-------|----------|--------|
| Q8 (L671) | MSS displacement requirement: strict or preferred? Make it quality score? | **PENDING** — v0.5 L487 hardcodes `if is_displacement(bar)` as strict requirement, but calibration_status L757 (`L15: PENDING`) means this isn't locked. No resolution. |

### D) New in v0.5 Not in Research Pack

1. **`fvg_created` field on MSS bead (v0.5 L492):** Not in RP. FVG creation at MSS time is now a first-class MSS attribute.

2. **MSS composite structure explicitly labeled (v0.5 L498):** "MSS is a composite — depends on two other primitives." The explicit composite labeling with dependency declaration is cleaner than RP's implicit treatment.

---

## 11. Order Block (OB)

**RP Section:** §3.12 (lines 469–506), §4 row 19, §7 Q4, Q9  
**v0.5 Section:** lines 513–554, calibration_status lines 760–763

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| Last opposing candle before displacement | RP L471, L478 | v0.5 L517, L522–523 |
| Zone defined by body (open/close) | RP L471, L495 | v0.5 L527 (`zone_body`) |
| Zone wick bounds also tracked | RP L495 (variant) | v0.5 L528 (`zone_wick`) — both tracked |
| Displacement dependency | RP L479 | v0.5 L536 |
| Staleness threshold needed (pending) | RP Q9 L673 | v0.5 L539–543 (candidates: [5, 10, 15, 20, 30]) |
| Retest tracking | RP L487 | v0.5 L532–535 |
| 121 OBs/day on 1m is noise | RP (implied by displacement dependency) | v0.5 L543 |

### B) Not Yet in v0.5 — Should Be Added

**1. Mean threshold (50% of body) as refined entry concept (RP L472, L483–484):**  
`mid = (open[i-2] + close[i-2]) / 2` — the mean threshold as the specific entry level within the OB zone is in RP L483 but not in v0.5. v0.5 tracks `zone_body` and `zone_wick` but has no `midpoint` or `mean_threshold` field. This means OTE-style entry within the OB is not represented.

**2. Phidias 8-point OB quality scoring system (RP §8 L761):**  
`phidiaspropfirm.com/education/order-blocks` provides an 8-point quality scoring framework for OBs. Not referenced in v0.5 at all. Potentially useful for `min_displacement_grade` calibration.

**3. FVG confirmation as quality gate (RP L497):**  
"FVG required? Preferred (not required)" — and "joshuaburton096 requires FVG creation as quality confirmation." v0.5 L549 says "OB without quality displacement is not meaningful" but doesn't mention FVG confirmation as a quality dimension.

**4. "Last candle" rule for consecutive opposing candles (RP L503):**  
"The 'last' candle convention needs a firm rule when 3 consecutive opposing candles precede the move." v0.5 L522 uses `bars[i-1]` (last candle before displacement) but doesn't document this as a deliberate convention for handling the 3-candle case.

**5. Staleness timeout debate (RP §7 Q9, L673):**  
RP cites YouTube source "if it takes more than five [candles], I'm not interested" alongside "10 bars or no timeout." v0.5 L541 has `candidates: [5, 10, 15, 20, 30]` but no source citations or research backing for any candidate.

**6. Source citations (RP §8 L761, L766–768):**  
Strike Money, Phidias, joshuaburton096 TradingView OB v2, GrandAlgo — none in v0.5.

### C) Open Questions

| RP Q# | Question | Status |
|-------|----------|--------|
| Q4 (L663) | OB zone: body-only or include wicks? | **PARTIALLY RESOLVED** — v0.5 L527–528 tracks BOTH (body and wick), deferring the entry decision to L2. This is more flexible than the binary the question implies. |
| Q9 (L673) | Staleness timeout: 5 bars, 10 bars, no timeout? | **PENDING** — v0.5 L539–543 lists candidates, `PENDING OLYA CALIBRATION`. |

### D) New in v0.5 Not in Research Pack

1. **`displacement_grade` as OB quality attribute (v0.5 L529):** `get_displacement_grade(bars[i])` — the OB inherits the grade of the triggering displacement. This cross-primitive quality inheritance isn't in RP.

2. **`min_displacement_grade` threshold (v0.5 L549):** ATR >= 1.5× as the gate condition. RP recommended this but v0.5 formalizes it as a named parameter.

---

## 12. Liquidity Sweep / Judas Swing

**RP Section:** §3.10 (lines 393–426), §4 row 21, §7 Q7  
**v0.5 Section:** lines 561–590, calibration_status lines 764–767

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| Sweep = wick beyond level + close back inside | RP L403–404 | v0.5 L571–575 |
| Key levels include: swing points, equal H/L, PDH/PDL, session H/L | RP L402 | v0.5 L570 |
| max_sweep_size pending (v0.4 = 30–40 pips, non-standard) | RP L416, Q7 L669 | v0.5 L584–586 |
| Judas Swing = time-filtered sweep in LOKZ context | RP L406–409 | v0.5 L567 (noted in definition) |
| Dependency on SWING_POINTS, EQUAL_HL, session levels | RP L402 | v0.5 L580 |

### B) Not Yet in v0.5 — Should Be Added

**1. Judas Swing pseudocode is absent (RP L406–409):**  
RP provides the specific Judas Swing detection pseudocode:
```python
if 0 <= ny_hour < 5:
  if low < asian_low AND close > midnight_open → BULLISH JUDAS
  if high > asian_high AND close < midnight_open → BEARISH JUDAS
```
v0.5 L567 only mentions "Also known as: Judas Swing (in LOKZ context)" — no dedicated Judas pseudocode. The 00:00–05:00 time window and midnight open anchoring logic is not in v0.5.

**2. Return window (1–4 candles) from Phidias (RP L417):**  
`phidiaspropfirm.com/education/liquidity-sweep`: "1–4 candles for price to close back inside." This temporal constraint isn't in v0.5. Without it, the sweep detector doesn't know how far to look back.

**3. Volume filter: ≥ 1.5× 20-bar average (RP L418):**  
Zeiierman and TradingView ICT Concepts script use volume confirmation. Not in v0.5 candidates.

**4. ATR-relative sweep size (RP Q7 L669):**  
RP recommends "remove fixed limit, rely on close-back-inside + ATR-relative filter." v0.5 L584–585 retains the v0.4 30–40 pip reference but doesn't add ATR-relative as a candidate. The candidates list is empty — it just says `default: "PENDING OLYA CALIBRATION"`.

**5. "Sweep vs BOS only distinguishable in retrospect" (RP L423):**  
"The same candle that probes beyond a level could be either. The close-back-inside criterion is the only real-time differentiator." This is an important implementation gotcha. Not in v0.5.

**6. Source citations (RP §8 L762, L773):**  
Phidias, Zeiierman, TradingView ICT Concepts — none in v0.5.

### C) Open Questions

| RP Q# | Question | Status |
|-------|----------|--------|
| Q7 (L669) | Sweep pip limit: fixed 30–40 pips or ATR-relative? | **PENDING** — v0.5 L584 has `v04_value: "30-40 pips"` but no candidates beyond that. No movement. |

### D) New in v0.5 Not in Research Pack
Nothing architecturally new — v0.5 is a direct simplification of RP.

---

## 13. OTE (Optimal Trade Entry)

**RP Section:** §3.9 (lines 359–390), §4 row 20  
**v0.5 Section:** lines 597–620, calibration_status lines 768–771

### A) Already Incorporated

| Research Finding | RP Location | v0.5 Location |
|-----------------|-------------|---------------|
| ICT Fibonacci levels: 62%, 79% | RP L381 | v0.5 L613–615 |
| Zone detection: `ote_bot <= current_price <= ote_top` | RP L373 | v0.5 L609 |
| After BOS confirmed, measure from swing | RP L367–371 | v0.5 L605–606 (range_low, range_high) |
| Standard ICT values unlikely to change in calibration | RP (implied by "Universal") | v0.5 L616 |

### B) Not Yet in v0.5 — Should Be Added

**1. The 70.5% sweet spot level is ABSENT from v0.5 (RP L370, L381):**  
This is a significant gap. ICT's most distinctive OTE level — 70.5% ("the sweet spot") — is in RP L370, L381, L382 and is referenced by GrandAlgo, TradingFinder. v0.5 L613–615 only specifies `fib_lower: 0.618` and `fib_upper: 0.79`. The 70.5% midpoint level that RP identifies as "unique to ICT, not found in standard Fibonacci theory" is entirely missing.

This matters because TradingView Script yLKbFuXN uses standard Fibonacci (61.8%/78.6%) while ICT specifically uses 62%/70.5%/79%. An Opus implementing OTE from v0.5 alone would implement generic Fibonacci, not ICT-specific OTE.

**2. Anchor swing selection problem (RP L387):**  
"The hard part is anchor swing selection — which swing do you draw the Fibonacci on? Multiple candidates exist simultaneously." v0.5 doesn't mention this problem. OTE cannot be implemented without solving the anchor selection question.

**3. BOS prerequisite (RP L367, L389):**  
"Build after BOS implementation. Require BOS preceding the swing." v0.5 L604 shows a pseudocode with `range_high` and `range_low` as inputs but doesn't specify that BOS must precede and define these. The gate condition is absent.

**4. Kill zone gating (RP L389):**  
"Gate to kill zone hours" — OTE entries should only fire during LOKZ/NYOKZ. Not in v0.5.

**5. Session rate expectation (RP L385):**  
"Activates 1–3× per trading session after BOS events." Not in v0.5.

**6. Source citations (RP §8 L767–770):**  
GrandAlgo, TradingFinder, FXNX — none in v0.5.

### C) Open Questions
No RP Section 7 questions about OTE directly.

### D) New in v0.5 Not in Research Pack
Nothing new in v0.5. OTE is minimally specified in both documents.

---

## 14. IFVG (Inverse Fair Value Gap)

**RP Section:** Not covered (did not exist in RP scope)  
**v0.5 Section:** lines 184–213, calibration_status lines 730–733

### A) Already Incorporated
IFVG was not researched in Phase 1. Nothing from RP applies.

### B) Not Yet in v0.5 — Should Be Added

**1. No research backing whatsoever.**  
IFVG is a new primitive introduced by the Olya session. v0.5 L181 says "Status: IDENTIFIED — 2026-03-04 Olya session. Build pending." The polarity-flip concept (a closed FVG becomes resistance/support of opposite polarity) has no cited sources, no empirical sanity band, no variant matrix, and no implementation references. This is the largest single research gap in the system.

**2. Specific gaps for targeted research (see Section 5 of this document):**
- How does ICT define IFVG canonically?
- What is the expected IFVG count per day at 5m (vs all closed FVGs)?
- How long does an IFVG remain relevant before it's stale?
- Are there PineScript implementations?
- Is the ACE FVG & IFVG Trading System (RP §8 L714: `tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/`) a suitable reference implementation?

### C) Open Questions
None in RP Section 7 (IFVG was out of scope).

### D) New in v0.5 Not in Research Pack
IFVG is entirely new. The state-transition-based detection approach (v0.5 L197–203) is architecturally elegant — IFVG is not a scan but a state change on an existing FVG bead. The `ifvg_flip_time` timestamp is a new field.

---

## 15. BPR (Balanced Price Range)

**RP Section:** Not covered  
**v0.5 Section:** lines 219–250, calibration_status lines 735–739

### A) Already Incorporated
Not in RP scope.

### B) Not Yet in v0.5 — Should Be Added

**1. No research backing.**  
Similar to IFVG, BPR was introduced by the Olya session. No sourced definition, no empirical data, no variant matrix. The overlap detection pseudocode (v0.5 L227–237) is logically sound but uncited.

**2. Cross-TF BPR is deferred without clarity (v0.5 L239–240):**  
"Cross-TF BPR deferred to strategy layer" — this decision needs research. Does ICT ever describe BPR across timeframes? Does the community have a position?

**3. `min_overlap` parameter is TBD (v0.5 L243):**  
"May not need minimum if both source FVGs passed floor." This needs an empirical sanity band — how many BPRs form per day at 5m? Is it signal or noise?

### C) Open Questions
None in RP Section 7 (out of scope).

### D) New in v0.5 Not in Research Pack
BPR is entirely new from the Olya session.

---

## 16. MMXM and VI (Removed Primitives)

**RP Section:** §3.13 (MMXM, lines 509–543), §3.2 (VI, lines 123–154)  
**v0.5 Section:** REMOVED block lines 700–717

### A) Already Incorporated
Both removal decisions are correctly reflected:
- VI removed: RP L28, L153 → v0.5 L705–707 ✓
- MMXM as primitive removed: RP L38, L540 → v0.5 L712–713 ✓

### B) Not Yet in v0.5 — Should Be Added

**MMXM state machine sketch (RP L516–526):**  
v0.5 removes MMXM as a primitive but also removes the state machine description. If MMXM is retained as an L2 narrative frame (which v0.5 states in L713), the 7-state machine from RP (IDLE → CONSOLIDATION → MANIPULATION → SMR → ACCUMULATION_1 → ACCUMULATION_2 → EXPANSION) would be useful in the REMOVED block or STRATEGY_SKELETON as a retrospective labeling aid.

**Why-it's-retrospective rationale (RP L540):**  
"Phase 2 (manipulation) looks identical to continuation BOS until Phase 3 (SMR) confirms the reversal." This explanation is in RP but not in v0.5.

---

# OPEN QUESTIONS RESOLUTION SUMMARY

Mapping all 11 RP Section 7 open questions to current status:

| Q# | Short Description | RP Line | v0.5 Status | Notes |
|----|------------------|---------|-------------|-------|
| Q1 | Asia Range threshold 30 pip vs lower | L657 | **PENDING** (v0.5 L394) | Candidates listed, not locked |
| Q2 | NY Reversal: 08:00–09:00 vs Silver Bullet 10:00–11:00 | L659 | **PARTIALLY RESOLVED** (v0.5 L650–661) | Two windows characterized; Olya L2 preference pending |
| Q3 | Displacement: ATR 1.5× + 65% body? AND or OR? | L661 | **PENDING** (v0.5 L453–458) | Candidates listed, `combination_mode: AND` as default not locked |
| Q4 | OB zone: body-only or include wicks? | L663 | **RESOLVED** (v0.5 L527–528) | Both tracked at L1; L2 decides entry zone |
| Q5 | Equal H/L tolerance: 1.5 pip or 2 pip? | L665 | **PENDING** (v0.5 L359) | Candidates listed, none locked |
| Q6 | Swing N=5+filter vs N=10–15 unfiltered? | L667 | **PENDING** (v0.5 L303–304) | N=5 default, N=10 test oracle; dual-N not resolved |
| Q7 | Sweep pip limit: fixed or ATR-relative? | L669 | **PENDING** (v0.5 L584) | No candidates added, just original v0.4 value noted |
| Q8 | MSS displacement: strict or quality score? | L671 | **PENDING** (v0.5 L487, L757) | Hardcoded as strict in pseudocode but L1.5 PENDING |
| Q9 | OB staleness timeout: 5, 10, or no timeout? | L673 | **PENDING** (v0.5 L539–543) | Candidates listed, not locked |
| Q10 | FVG invalidation: outer boundary vs CE midpoint? | L675 | **PARTIALLY RESOLVED** (v0.5 L174–177) | L1 state machine covers both; L2 preference pending |
| Q11 | Multi-TF swing hierarchy: dual N? Which TFs? | L677 | **PENDING** (v0.5 L294, L303) | Native TF detection principle stated; dual-N architecture not resolved |

**Summary: 1 RESOLVED, 3 PARTIALLY RESOLVED, 7 PENDING**

---

# TARGETED RESEARCH GAPS

Areas where targeted research would materially help the next Olya calibration sessions. Ordered by primitives nearest to being locked.

---

## RG-1: IFVG — Complete Research Gap (Highest Priority)

**Situation:** IFVG was not in Phase 1 scope. It was introduced in the Olya session as a confirmed L2 usage primitive. v0.5 has a clean architectural definition (state transition on FVG bead) but no sourced evidence for how ICT defines it, whether the polarity-flip interpretation is canonical, what the expected detection rate is, or what implementations look like.

**What to research:**
1. ICT's canonical IFVG definition — search `innercircletrader.net` for "inverse fair value gap" and cross-reference ICT YouTube lectures on IFVG
2. The ACE FVG & IFVG Trading System (`tradingview.com/script/7tbdroH5-ACE-FVG-IFVG-Trading-System/`) — already in RP §8 L714 but never analyzed. This is the most likely production reference implementation.
3. IFVG sanity band: expected count/day at 5m (how many FVGs close per day → how many IFVGs are created?)
4. IFVG staleness: does polarity remain relevant indefinitely or decay? ICT teaching on this.
5. GitHub: any `IFVG` implementations in Python or PineScript

---

## RG-2: BPR (Balanced Price Range) — Complete Research Gap

**Situation:** BPR also not in Phase 1. Introduced by Olya session. No sourced definition.

**What to research:**
1. Is BPR an ICT term or a community term? Search `innercircletrader.net` + ICT YouTube for "balanced price range"
2. TradingView scripts implementing BPR — what overlap algorithm do they use?
3. Expected BPR count per 5m session — sanity band
4. Cross-TF BPR: does the community ever use a higher-TF FVG overlapping a lower-TF FVG?

---

## RG-3: Swing Points — Height and Strength Thresholds

**Situation:** Swing detection L1 is defined. The two critical parameters — `height_filter` and `strength_threshold` — are both PENDING OLYA CALIBRATION. The next calibration session needs a visual bible showing swing detection results at different parameter combinations.

**What to research:**
1. Empirical swing count at each height_filter candidate ([1.0, 1.5, 2.0, 2.5, 3.0, 4.0] pips) on the same 7,177-bar EURUSD 1m dataset — fill the gap in RP §5 that only had the N-varied table
2. Strength distribution: what is the actual distribution of strength values on the 7,177-bar dataset? Are strength scores > 5 rare or common? This tells Olya whether `dim/mid/vivid` classifications are meaningful or arbitrary.
3. ATR-adaptive height filter implementation — RP §3.3 L180 rated this "Best" but v0.5 candidates are all static pips. Concretely: what does `height >= 0.8 × ATR(14)` produce at EURUSD 1m vs static 2.5 pips?

---

## RG-4: Equal Highs/Lows — Sanity Band and Temporal Filter

**Situation:** EQUAL_HL has a structural definition but no empirical validation. The `min_separation` parameter (CTO recommends 30 min) is completely unevidenced.

**What to research:**
1. EQUAL_HL count per day at tolerance `[0.5, 1.0, 1.5, 2.0, 2.5]` pips on the 7,177-bar dataset — equivalent to what RP §5 provided for FVG
2. Temporal distribution of qualifying pairs: how many are < 5 min apart? < 30 min? This validates or refutes the `min_separation` hypothesis
3. ICT primary source on EQH/EQL as BSL/SSL (buy-side/sell-side liquidity) — `innercircletrader.net` search or ICT YouTube — to anchor the canonical definition

---

## RG-5: Displacement Threshold Calibration

**Situation:** Displacement is the foundation of MSS, OB, and Liquidity Sweep quality filters. All three primitives are blocked on displacement parameter selection. The calibration session needs empirical data.

**What to research:**
1. Displacement count per day at combinations of: ATR multiplier × body ratio at [1.0, 1.25, 1.5, 2.0] × [0.55, 0.60, 0.65, 0.70] with AND mode — a 4×4 grid of counts, analogous to RP §5's FVG threshold table
2. FVG creation rate per displacement at each parameter combination — RP §5 doesn't have this; v0.5 L446 says "~54% at default params" but default is undefined. What combination yields the highest `created_fvg` rate?
3. News event contamination: how many displacement detections coincide with known news release times (08:30 ET)? This tests the news spike problem from RP L463.

---

## RG-6: BOS — Missing Primitive Research

**Situation:** BOS is not in v0.5 at all. It's in RP but was never assigned a calibration session. MSS cannot be fully interpreted without BOS because they are defined relative to each other (BOS = same-direction swing break; MSS = counter-direction swing break).

**What to research:**
1. BOS vs MSS disambiguation: confirm the trend-direction state machine from RP §3.8 (lines 331–336) against LuxAlgo MSS and Equiti MSS vs BOS guide
2. BOS detection rate: how many BOS events per session on 5m EURUSD? Expected 3–8 per RP L351 — verify empirically
3. Whether v0.5 intentionally omitted BOS (strategic decision) or accidentally (oversight) — this determines whether it needs a REMOVED entry or a PENDING CALIBRATION entry

---

## RG-7: OTE Anchor Swing Selection

**Situation:** OTE L1 is locked at 61.8%–79%, but the anchor swing problem (which swing do you draw from?) is not solved. v0.5 doesn't even mention the problem. Without an anchor selection algorithm, OTE cannot be implemented.

**What to research:**
1. How do the top OTE TradingView scripts select the anchor swing? Specifically: `tradingview.com/script/yLKbFuXN-OTE-...` and `github.com/ArunKBhaskar/PineScript/...` (already in RP §8)
2. ICT's teaching on anchor selection: "most recent BOS defines the swing" — confirm from `innercircletrader.net/tutorials/ict-optimal-trade-entry-ote-pattern/`
3. Add the 70.5% sweet spot level to v0.5 OTE parameters (it's ICT-canonical per RP L381 but missing from v0.5 entirely)

---

## RG-8: Liquidity Sweep / Judas Swing — Return Window and Size Filter

**Situation:** The max_sweep_size parameter has no candidates. The return window (bars allowed before close-back-inside) is not specified. The Judas Swing time-filtered variant lacks pseudocode in v0.5.

**What to research:**
1. Empirical sweep return window: on the 7,177-bar dataset, for all wick-beyond-level events, what percentage close back inside within 1 bar? 2 bars? 5 bars? This validates the Phidias "1–4 candle" guidance (RP L417)
2. ATR-relative max_sweep_size calibration: what ATR multiple separates legitimate sweeps from trend continuation on EURUSD 1m? (e.g., 0.5× ATR, 1.0× ATR)
3. Judas Swing implementation reference: `innercircletrader.net/tutorials/ict-judas-swing-complete-guide/` (already in RP §8 L695) — extract the exact pseudocode specification for the time-filtered Judas variant

---

## RG-9: Asia Range Threshold — Expand Sample Week

**Situation:** The 30-pip threshold decision rests on 5 days of data (Jan 8–12 2024), which RP itself acknowledges may be an atypically quiet week. All 5 days were below 30 pips (median 12.7).

**What to research:**
1. Asia Range distribution on a larger EURUSD 1m dataset (90+ days) — what percentage of days exceed 15 pips? 18 pips? 20 pips? 30 pips? This gives the TIGHT/WIDE classification hit rate at each candidate threshold.
2. Correlation between Asia Range classification (TIGHT/WIDE) and LOKZ sweep outcome — does a "TIGHT" classification actually predict a cleaner LOKZ sweep? This validates the L2 logic (v0.5 L410–415).

---

# CROSS-DOCUMENT DISCREPANCY REGISTER

Items where RP and v0.5 show different data or conflicting specifications:

| # | Discrepancy | RP Value | v0.5 Value | Impact |
|---|------------|----------|-----------|--------|
| 1 | Asia Range per-day values | Mon 22.4, Fri 12.7 pips (RP L287–292) | Mon 20.7, Fri 22.2 pips (v0.5 L399–403) | Medium — affects threshold candidates and which day was TIGHT |
| 2 | FVG recommended floor | ≥ 2 pips empirically optimal (RP L40, L114) | 0.5 pip (v0.5 L150) | High — direct reversal of RP recommendation, deliberate Olya override |
| 3 | OTE lower fib | 62% per ICT (RP L381) | 0.618 (v0.5 L613) | Low — functional equivalent, but ICT uses 62% not 61.8% |
| 4 | OTE 70.5% level | Present (RP L370, L381) | **ABSENT** (v0.5 L611–616) | High — ICT's distinctive level is missing |
| 5 | NYOKZ window | 07:00–10:00, 08:00–11:00 as extended variant (RP L66) | 07:00–10:00 only (v0.5 L61) | Low — variant documented in RP but not in v0.5 |
| 6 | BOS | Full primitive (RP §3.8) | **NOT PRESENT** (v0.5) | High — complete omission |
| 7 | VI detection logic for `vi_confluent` tag | ICT 2-candle body-to-body (RP L133) | Not specified in v0.5 (v0.5 L143) | Medium — implementation ambiguity |

---

*Gap Analysis complete. All line references verified against source documents.*  
*Next action: brief Olya on items Q1, Q3, Q5, Q6, Q7, Q8, Q9, Q11 — the 7 truly pending open questions.*  
*Priority research: RG-1 (IFVG), RG-6 (BOS), RG-5 (Displacement thresholds).*
