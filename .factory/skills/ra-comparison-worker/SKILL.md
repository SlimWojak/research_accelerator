---
name: ra-comparison-worker
description: Builds Phase 3 comparison interface features (HTML/JS/CSS) with visual verification via agent-browser
---

# RA Comparison Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for features that create or modify the comparison interface: HTML pages, JavaScript modules, CSS styling, data loading logic, chart rendering, interactive controls, and fixture data generation. Covers Phase 3 comparison features AND Phase 4 variant UI selector, ground truth dashboard. All work is in the `site/` directory.

## Reference Documents (Read ONLY what you need)

Read these ONLY when your feature requires them — do NOT read all of them:
- `.factory/library/output_schemas.md` — Schema 4A-4E structures. Read ONLY the schema sections relevant to your feature's data.
- `build_plan/CHART_PATTERNS_REFERENCE.md` — Chart code patterns. Read ONLY if your feature uses Lightweight Charts.
- `site/BUILDSPEC.md` — Design system tokens. Read ONLY if creating new CSS (113 lines, quick).
- `site/compare.html` — Read the current state. ALWAYS read this.
- `site/js/shared.js` — Shared utilities. ALWAYS read this.

## Technology Stack

- **Price charts:** TradingView Lightweight Charts v4.1.3 (CDN, global `LightweightCharts`)
- **Non-price charts:** Plotly.js 2.35.2 (CDN, global `Plotly`)
- **Styling:** Vanilla CSS with design tokens (CSS custom properties from BUILDSPEC.md)
- **No build system.** No npm, no webpack, no TypeScript. Plain HTML/JS/CSS.
- **Data:** Pre-computed JSON files loaded via `fetch()` from `site/eval/` directory

## Work Procedure

### Step 1: Understand the Feature

Read the feature description, preconditions, and expectedBehavior carefully. Identify:
- Which files need to be created or modified
- What data from Schema 4A-4E is consumed
- What user interactions are required
- Which validation assertions this feature fulfills

### Step 2: Read Current State

Read the current state of files you'll modify:
- `site/compare.html` — understand the current page structure
- `site/js/shared.js` — understand available utilities, state object, data loading
- Any existing JS module files relevant to your feature
- Check what data files exist in `site/eval/`

### Step 3: Generate Fixture Data (if needed)

If this is the foundation feature or data files are missing:
```bash
cd /Users/echopeso/research_accelerator
bash site/generate_eval_data.sh
```
Verify the JSON files exist in `site/eval/` and are valid.

### Step 4: Write the Code

For new JS modules (e.g., `site/js/chart-tab.js`):
1. Create the file with an init function (e.g., `function initChartTab()`)
2. The init function is called when the tab is activated
3. Use the global `app` state object from shared.js
4. Follow patterns from `build_plan/CHART_PATTERNS_REFERENCE.md`

For Lightweight Charts features:
- Use the exact chart creation options from CHART_PATTERNS_REFERENCE.md Section B
- Use ISeriesPrimitive 3-class pattern for overlays (Section C)
- Use candleSeries.setMarkers() for detection markers
- Use toTS() for timestamp conversion
- Call chart.timeScale().fitContent() after data load

For Plotly.js features:
- Use dark theme: `{ paper_bgcolor: '#0a0e17', plot_bgcolor: '#131722', font: { color: '#d1d4dc', family: "'IBM Plex Mono', monospace" } }`
- Use Plotly.newPlot(element, traces, layout, config)
- Set `config: { responsive: true, displayModeBar: false }`

For HTML modifications to compare.html:
- Add `<script src="js/your-module.js"></script>` before closing `</body>`
- Add tab content container if needed: `<div id="your-tab" class="tab-content">...</div>`

**IMPORTANT CSS conventions:**
- Use CSS custom properties: var(--bg), var(--surface), var(--border), var(--text), var(--teal), var(--red), var(--blue), var(--yellow), var(--mono)
- Font sizes: 11px labels, 13px body, 15px headings
- Include Perplexity attribution in `<head>` and `<footer>` (see BUILDSPEC.md)

### Step 5: Verify with agent-browser

Start the HTTP server and verify visually:

