# Mirror Real-Time Enhancements Design

**Date:** 2026-03-23
**Status:** Approved
**Author:** COO (Claude Code)
**Scope:** P1-P3 enhancements to make mirror.a8ra.com a genuine real-time projection of a8ra system state

## Problem

The mirror dashboard at mirror.a8ra.com serves live EURUSD candlestick charts via WebSocket but has three categories of limitation:

1. **No live detections** — Detection pipeline (`daily_detection_export.py`) is batch-only. The detection directory was empty until manually seeded. No signals fire in real time.
2. **Single-TF push** — Backend only streams 5m bars. Switching timeframes falls back to REST, breaking the real-time feel.
3. **UX bugs** — WebSocket URL was hardcoded to localhost (broken via Cloudflare), NOW button was dead, status badge never updated correctly. (P0 fixes already applied.)

Olya needs to monitor a8ra system state alongside her TradingView screen — detections, signals, and WorldState updating in real time across all timeframes.

## Architecture

Two-process model communicating via filesystem:

```
start-mirror.sh
  ├── server.py (port 8300)           — frontend, WebSocket, REST API
  └── detection_runner.py              — 5m cycle, writes detection JSON
       │
       └── writes → ~/dexter/output/detections/{date}.json
                          │
       server.py watches ←┘ (watchdog observer)
                          │
       broadcasts → WS clients (detections + world_state + signals)
```

Cloudflare tunnel (`a8ra-mirror`) proxies mirror.a8ra.com → localhost:8300. The `http://` service type handles WebSocket upgrade natively — no config change needed.

## Component 1: Detection Runner

**File:** `mirror/backend/detection_runner.py`

Standalone daemon that runs the full dexter detection pipeline on a schedule and writes results to the standard detection output directory.

### Lifecycle

1. Boot: determine today's forex day, run full pipeline immediately, write JSON
2. Sleep 5 minutes
3. Wake: check if forex day rolled (17:00 NY), re-run pipeline for current day, write JSON
4. Repeat until SIGINT/SIGTERM

### Pipeline Reuse

Imports `run_pipeline()` from `dexter/scripts/daily_detection_export.py`. No producer logic duplicated. The runner is a thin scheduling wrapper.

**Calling convention:** `run_pipeline(today, today)` where `today` is `date.fromisoformat(forex_day)`. The function takes a date range — for single-day real-time use, start == end. The summary file (`{date}_{date}_summary.json`) gets overwritten each cycle, which is fine — `_available_detection_dates()` in server.py already filters by 10-character stems only.

### Market-Aware Scheduling

- Market hours (weekday): 5-minute cycle
- Market closed (Fri 17:00 NY → Sun 17:00 NY): 30-minute cycle
- Detection via staging file existence (same logic as server.py `_determine_market_state`)

### Status File

Writes `~/.mirror-runner-status.json` after each cycle:

```json
{
  "last_run": "2026-03-23T14:40:00Z",
  "forex_day": "2026-03-23",
  "bars_loaded": 1440,
  "detections_written": 167,
  "signals_emitted": 3,
  "error": null,
  "next_run": "2026-03-23T14:45:00Z"
}
```

### Error Handling

- Pipeline exceptions: log, write error to status file, sleep 5 minutes, retry
- No River data (weekend): detect early, sleep 30 minutes
- Never crash the loop

### Atomic File Writes

The runner MUST write detection JSON atomically to prevent the server's watchdog from reading partial/corrupt files. Pattern: write to a temp file in the same directory, then `os.rename()` into place. `os.rename()` is atomic on POSIX filesystems (APFS/HFS+). This also prevents the watchdog from firing multiple events during a long write.

## Component 2: Detection File Watcher

**File:** Addition to `server.py`

### Changes

- New `DetectionFileHandler` class watching `~/dexter/output/detections/` for `.json` modifications. Same watchdog pattern as existing `StagingFileHandler`.
- On file change: reload detection JSON, compare against cached state, broadcast if different.
- Broadcasts three message types: `detections`, `world_state`, `signals`.
- Replaces the existing `_detection_refresh_loop` (5-min async polling) with event-driven file watching.

### Broadcast Flow

```
detection_runner.py writes 2026-03-23.json
  → watchdog fires DetectionFileHandler.on_modified
    → reload JSON, update cached_detections + cached_world_state
      → broadcast({type: "detections", data: ...})
      → broadcast({type: "world_state", data: ...})
      → broadcast({type: "signals", data: ...})
```

Sub-second latency from runner write to browser update.

### Edge Cases

