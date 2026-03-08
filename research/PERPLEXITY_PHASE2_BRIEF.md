# a8ra Phase 2 Brief — Calibration Visual Bible

**From:** CTO + Advisor Panel (GPT / OWL / BOAR)
**To:** Perplexity Computer (Phase 2 Builder)
**Date:** 2026-03-04
**Status:** Phase 1 COMPLETE. Phase 2 scope AMENDED per advisor synthesis.

---

## 1. CONTEXT — What happened since Phase 1

Your Phase 1 research pack was excellent — production grade. We ran it through a 4-advisor pressure test (structural auditor, spec linter, chaos auditor, CTO synthesis). The research quality, sourcing, and empirical grounding all passed review.

The key strategic finding from our review changes Phase 2's mission:

**We were asking the wrong questions.** The 11 "Questions for Olya" were phrased as "what number should this threshold be?" — but our strategist (Olya) is a visual pattern expert, not a parameter tuner. Asking her to pick pip values is asking a human to compute. Our system should compute; she should judge.

**The corrected approach:** Build visual overlays at MULTIPLE candidate thresholds on the same real data. Olya looks at the overlays, points at the view that matches her trading practice. Her visual selection IS the parameter lock. The system finds the numbers; the human validates the output.

This is a fundamental architectural principle in our system: **humans frame and interpret, machines compute.**

---

## 2. WHAT CHANGED — Advisor Synthesis Decisions

These decisions are LOCKED. Phase 2 should build from them.

### 2.1 Three-Layer Architecture (Unanimous)

