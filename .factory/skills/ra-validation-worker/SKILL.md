---
name: ra-validation-worker
description: Builds Phase 3.5 validation mode features (Python CLI, HTTP server, HTML/JS/CSS) with visual verification via agent-browser
---

# RA Validation Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for features that create or modify the Phase 3.5 validation mode: the detect.py CLI, serve.py write server, validate.html page, validation JS modules, and related data generation. All work is in the `site/` directory.

## Reference Documents (Read ONLY what you need)

- `site/BUILDSPEC.md` — Design system tokens (113 lines, quick read). ALWAYS read for UI features.
- `build_plan/CHART_PATTERNS_REFERENCE.md` — LC chart patterns. Read ONLY if your feature uses Lightweight Charts.
- `site/js/ground-truth.js` — Mode 1 label system. Read ONLY if building the ground truth feature (for pattern reference, do NOT modify).
- `site/js/chart-tab.js` — Mode 1 chart. Read ONLY for chart pattern reference (do NOT modify).
- `.factory/library/output_schemas.md` — Schema 4A-4E. Read ONLY if you need to understand detection data structure.

## Technology Stack

- **Python CLI:** argparse, ra.data.river_adapter, ra.evaluation.runner, ra.data.tf_aggregator, ra.config.loader
- **Python server:** http.server stdlib (extended with POST handling)
- **Price charts:** TradingView Lightweight Charts v4.1.3 (CDN)
- **Styling:** Vanilla CSS with design tokens from BUILDSPEC.md
- **No build system.** No npm, no webpack, no TypeScript. Plain HTML/JS/CSS.
- **Data:** Per-week JSON files in site/data/ loaded via fetch()

## Work Procedure

### Step 1: Understand the Feature

Read the feature description, preconditions, and expectedBehavior. Identify what files to create/modify and what to verify.

### Step 2: Read Current State

- For Python features: read existing generate scripts (site/generate_comparison_fixture.py) for patterns
- For UI features: read site/validate.html (if exists), any validate-*.js files
- For all features: read AGENTS.md for data format specs and conventions

### Step 3: Write the Code

**For Python CLI (detect.py):**
- Use RiverAdapter.load_bars(pair, start_date, end_date) — returns DataFrame
- Use aggregate(bars_1m, "5m") for TF aggregation
- Use load_config() + EvaluationRunner(config).run_locked(bars_by_tf) for detections
- Handle numpy types: subclass json.JSONEncoder, convert numpy.bool_ → bool, numpy.int64 → int, numpy.float64 → float
- Slim format: strip properties.qualifies from all detections

**For Python server (serve.py):**
- Subclass http.server.SimpleHTTPRequestHandler
- Override do_POST to match /api/labels/{week} and /api/lock-records/{week}
- Parse JSON body, write to file, return 200
- Use os.makedirs(exist_ok=True) for auto-creating directories
- Change to site/ directory for static serving

**For HTML/JS (validate.html, validate-*.js):**
- Dark theme: CSS custom properties from BUILDSPEC.md
- LC chart: follow patterns from CHART_PATTERNS_REFERENCE.md Section B
- SessionBandsPrimitive: 3-class ISeriesPrimitive (Section C)
- Detection markers: candleSeries.setMarkers() with bullish/bearish positioning
- Labels: POST to /api/labels/{week} on every label action, fetch on page load
- Perplexity attribution in head and footer

### Step 4: Verify

**For Python features:**
```bash
# CLI: run on 2-week range
python3 site/detect.py --start 2025-10-13 --end 2025-10-24 --config configs/locked_baseline.yaml --output site/data/
# Check outputs
ls site/data/detections/ site/data/candles/ site/data/sessions/
cat site/data/weeks.json
python3 -c "import json; d=json.load(open('site/data/detections/2025-W42.json')); print(len([x for p in d['detections_by_primitive'].values() for t in p.values() for x in t]))"
```

**For server features:**
```bash
python3 site/serve.py &
sleep 2
curl -sf http://localhost:8200/ | head -3
curl -X POST -H 'Content-Type: application/json' -d '{"test":true}' http://localhost:8200/api/labels/test-week
cat site/data/labels/test-week.json
lsof -ti :8200 | xargs kill 2>/dev/null || true
```

**For UI features:**
```bash
python3 site/serve.py &
sleep 2
curl -sf http://localhost:8200/validate.html | head -5
```
Then use agent-browser to navigate, screenshot, test interactions, check console.

### Step 5: Stop Server and Commit

```bash
lsof -ti :8200 | xargs kill 2>/dev/null || true
```

## Handoff Requirements

### salientSummary
1-4 sentences: what was built, what was verified, any issues found.

### whatWasImplemented
Specific files created/modified with what they contain.

### verification.commandsRun
```json
[
  {"command": "python3 site/detect.py --start 2025-10-13 --end 2025-10-24 ...", "exitCode": 0, "observation": "2 weeks generated, 19280 total detections"},
  {"command": "curl -sf http://localhost:8200/validate.html | head -5", "exitCode": 0, "observation": "Page served correctly"}
]
```

### verification.interactiveChecks
```json
[
  {"action": "Opened validate.html, selected week 2025-W42", "observed": "Chart rendered with candlesticks and detection markers, 5 day tabs visible"},
  {"action": "Clicked detection marker, labeled CORRECT", "observed": "Green ring appeared, POST sent to server, file written to disk"}
]
```

### discoveredIssues
Any issues found (severity: low/medium/high).

## Example Handoff

```json
{
  "salientSummary": "Built detect.py CLI that generates per-week detection and candle data from River parquet. Verified on 2-week range: 19,280 detections across 2 weeks, slim format (no qualifies), manifest accurate, all files < 10MB per week.",
  "whatWasImplemented": "Created site/detect.py (180 lines): argparse CLI, RiverAdapter integration, EvaluationRunner at locked params, slim JSON serializer stripping qualifies, per-week output (detections, candles, sessions), weeks.json manifest, params/locked.json snapshot, progress display, numpy type handling.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {"command": "python3 site/detect.py --start 2025-10-13 --end 2025-10-24 --config configs/locked_baseline.yaml --output site/data/", "exitCode": 0, "observation": "2 weeks generated in 6.1s. W42: 9640 dets (2.9s), W43: 9640 dets (2.8s)"},
      {"command": "python3 -c to check no qualifies field", "exitCode": 0, "observation": "0 detections have qualifies key"},
      {"command": "du -sh site/data/detections/2025-W42.json", "exitCode": 0, "observation": "5.5M — under 10MB target"}
    ],
    "interactiveChecks": []
  },
  "tests": {
    "added": [{"file": "site/detect.py", "cases": [{"name": "batch generation", "verifies": "CLI produces correct per-week files from River data"}]}]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- River parquet data missing or corrupt for requested date range
- RiverAdapter or EvaluationRunner API changed from what AGENTS.md describes
- Port 8200 already in use and can't be freed
- Mode 1 files need modification (they're off-limits)
- Feature requires modifying src/ra/ Python code
