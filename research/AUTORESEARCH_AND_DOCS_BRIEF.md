# ═══════════════════════════════════════════════════════════════════════════════
# AUTORESEARCH HARNESS + DOCUMENTATION REFRESH
# From: G (Sovereign) + Claude (CTO)
# To: Opus (Droid)
# Date: 2026-03-15
# Mode: Two deliverables. Build + Document.
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT
# ─────────────────────────────────────────────────────────────────────────────

context: |
  The v2 state detection logic is validated against 4 annotated trades.
  1D detection is live. The forensic analysis was done manually — Opus
  walked through each trade, checked detections, applied v2 phase logic,
  reported results. That manual process is exactly what AutoResearch
  automates.

  Simultaneously, the RA tool has grown from a simple comparison interface
  to a 6-phase research platform with detection engine, validation mode,
  strategy designer, HTF support, scrollable charts, and now state
  detection logic. The documentation has not kept pace. A fresh Opus or
  CTO session cannot currently orient from the docs alone — they'd need
  a briefing session.

  This mission delivers both: the research automation harness AND the
  documentation that makes the entire system self-orienting.

# ═══════════════════════════════════════════════════════════════════════════════
# DELIVERABLE 1: AUTORESEARCH HARNESS
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# 1. WHAT AUTORESEARCH IS
# ─────────────────────────────────────────────────────────────────────────────

autoresearch:

  concept: |
    Pattern: Karpathy AutoResearch (github.com/karpathy/autoresearch).
    We adapt the pattern, not the code.

    Core loop:
      1. Ground truth: Olya's annotated trades (date, pair, state, direction, outcome)
      2. System under test: Detection engine + v2 phase classifier
      3. Run: Execute pipeline on each trade's date range
      4. Score: Does the system correctly classify state + direction + fire chain?
      5. Diagnose: For misses, which fact / rule / threshold failed and by how much?
      6. Iterate: Adjust tunable thresholds, re-run, re-score

    Human role: Olya annotates trades (grows ground truth). G/CTO review
    findings and approve parameter changes. The harness does the iteration.

  what_it_is_NOT: |
    - NOT a trading backtest (no P&L, no Sharpe, no RR)
    - NOT an L1 parameter optimiser (Olya calibrates L1.5 visually)
    - NOT a strategy discoverer (Olya designs strategies, system validates)
    The fitness function is: "does the system see what Olya sees?"
    Precision/recall against Olya's annotations. Nothing else.

# ─────────────────────────────────────────────────────────────────────────────
# 2. GROUND TRUTH FORMAT
# ─────────────────────────────────────────────────────────────────────────────

ground_truth:

  description: |
    Each annotated trade is a YAML entry in a growing dataset file.
    Olya provides the annotations. The format must be simple enough
    that she can dictate trades and G transcribes, or she fills in
    a template directly.

  file: "research/ground_truth/annotated_trades.yaml"

  schema:
    trade:
      id: "unique identifier (e.g., trade_001)"
      date: "YYYY-MM-DD"
      pair: "EURUSD"
      execution_time: "HH:MM NY (approximate entry time)"
      kill_zone: "LOKZ | NYOKZ"
      direction: "LONG | SHORT"

      expected_state:
        htf_phase: "EXPANSION | RETRACE | RANGE | INDEPENDENT"
        direction_permission: "WITH_EXPANSION | COUNTER_ALLOWED | BOTH | INDEPENDENT"
        daily_direction: "BULLISH | BEARISH | NEUTRAL"
        authority_tf: "Daily | 4H | 1H | N/A"

      execution_chain:
        steps:
          - primitive: "liquidity_sweep | mss | displacement | fvg | ob | ote"
            tf: "15m | 5m"
            time: "HH:MM (approximate)"
        notes: "Any special conditions (e.g., SMT used as sweep substitute)"

      htf_context:
        description: "Plain text summary of HTF narrative (Olya's words)"

      strategy_type: "state_gated | asia_range_scalp | other"

  initial_dataset: |
    Pre-populate with the 4 trades already annotated:
    - trade_001: Oct 1 2025, EXPANSION bearish, short
    - trade_002: Sept 29 2025, RETRACE, counter-long
    - trade_003: Dec 12 2025, RANGE, 4H bullish long
    - trade_004: Oct 28 2025, INDEPENDENT, Asia scalp short

# ─────────────────────────────────────────────────────────────────────────────
# 3. EVALUATION HARNESS
# ─────────────────────────────────────────────────────────────────────────────

