# User Testing

## Flow Validator Guidance: CLI (Phase 4 Parameter Search)

**Surface:** Terminal commands — search.py CLI, Python modules

**Isolation rules:**
- CLI tests are stateless — no shared state between subagents.
- Use /tmp/ for output files (e.g., /tmp/search-test-*).
- Do NOT modify source code or existing data files.
- search.py reads from data/ and configs/ — these are read-only.
- Output goes to results/ or specified --output path.

**Key files:**
- `search.py` — CLI entry point
- `configs/locked_baseline.yaml` — Base config
- `configs/search_space.yaml` — Search space definition
- `site/data/labels/2025-W43.json` — Ground truth labels (3 labels)
- `data/eurusd_1m_2024-01-07_to_2024-01-12.csv` — Regression dataset
- `results/search_results.json` — Pre-existing search results
- `site/eval/search_winner.json` — Pre-existing winner fixture

**Testing approach:**
1. Run search.py --help to verify flags
2. Run search.py with small iteration counts (2-3) for quick validation
3. Inspect output JSON structure for schema compliance
4. Use --seed for reproducibility testing
5. Check provenance fields in output
6. Test --export-winner with existing search results

## Flow Validator Guidance: agent-browser (Phase 4 Winner Review)

**Surface:** Web UI at http://localhost:8100/compare.html

**Isolation rules:**
- Read-only web UI, no backend state mutation.
- Each subagent MUST use a unique browser session ID.

**Testing approach:**
1. Navigate to http://localhost:8100/compare.html
2. Check for search_winner.json fixture in fixture switcher
3. Load winner fixture and verify Stats tab shows improvement metrics
4. Verify chart shows detection differences between baseline and winner
5. Take screenshots as evidence
6. Check browser console for errors

**Fixture details:**
- `site/eval/search_winner.json` — Schema 4A comparison fixture with search provenance (winner vs baseline)

## Phase 4 Variant Architecture Testing

### CLI Testing Surface

All variant engine, detector, and eval assertions can be tested via Python CLI. No authentication, no browser needed.

**Key files:**
- `src/ra/detectors/luxalgo_mss.py` — LuxAlgo MSS detector
- `src/ra/detectors/luxalgo_ob.py` — LuxAlgo OB detector
- `src/ra/engine/cascade.py` — CascadeEngine with variant_by_primitive support
- `src/ra/engine/registry.py` — Registry with multi-variant support
- `eval.py` — CLI with compare --variant-a/--variant-b flags
- `configs/locked_baseline.yaml` — Base config
- `data/eurusd_1m_2024-01-07_to_2024-01-12.csv` — Regression dataset

**No isolation concerns:** CLI tests are read-only and stateless. Multiple subagents can run in parallel.

### Browser Testing Surface

Variant UI assertions test compare.html on http://localhost:8100/compare.html

**Fixture for variant testing:** `site/eval/evaluation_run_variant.json` — contains a8ra_v1 and luxalgo_v1 comparison data.

**How to load variant fixture:** compare.html has a fixture switcher. Navigate to compare.html, use the fixture dropdown/switcher to select the variant comparison fixture.

## Flow Validator Guidance: CLI (Phase 4 Ground Truth Scoring)

**Surface:** Terminal commands — Python modules and eval.py CLI

**Isolation rules:**
- CLI tests are read-only and stateless — no shared state.
- Use temporary directories for output (e.g., /tmp/gt-test-*).
- Do NOT modify source code or existing data files.
- Label data: use existing site/data/labels/ directory for validate-mode labels.
- Compare-mode labels: use /tmp/test_compare_labels.json fixture.

**Testing approach:**
1. Import label_ingestion and scoring modules directly in Python
2. Run eval.py compare commands with --labels flag
3. Verify output programmatically (JSON parsing, field validation)
4. Report results in the flow JSON file

