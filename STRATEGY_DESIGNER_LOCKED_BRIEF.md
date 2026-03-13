# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY DESIGNER — LOCKED BUILD BRIEF
# From: G (Sovereign) + Claude (CTO) + Opus (Architecture)
# To: Opus (Droid) — overnight autonomous build with sub-agents
# Date: 2026-03-13
# Status: LOCKED — architecture reviewed, adjustments applied, build authorised
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# 1. OUTCOME
# ─────────────────────────────────────────────────────────────────────────────

outcome: |
  Olya's sovereign strategy tool. She opens a known good week, sets a
  direction, composes a primitive chain describing her trade setup, and the
  chart instantly lights up showing every point where that chain fires
  (green), nearly fires (amber), or doesn't match.

  She clicks any match to drill down into the exact primitive sequence with
  timestamps. Near-misses show exactly which primitive failed and why. She
  saves strategies as named templates for reuse.

  When done: Olya says "the system catches the trades I would take, and I
  can see exactly why."

success_criteria:
  - Open a week she knows had a great trade
  - Define a primitive chain describing her strategy
  - Instantly see every point in the dataset where the chain fires
  - Click any match and see the exact primitive sequence with timestamps
  - See near-misses and understand which primitive failed and why
  - Save her strategy as a named template for reuse
  - Do all of the above independently, without CTO assistance

# ─────────────────────────────────────────────────────────────────────────────
# 2. HARD CONSTRAINTS
# ─────────────────────────────────────────────────────────────────────────────

