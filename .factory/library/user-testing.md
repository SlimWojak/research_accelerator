# User Testing — Phase 3 Comparison Interface

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