harness:

  description: |
    A Python script that reads the ground truth file, runs each trade
    through the detection pipeline + v2 phase logic, and produces a
    structured evaluation report.

  file: "tools/autoresearch/evaluate.py"

  inputs:
    ground_truth: "research/ground_truth/annotated_trades.yaml"
    detection_data: "site/data/detections/ (25 weeks, all TFs)"
    candle_data: "site/data/candles/ (25 weeks, all TFs)"
    config: "configs/locked_baseline.yaml (locked LTF + proposed HTF)"
    v2_params: |
      Classifier thresholds (can be overridden per run):
        h1_counter_persistence_bars: 3
        momentum_stall_window_daily_bars: 3
        key_level_tolerance_atr_factor: 0.5
        transition_lockout_h1_bars: 2
        retrace_to_range_daily_bars: 3
        kill_zone_realignment_lookback_hours: 2

  process:

    per_trade:
      1_load_data: |
        Load detection and candle data for the trade's date range.
        Include sufficient lookback for context:
          - State-gated trades: 2 weeks before trade date
          - INDEPENDENT trades: trade date only

      2_compute_htf_facts: |
        From detection data on Daily/4H/1H, compute:
          - daily_structure_direction (MSS invalidation-based)
          - h1_alignment (swing-primary, displacement-quality gate)
          - momentum_active (displacement recency)
          - at_key_level (spatial query)
          - premium_discount (MSS-anchored dealing range)
          - liquidity_levels_active (EQH/EQL status)

      3_classify_phase: |
        Apply v2 phase classification rules:
          - Check RANGE conditions first (daily neutral + key level + stall)
          - Check RETRACE (daily direction + h1 counter)
          - Default EXPANSION (daily direction + h1 aligned)
          - INDEPENDENT bypasses classifier

      4_determine_permission: |
        From phase:
          EXPANSION → WITH_EXPANSION_ONLY (daily direction)
          RETRACE → COUNTER_ALLOWED (both, but context noted)
          RANGE → BOTH (authority TF determines direction)
          INDEPENDENT → per strategy rules

      5_check_execution: |
        On execution TF (15m/5m), verify that the expected chain
        primitives fire within the expected time window:
          - Sweep detected?
          - MSS detected?
          - Displacement confirmed?
          - OTE zone reached?
          - Within correct kill zone?

      6_score: |
        Compare computed classification against expected_state:
          - htf_phase: MATCH | MISMATCH
          - direction_permission: MATCH | MISMATCH
          - execution_chain: FIRED | PARTIAL | MISSED
        Overall: PASS (all match) | PARTIAL (phase correct, chain partial) | FAIL

      7_diagnose: |
        For any MISMATCH or MISSED:
          - Which fact was wrong?
          - Which threshold caused the miss?
          - What value would the threshold need to be to produce correct result?
          - How far off was it? (e.g., "body_ratio 0.58 vs threshold 0.65, delta 0.07")

  output:
    file: "reports/autoresearch/eval_{timestamp}.yaml"
    sections:
      summary:
        total_trades: N
        pass: N
        partial: N
        fail: N
        score: "N/N (percentage)"
      per_trade:
        - trade_id
        - expected_state
        - computed_state
        - verdict: PASS | PARTIAL | FAIL
        - diagnostics: [list of fact/threshold mismatches]
      threshold_sensitivity:
        description: |
          For each tunable threshold, report the range that satisfies
          all PASS trades. Flag any threshold where trades conflict.
      recommendations:
        description: |
          Suggested threshold adjustments with evidence.
          Only for classifier engineering thresholds, NOT L1.5 visual params.

# ─────────────────────────────────────────────────────────────────────────────
# 4. PARAMETER SWEEP (HOOK — NOT FULL BUILD)
# ─────────────────────────────────────────────────────────────────────────────