**Key files for ground-truth-scoring:**
- `src/ra/evaluation/label_ingestion.py` — Label ingestion module
- `src/ra/evaluation/scoring.py` — Scoring pipeline
- `eval.py` — CLI with compare --labels flag
- `site/detect.py` — CLI with --start/--end date range support
- `site/data/labels/` — Validate-mode labels directory (has 2025-W43.json)
- `/tmp/test_compare_labels.json` — Test compare-mode export labels
- `configs/locked_baseline.yaml` — Base config
- `data/eurusd_1m_2024-01-07_to_2024-01-12.csv` — Regression dataset

## Flow Validator Guidance: agent-browser (Phase 4 Ground Truth Dashboard)

**Surface:** Web UI at http://localhost:8100/compare.html

**Isolation rules:**
- Read-only web UI, no backend state mutation.
- Each subagent MUST use a unique browser session ID.

**Testing approach:**
1. Navigate to http://localhost:8100/compare.html
2. The page loads with default fixture (evaluation_run.json) — NO scoring data → test no-label state
3. Switch to evaluation_run_variant.json fixture — HAS scoring data → test scored display
4. Check Stats tab for Ground Truth section with P/R/F1
5. Check per-primitive breakdown and per-variant scores
6. Take screenshots as evidence
7. Check browser console for errors

**Fixture details:**
- `evaluation_run.json` — NO scoring section (test VAL-GTUI-003 no-label state)
- `evaluation_run_variant.json` — HAS scoring section with per_primitive P/R/F1 and per_variant data

## Flow Validator Guidance: CLI (Phase 4 Variant Architecture)

**Surface:** Terminal commands — Python scripts and eval.py CLI

**Isolation rules:**
- CLI tests are read-only. No shared state.
- Use `--output` to write to temporary directories if needed.
- Do NOT modify source code or existing data files.

**Testing approach:**
1. Import modules directly in Python
2. Run eval.py commands via shell
3. Inspect output programmatically
4. Report results in the flow JSON file

## Flow Validator Guidance: agent-browser (Phase 4 Variant UI)

**Surface:** Web UI at http://localhost:8100/compare.html

**Isolation rules:**
- Read-only web UI, no backend state mutation.
- Each subagent MUST use a unique browser session ID.
- No localStorage writes needed for variant testing.

**Testing approach:**
1. Navigate to http://localhost:8100/compare.html
2. The page loads with default fixture. To test variant features, need to load variant fixture.
3. Look for fixture switcher dropdown to select evaluation_run_variant.json
4. Check variant dropdown in config panel
5. Switch variants and observe marker changes
6. Check Stats tab for variant names in headers
7. Take screenshots as evidence
8. Check browser console for errors

---

## Phase 3.5 Validation Interface

**Primary URL:** http://localhost:8200/validate.html
**Write server:** http://localhost:8200 (supports GET static files + POST for labels/lock-records)

### Setup Steps (Phase 3.5)
1. Generate validation data (if not done):
   `python3 site/detect.py --start 2025-09-01 --end 2026-02-28 --config configs/locked_baseline.yaml --output site/data/`
2. Start write server:
   `cd /Users/echopeso/research_accelerator && python3 site/serve.py &`
3. Verify: `curl -sf http://localhost:8200/validate.html | head -5`
4. Stop: `lsof -ti :8200 | xargs kill 2>/dev/null || true`

### Data Persistence (Phase 3.5)
- Labels: saved to disk at `site/data/labels/{week}.json` via POST to write server
- Lock records: saved to disk at `site/data/lock-records/{week}.json` via POST
- NOT localStorage — files on disk, grep-able, machine-readable

### CLI Smoke Tests
- POST label: `curl -X POST -H 'Content-Type: application/json' -d '[{"detection_id":"test","label":"CORRECT"}]' http://localhost:8200/api/labels/test-week`
- Verify: `cat site/data/labels/test-week.json`

### Known Data Facts (2-week test data)
- Weeks available: 2025-W42 (Oct 13-17), 2025-W43 (Oct 20-24)
- Each week: ~9,500+ detections, 6 forex days
- Data paths: site/data/detections/{week}.json, site/data/candles/{week}.json, site/data/sessions/{week}.json
- Manifest: site/data/weeks.json
- Params: site/data/params/locked.json
- Labels (created by UI): site/data/labels/{week}.json
- Lock records (created by UI): site/data/lock-records/{week}.json

