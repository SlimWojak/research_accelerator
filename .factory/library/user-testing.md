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