parameter_sweep:

  description: |
    The optimiser layer. Runs evaluate.py with varying classifier thresholds
    and finds the combination that maximises score against ground truth.
    Build the HOOK now (interface for parameter override). Run the sweep
    later when ground truth dataset has 10+ trades.

  file: "tools/autoresearch/sweep.py"

  scope: |
    ONLY classifier engineering thresholds. These are tuned by AutoResearch:
      - h1_counter_persistence_bars (currently 3, sweep 2-5)
      - momentum_stall_window_daily_bars (currently 3, sweep 2-5)
      - key_level_tolerance_atr_factor (currently 0.5, sweep 0.3-0.7)
      - transition_lockout_h1_bars (currently 2, sweep 1-4)
      - retrace_to_range_daily_bars (currently 3, sweep 2-5)
      - kill_zone_realignment_lookback_hours (currently 2, sweep 1-4)

    NOT tuned by AutoResearch (Olya calibrates visually):
      - displacement_body_ratio
      - displacement_atr_multiple
      - mss_confirmation_window
      - swing_N
      - swing_height_filter
      - fvg_floor

  implementation: |
    Simple grid search over the parameter space.
    For each combination:
      1. Override v2_params in evaluate.py
      2. Run evaluation against all trades
      3. Record score
    Output: ranked parameter combinations with scores.
    When dataset is small (4-10 trades): exhaustive grid.
    When dataset grows (20+): consider smarter search (Bayesian, etc.)

  current_action: |
    Build the interface: evaluate.py accepts --param-overrides as CLI args.
    Build sweep.py that calls evaluate.py in a loop with varying params.
    Do NOT run the sweep yet — 4 trades is too few. Just wire the plumbing.

# ─────────────────────────────────────────────────────────────────────────────
# 5. WORKFLOW
# ─────────────────────────────────────────────────────────────────────────────

workflow:

  daily_use: |
    Olya annotates a trade → G adds it to annotated_trades.yaml →
    Run: python tools/autoresearch/evaluate.py →
    Review report → if PASS: ground truth grows → if FAIL: investigate

  periodic_sweep: |
    When ground truth reaches 10+ trades:
    Run: python tools/autoresearch/sweep.py →
    Review ranked parameter combinations →
    G/CTO approve adjustments → update v2_params → re-evaluate

  calibration_session: |
    When sweep suggests L1.5 visual params are borderline:
    Open calibration tool → Olya reviews specific bars →
    Confirm or adjust → lock → re-evaluate

# ═══════════════════════════════════════════════════════════════════════════════
# DELIVERABLE 2: DOCUMENTATION REFRESH
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# 6. WHAT NEEDS DOCUMENTING
# ─────────────────────────────────────────────────────────────────────────────

documentation:

  problem: |
    The RA tool has grown from a Phase 3 comparison interface to a 6-phase
    research platform. Key additions since the last doc refresh:
    - Phase 5: Strategy Designer (chain composer, evaluator, templates)
    - Phase 6: Production hardening (HTF parity, scrollable charts,
      localStorage fallback, export/import, 1D detection)
    - State Detection Logic v2 (event-cycle phase model)
    - HTF forensic analysis methodology
    - AutoResearch harness (this mission)
    - Cross-TF chains in Strategy Designer
    - Continuous scrolling across weeks on HTF

    A fresh Opus or CTO session currently cannot orient from docs alone.
    That must change.

  principle: |
    Dense, concise, complete. Not a tutorial — a reference that a machine
    or experienced human can parse in one read and know:
    - What exists
    - Where it lives
    - How it works
    - What's locked vs proposed vs deferred
    - How to run it