## Flow Validator Guidance: agent-browser (Phase 3.5 Validation Mode)

**Surface:** Web UI at http://localhost:8200/validate.html (served by serve.py write server)

**Isolation rules:**
- Write server supports both GET (static files) and POST (labels, lock-records).
- Each subagent MUST use a unique browser session ID (prefixed with worker session ID).
- Label/lock-record files are per-week. Subagents testing labels should use DIFFERENT weeks to avoid write conflicts.
- Subagent A: use week 2025-W42 for labeling tests. Subagent B: use 2025-W43 for labeling tests.
- Before testing labels, ensure no stale label files exist (start clean).

**Boundaries:**
- Do NOT modify any Python files or JS source code.
- Do NOT stop the serve.py server.
- Do NOT modify Mode 1 files or the port 8100 server.

**Testing approach:**
1. Navigate to http://localhost:8200/validate.html
2. Wait for page to load — check that week picker is populated
3. Select a week from the picker
4. Wait for chart to render (candles visible)
5. For each assertion, interact and verify
6. Check browser console for errors after key interactions
7. Report results in the flow JSON file

**Detection marker interaction:**
- Detection markers are arrows on the chart — bullish (upward) below candles, bearish (downward) above
- Click near a marker to trigger the label popover
- Markers may be dense — try zooming in first
- After labeling, a colored ring should appear (green=CORRECT, red=NOISE, yellow=BORDERLINE)

## Flow Validator Guidance: CLI/curl (Phase 3.5)

**Surface:** Terminal commands — no browser needed

**Isolation rules:**
- CLI tests (detect.py) write to site/data/ — use a TEMPORARY output directory to avoid overwriting real data
- Server tests (curl to serve.py) should use test-specific week IDs (e.g., "test-srv-week") to avoid conflicting with browser tests
- Clean up any test files created after testing

**Testing approach:**
1. For CLI assertions: run detect.py with a small date range to a temp output dir, verify file structure/content
2. For server assertions: use curl to POST/GET test data with unique week IDs
3. Verify file contents on disk after POST operations
4. Check for proper error handling (invalid JSON, etc.)

---

## Phase 3 Calibration Interface (Mode 1) — Phase 3 Comparison Interface

**What belongs here:** Testing surface, tools, URLs, setup steps, isolation notes, known quirks.

---

## Testing Surface

**Primary URL:** http://localhost:8100/compare.html
**Index page:** http://localhost:8100/

## Setup Steps

1. Generate fixture data (if not already present):
   ```bash
   cd /Users/echopeso/research_accelerator && bash site/generate_eval_data.sh
   ```

2. Start HTTP server:
   ```bash
   cd /Users/echopeso/research_accelerator && python3 -m http.server 8100 -d site &
   ```

3. Verify server running:
   ```bash
   curl -sf http://localhost:8100/compare.html | head -5
   ```

4. Stop server when done:
   ```bash
   lsof -ti :8100 | xargs kill 2>/dev/null || true
   ```

## Testing Tools

- **agent-browser**: Primary tool for visual verification. Navigate to URLs, take screenshots, interact with page elements, check console.
- **curl**: Quick smoke test for page availability.
- **Python http.server**: Serves site/ directory on port 8100. READ-ONLY (no POST/PUT support).

## Data Persistence

- **Ground truth labels**: Stored in browser localStorage (key: `gt_labels_{run_id}`)
- **Lock records**: Stored in browser localStorage (key: `lock_records_{run_id}`)
- **Export**: Download buttons produce JSON files from localStorage data
- **Isolation**: Each browser session has independent localStorage. Opening in incognito gives a clean state.

## Known Quirks

