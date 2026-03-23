# Mirror Real-Time Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make mirror.a8ra.com a genuine real-time projection of a8ra system state — live detections, multi-TF bars, and WorldState streaming to Olya's browser.

**Architecture:** Two-process model (server + detection runner) communicating via filesystem. Runner writes detection JSON every 5 minutes, server watches via watchdog and broadcasts to WebSocket clients. Launcher script manages both processes.

**Tech Stack:** Python 3 (FastAPI, watchdog, uvicorn), vanilla JS (LightweightCharts), bash

**Spec:** `docs/superpowers/specs/2026-03-23-mirror-realtime-enhancements-design.md`

---

## File Structure

| File | Role | Action |
|---|---|---|
| `mirror/backend/detection_runner.py` | Standalone daemon — runs dexter pipeline every 5m, writes detection JSON atomically | **Create** |
| `mirror/backend/server.py` | FastAPI backend — add detection file watcher, multi-TF push, remove polling loop | **Modify** |
| `mirror/js/mirror-app.js` | Frontend WS client — conditional chart refresh on active TF only | **Modify** |
| `mirror/start-mirror.sh` | Launcher — starts both processes, health checks, clean shutdown | **Create** |

---

### Task 1: Detection Runner

**Files:**
- Create: `mirror/backend/detection_runner.py`

- [ ] **Step 1: Create the detection runner script with imports and constants**

```python
"""MIRROR Detection Runner — runs dexter pipeline every 5 minutes.

Standalone daemon. Writes detection JSON atomically to
~/dexter/output/detections/{forex_day}.json for the server's
watchdog to pick up.

Usage:
    python detection_runner.py
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DEXTER_ROOT = Path(os.environ.get("DEXTER_ROOT", str(Path.home() / "dexter")))
DEXTER_PKG = DEXTER_ROOT / "dexter"
DEXTER_SCRIPTS = DEXTER_ROOT / "scripts"
RIVER_ROOT = Path(os.environ.get("RIVER_ROOT", str(Path.home() / "phoenix-river")))
STAGING_DIR = RIVER_ROOT / "EURUSD" / ".staging"
OUTPUT_DIR = DEXTER_ROOT / "output" / "detections"
STATUS_FILE = Path.home() / ".mirror-runner-status.json"

NY_TZ = ZoneInfo("America/New_York")

CYCLE_MARKET_OPEN = 300    # 5 minutes
CYCLE_MARKET_CLOSED = 1800  # 30 minutes

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | [RUNNER] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("mirror.runner")

# ---------------------------------------------------------------------------
# Ensure dexter imports work
# ---------------------------------------------------------------------------
if str(DEXTER_PKG) not in sys.path:
    sys.path.insert(0, str(DEXTER_PKG))
if str(DEXTER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DEXTER_SCRIPTS))
```

- [ ] **Step 2: Add helper functions — forex day, market state, atomic write**

```python
def _current_forex_day() -> str:
    """Return today's forex day label (NY-based)."""
    from bead_field.producers.utils.tf_aggregator import get_forex_day, to_ny
    now_ny = datetime.now(NY_TZ)
    return get_forex_day(now_ny)


def _market_is_open() -> bool:
    """Check if forex market is likely open based on staging file."""
    today = _current_forex_day()
    staging = STAGING_DIR / f"{today}.jsonl"
    if staging.exists() and staging.stat().st_size > 0:
        return True
    # Also check day of week (forex closed Sat-Sun NY time)
    now_ny = datetime.now(NY_TZ)
    # Friday after 17:00 NY → Sunday 17:00 NY = closed
    wd = now_ny.weekday()  # Mon=0 .. Sun=6
    hour = now_ny.hour
    if wd == 4 and hour >= 17:  # Friday evening
        return False
    if wd == 5:  # Saturday
        return False
    if wd == 6 and hour < 17:  # Sunday before open
        return False
    return True


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".det_"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.rename(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _write_status(forex_day: str, bars: int = 0, detections: int = 0,
                  signals: int = 0, error: str | None = None,
                  next_sleep: int = CYCLE_MARKET_OPEN) -> None:
    """Write runner status file."""
    now = datetime.now(timezone.utc)
    status = {
        "last_run": now.isoformat(),
        "forex_day": forex_day,
        "bars_loaded": bars,
        "detections_written": detections,
        "signals_emitted": signals,
        "error": error,
        "next_run": (now + timedelta(seconds=next_sleep)).isoformat(),
    }
    try:
        _atomic_write_json(STATUS_FILE, status)
    except Exception as exc:
        log.warning("Failed to write status file: %s", exc)
```