# ─────────────────────────────────────────────────────────────────────────────
# 7. DOCUMENTS TO UPDATE OR CREATE
# ─────────────────────────────────────────────────────────────────────────────

  documents:

    project_state:
      file: "PROJECT_STATE.md"
      action: UPDATE
      changes:
        - "Add Phase 6 (Production Hardening) to phase table"
        - "Add AutoResearch harness to tool inventory"
        - "Add State Detection Logic v2.1 status"
        - "Update calibration status: 1D detection PROPOSED"
        - "Update deployment status (localStorage fallback, export/import)"
        - "Add ground truth dataset status (4 trades annotated)"
        - "Update git history with recent commits"

    readme:
      file: "README.md"
      action: UPDATE
      changes:
        - "Update repo structure tree (new files, new directories)"
        - "Add AutoResearch section (tools/autoresearch/)"
        - "Add State Detection section (research/)"
        - "Add ground truth dataset section (research/ground_truth/)"
        - "Update quick start instructions if paths changed"

    system_architecture:
      file: "docs/ARCHITECTURE.md"
      action: CREATE
      content: |
        Complete architectural overview of the RA tool ecosystem.
        Dense M2M reference. Sections:

        1. SYSTEM OVERVIEW
           - Purpose: research platform for ICT methodology calibration
           - Relationship to core a8ra (RA proves, core consumes)
           - Design principles (quality > speed, Olya as oracle, L1/L2 separation)

        2. DETECTION ENGINE
           - CascadeEngine: 14-node dependency graph, TF-agnostic
           - detect.py: CLI, --full flag, --pair flag, timeframes
           - Locked L1 primitives: 13/13, vLOCK.yaml canonical
           - L1.5 parameters: LTF LOCKED, HTF PROPOSED
           - Detection output format: enriched JSON (tags, upstream_refs, full properties)

        3. DATA ARCHITECTURE
           - site/data/candles/: per-week candle files, all TFs including 1D
           - site/data/detections/: per-week enriched detections, all TFs
           - site/data/sessions/: session classification data
           - site/data/strategies/: saved strategy templates
           - site/data/labels/: ground truth labels (validate mode)
           - site/data/lock-records/: primitive lock records
           - 25 weeks EURUSD Sep 2025 - Feb 2026, 105,917 detections

        4. TOOL SUITE
           For each tool: URL, purpose, key features, TF support, data source.

           4a. Calibration Pages (6 charts) — localhost:8100
               FVG, Swings, Displacement, OB, NY Windows, Asia Range
               + HTF Liquidity page
               All TFs including 1H/4H/1D. Week picker on some pages.

           4b. Comparison Interface — localhost:8200/compare.html
               Multi-config overlay, stats, heatmap, walk-forward, divergence
               TF selector (1m-1D), week picker, fixture mode + detection mode
               Continuous scrolling on HTF

           4c. Validation Mode — localhost:8200/validate.html
               Ground truth labeling, lock panel, primitive toggles
               TF selector (1m-1D), 25-week picker
               Continuous scrolling, all-weeks HTF view
               Disk persistence (serve.py) + localStorage fallback

           4d. Strategy Designer — localhost:8200/strategy.html
               Chain composer (direction, steps with per-step TF, gates)
               Chain evaluator (direction/constraint/timing matching, near-miss)
               Chart overlays (green/amber bands, numbered step markers)
               Drill-down panel, convergence funnel
               Cross-TF chains, template save/load, export/import
               Continuous scrolling, all-weeks HTF view

           4e. AutoResearch Harness — tools/autoresearch/
               evaluate.py: run annotated trades through pipeline, score, diagnose
               sweep.py: grid search over classifier thresholds
               Ground truth: research/ground_truth/annotated_trades.yaml

        5. STATE DETECTION MODEL (v2.1)
           - Three HTF phases: EXPANSION, RETRACE, RANGE
           - Universal event cycle across all TFs
           - Direction permission output
           - Classifier thresholds (engineering, tunable by AutoResearch)
           - Reference: research/STATE_DETECTION_LOGIC_v2.yaml

        6. SERVING & DEPLOYMENT
           - localhost:8100: static server (calibration pages)
           - localhost:8200: serve.py (full tool suite with persistence)
           - GitHub Pages (ra-tools): static hosting with localStorage fallback
           - Export/Import for strategy templates and GT labels

        7. CONFIGURATION
           - locked_baseline.yaml: LOCKED LTF + PROPOSED HTF parameters
           - vLOCK.yaml: canonical L1 specification (DO NOT MODIFY)
           - Per-TF parameter tables for all primitives

        8. KEY CONSTRAINTS
           - L1/L2 boundary: Strategy Designer consumes, never modifies detection
           - vLOCK immutable: no parameter changes without Olya calibration session
           - Fitness function: precision/recall against Olya, never trading metrics
           - Quality > speed: every lock requires visual confirmation

    tool_guide:
      file: "docs/TOOL_GUIDE.md"
      action: CREATE
      content: |
        Quick reference for running each tool. Not architecture — operations.

        HOW TO RUN:
          Static server: cd site && python3 -m http.server 8100
          Full server: python3 site/serve.py (port 8200)
          Detection: python3 detect.py --full [--pair EURUSD] [--start DATE --end DATE]
          AutoResearch: python3 tools/autoresearch/evaluate.py
          Sweep: python3 tools/autoresearch/sweep.py

        HOW TO ADD A WEEK:
          Run detect.py with --start/--end for the new week.
          Data auto-appears in all tools.

        HOW TO ADD A TRADE ANNOTATION:
          Edit research/ground_truth/annotated_trades.yaml
          Follow the schema (trade_id, date, pair, state, chain, context)
          Run evaluate.py to validate

        HOW TO RUN OLYA CALIBRATION SESSION:
          1. Open calibration tool (localhost:8100)
          2. Select TF and dataset
          3. Review detections with Olya
          4. Adjust thresholds in locked_baseline.yaml
          5. Re-run detect.py, verify on chart
          6. Lock when confirmed

        HOW TO DEPLOY TO GITHUB PAGES:
          cd ~/ra-tools
          [copy updated files from research_accelerator/site/]
          git add . && git commit -m "description" && git push origin main
          Note: persistence uses localStorage on static hosting

    state_detection_readme:
      file: "research/README.md"
      action: CREATE
      content: |
        Index for the research/ directory:

        STATE DETECTION LOGIC:
          - STATE_DETECTION_LOGIC_v2.yaml: canonical v2.1 spec (event-cycle model)
          - HTF_FORENSIC_ANALYSIS_BRIEF.md: methodology brief for forensic analysis

        GROUND TRUTH:
          - ground_truth/annotated_trades.yaml: Olya's trade annotations (4 trades)
          - Format: see schema in file header

        REPORTS:
          - ../reports/htf_forensic_analysis_2026-03-15.yaml: parameter candidates
          - ../reports/v2_trade_validation_2026-03-15.yaml: 4-trade validation
          - ../reports/autoresearch/: evaluation run outputs

        STATUS:
          - v2.1 validated against 4 trades (4/4 PASS)
          - HTF L1.5 parameters: PROPOSED (pending Olya visual confirmation)
          - AutoResearch harness: built, sweep deferred until 10+ trades

    factory_environment:
      file: ".factory/library/environment.md"
      action: UPDATE
      changes:
        - "Add tools/autoresearch/ to directory listing"
        - "Add research/ directory to listing"
        - "Update detection data description (now includes 1D)"
        - "Add ground truth dataset reference"
        - "Update tool descriptions with current feature set"

    factory_skill:
      file: ".factory/skills/ra-engine-worker/SKILL.md"
      action: UPDATE
      changes:
        - "Add 1D to supported timeframes"
        - "Add AutoResearch harness to tool knowledge"
        - "Update study order to include v2 state detection"
        - "Add ground truth dataset as reference material"

