# CLAUDE.md — research_accelerator

## Purpose

Canon detection harness for en1gma. Originally built as LTF primitive locking tool; as of 2026-05-19 PIVOTED to also be the primary HTF Map V1 visual calibration surface for Olya (replacing pine_calibration sandbox in that role).

This repo's algorithms ARE en1gma canon. The 12 detector modules under `src/ra/detectors/` mirror `~/en1gma/en1gma/console/detection/ra_engine/detectors/*.py` and consume `~/en1gma/en1gma/console/detection/locked_baseline.yaml` parameters. There is no canon-mirror tax here; canon IS what runs.

## Authority anchor

- en1gma is canon authority. This repo serves it.
- Pivot context: `~/en1gma/docs/reviews/HTF_CALIBRATION_PIVOT_PINE_TO_RESEARCH_ACCELERATOR_2026_05_19.md`
- Methodology baseline: `~/en1gma/docs/reviews/PHASE_5_C2_DAILY_LED_HTF_MAP_V1_METHODOLOGY_BASELINE_RATIFIED_2026_05_05.md`
- Primitive index: `~/en1gma/docs/canonical/DETECTION_PRIMITIVES_INDEX.md`
- Standing stops bind this repo by reference: `~/en1gma/CLAUDE.md` section 6 (no B01, OB/BPR/IFVG/composite PDA work, methodology change, etc.)

## Hard rules

- This repo's detectors track en1gma canon detectors. If the two diverge, en1gma wins (CODE WINS rule per DETECTION_PRIMITIVES_INDEX.md). Re-sync against `~/en1gma/en1gma/console/detection/ra_engine/detectors/` before any methodology session.
- Parameter source of truth is en1gma `locked_baseline.yaml`. `configs/locked_baseline.yaml` here mirrors it; if you change one, change the other and document.
- Do NOT promote LOCKED status on any HTF parameter section without G + Olya signoff captured in en1gma `docs/raw/` source authority files.
- Do NOT add new detectors that don't exist in en1gma. Reuse existing primitives via composition.
- Keep tool engineering separate from methodology work. Pine_calibration's prior trap was algorithm fights; this repo's trap risk is build-system fights. Build only what an Olya labeling session needs; defer the rest.

## Phase 5 HTF Map V1 visual calibration role (NEW from pivot)

Until pivot: this repo's primary use was LTF primitive locking (locked LTF swing, displacement, MSS, FVG via Phase 3.5 validate.html with Olya).

Post-pivot: this repo extends to HTF Map V1 visual calibration. Specifically:

1. **Phase A — confirm HTF rendering works.** validate.html should render Daily candles cleanly, position detection markers at correct bar timestamps for HTF (not LTF), persist labels per Daily bar. Verify on EUR/USD Daily 2024-01-01 to 2026-03-31 window.

2. **Phase B — Map V1 visualization overlay.** Add a chart layer that surfaces the 7 Map V1 components per bar (Map Direction, Active Daily Dealing Range origin/extreme, Current Extreme, Daily Location, Daily PDA Respect/Control, First Draw + Main DOL, Daily State) plus Delivery Failure event flag and Monthly/Weekly Awareness Sidebar. Visualization spec: `~/en1gma/docs/draft_map_html/MAP_V1_GATE_2_DAILY_STATE_TABLE_PERDAY_2026_05_18.html` is the rendering target — same fields, but on a chart instead of a table.

3. **Phase C — Olya labeling workflow at HTF.** Reuse the existing CORRECT/NOISE/BORDERLINE labeling pattern but at Daily bar granularity, captured in per-day verdicts. Lock panel records per-primitive parameter decisions with provenance.

4. **Phase D — V005 sprint integration.** When V005 sprint dispatches separately (G-ratified), it consumes the verified HTF parameters from this repo's labeling sessions and writes them to `~/en1gma/en1gma/console/detection/locked_baseline.yaml`. This repo is V005's evidence source, not V005's writer.

The actual brief for Phase A through D is yet to be authored. Reusable patterns from the now-deprecated PINE_PRIMITIVE_EQUALISATION_BRIEF.md (run ledger, evaluator cadence, GOAL_EVIDENCE_BLOCK schema, orchestration protocol, halt taxonomy) are valuable; the Pine-specific scope is dead.

## What this repo provides today

Per `README.md`:

- 12 canon detector modules under `src/ra/detectors/`
- TF aggregation 1m to 5m / 15m / 1H / 4H / 1D via DuckDB
- River parquet adapter at `src/ra/data/river_adapter.py`
- 970+ tests
- `site/validate.html` — week-by-week chart with detection markers, click-to-label, lock panel
- `site/compare.html` — A/B parameter comparison with chart overlays
- `site/strategy.html` — chain composition tool
- `eval.py` CLI (sweep, compare, walk-forward)
- `run.py` cascade entry over CSV / River data
- Phase 5.5 state detection + AutoResearch harness

## Pine sandbox relationship (now PARKED)

`~/pine_calibration/pine/htf_map_v1.pine` is preserved as a sanity-check artifact on Olya's TradingView terminal. Three primitives canon-mirrored (swing_points, displacement, mss) with 11 fixes. NOT extended. Useful for ad-hoc spot-check during Olya session if she has TV open and wants live verification. NOT primary calibration surface. See `~/pine_calibration/CLAUDE.md` for PARKED status.

## Workflow per HTF calibration session

1. Author or update brief naming the Olya question to be answered (one anchor, one rule, or one parameter decision per session).
2. Confirm `~/research_accelerator/configs/locked_baseline.yaml` mirrors en1gma current state. Re-sync if drift.
3. Run cascade against agreed Daily window via `run.py` or `eval.py`.
4. Open validate.html / compare.html with HTF view active.
5. Olya labels CORRECT / NOISE / BORDERLINE per Daily bar; lock panel captures per-primitive parameter decisions.
6. Export labeled session to YAML / JSON; route to en1gma `docs/raw/OLYA_*_<date>.yaml` as source authority for V005 sprint or future Olya methodology session.
7. Do NOT write to en1gma `locked_baseline.yaml` directly; that's V005 sprint's job.

## Related repos

- `~/en1gma` — source of truth for HTF Map V1 spec and canon detection
- `~/pine_calibration` — PARKED visual sanity-check sandbox (was primary, no longer)

## Pivot lineage

- 2026-05-19 — pivot from pine_calibration (primary) to research_accelerator (primary) for HTF Map V1 visual calibration. See `~/en1gma/docs/reviews/HTF_CALIBRATION_PIVOT_PINE_TO_RESEARCH_ACCELERATOR_2026_05_19.md`.
- Pre-pivot (Q1 2026): LTF primitive locking via Phase 3.5 validate.html with Olya. Successful. UX viability for HTF labeling proven by transitive precedent.