- [ ] **Step 3: Add the pipeline execution wrapper**

```python
def _run_cycle(forex_day: str) -> dict:
    """Run the dexter detection pipeline for a single forex day.

    Returns a summary dict with bar/detection/signal counts.
    """
    from daily_detection_export import run_pipeline

    target = date.fromisoformat(forex_day)
    log.info("Running pipeline for %s ...", forex_day)

    start_time = time.monotonic()
    try:
        pipeline_result = run_pipeline(target, target)
        elapsed = time.monotonic() - start_time
        log.info("Pipeline completed in %.1fs", elapsed)
    except Exception as exc:
        elapsed = time.monotonic() - start_time
        log.error("Pipeline failed after %.1fs: %s", elapsed, exc)
        raise

    if pipeline_result is None:
        log.warning("Pipeline returned None — no bars available for %s", forex_day)
        return {"bars": 0, "detections": 0, "signals": 0}

    # Count what was produced from the output file
    det_path = OUTPUT_DIR / f"{forex_day}.json"
    bars = 0
    detections = 0
    signals = 0
    if det_path.exists():
        try:
            with open(det_path) as f:
                data = json.load(f)
            # Count bars from the detection metadata if available
            for prim, by_tf in data.get("detections_by_primitive", {}).items():
                for tf, dets in by_tf.items():
                    detections += len(dets)
            signals = len(data.get("diagnostic_signals", []))
        except Exception:
            pass

    # Get bar count from adapter directly
    try:
        from bead_field.river.river_adapter import RiverBarAdapter
        adapter = RiverBarAdapter()
        raw_bars = adapter.load_date_range(target, target)
        bars = len(raw_bars) if raw_bars else 0
    except Exception:
        pass

    return {"bars": bars, "detections": detections, "signals": signals}
```

- [ ] **Step 4: Add the main loop and signal handling**

```python
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log.info("Received signal %d, shutting down...", signum)
    _shutdown = True


def main():
    global _shutdown

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    log.info("Mirror Detection Runner starting")
    log.info("  DEXTER_ROOT: %s", DEXTER_ROOT)
    log.info("  OUTPUT_DIR:  %s", OUTPUT_DIR)
    log.info("  STAGING_DIR: %s", STAGING_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    last_forex_day = None

    while not _shutdown:
        forex_day = _current_forex_day()
        market_open = _market_is_open()
        cycle_time = CYCLE_MARKET_OPEN if market_open else CYCLE_MARKET_CLOSED

        if forex_day != last_forex_day:
            log.info("Forex day: %s (market: %s)",
                     forex_day, "OPEN" if market_open else "CLOSED")
            last_forex_day = forex_day

        try:
            summary = _run_cycle(forex_day)
            _write_status(
                forex_day,
                bars=summary["bars"],
                detections=summary["detections"],
                signals=summary["signals"],
                next_sleep=cycle_time,
            )
            log.info("Cycle done: %d detections, %d signals. Next in %ds.",
                     summary["detections"], summary["signals"], cycle_time)
        except Exception as exc:
            log.error("Cycle failed: %s", exc)
            _write_status(forex_day, error=str(exc), next_sleep=cycle_time)

        # Sleep in 1s increments so we can respond to signals
        for _ in range(cycle_time):
            if _shutdown:
                break
            time.sleep(1)

    log.info("Runner stopped.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Smoke test the runner manually**

Run:
```bash
cd ~/research_accelerator/mirror/backend && \
  DEXTER_ROOT=~/dexter PYTHONPATH=~/dexter/dexter:~/dexter/scripts \
  ~/dexter/.venv/bin/python3 detection_runner.py &