```bash
cd /Users/echopeso/research_accelerator && python3 -m http.server 8100 -d site &
sleep 2
curl -sf http://localhost:8100/compare.html | head -5
```

Use agent-browser to:
1. Navigate to http://localhost:8100/compare.html
2. Take a screenshot of the page
3. Test the specific interactions for your feature
4. Check the browser console for errors (JavaScript console)
5. Take screenshots as evidence

For each validation assertion your feature fulfills:
- Perform the action described in the assertion
- Verify the expected behavior
- Record the result in your handoff

### Step 6: Stop the HTTP Server

```bash
lsof -ti :8100 | xargs kill 2>/dev/null || true
```

### Step 7: Verification Complete

The Python test suite (631 tests, 14 minutes) tests the evaluation engine, NOT the comparison UI.
**Do NOT run it.** Your verification is complete after agent-browser visual testing in Step 5.
Commit your work and proceed to handoff.

## Handoff Requirements

### salientSummary
1-4 sentences: what was built, what was verified, any issues found.

### whatWasImplemented
Specific files created/modified with what they contain.

### verification.commandsRun
```json
[
  {"command": "curl -sf http://localhost:8100/compare.html | head -5", "exitCode": 0, "observation": "Page served correctly"}
]
```

### verification.interactiveChecks
One entry per visual verification performed:
```json
[
  {"action": "Opened http://localhost:8100/compare.html in agent-browser", "observed": "Page loaded with 4 tabs, Chart active by default, dark theme applied"},
  {"action": "Clicked Stats tab", "observed": "Stats panel visible with side-by-side config tables, Chart panel hidden"},
  {"action": "Checked browser console", "observed": "Zero errors, 2 info messages about data loading"}
]
```

### tests.added
```json
[
  {"file": "site/js/chart-tab.js", "cases": [{"name": "chart rendering", "verifies": "Candlestick chart with multi-config overlay"}]}
]
```

### discoveredIssues
Any issues found during implementation (severity: low/medium/high).

## Example Handoff

```json
{
  "salientSummary": "Built the Stats tab with side-by-side config comparison, Plotly grouped bar chart for session distribution, and cascade funnel chart. Verified in agent-browser: stats render correctly for both configs, funnel shows correct level ordering with conversion rates, zero console errors.",
  "whatWasImplemented": "Created site/js/stats-tab.js (420 lines): initStatsTab() renders comparison tables, Plotly grouped bars for by_session, direction split with teal/red coloring, and Plotly funnel chart from cascade_funnel.levels[]. Added stats tab container HTML to compare.html. Stats update when primitive selector changes.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {"command": "curl -sf http://localhost:8100/compare.html | wc -c", "exitCode": 0, "observation": "12847 bytes"}
    ],
    "interactiveChecks": [
      {"action": "Opened compare.html, clicked Stats tab", "observed": "Stats panel rendered with 2 config columns, detection counts match JSON data"},
      {"action": "Viewed session distribution bar chart", "observed": "Plotly grouped bars with 4 sessions, 2 configs, dark theme colors"},
      {"action": "Viewed cascade funnel", "observed": "6 levels displayed leaf→composite→terminal with conversion rates between levels"},
      {"action": "Changed primitive selector to fvg", "observed": "All stats updated to FVG data, bar chart re-rendered"},
      {"action": "Checked console", "observed": "0 errors, 0 warnings"}
    ]
  },
  "tests": {
    "added": [
      {"file": "site/js/stats-tab.js", "cases": [
        {"name": "stats rendering", "verifies": "Side-by-side config stats with detection counts, per-day mean/std"},
        {"name": "session bar chart", "verifies": "Plotly grouped bars for 4 sessions x N configs"},
        {"name": "cascade funnel", "verifies": "Plotly funnel with correct level ordering and conversion rates"}
      ]}
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Schema 4A/4B/4C/4D/4E data structure doesn't match what output_schemas.md specifies
- Fixture data generation (eval.py) fails or produces invalid JSON
- Plotly or Lightweight Charts CDN is unreachable
- Browser rendering issues that can't be resolved (CSP, CORS, etc.)
- Feature requires modifying Python code (Phase 3 should not touch src/ra/)
- Previous feature left compare.html in a broken state