# ─────────────────────────────────────────────────────────────────────────────
# 8. DOCUMENTATION PRINCIPLES
# ─────────────────────────────────────────────────────────────────────────────

  doc_principles:
    - "Dense and concise. No padding, no tutorials, no hand-holding."
    - "Complete. A fresh Opus session reads ARCHITECTURE.md and knows the system."
    - "Accurate. Every file path, every parameter, every URL is current."
    - "Layered. PROJECT_STATE for status. ARCHITECTURE for design. TOOL_GUIDE for ops."
    - "Machine-parseable where possible. YAML headers, structured sections."
    - "Match existing doc style in the repo. Don't introduce new conventions."

# ─────────────────────────────────────────────────────────────────────────────
# EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

execution:

  order:
    1: "Deliverable 1: AutoResearch harness"
    1a: "Create ground truth file with 4 pre-populated trades"
    1b: "Build evaluate.py (core evaluation loop)"
    1c: "Build sweep.py (parameter grid search hook)"
    1d: "Run evaluate.py against 4 trades — verify 4/4 PASS"
    2: "Deliverable 2: Documentation refresh"
    2a: "Create docs/ARCHITECTURE.md"
    2b: "Create docs/TOOL_GUIDE.md"
    2c: "Create research/README.md"
    2d: "Update PROJECT_STATE.md"
    2e: "Update README.md"
    2f: "Update .factory/library/environment.md"
    2g: "Update .factory/skills/ra-engine-worker/SKILL.md"

  delegation:
    opus: "All of it. This is architecture + analysis work, not boilerplate."

  verification:
    - "evaluate.py runs and produces 4/4 PASS report"
    - "sweep.py runs without error (even if results are trivial on 4 trades)"
    - "A fresh Opus session can read ARCHITECTURE.md and orient without briefing"
    - "All file paths in docs are accurate and current"
    - "All existing tests still pass"

# ─────────────────────────────────────────────────────────────────────────────
# CONSTRAINTS
# ─────────────────────────────────────────────────────────────────────────────

constraints:
  - "Do NOT modify vLOCK.yaml"
  - "Do NOT modify locked L1 detection algorithms"
  - "Do NOT run the parameter sweep — just build the plumbing"
  - "Do NOT invent new ground truth trades — use only the 4 annotated ones"
  - "AutoResearch tunes CLASSIFIER thresholds only, NOT L1.5 visual params"
  - "Documentation must be accurate to current state, not aspirational"

# ═══════════════════════════════════════════════════════════════════════════════
# END BRIEF — Opus: build harness, refresh docs, verify, push.
# ═══════════════════════════════════════════════════════════════════════════════