constraints:

  l1_l2_boundary: |
    The Strategy Designer CONSUMES locked L1 detection output. It does NOT
    modify detection parameters. No sliders for body_ratio, ATR thresholds,
    or any L1.5 parameter. vLOCK parameters are immutable from this tool.
    If a near-miss reveals a threshold issue, that finding goes back to a
    calibration session — not a UI control.

  no_trading_metrics: |
    No win_rate, no RR, no Sharpe, no drawdown in v1. The Strategy Designer
    answers "does this pattern exist in the data?" Backtesting answers "is
    this pattern profitable?" — that's Dexter's job. Convergence funnel
    stats (fire rates per step) are fine — that's chain diagnostics, not
    trading performance.

  direction_first_class: |
    Direction (Bullish/Bearish) is the outer frame, not an optional filter.
    Set first, filters everything downstream. Templates use direction_match:
    "same" so one template works for both directions.

  palette_matches_locked_l1: |
    Only primitives with LOCKED L1 status in vLOCK.yaml belong in the menu.
    No Equal HL (DEFERRED), no Premium/Discount as standalone (part of OTE),
    no Window B (Olya excluded it).

  do_not_modify: |
    - SYNTHETIC_OLYA_METHOD_vLOCK.yaml
    - Any locked primitive detection logic
    - Existing validate.html functionality
    - Slim detection output format (enrich additively, don't break existing)

# ─────────────────────────────────────────────────────────────────────────────
# 3. ARCHITECTURE (LOCKED)
# ─────────────────────────────────────────────────────────────────────────────

architecture:

  location: |
    New page: site/strategy.html
    Served alongside existing calibration tool (serve.py port 8200).
    NOT an extension of validate.html (different mental model, different UX).
    Same vanilla HTML/JS + LWC + Plotly stack. No new frameworks.

  modules:
    - strategy-app.js      # state management, data loading, week/day nav
    - strategy-chart.js    # chart rendering, markers, chain highlight overlays
    - strategy-chain.js    # chain definition UI, evaluator, near-miss diagnostics
    - strategy-templates.js # save/load/manage named strategy templates

  reusable_from_existing:
    - toTS() timestamp conversion (shared.js)
    - Session band rendering (VSessionBandsPrimitive)
    - Candle loading + day tabs + TF buttons (validate-app.js patterns)
    - Primitive color palette (shared.js)
    - Dark theme + LWC chart config (validate-chart.js)

# ─────────────────────────────────────────────────────────────────────────────
# 4. DETECTION DATA: ENRICHED OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

detection_enrichment:

  approach: |
    Add --full flag to detect.py. When set, skip slim_detection() and
    serialize the full Detection dataclass with all properties intact.
    Write to the SAME site/data/detections/ directory. validate.html
    ignores extra fields. One directory, one format, no sync problem.
    ~3x file size increase is negligible (~50KB → ~150KB per week per TF).

  gating_note: |
    THIS IS TASK 1. It gates everything else. The slim format is missing:
    - MSS: broken_swing, displacement sub-object, fvg_created, window_used
    - OTE: fib level prices, range_high/low, P/D midpoint
    - Order Block: zone_body, mss_direction, displacement_grade, state
    - FVG: zone_top, zone_bottom, ce, lifecycle state
    - Liquidity Sweep: source, qualified_sweep, rejection_wick_pct
    - All primitives: tags (kill_zone, session), upstream_refs
    These fields already exist in the engine output — slim_detection()
    just discards them.

  enriched_format_example: |
    {
      "id": "mss_5m_2025-10-01T03:25:00_bear",
      "time": "2025-10-01T03:25:00",
      "direction": "bearish",
      "type": "mss",
      "price": 1.08391,
      "properties": {
        "break_type": "REVERSAL",
        "forex_day": "2025-10-01",
        "session": "lokz",
        "tf": "5m",
        "broken_swing": {"type": "SwingHigh", "price": 1.08432, "time": "..."},
        "displacement": {"atr_multiple": 1.82, "body_ratio": 0.72, "quality_grade": "VALID"},
        "fvg_created": true,
        "window_used": 0
      },
      "tags": {
        "session": "lokz",
        "kill_zone": "lokz",
        "forex_day": "2025-10-01"
      },
      "upstream_refs": ["displacement_5m_...", "swing_points_5m_..."]
    }

  regeneration: |
    After enriching detect.py, regenerate all 25 weeks (Sep 2025 – Feb 2026)
    with --full flag. ~10-15 minutes based on existing pipeline speed.

# ─────────────────────────────────────────────────────────────────────────────
# 5. CHAIN EVALUATION: CLIENT-SIDE
# ─────────────────────────────────────────────────────────────────────────────

evaluator:

  runs_in: browser (JavaScript)
  reason: |
    ~4000 events per week per TF. Linear scan with indexed lookups.
    Sub-millisecond evaluation. Instant feedback when Olya changes a step.
    No server round-trip.

  algorithm: |
    1. Pre-index: group detections by (forex_day, kill_zone) into temporal index
    2. For each Step 1 candidate matching direction + constraints:
       a. Walk forward through subsequent steps
       b. Search temporal index within timing window for each step
       c. Check step-specific constraints (session, grade, zone overlap)
       d. Accumulate chain_context: earlier steps provide context to later steps
          (e.g., MSS dealing range feeds OTE zone check)
       e. Record: FULL_MATCH / NEAR_MISS (N-1) / NO_MATCH
    3. For near-misses: record which step failed, why, specific values vs thresholds
    4. Return: ChainMatch[] with timestamps, step details, failure diagnostics

  chain_context: |
    CRITICAL: As the evaluator walks steps, earlier matched detections
    accumulate in a context object. Later steps can reference earlier results:
    - Step 2 (MSS) establishes the dealing range
    - Step 3 (OTE) is computed FROM that dealing range
    - Step 4 (FVG in OTE zone) checks spatial overlap against Step 3's zone
    Without chain context, the evaluator can't verify cross-step relationships.

  spatial_constraints: |
    "FVG in OTE zone" is a SPATIAL check, not just temporal. The evaluator
    resolves in_ote_zone: true by finding the active OTE zone from chain
    context and checking price level overlap against FVG zone_top/zone_bottom
    or OB zone_body. The enriched detection format carries these fields.

# ─────────────────────────────────────────────────────────────────────────────
# 6. STRATEGY DEFINITION SCHEMA (LOCKED)
# ─────────────────────────────────────────────────────────────────────────────

schema:
  version: "1.0"
  note: |
    Every template Olya saves becomes a regression test for the full L1+L2
    stack AND the handoff contract to Dexter for backtesting. This schema
    must be self-contained — all information needed to evaluate the chain
    against any dataset, no implicit state.

  example: |
    {
      "schema_version": "1.0",
      "name": "Asia Sweep London Reversal",
      "direction": "bearish",
      "description": "Sweep of Asia high in LOKZ, MSS with displacement, OTE retrace, FVG/OB entry",
      "created_at": "2026-03-14T10:30:00",
      "updated_at": "2026-03-14T10:30:00",

      "steps": [
        {
          "step": 1,
          "primitive": "liquidity_sweep",
          "label": "Sweep of Asia high",
          "direction_match": "same",
          "constraints": {
            "qualified_sweep": true
          },
          "timing": { "mode": "chain_start" }
        },
        {
          "step": 2,
          "primitive": "mss",
          "label": "Structure shift",
          "direction_match": "same",
          "constraints": {
            "break_type": "REVERSAL",
            "displacement_grade_min": "VALID"
          },
          "timing": { "mode": "after_previous", "window": "same_kill_zone" }
        },
        {
          "step": 3,
          "primitive": "ote",
          "label": "OTE zone reached",
          "direction_match": "same",
          "constraints": {
            "fib_range": [0.618, 0.79]
          },
          "timing": { "mode": "after_previous", "window": "same_kill_zone" }
        },
        {
          "step": 4,
          "primitive": ["fvg", "order_block"],
          "label": "PDA for entry",
          "direction_match": "same",
          "constraints": {
            "in_ote_zone": true
          },
          "timing": { "mode": "after_previous", "window": "same_kill_zone" }
        }
      ],

      "gates": {
        "kill_zone": ["lokz", "nyokz"],
        "asia_range_tier": ["tight", "mid"]
      }
    }

  schema_design_decisions:
    direction_match: |
      "same" = match strategy direction. "opposing" = opposite.
      Templates are direction-agnostic — flip by changing top-level direction.
    primitive_as_array: |
      OR semantics. ["fvg", "order_block"] = match if ANY fires.
      Olya's chains often end with "FVG or OB in the zone."
    gates: |
      Global filters on the entire chain, not individual steps.
      kill_zone gate = chain must START within a kill zone.
      asia_range_tier gate = filter which days qualify.
    timing_window: |
      See timing model below. Default: same_kill_zone.
    tf_per_step: |
      Optional "tf" field per step exists in schema. V1 UI uses single
      TF selector at top. Cross-TF chains are Phase 2 — schema is ready,
      UI defers. No migration needed later.

# ─────────────────────────────────────────────────────────────────────────────
# 7. TIMING CONSTRAINT MODEL (LOCKED)
# ─────────────────────────────────────────────────────────────────────────────

timing:

  default: same_kill_zone

  modes:
    same_bar:       "Step B on exact same candle as Step A"
    same_kill_zone: "Step B within same kill zone (LOKZ 02-05 / NYOKZ 07-10). DEFAULT."
    same_session:   "Step B within same session boundary (asia/lokz/nyokz)"
    same_day:       "Step B within same forex day"
    within_bars_N:  "Step B within N bars on active TF"

  implementation: |
    Resolved via tag comparison on enriched detections:
    - same_kill_zone: a.tags.kill_zone === b.tags.kill_zone && !== null
    - same_session: a.tags.session === b.tags.session
    - same_day: a.properties.forex_day === b.properties.forex_day
    - within_bars_N: abs(b.bar_index - a.bar_index) <= N
    - same_bar: a.time === b.time
    Temporal ordering enforced: Step B time >= Step A time (sequential).

# ─────────────────────────────────────────────────────────────────────────────
# 8. SMART DEFAULTS PER PRIMITIVE (CTO ADJUSTMENT)
# ─────────────────────────────────────────────────────────────────────────────

smart_defaults:
  note: |
    When Olya adds a step, it comes pre-configured with the settings she'd
    use 80% of the time. Constraints are an expandable "advanced" section,
    NOT the primary interface. The chain builder stays light and clean.

  primitives:
    liquidity_sweep:
      default: { qualified_sweep: true }
      advanced: [source filter, min_breach_pips]
    mss:
      default: { break_type: REVERSAL, displacement_grade_min: VALID }
      advanced: [fvg_created, window_used]
    displacement:
      default: { quality_grade_min: VALID }
      advanced: [body_ratio_min, atr_multiple_min, type]
    fvg:
      default: { state: ACTIVE }
      advanced: [min_gap_pips, zone_top/bottom filter]
    order_block:
      default: { state: ACTIVE, zone_type: body }
      advanced: [min_displacement_grade, staleness]
    ote:
      default: { fib_range: [0.618, 0.79] }
      advanced: [include 0.50, P/D midpoint]
    session_liquidity:
      default: { classification: CONSOLIDATION_BOX }
      advanced: [efficiency/balance thresholds]
    asia_range:
      default: { tier: [tight, mid] }
      advanced: [specific pip range]
    htf_eqh_eql:
      default: { status: UNTOUCHED, min_touches: 2 }
      advanced: [TF filter]
    kill_zone:
      default: { window: [lokz, nyokz] }
      advanced: [specific time range]
    reference_levels:
      default: "(no filter — all levels)"
      advanced: [specific level type PDH/PDL/MO/EQ]

# ─────────────────────────────────────────────────────────────────────────────
# 9. CHART RENDERING
# ─────────────────────────────────────────────────────────────────────────────

rendering:

  reuse: |
    Chart creation, candle loading, session bands, day tabs, TF buttons,
    week picker — all reuse patterns from validate-app.js / validate-chart.js.

  new_components:

    chain_highlight_overlay: |
      New ISeriesPrimitive (same pattern as VSessionBandsPrimitive).
      - GREEN band rgba(38,166,154,0.25): full chain match time range
      - AMBER band rgba(247,197,72,0.20): near-miss time range
      - zOrder: bottom, behind candles and markers

    numbered_step_markers: |
      On chain match selection (click), standard markers replaced with
      numbered markers (1, 2, 3, 4) in highlight color. LWC native marker
      API with text field.

    drill_down_panel: |
      Right sidebar (400px, slide-in, same pattern as validate-gt.js lock
      panel). Shows per-step detail:
      - Step number, primitive name, timestamp, PASS/FAIL
      - PASS: detection details (level, body_ratio, grade, zone)
      - FAIL: specific diagnostic (value vs threshold, reason string)

    convergence_funnel: |
      Stats panel (below chart or collapsible bottom section). Shows:
      - Fire rates per step: "Sweep 8x → MSS 6x → OTE 4x → Entry 3x"
      - Failure distribution: "Step 3 (OTE) failed 60% of near-misses"
      - Per day/week totals: N full matches, M near-misses
      NOT trading performance. Chain convergence diagnostics only.

  left_panel_chain_builder: |
    Replaces primitive toggle panel from validate.html.
    1. Direction selector (Bull/Bear toggle) — prominent, top of panel
    2. Step list — cards with: step number, primitive dropdown, smart
       defaults shown, constraints expandable as "advanced"
    3. "+ Add Step" button
    4. Gates section (kill zone, asia range tier)
    5. Template controls (Save / Load / name field)
    No drag-and-drop. Add sequentially. Reorder via arrows. Delete via X.

# ─────────────────────────────────────────────────────────────────────────────
# 10. TEMPLATE PERSISTENCE
# ─────────────────────────────────────────────────────────────────────────────

templates:

  storage: site/data/strategies/{template_name}.json
  server: |
    Extend serve.py with POST endpoint for save, GET for list/load.
    Same pattern as existing label persistence in validate mode.
  format: |
    The strategy schema from Section 6. Self-contained JSON.
    Each saved template = regression test for L1+L2 stack.
    Each saved template = Dexter backtest handoff contract.

# ─────────────────────────────────────────────────────────────────────────────
# 11. IMPLEMENTATION ORDER + MODEL DELEGATION
# ─────────────────────────────────────────────────────────────────────────────

implementation:

  order:
    1:
      task: "Enrich detect.py with --full flag"
      description: "Preserve all detection fields. Same output directory. validate.html ignores extras."
      model: Sonnet
      gates: "Everything downstream"
    2:
      task: "Regenerate 25 weeks enriched data"
      description: "Run enriched pipeline over Sep 2025 – Feb 2026 dataset"
      model: script run
    3:
      task: "strategy.html scaffold + base UI"
      description: "Page structure, CSS, four JS module stubs. Week picker, day tabs, TF selector, direction toggle. Reuse validate patterns."
      model: Sonnet
    4:
      task: "Chain builder UI (left panel)"
      description: "Direction selector, step cards with smart defaults, add/remove/reorder, gates section, template name field. Constraints as expandable advanced."
      model: Sonnet
    5:
      task: "Chain evaluator engine"
      description: "strategy-chain.js: pre-indexing, temporal walk, constraint matching, chain context accumulation, spatial constraint resolution, near-miss diagnostics."
      model: "Opus review + Sonnet code. This is the core logic — Opus architects the evaluator, Sonnet implements."
    6:
      task: "Chart rendering overlays"
      description: "Highlight bands (green/amber), numbered step markers on selection, drill-down panel (right sidebar), convergence funnel stats."
      model: Sonnet
    7:
      task: "Template save/load"
      description: "serve.py POST endpoint, save/load/list in UI, site/data/strategies/ directory."
      model: Sonnet
    8:
      task: "Integration testing"
      description: "Load known good weeks, define chains matching calibration session trades, verify green/amber/nothing fires correctly."
      model: Opus

  delegation_principle: |
    Opus: architects, reviews core logic (evaluator), integration tests.
    Sonnet: writes code (UI, rendering, data pipeline, persistence).
    Codex: boilerplate, repetitive patterns, CSS, module scaffolding.
    Opus does NOT write boilerplate. Sonnet does NOT architect the evaluator.

# ─────────────────────────────────────────────────────────────────────────────
# 12. NOT IN V1
# ─────────────────────────────────────────────────────────────────────────────

deferred:
  - "Replay mode (bar-by-bar playback) — Phase 2"
  - "Drag-and-drop chain builder — use list-based UX"
  - "Parameter adjustment sliders — hard no, L1/L2 boundary"
  - "Trading analytics (win rate, RR, drawdown) — Dexter's job"
  - "Pattern extraction / clustering — Phase 2"
  - "Cross-TF chains in UI — schema supports it, UI defers to Phase 2"
  - "HTF bias integration (weekly/daily reading) — future phase"

# ─────────────────────────────────────────────────────────────────────────────
# 13. REFERENCE
# ─────────────────────────────────────────────────────────────────────────────

reference:
  canonical_spec: "SYNTHETIC_OLYA_METHOD_vLOCK.yaml (repo root)"
  project_state: "PROJECT_STATE.md"
  calibration_tool: "localhost:8100 (existing rendering pipeline)"
  walk_forward: "reports/walk_forward_stability_2025-09_2026-02.yaml"
  cto_broadcast: "CTO_BROADCAST_2026-03-13.md"
  strategy_ideas: "STRATEGY_DESIGNER_IDEAS.md (background, not spec)"
  detection_output: "pipeline output + test fixtures for field shapes"

# ═══════════════════════════════════════════════════════════════════════════════
# BUILD AUTHORISED — G + CTO — 2026-03-13
# Opus: read, orient from PROJECT_STATE.md, cook overnight with sub-agents.
# ═══════════════════════════════════════════════════════════════════════════════