RUNNER_PID=$!
sleep 30  # let one cycle complete
kill $RUNNER_PID
```

Expected: Logs show `Running pipeline for 2026-03-23`, `Pipeline completed in ~10s`, `Cycle done: N detections, N signals`. Detection JSON updated at `~/dexter/output/detections/2026-03-23.json`. Status file at `~/.mirror-runner-status.json`.

- [ ] **Step 6: Commit**

```bash
cd ~/research_accelerator
git add mirror/backend/detection_runner.py
git commit -m "feat(mirror): add detection runner daemon — 5m pipeline cycle"
```

---

### Task 2: Detection File Watcher in server.py

**Files:**
- Modify: `mirror/backend/server.py`

- [ ] **Step 1: Add DetectionFileHandler class after StagingFileHandler**

Add after the `_start_file_watcher` function (around line 310):

```python
class DetectionFileHandler(FileSystemEventHandler):
    """Watches detection JSON files for updates from the runner."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._loop = loop
        self._last_mtime: dict[str, float] = {}

    def on_modified(self, event: FileModifiedEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix != ".json":
            return
        # Debounce: skip if mtime unchanged
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            return
        last = self._last_mtime.get(path.name, 0)
        if mtime <= last:
            return
        self._last_mtime[path.name] = mtime

        asyncio.run_coroutine_threadsafe(
            self._handle_detection_update(path), self._loop
        )

    async def _handle_detection_update(self, path: Path) -> None:
        """Reload detection JSON and broadcast if changed."""
        date_str = path.stem
        log.info("Detection file updated: %s", date_str)
        try:
            detections = _load_detections(date_str)
        except Exception as exc:
            log.error("Failed to reload detections for %s: %s", date_str, exc)
            return

        if not detections:
            return

        # Only broadcast if content actually changed
        if detections == state.cached_detections:
            return

        state.cached_detections = detections

        # Broadcast detections
        det_payload = detections.get("detections_by_primitive", detections)
        await broadcast({"type": "detections", "data": det_payload})

        # Broadcast world_state (retain previous if absent)
        ws = detections.get("world_state")
        if ws:
            state.cached_world_state = ws
            await broadcast({"type": "world_state", "data": ws})

        log.info("Detection broadcast complete for %s", date_str)


def _start_detection_watcher(loop: asyncio.AbstractEventLoop) -> Observer:
    """Start watchdog observer on the detection output directory."""
    observer = Observer()
    handler = DetectionFileHandler(loop)
    watch_path = str(DETECTION_DIR)
    log.info("Starting detection file watcher on %s", watch_path)
    DETECTION_DIR.mkdir(parents=True, exist_ok=True)
    observer.schedule(handler, watch_path, recursive=False)
    observer.daemon = True
    observer.start()
    return observer
```

- [ ] **Step 2: Remove the polling loop and add detection watcher to lifespan**

In `ServerState.__init__`, remove `self._detection_task` field.

In `lifespan()`, replace the detection refresh loop start with the file watcher:

```python
# Replace this:
#   state._detection_task = asyncio.create_task(_detection_refresh_loop())
# With:
try:
    state.detection_observer = _start_detection_watcher(loop)
except Exception as exc:
    log.warning("Could not start detection file watcher: %s", exc)
```

In the shutdown section, replace the detection task cancel with observer stop:

```python
# Replace this:
#   if state._detection_task:
#       state._detection_task.cancel()
#       ...
# With:
if hasattr(state, 'detection_observer') and state.detection_observer:
    state.detection_observer.stop()
    state.detection_observer.join(timeout=5)
```

Remove the `_detection_refresh_loop` function and the `DETECTION_REFRESH_INTERVAL` constant entirely.

Also remove the separate `signals` broadcast from the WebSocket connect handler (server.py lines 529-535) to prevent feed deduplication issues. Signals are already embedded in the detection JSON under `diagnostic_signals` and rendered by `updateFeedFromDetections()`. The block to remove:

```python
# REMOVE this block from websocket_endpoint:
if isinstance(state.cached_detections, dict):
    sigs = state.cached_detections.get("diagnostic_signals", [])
    if sigs:
        await ws.send_text(json.dumps({
            "type": "signals",
            "data": sigs,
        }))
```

Add `self.detection_observer: Observer | None = None` to `ServerState.__init__` (replacing `hasattr` check).

- [ ] **Step 3: Smoke test detection watcher**

With server running, manually touch/update a detection file:
```bash
# Server should be running on port 8300
# In another terminal:
cd ~/dexter && PYTHONPATH=~/dexter/dexter .venv/bin/python3 scripts/daily_detection_export.py 2026-03-23

# Check server logs for "Detection file updated: 2026-03-23"
# Check WS clients receive detection broadcast
curl -s http://localhost:8300/api/heartbeat | python3 -m json.tool
```

Expected: Server logs show detection file watcher fired, detection data broadcast to connected clients.

- [ ] **Step 4: Commit**

```bash
cd ~/research_accelerator
git add mirror/backend/server.py
git commit -m "feat(mirror): replace detection polling with file watcher"
```

---

### Task 3: Multi-TF Push

**Files:**
- Modify: `mirror/backend/server.py`
- Modify: `mirror/js/mirror-app.js`

- [ ] **Step 1: Modify StagingFileHandler to push all TFs**

In `server.py`, replace the bar broadcast section in `StagingFileHandler._handle_new_bars` (around line 294):

Replace:
```python
bars_5m = _load_bars_as_dicts(date_str, "5m")
state.cached_bars_5m = bars_5m
await broadcast({"type": "bars", "tf": "5m", "data": bars_5m})
```

With:
```python
for tf in ["1m", "5m", "15m", "1H", "4H"]:
    bars = _load_bars_as_dicts(date_str, tf)
    if tf == "5m":
        state.cached_bars_5m = bars
    await broadcast({"type": "bars", "tf": tf, "data": bars})
```

- [ ] **Step 2: Update frontend bars handler for conditional refresh**

In `mirror-app.js`, in the `handleWSMessage` function, replace the `bars` case:

Replace:
```javascript
    case 'bars':
      mApp.candleData[msg.tf] = msg.data || msg.bars || [];
      if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
      break;
```

With:
```javascript
    case 'bars':
      mApp.candleData[msg.tf] = msg.data || msg.bars || [];
      if (msg.tf === mApp.tf && typeof refreshMirrorChart === 'function') refreshMirrorChart();
      break;
```

- [ ] **Step 3: Verify TF switching uses cached data**

Open `mirror.a8ra.com` in browser. Wait for initial load. Switch between TF buttons (5m, 15m, 1H). Verify:
- No loading spinner appears (data already cached from WS push)
- Chart updates instantly on TF switch
- Console shows no REST fetch calls for cached TFs

- [ ] **Step 4: Commit**

```bash
cd ~/research_accelerator
git add mirror/backend/server.py mirror/js/mirror-app.js
git commit -m "feat(mirror): push all TFs on staging update, conditional chart refresh"
```

---

### Task 4: Launcher Script

**Files:**
- Create: `mirror/start-mirror.sh`

- [ ] **Step 1: Write the launcher script**

```bash
#!/usr/bin/env bash
# start-mirror.sh — Launch MIRROR server + detection runner
#
# Usage:
#   ./start-mirror.sh          Start both processes
#   ./start-mirror.sh stop     Graceful shutdown

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
PID_FILE="/tmp/mirror.pid"

# Venv paths
SERVER_PYTHON="$HOME/research_accelerator/.venv/bin/python3"
RUNNER_PYTHON="$HOME/dexter/.venv/bin/python3"
RUNNER_PYTHONPATH="$HOME/dexter/dexter:$HOME/dexter/scripts"

# --- Stop mode ---
if [[ "${1:-}" == "stop" ]]; then
    if [[ -f "$PID_FILE" ]]; then
        echo "[MIRROR] Reading PIDs from $PID_FILE..."
        while IFS= read -r pid; do
            if kill -0 "$pid" 2>/dev/null; then
                echo "[MIRROR] Stopping PID $pid..."
                kill -TERM "$pid" 2>/dev/null || true
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
        echo "[MIRROR] Stopped."
    else
        echo "[MIRROR] No PID file found at $PID_FILE"
    fi
    exit 0
fi

# --- Check prerequisites ---
if [[ ! -x "$SERVER_PYTHON" ]]; then
    echo "[MIRROR] ERROR: Server Python not found: $SERVER_PYTHON"
    exit 1
fi
if [[ ! -x "$RUNNER_PYTHON" ]]; then
    echo "[MIRROR] ERROR: Runner Python not found: $RUNNER_PYTHON"
    exit 1
fi

# --- Cleanup on exit ---
SERVER_PID=""
RUNNER_PID=""

cleanup() {
    echo ""
    echo "[MIRROR] Shutting down..."
    [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null && echo "[MIRROR] Server stopped (PID $SERVER_PID)"
    [[ -n "$RUNNER_PID" ]] && kill "$RUNNER_PID" 2>/dev/null && echo "[MIRROR] Runner stopped (PID $RUNNER_PID)"
    rm -f "$PID_FILE"
    wait 2>/dev/null
    echo "[MIRROR] All processes stopped."
}

trap cleanup EXIT INT TERM

# --- Start server ---
echo "[MIRROR] Starting server..."
cd "$BACKEND_DIR"
"$SERVER_PYTHON" server.py &
SERVER_PID=$!
echo "[MIRROR] Server PID: $SERVER_PID"

# Brief pause to let server bind port
sleep 2

# --- Start detection runner ---
echo "[MIRROR] Starting detection runner..."
DEXTER_ROOT="$HOME/dexter" \
PYTHONPATH="$RUNNER_PYTHONPATH" \
"$RUNNER_PYTHON" "$BACKEND_DIR/detection_runner.py" &
RUNNER_PID=$!
echo "[MIRROR] Runner PID: $RUNNER_PID"

# --- Write PID file (individual PIDs for safe stop) ---
printf "%s\n%s\n%s\n" "$$" "$SERVER_PID" "$RUNNER_PID" > "$PID_FILE"

echo "[MIRROR] ================================================"
echo "[MIRROR]  Server:  http://localhost:8300"
echo "[MIRROR]  Public:  https://mirror.a8ra.com"
echo "[MIRROR]  Stop:    ./start-mirror.sh stop  (or Ctrl+C)"
echo "[MIRROR] ================================================"

# --- Health monitor loop ---
while true; do
    # Check server
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "[MIRROR] WARNING: Server died, restarting in 5s..."
        sleep 5
        cd "$BACKEND_DIR"
        "$SERVER_PYTHON" server.py &
        SERVER_PID=$!
        echo "[MIRROR] Server restarted (PID $SERVER_PID)"
    fi

    # Check runner
    if ! kill -0 "$RUNNER_PID" 2>/dev/null; then
        echo "[MIRROR] WARNING: Runner died, restarting in 5s..."
        sleep 5
        DEXTER_ROOT="$HOME/dexter" \
        PYTHONPATH="$RUNNER_PYTHONPATH" \
        "$RUNNER_PYTHON" "$BACKEND_DIR/detection_runner.py" &
        RUNNER_PID=$!
        echo "[MIRROR] Runner restarted (PID $RUNNER_PID)"
    fi

    sleep 10
done
```

- [ ] **Step 2: Make executable and test**

```bash
chmod +x ~/research_accelerator/mirror/start-mirror.sh
```

Test start and stop:
```bash
cd ~/research_accelerator/mirror
./start-mirror.sh &
sleep 15
# Verify both processes running:
ps aux | grep -E "server.py|detection_runner" | grep -v grep
# Verify API responds:
curl -s http://localhost:8300/api/heartbeat | python3 -m json.tool
# Stop:
./start-mirror.sh stop
# Verify processes gone:
ps aux | grep -E "server.py|detection_runner" | grep -v grep
```

Expected: Both processes start, API responds, clean shutdown on stop command.

- [ ] **Step 3: Commit**

```bash
cd ~/research_accelerator
git add mirror/start-mirror.sh
git commit -m "feat(mirror): add launcher script for server + runner"
```

---

### Task 5: Integration Test — Full Stack Verification

**Files:** None (manual verification)

- [ ] **Step 1: Stop any running mirror processes**

```bash
cd ~/research_accelerator/mirror
./start-mirror.sh stop 2>/dev/null; true
# Also kill any leftover processes:
pkill -f "server.py" 2>/dev/null; true
pkill -f "detection_runner" 2>/dev/null; true
```

- [ ] **Step 2: Start the full stack via launcher**

```bash
cd ~/research_accelerator/mirror
./start-mirror.sh
```

Wait for initial runner cycle to complete (watch for `[RUNNER] Cycle done` in logs).

- [ ] **Step 3: Verify API endpoints**

```bash
# Heartbeat shows LIVE + connected clients
curl -s http://localhost:8300/api/heartbeat | python3 -m json.tool

# Detections available for today
curl -s http://localhost:8300/api/dates | python3 -m json.tool

# Detection data loads
curl -s http://localhost:8300/api/detections/$(date +%Y-%m-%d) | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Primitives: {len(d.get(\"detections_by_primitive\",{}))} | WorldState: {bool(d.get(\"world_state\"))} | Signals: {len(d.get(\"diagnostic_signals\",[]))}')"

# Multi-TF bars
for tf in 1m 5m 15m 1H 4H; do
  count=$(curl -s "http://localhost:8300/api/bars/$(date +%Y-%m-%d)?tf=$tf" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))")
  echo "  $tf: $count bars"
done
```

- [ ] **Step 4: Verify WebSocket real-time flow**

```bash
# Connect a WS client and observe messages for 30s
python3 -c "
import asyncio, websockets, json
async def listen():
    async with websockets.connect('ws://localhost:8300/ws') as ws:
        for i in range(10):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
            print(f'  [{msg[\"type\"]}] ', end='')
            if msg['type'] == 'bars': print(f'tf={msg.get(\"tf\")} count={len(msg.get(\"data\",[]))}')
            elif msg['type'] == 'detections': print(f'primitives={len(msg.get(\"data\",{}))}')
            elif msg['type'] == 'world_state': print(f'phase={msg.get(\"data\",{}).get(\"htf_phase\",\"?\")}')
            elif msg['type'] == 'status': print(f'state={msg.get(\"data\",{}).get(\"state\",\"?\")}')
            else: print(json.dumps(msg)[:80])
asyncio.run(listen())
" 2>&1 || echo "(websockets package may not be installed — verify manually in browser)"
```

Expected: Messages arrive for `status`, `bars` (multiple TFs), `detections`, `world_state`.

- [ ] **Step 5: Verify runner status file**

```bash
cat ~/.mirror-runner-status.json | python3 -m json.tool
```

Expected: Shows last_run, forex_day, detection/signal counts, no error, reasonable next_run.

- [ ] **Step 6: Final commit — P0 fixes + all enhancements**

```bash
cd ~/research_accelerator
git add -A
git status
# If any uncommitted changes remain:
git commit -m "chore(mirror): integration verification complete"
```