| Layer | Name | Who Decides | What It Contains |
|-------|------|-------------|-----------------|
| L1 | Geometric Detection | Locked by research (Phase 1) | The algorithm itself — what an FVG IS, what a swing IS |
| L1.5 | Parameter Thresholds | System calibrates, Olya validates | Pip filters, ATR multipliers, tolerance bands — configurable per pair/regime |
| L2 | Strategy Interpretation | Olya (not Phase 2's scope) | How primitives combine into trade setups |

**Principle:** L2 never rewrites L1. L1.5 is the tuning surface. Phase 2 builds the calibration interface for L1.5.

### 2.2 Locked Decisions (No longer open questions)

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| **VI standalone** | KILLED | 765/day flooding, wrong definition, no production usage. Retain only as FVG attribute: if FVG overlaps a VI, mark `fvg_vi_confluent: true`. Do not build standalone VI visuals. |
| **MMXM** | RETROSPECTIVE ONLY | Not a primitive — narrative meta-pattern. Do not build detection visuals. Deferred to future retrospective labeling system. |
| **FVG detection condition** | CONFIRMED CORRECT | `low[C] > high[A]` is universal. Fix the two rendering bugs (boundary off-by-one + anchor time). |
| **Swing equality** | FIX: `>=` left, `>` right | Most likely root cause of inconsistent detection. |
| **Sessions / PDH / PDL / Midnight Open** | ALL CONFIRMED | No changes. No visuals needed for validation. |
| **Threshold model** | HYBRID: `max(floor_pips, ATR_fraction)` | Fixed pip floor prevents starvation; ATR fraction scales with regime. Both values need calibration. |
| **FVG invalidation (Q10)** | TRACK BOTH | L1 tracks both "CE midpoint touched" and "outer boundary closed through." L2 decides which kills the trade. Build both as visual events if feasible. |
| **Dual-N swings (Q6)** | SINGLE PRODUCER, STRENGTH ATTRIBUTE | Don't run two swing detectors. Run one with a "strength" attribute derived from N-confirmation-depth + pip-excursion. Olya subscribes to strength threshold. |
| **OB zone boundary (Q4)** | TRACK BOTH body and wick | L1 records both. L2 decides. |
| **MSS displacement (Q8)** | DETECT BOTH with and without | L1 flags displacement presence as attribute. L2 filters. |
| **Sweep pip limit (Q7)** | ATR-RELATIVE | Remove fixed 30-40 pip limit. Use close-back-inside + ATR-relative threshold. |
| **MTF hierarchy (Q11)** | STRENGTH ATTRIBUTE | Resolved by swing strength — no separate multi-timeframe build needed. |

### 2.3 Remaining Calibration Questions (5 of original 11)

These are the questions Phase 2 visuals must help answer. Note: we are NOT asking Olya to pick numbers. We are showing her detections at multiple thresholds and asking her to pick the VIEW that matches her trading.

| ID | Primitive | What Olya Sees | What She Decides |
|----|-----------|---------------|-----------------|
| Q1 | Asia Range threshold | 5 Asia sessions with threshold lines at multiple values | "Which of these sessions were consolidation vs trending?" |
| Q2 | NY Reversal window | 5 NY sessions with BOTH 08-09 and 10-11 windows marked | "Which window(s) do you watch for reversal setups?" (This is L2 intent, not a threshold) |
| Q3 | Displacement thresholds | Charts with displacement candles highlighted at multiple ATR/body combinations | "Which highlighted candles represent real displacement to you?" |
| Q5 | Equal H/L tolerance | Chart pairs showing highs at various pip distances | "At what gap do these stop being 'equal'?" |
| Q9 | OB staleness | Order blocks shown with age counters at various timeouts | "At what age would you stop watching this OB?" |

---

## 3. PHASE 2 MISSION — Calibration Visual Bible

### 3.1 Core Deliverable

An interactive HTML file (or small set of files) that Olya can open in a browser. For each primitive requiring calibration, the same chart data is shown with toggleable threshold overlays. She sees what changes as parameters shift, and selects the view that matches her mental model.

### 3.2 Data

Use the same 7,177 bars of EURUSD 1m data from Phase 1 (2024-01-07 to 2024-01-12). All charts should use this real data.

### 3.3 Per-Primitive Specifications

#### A. FVG — Threshold Sweep

**Chart:** Real EURUSD 1m price action with FVG zones overlaid.
**Sweep values:** Minimum gap size at [0.5, 1.0, 1.5, 2.0, 2.5, 3.0] pips.
**Toggle:** User can switch between thresholds on the same chart. Show detection count per day at each threshold.
**Bug fixes applied:** Use corrected boundary (`high[i-2]` not `high[i-1]`) and anchor at candle A's time.
**Olya's task:** "Which density looks like the FVGs you'd actually mark on a chart?"
**Bonus (if feasible):** Highlight FVGs that overlap with a VI zone as `vi_confluent` with a distinct visual marker.

#### B. Swing Points — Threshold Sweep + Strength Demo

**Chart:** Real EURUSD 1m with swing high/low markers.
**Sweep values:** N=5 with minimum height filter at [1.0, 1.5, 2.0, 2.5, 3.0, 4.0] pips.
**Equality fix applied:** `>=` on left side, `>` on right side.
**Toggle:** Switch between height filter values. Show swing count per day.
**Strength concept (if feasible):** Color-code swings by a simple strength metric (e.g., number of confirming bars beyond N=5, or height in ATR units). This demonstrates the "single producer, strength attribute" concept visually.
**Olya's task:** "Which swings are the ones you'd actually mark as structural?"
**Equal H/L demo:** Show detected "equal highs" and "equal lows" at [0.5, 1.0, 1.5, 2.0, 2.5] pip tolerance. Olya says which pairs look "equal" to her.

#### C. Asia Range — Threshold Comparison

**Chart:** 5 Asia sessions (one per day) showing the range band (high-low).
**Sweep values:** Horizontal threshold lines at [12, 15, 18, 20, 25, 30] pips.
**Display:** For each threshold, mark the session as "TIGHT" (below threshold) or "WIDE" (above). Show which days trigger at each value.
**Olya's task:** "Which of these 5 sessions were consolidation to you? Which were trending?" Her binary classification determines the correct threshold.

#### D. Displacement — Dual Parameter Sweep

**Chart:** Real EURUSD 1m with displacement candles highlighted.
**Sweep values:**
- ATR multiplier: [1.0, 1.25, 1.5, 2.0] × ATR(14)
- Body/range ratio: [0.55, 0.60, 0.65, 0.70]
- Show both AND mode (both conditions required) and OR mode (either condition)
**Toggle:** Switch between ATR values and body ratio values independently. Show displacement count per session.
**Olya's task:** "Which highlighted candles represent real institutional displacement?"

#### E. NY Reversal Windows — Side-by-Side

**Chart:** 5 NY sessions showing price action with two windows marked:
- Window A: 08:00-09:00 NY (macro reversal)
- Window B: 10:00-11:00 NY (Silver Bullet)
**No sweep needed** — this is a strategic intent question, not a threshold question.
**Show:** Any notable reversals/FVGs/displacement that occurred within each window.
**Olya's task:** "Which window(s) do you watch? Both? One? Neither?"

#### F. OB Staleness (lower priority, build if time permits)

**Chart:** After displacement detector is shown, highlight the "last opposing candle" as the OB zone. Show a bar-count age label.
**Sweep values:** Fade/grey-out the OB after [5, 10, 15, 20, 30] bars without retest.
**Olya's task:** "At what age would you stop watching this OB?"

### 3.4 What NOT to Build

- No production Python algorithms (premature — params not locked yet)
- No locked code specifications (params are the input to code specs, not the other way around)
- No MMXM detection or visualization (retrospective only, build last)
- No standalone VI visualization (killed)
- No session boundary visuals (already confirmed correct)
- No v0.5 methodology format document (deferred to post-calibration)

### 3.5 Technical Notes

- Interactive HTML is the preferred format. Sliders or toggles for threshold selection.
- If a single HTML file is too complex, a small set of per-primitive HTML files is fine.
- Chart rendering: candlestick charts with overlay zones. Libraries like Plotly, Lightweight Charts, or D3 are all acceptable — whatever produces the clearest output.
- Each view should show a detection count summary (e.g., "At 2.0 pip threshold: 15 FVGs/day median [11-27 range]") so Olya can see the density impact of her choice.
- Priority order: FVG → Swing Points → Asia Range → Displacement → NY Windows → OB Staleness.

---

## 4. WHAT WE WANT FROM YOU FIRST — Before Building

**Do not start building yet.** We want your counsel first.

Please review this brief and respond with:

1. **Comprehension check:** Restate the core shift in your own words — do you see why we moved from "Olya picks numbers" to "Olya picks views"?

2. **Feasibility assessment:** For each of the 6 primitive visualizations (A–F), can you build it with the data and algorithms you already have from Phase 1? Flag any blockers.

3. **Enhancement ideas:** Anything you'd add, resequence, or change about the approach? You have the research depth — we want your input on what would make the calibration visuals most effective for a visual/intuitive trader.

4. **Questions for clarity:** Anything ambiguous or underspecified in this brief?

5. **Proposed delivery format:** Single HTML file vs multiple files? Which charting library? Estimated complexity?

We confirm alignment, THEN you build. Measure twice, cut once.

---

## 5. SUMMARY

Phase 1 told us WHAT primitives are. Phase 2 builds the calibration surface that lets our strategist visually lock the thresholds that sit between detection and strategy. The output is an interactive visual bible that turns "what number?" questions into "which view matches your trading?" questions.

The system computes. The human validates. This is the pattern.
