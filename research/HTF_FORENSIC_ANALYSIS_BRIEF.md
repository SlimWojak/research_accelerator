# ═══════════════════════════════════════════════════════════════════════════════
# HTF PARAMETER FORENSIC ANALYSIS
# From: G (Sovereign) + Claude (CTO)
# To: Opus (Droid)
# Date: 2026-03-15
# Mode: ANALYSIS — no code changes, no tool modifications. Pure investigation.
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# GOAL
# ─────────────────────────────────────────────────────────────────────────────

goal: |
  We have 4 annotated trades with known-correct state classifications.
  We have a state detection model (v2) that requires L1 primitives to fire
  correctly on Daily, 4H, and 1H bars.
  We have locked L1 detection algorithms that are TF-agnostic.
  We have PROPOSED (not locked) HTF L1.5 parameters.

  YOUR TASK: Work backward from the known-correct outcomes to determine
  what parameter values would produce the correct primitive detections
  on the relevant dates.

  This is forensic analysis, not calibration. You are finding the parameter
  space that satisfies the ground truth, not proposing final values.

# ─────────────────────────────────────────────────────────────────────────────
# REFERENCE DOCUMENTS
# ─────────────────────────────────────────────────────────────────────────────

references:
  v2_spec: "STATE_DETECTION_LOGIC_v2.yaml — the state detection model"
  locked_primitives: "SYNTHETIC_OLYA_METHOD_vLOCK.yaml — L1 detection algorithms"
  current_proposed_htf:
    displacement: "body_ratio: 0.65, ATR_multiple: 1.5x, mode: AND, structure_close: required"
    mss: "confirmation_window: 1, body_ratio: 0.65, structure_close: required"
    swing_points: "N: UNDEFINED for HTF, height_filter: UNDEFINED for HTF"

# ─────────────────────────────────────────────────────────────────────────────
# THE 4 TRADES — WHAT MUST BE TRUE
# ─────────────────────────────────────────────────────────────────────────────