- **Watchdog debounce:** macOS FSEvents can fire multiple `on_modified` for a single write. Use a content-hash or mtime comparison guard (similar to `StagingFileHandler`'s `last_known_sizes` pattern) to avoid redundant reloads.
- **Missing `world_state`:** Early in a forex day, no HTF bar boundaries may have occurred yet, so detection JSON may lack `world_state`. The server should retain the previous cached `world_state` rather than clearing it.
- **Forex day rollover:** When the runner writes a new day's file, the server picks it up via watchdog. The server should update its internal `load_date` tracking to match the new file's forex day. Bars may still be from the previous day until new staging data arrives — this is acceptable (the chart will update when bars flow in).
- **Remove polling loop:** The existing `_detection_refresh_loop` and `DETECTION_REFRESH_INTERVAL` are replaced entirely by the watchdog. Remove the polling task from `ServerState` and `lifespan()`.

## Component 3: Multi-TF Push

**Files:** `server.py`, `mirror-app.js`

### server.py Changes

`StagingFileHandler._handle_new_bars` changes from pushing only 5m to pushing all standard timeframes on each staging update:

```python
for tf in ["1m", "5m", "15m", "1H", "4H"]:
    bars = _load_bars_as_dicts(date_str, tf)
    await broadcast({"type": "bars", "tf": tf, "data": bars})
```

1D excluded — daily bars update once, REST endpoint suffices.

### mirror-app.js Changes

The `bars` message handler already keys by TF (`mApp.candleData[msg.tf] = msg.data`). All incoming TF data is always cached regardless of active TF (so switching TFs is instant without REST fallback). Change: only call `refreshMirrorChart()` when the incoming TF matches the active TF to avoid unnecessary re-renders.

### Signal Feed Deduplication

The server broadcasts `detections` and `signals` as separate messages. The frontend's `updateFeedFromDetections()` rebuilds the feed from scratch, but `addSignalsToFeed()` prepends without dedup. To prevent duplicates: the `signals` broadcast should be removed from the detection file handler — signals are already embedded in the detection JSON under `diagnostic_signals` and get rendered by `updateFeedFromDetections()`. Only broadcast `detections` and `world_state` from the file watcher.

### Why Not Per-Client Subscriptions

With 1-2 clients the overhead of extra TF payloads is negligible. Per-client subscription tracking adds complexity without benefit at this scale.

## Component 4: Launcher Script

**File:** `mirror/start-mirror.sh`

### Usage

```bash
./start-mirror.sh          # start both processes
./start-mirror.sh stop     # graceful shutdown
```

### Behavior

- Starts `server.py` and `detection_runner.py` as background children
- Both log to stdout, prefixed with `[SERVER]` / `[RUNNER]`
- Traps SIGINT/SIGTERM, forwards to both children for clean shutdown
- Health check: if either process dies, logs which one and restarts after 5s
- Writes PID file to `/tmp/mirror.pid` for `stop` command
- Sets PYTHONPATH and venv per process:
  - server.py: `~/research_accelerator/.venv`
  - detection_runner.py: `~/dexter/.venv` + `PYTHONPATH=~/dexter/dexter`

### Not In Scope

- No log rotation (pipe to `tee` if needed)
- No boot-on-startup (graduate to launchd later)
- No resource limits (M3 Ultra has headroom)

## P0 Fixes Already Applied

For completeness, these were fixed earlier in this session:

1. **WebSocket URL** — `mirror-app.js` now derives `ws://`/`wss://` from `location.protocol` + `location.host`
2. **NOW button** — Selector fixed from `#btn-now` to `#now-btn`
3. **Status badge** — Handler now reads `msg.data.state` correctly; CSS class names aligned; WS dot syncs
4. **Detection data seeded** — Ran `daily_detection_export.py` for Mar 20-23, output directory populated

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Runner cycle time | 5 minutes | Aligns with primary 5m analysis TF, responsive without hammering producers |
| Pipeline mode | Full replay per cycle | Reuses proven pipeline, guarantees correctness, 10s compute is negligible on M3 Ultra |
| Process model | Separate process | Crash isolation, independent restarts, no async loop blocking |
| Inter-process communication | Filesystem (detection JSON) | Natural interface, format already exists, server already reads it |
| TF push strategy | All TFs on each update | Simple, negligible overhead at 1-2 client scale |
| Process management | Launcher script | One command to start/stop, light and transparent |

## File Changes Summary

| File | Action |
|---|---|
| `mirror/backend/detection_runner.py` | **New** — incremental detection daemon |
| `mirror/backend/server.py` | **Edit** — add detection file watcher, multi-TF push, remove polling loop |
| `mirror/js/mirror-app.js` | **Edit** — conditional chart refresh on active TF match |
| `mirror/start-mirror.sh` | **New** — launcher script |