- Plotly.js CDN is 3.5MB — first load may take a few seconds on slow connections
- Lightweight Charts requires timestamps as Unix seconds (UTC trick for NY time display)
- Loading state on localhost may be too fast to capture in screenshots — verify via DOM inspection
- Session boundary data from existing `site/session_boundaries.json` is for the 5-day dataset only
- Walk-forward fixture has 0 windows (5-day dataset too short for 3-month train windows). Walk-forward tab should show "No windows" or empty state gracefully.
- The sweep JSON file is named `sweep_displacement_ltf_atr_multiplier.json` (not just `sweep_displacement.json`)

## Flow Validator Guidance: agent-browser

**Surface:** Web UI at http://localhost:8100/compare.html (served by Python http.server)

**Isolation rules:**
- This is a read-only web UI with no authentication and no backend state mutation.
- Each subagent MUST use a unique browser session ID (prefixed with worker session ID).
- localStorage is per-origin and shared across sessions on the same browser — but since we're only testing read/visual behavior (not localStorage writes), this is not a conflict concern for comparison-core milestone assertions.
- Subagents should NOT modify localStorage or create ground truth labels during comparison-core testing (those are milestone-2 features).
- All subagents can safely read the same page simultaneously since the HTTP server is read-only.

**Boundaries:**
- Do NOT click links that navigate away from compare.html (except for VAL-FOUND-010 / VAL-CROSS-P3-001 which test the index.html → compare.html navigation).
- Do NOT modify any files on disk.
- Do NOT stop the HTTP server.

**Testing approach:**
1. Navigate to http://localhost:8100/compare.html
2. Wait for page to fully load (check for loading overlay to disappear or chart to render)
3. For each assertion, interact with the page as described and take screenshots as evidence
4. Check browser console for errors after interactions
5. Report results in the flow JSON file

**Known data facts for verification:**
- Schema 4A has 2 configs: "candidate_relaxed" and "current_locked" — check configs[] array
- Fixture has 5 days of data: 2024-01-08 (Mon) through 2024-01-12 (Fri)
- Primitives with detections: displacement, fvg, mss, order_block, liquidity_sweep, swing_points, asia_range
- Walk-forward has 9 windows, verdict "CONDITIONALLY_STABLE", degradation_flag true, 8 passed / 1 failed, worst_window at index 3.
- Sweep has 7×7 2D grid: axes.x.param = "ltf.atr_multiplier" (values 1.0-3.0), axes.y.param = "ltf.body_ratio" (values 0.5-0.8). current_lock at x=1.5, y=0.6, metric_value=5247.0. plateau=null.
- Divergence index has 9832 entries across multiple primitives.

## Milestone 2 (analytics-and-annotation) Testing Notes

**localStorage isolation for GT/Lock testing:**
- Ground truth labels and lock records are stored in browser localStorage under keys like `gt_labels_{run_id}` and `lock_records_{run_id}`.
- Subagents testing GT/Lock assertions MUST clear localStorage at the start of their session to ensure clean state.
- To clear: execute `localStorage.clear()` via browser console at start.
- GT label tests require clicking on detection markers in the chart — markers must be visible (Chart tab active, at least one config enabled).
- Lock panel tests require walk-forward data to be loaded (for verdict display).

**Walk-forward specifics:**
- Walk-forward file: `site/eval/walk_forward_displacement.json`
- Has 9 windows, 8 passed, 1 failed (index 3). Verdict: CONDITIONALLY_STABLE. degradation_flag: true.
- Lock button should be enabled (verdict is CONDITIONALLY_STABLE, not UNSTABLE).

**Heatmap specifics:**
- Sweep file: `site/eval/sweep_displacement_ltf_atr_multiplier.json`
- 7×7 2D grid: atr_multiplier (7 values) × body_ratio (7 values). Should render as 2D Plotly heatmap.
- Lock marker at x=1.5, y=0.6. plateau=null (no outline expected).

**Divergence specifics:**
- Divergence data from Schema 4C pairwise section of evaluation_run.json.
- Click-to-scroll should center the chart on the divergence timestamp.
- Filter by primitive and session should update the displayed list and counts.