trades:

  trade_1:
    date: 2025-10-01
    pair: EURUSD
    v2_phase: HTF_EXPANSION_PHASE (bearish)
    direction_permission: SHORTS_ONLY
    execution_time: "LOKZ ~03:12-04:30"
    execution_chain: "Sweep 1H EQH → MSS bearish → OTE entry"

    primitives_that_must_fire:
      daily_mss_bearish:
        expected_date: "2025-09-24 or 2025-09-25"
        description: "Daily bearish MSS — the event that established bearish expansion"
        what_to_find: |
          On daily bars around Sept 24-25, a bearish MSS should fire.
          This means: a swing high was broken to the downside with
          displacement (body_ratio >= threshold, ATR >= threshold).
          FIND: the exact bar(s) where this occurs and what parameter
          values produce the detection.
      daily_displacement_bearish:
        expected_date: "2025-09-24 or 2025-09-25"
        description: "Daily bearish displacement confirming the MSS"
        what_to_find: |
          Daily bar(s) with bearish body large enough to qualify as
          displacement. What body_ratio do these bars have? What ATR
          multiple? Does the PROPOSED 0.65/1.5x fire here?
      daily_fvg_bearish:
        expected_date: "On or after 2025-09-24"
        description: "Bearish daily FVG created by the displacement"
        what_to_find: |
          Does the displacement create a 3-bar FVG on daily? If so,
          what's the gap size in pips? Is it still ACTIVE on Oct 1?
          What floor value would be needed for daily FVG detection?
      h1_mss_bearish:
        expected_date: "2025-10-01 morning (pre-LOKZ or early LOKZ)"
        description: "1H realigns bearish — confirms EXPANSION phase restored"
        what_to_find: |
          On 1H bars Oct 1 morning, does a bearish MSS fire? This is
          what transitions from RETRACE back to EXPANSION in v2.
      h1_eqh_formation:
        expected_date: "2025-09-30"
        description: "1H equal highs forming — liquidity building"
        what_to_find: |
          On 1H bars Sept 30, do equal highs form? What swing N and
          tolerance values detect them? Are they classified as UNTOUCHED
          going into Oct 1?

  trade_2:
    date: 2025-09-29
    pair: EURUSD
    v2_phase: HTF_RETRACE_PHASE
    direction_permission: COUNTER_ALLOWED (longs)
    execution_time: "NYOKZ reversal window"
    execution_chain: "SMT substitute → MSS bullish → expansion → OTE"

    primitives_that_must_fire:
      daily_mss_bearish:
        expected_date: "2025-09-24 or 2025-09-25"
        description: "Same daily bearish MSS as Trade 1 — still active, not invalidated"
        what_to_find: "Same as Trade 1. This MSS must still be the dominant structure on Sept 29."
      h1_mss_bullish:
        expected_date: "Between 2025-09-26 and 2025-09-29"
        description: "1H bullish MSS — counter to daily, triggers RETRACE phase"
        what_to_find: |
          On 1H bars between Sept 26-29, a bullish MSS should fire.
          This is the event that tells the system 1H is counter-directional.
          It must persist for 3+ consecutive 1H bars (per v2 anti-noise filter).
          FIND: when does this fire and with what parameters?
      daily_fvg_bearish_active:
        expected_date: "Still ACTIVE on 2025-09-29"
        description: "The daily bearish FVG is the pullback TARGET"
        what_to_find: |
          Is the daily bearish FVG (from Sept 24-25 displacement) still
          ACTIVE on Sept 29? Has it been partially mitigated? What's
          the zone boundary relative to price on Sept 29?

  trade_3:
    date: 2025-12-12
    pair: EURUSD
    v2_phase: HTF_RANGE_OR_UNCLEAR_PHASE
    direction_permission: BOTH (4H says bullish)
    execution_time: "NYOKZ reversal window"
    execution_chain: "Sweep sell-side → MSS bullish → OTE → target 4H expansion high"

    primitives_that_must_fire:
      daily_structure_neutral:
        expected_date: "2025-12-12"
        description: "Daily has no clear direction — at decision level"
        what_to_find: |
          On daily bars leading into Dec 12, daily structure should be
          NEUTRAL or conflicted. This means either:
          a) No recent daily MSS, or
          b) Opposing MSS events have cancelled each other, or
          c) Daily is at a key level with momentum stalled
          FIND: what does the daily bar history show? Is there a recent
          daily MSS? If so, has it been invalidated?
      daily_at_key_level:
        expected_date: "2025-12-12"
        description: "Daily at a significant HTF zone"
        what_to_find: |
          Is there an active weekly or monthly FVG near price?
          Are there untouched HTF EQH/EQL levels nearby?
          What makes this a "decision area" structurally?
      h4_expansion_bullish:
        expected_date: "From 2025-11-21 onwards"
        description: "4H has been in bullish expansion for ~3 weeks"
        what_to_find: |
          On 4H bars from Nov 21 to Dec 12, is there a bullish MSS
          followed by sustained expansion? What parameter values detect
          the 4H MSS? Is there 4H displacement? What's the expansion
          range (high/low)?
      h4_fvg_bullish:
        expected_date: "Within the 4H expansion range"
        description: "4H bullish FVG that Olya used as entry zone"
        what_to_find: |
          Active 4H bullish FVG(s) within the expansion range.
          Gap size? Still ACTIVE on Dec 12?
      h1_fvg_bullish:
        expected_date: "Overlapping with 4H FVG"
        description: "1H bullish FVG overlapping with 4H — confluence zone"
        what_to_find: |
          Active 1H bullish FVG(s) in the same price zone as 4H FVG.
          This is the "overlapping FVG" confluence Olya described.

  trade_4:
    date: 2025-10-28
    pair: EURUSD
    v2_phase: STATE_INDEPENDENT (Asia Range Scalp)
    direction_permission: "Determined by Asia Range strategy rules"
    execution_time: "NY midnight to first 2 hours LOKZ"
    execution_chain: "Asia high swept → FVG on re-entry → immediate entry → target Asia low"

    primitives_that_must_fire:
      asia_range_classification:
        expected_date: "2025-10-28"
        description: "Asia range must be <= 30 pips"
        what_to_find: |
          What was the Asia range on Oct 28? Does it classify as
          TIGHT or MID (both valid for this strategy)?
      sweep_of_asia_high:
        expected_date: "2025-10-28, ~01:00 pre-London"
        description: "Price sweeps Asia high"
        what_to_find: |
          On 5m bars, does a qualified liquidity sweep of the Asia
          high fire around 01:00? This uses LTF params (already locked).
      fvg_on_reentry:
        expected_date: "2025-10-28, shortly after sweep"
        description: "5m FVG created as price re-enters Asia range"
        what_to_find: |
          After the sweep, does price create a 5m bearish FVG as it
          closes back inside the Asia range? Gap size?

    note: |
      Trade 4 uses LOCKED LTF parameters only. No HTF calibration needed.
      Include in the analysis as a control — it should "just work" with
      existing locked params. If it doesn't, something is wrong.

# ─────────────────────────────────────────────────────────────────────────────
# ANALYSIS METHOD
# ─────────────────────────────────────────────────────────────────────────────

method:

  step_1_gather_bars:
    what: |
      For each trade, gather the raw bar data on all relevant TFs
      (Daily, 4H, 1H, 15m, 5m) covering the relevant date range.
      Trade 1+2 share context: need Sept 20 → Oct 3 at minimum.
      Trade 3: need Nov 15 → Dec 15.
      Trade 4: need Oct 27-28.
    source: "Bead field data or Phoenix River. 1m FACTs aggregated to HTF bars."

  step_2_run_detections:
    what: |
      Run the locked L1 detection algorithms on the gathered bars.
      Start with the PROPOSED HTF parameters:
        Displacement: body_ratio=0.65, ATR_multiple=1.5x, mode=AND
        MSS: confirmation_window=1, body_ratio=0.65
        Swing: try N=2 and N=3 on Daily, N=2 on 4H, N=2 on 1H
        FVG: try floor=5pip on Daily, floor=3pip on 4H, floor=1pip on 1H
      Record what fires and what doesn't.

  step_3_gap_analysis:
    what: |
      For each trade, compare actual detections against what v2 REQUIRES
      to correctly classify the trade (Section: primitives_that_must_fire).
      For each required primitive:
        - DID IT FIRE with proposed params? → record details
        - DID IT NOT FIRE? → find the actual bar values and determine
          what parameter threshold WOULD make it fire
        - DID IT FIRE BUT SHOULDN'T HAVE? → false positive. Record.

  step_4_parameter_sweep:
    what: |
      For any primitive that didn't fire with proposed params, sweep
      the parameter space to find the range that produces correct detection.
      Example: if daily MSS didn't fire at body_ratio=0.65 but the actual
      bar has body_ratio=0.58, report:
        - "Daily MSS on Sept 24 requires body_ratio <= 0.58"
        - "PROPOSED 0.65 is too restrictive for this event"
      Do this for EVERY required primitive across all 4 trades.

  step_5_cross_trade_consistency:
    what: |
      Find the parameter values that satisfy ALL 4 trades simultaneously.
      For each parameter (displacement body_ratio, MSS window, swing N, FVG floor):
        - What's the range that works for Trade 1?
        - What's the range that works for Trade 2?
        - What's the range that works for Trade 3?
        - What's the INTERSECTION across all trades?
      If no intersection exists for a parameter, flag it — this means
      the trades require different thresholds and the parameter may need
      to be TF-specific or context-dependent.

# ─────────────────────────────────────────────────────────────────────────────
# DELIVERABLE
# ─────────────────────────────────────────────────────────────────────────────

deliverable:

  format: "Structured YAML report"
  location: "reports/htf_forensic_analysis_2026-03-15.yaml"

  sections:

    1_per_trade_detection_report:
      content: |
        For each of the 4 trades:
        - All primitive events that fired (with params, timestamps, values)
        - All required primitives that did NOT fire (with actual bar values
          and the threshold that would make them fire)
        - False positives (primitives that fired but shouldn't have)
        - v2 phase classification: does it classify correctly given the
          actual detections?

    2_parameter_candidates:
      content: |
        For each HTF parameter:
        - displacement_body_ratio: candidate range from all 4 trades
        - displacement_atr_multiple: candidate range
        - mss_confirmation_window: candidate range
        - mss_body_ratio: candidate range
        - swing_N_daily: candidate range
        - swing_N_4h: candidate range
        - swing_N_1h: candidate range (may already be covered by locked LTF)
        - swing_height_daily: candidate range
        - fvg_floor_daily: candidate range
        - fvg_floor_4h: candidate range
        Cross-trade intersection for each parameter.

    3_v2_validation:
      content: |
        With the candidate parameters applied, does the v2 phase detector
        correctly classify all 4 trades?
        - Trade 1: EXPANSION → SHORTS? (expected: yes)
        - Trade 2: RETRACE → LONGS? (expected: yes)
        - Trade 3: RANGE → BOTH (4H bullish)? (expected: yes)
        - Trade 4: INDEPENDENT? (expected: yes, control)
        Walk through the phase transitions for the Sept 24 → Oct 1 sequence.

    4_gaps_and_flags:
      content: |
        - Parameters where no cross-trade intersection exists
        - Primitives that are structurally problematic on HTF
          (e.g., daily FVG floor — what gap size is meaningful on daily?)
        - Data availability issues (missing bars, insufficient history)
        - Any detection that surprises you (unexpected fires or misses)

    5_recommendation:
      content: |
        Proposed parameter values for Olya visual confirmation.
        These are the VALUES Olya will see rendered on the chart
        when we add Daily to the calibration tool.
        Present as: "With these params, here's what fires on your trade dates."

# ─────────────────────────────────────────────────────────────────────────────
# CONSTRAINTS
# ─────────────────────────────────────────────────────────────────────────────

constraints:
  - "Do NOT modify vLOCK.yaml or any locked L1 detection algorithms"
  - "Do NOT modify the RA tool code — this is analysis only"
  - "Do NOT lock any parameters — propose candidates for Olya confirmation"
  - "Use the LOCKED detection algorithms as-is, only vary L1.5 thresholds"
  - "Report honestly — if a trade cannot be made to fire with reasonable params, say so"
  - "Trade 4 uses locked LTF params only — treat as a control test"

# ─────────────────────────────────────────────────────────────────────────────
# DATA ACCESS
# ─────────────────────────────────────────────────────────────────────────────

data:

  primary: |
    Bead field at ~/data/synthetic-field (69GB, ~11.4M FACTs, EURUSD, 2021-2026).
    Contains 1m bars that can be aggregated to any TF.

  alternative: |
    If bar aggregation to Daily is not yet in the pipeline, you can
    aggregate 1m bars manually for the specific date ranges needed.
    Only 4 date ranges, small scope. Pragmatic over perfect.

  detection_engine: |
    CascadeEngine in ~/repos/research_accelerator.
    detect.py can run detection on any bar array.
    Pass aggregated daily/4H bars through the engine with varying params.

# ═══════════════════════════════════════════════════════════════════════════════
# END BRIEF — Opus: analyse, report, propose candidates. Do not build.
# ═══════════════════════════════════════════════════════════════════════════════
