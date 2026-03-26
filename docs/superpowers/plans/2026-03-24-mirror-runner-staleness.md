# Mirror Runner Launchd + Staleness Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get the detection runner managed by launchd and add staleness detection to the LIVE badge so Olya knows immediately when data is stale.

**Architecture:** Separate launchd plist for the runner (matching river pattern), periodic staleness checker in server.py that evaluates bar and detection freshness every 30s, amber STALE badge on the frontend.

**Tech Stack:** launchd (macOS), Python/FastAPI (server.py), vanilla JS/CSS (frontend)

**Spec:** `docs/superpowers/specs/2026-03-24-mirror-runner-staleness-design.md`

---

### Task 1: Create Runner Launcher Script

**Files:**
- Create: `mirror/backend/launch_runner.sh`

- [ ] **Step 1: Create the launcher script**

```bash
#!/bin/bash
# Detection Runner Launch Script — invoked by launchd (com.a8ra.mirror-runner)
# Runs dexter pipeline every 5m (market open) or 30m (closed), writes detection JSON.
# Auto-restarts on crash via launchd KeepAlive.

cd "$(dirname "$0")" || exit 1

export DEXTER_ROOT="${DEXTER_ROOT:-$HOME/dexter}"
export RIVER_ROOT="${RIVER_ROOT:-$HOME/phoenix-river}"
export PYTHONPATH="$HOME/dexter/dexter:$HOME/dexter/scripts"
export PYTHONUNBUFFERED=1

if [ -f "$HOME/dexter/.venv/bin/python3" ]; then
    exec "$HOME/dexter/.venv/bin/python3" detection_runner.py "$@"
else
    echo "ERROR: dexter venv not found at $HOME/dexter/.venv/bin/python3" >&2
    exit 1
fi
```

- [ ] **Step 2: Make executable**

Run: `chmod +x ~/research_accelerator/mirror/backend/launch_runner.sh`

- [ ] **Step 3: Verify it starts and exits cleanly**

Run: `cd ~/research_accelerator/mirror/backend && timeout 10 bash launch_runner.sh 2>&1 | head -5`
Expected: Pipeline log output (will be killed by timeout after 10s, that's fine — we just verify it starts)

- [ ] **Step 4: Commit**

```bash
cd ~/research_accelerator
git add mirror/backend/launch_runner.sh
git commit -m "feat(mirror): add detection runner launcher script for launchd"
```

---

### Task 2: Create Runner Launchd Plist

**Files:**
- Create: `~/Library/LaunchAgents/com.a8ra.mirror-runner.plist`

- [ ] **Step 1: Create the plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>com.a8ra.mirror-runner</string>

	<key>ProgramArguments</key>
	<array>
		<string>/bin/bash</string>
		<string>/Users/a8ra_m3/research_accelerator/mirror/backend/launch_runner.sh</string>
	</array>

	<key>WorkingDirectory</key>
	<string>/Users/a8ra_m3/research_accelerator/mirror/backend</string>

	<key>RunAtLoad</key>
	<true/>

	<key>KeepAlive</key>
	<true/>

	<key>ThrottleInterval</key>
	<integer>60</integer>

	<key>EnvironmentVariables</key>
	<dict>
		<key>PATH</key>
		<string>/Users/a8ra_m3/.pyenv/shims:/Users/a8ra_m3/.pyenv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
		<key>RIVER_ROOT</key>
		<string>/Users/a8ra_m3/phoenix-river</string>
		<key>DEXTER_ROOT</key>
		<string>/Users/a8ra_m3/dexter</string>
	</dict>

	<key>StandardOutPath</key>
	<string>/Users/a8ra_m3/logs/mirror-runner.stdout.log</string>

	<key>StandardErrorPath</key>
	<string>/Users/a8ra_m3/logs/mirror-runner.stderr.log</string>
</dict>
</plist>
```

- [ ] **Step 2: Bootstrap the launchd job**

Run: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.a8ra.mirror-runner.plist`

- [ ] **Step 3: Verify runner process started**

Run: `sleep 5 && ps aux | grep detection_runner | grep -v grep`
Expected: One python process running `detection_runner.py`

Run: `launchctl print gui/$(id -u)/com.a8ra.mirror-runner 2>&1 | head -5`
Expected: Shows `state = running`

- [ ] **Step 4: Verify runner is producing detections**

Run: `sleep 60 && cat ~/.mirror-runner-status.json | python3 -m json.tool`
Expected: `last_run` timestamp is recent (within last 60s), `error` is null

Run: `stat -f "%Sm" ~/dexter/output/detections/$(python3 -c "from datetime import datetime; from zoneinfo import ZoneInfo; from bead_field.producers.utils.tf_aggregator import get_forex_day; print(get_forex_day(datetime.now(ZoneInfo('America/New_York'))))").json 2>/dev/null || echo "No detection file yet"`
Expected: Recent modification time

---

### Task 3: Add Staleness Tracking to server.py

**Files:**
- Modify: `mirror/backend/server.py:11` (add `import time`)
- Modify: `mirror/backend/server.py:86-96` (add fields to `ServerState.__init__`)
- Modify: `mirror/backend/server.py:92` (update market_state comment)
- Modify: `mirror/backend/server.py:373-379` (replace `_determine_market_state`)
- Modify: `mirror/backend/server.py:463` (add timestamp in `_handle_new_bars`)
- Modify: `mirror/backend/server.py:469-472` (remove direct market_state assignment)
- Modify: `mirror/backend/server.py:538` (add timestamp in `_handle_detection_update`)

- [ ] **Step 1: Add `import time` to imports**

In the stdlib imports block (after `import signal` on line 16), add:
```python
import time
```

- [ ] **Step 2: Add freshness fields to `ServerState.__init__`**

At `server.py:93`, after `self.last_bar_time: str = ""`, add:
```python
        self.last_bar_received_at: float = 0.0
        self.last_detection_updated_at: float = 0.0
```

Update the comment on line 92 to:
```python
        self.market_state: str = "CONNECTING"  # LIVE | MARKET_CLOSED | STALE | CONNECTING
```

- [ ] **Step 3: Add staleness constants and replace `_determine_market_state`**

Replace the `_determine_market_state` function (search for `def _determine_market_state`) with:
```python
STALE_BAR_THRESHOLD = 120         # 2 min — river writes every 60s
STALE_DETECTION_THRESHOLD = 600   # 10 min — runner cycles every 5m
STALENESS_CHECK_INTERVAL = 30     # how often the checker runs

def _determine_market_state() -> str:
    """Decide market state: LIVE, STALE, or MARKET_CLOSED."""
    today = _today_forex_day()
    staging = _staging_path_for(today)

    # No staging file → market is closed
    if not staging.exists() or staging.stat().st_size == 0:
        return "MARKET_CLOSED"

    # Schedule-based close check (prevents false STALE from lingering Friday file)
    now_ny = datetime.now(NY_TZ)
    wd = now_ny.weekday()  # Mon=0 .. Sun=6
    h = now_ny.hour
    if (wd == 4 and h >= 17) or wd == 5 or (wd == 6 and h < 17):
        return "MARKET_CLOSED"

    now = time.time()

    # Bar freshness
    if state.last_bar_received_at > 0:
        if (now - state.last_bar_received_at) > STALE_BAR_THRESHOLD:
            return "STALE"

    # Detection freshness
    if state.last_detection_updated_at > 0:
        if (now - state.last_detection_updated_at) > STALE_DETECTION_THRESHOLD:
            return "STALE"

    return "LIVE"
```

- [ ] **Step 4: Add bar freshness timestamp in `_handle_new_bars`**

In `_handle_new_bars`, after `state.last_bar_time = last.get("timestamp", "")`, add:
```python
        state.last_bar_received_at = time.time()
```

- [ ] **Step 5: Remove direct market_state assignment in `_handle_new_bars`**

In `_handle_new_bars`, find and delete the block:
```python
        # Transition to LIVE if we were MARKET_CLOSED
        if state.market_state != "LIVE":
            state.market_state = "LIVE"
            await broadcast(state.status_payload)
```

The staleness checker is now the sole authority for state transitions.

- [ ] **Step 6: Add detection freshness timestamp in `_handle_detection_update`**

In `_handle_detection_update`, after `log.info("Detection file updated: %s", date_str)`, add:
```python
        state.last_detection_updated_at = time.time()
```

- [ ] **Step 7: Verify server still starts**

Run:
```bash
launchctl bootout gui/$(id -u)/com.a8ra.mirror && sleep 2 && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.a8ra.mirror.plist && sleep 3 && curl -s http://localhost:8300/api/available-range | python3 -m json.tool
```
Expected: JSON response with date range (server is alive)

- [ ] **Step 8: Commit**

```bash
cd ~/research_accelerator
git add mirror/backend/server.py
git commit -m "feat(mirror): add staleness tracking — bar and detection freshness timestamps"
```

---

### Task 4: Add Staleness Checker Background Task to Lifespan

**Files:**
- Modify: `mirror/backend/server.py` (lifespan function and area above it)

**NOTE:** Line numbers below are landmarks in the *original* file. After Task 3's edits, they will have shifted. Use the surrounding code patterns (function names, comments) to locate insertion points — not absolute line numbers.

- [ ] **Step 1: Add the staleness checker coroutine**

Before the `@asynccontextmanager` decorator above `async def lifespan(app)`, add:
```python
async def _staleness_checker():
    """Periodic task: evaluate data freshness, broadcast state changes."""
    while True:
        await asyncio.sleep(STALENESS_CHECK_INTERVAL)
        new_state = _determine_market_state()
        if new_state != state.market_state:
            log.info("Market state: %s -> %s", state.market_state, new_state)
            state.market_state = new_state
            await broadcast(state.status_payload)
```

- [ ] **Step 2: Seed freshness timestamps in lifespan startup**

In the `lifespan` function, after the line `state.market_state = _determine_market_state()` and `today = _today_forex_day()`, add:
```python
    # Seed freshness timestamps from file mtimes (prevents false STALE on restart)
    staging = _staging_path_for(today)
    if staging.exists():
        state.last_bar_received_at = staging.stat().st_mtime
    det_path = DETECTION_DIR / f"{today}.json"
    if det_path.exists():
        state.last_detection_updated_at = det_path.stat().st_mtime
```

- [ ] **Step 3: Start the staleness checker task**

After the detection watcher try/except block (the one containing `_start_detection_watcher`), before the `yield` line, add:
```python
    # Start periodic staleness checker
    staleness_task = asyncio.create_task(_staleness_checker())
    log.info("Staleness checker started (interval=%ds, bar_threshold=%ds, det_threshold=%ds)",
             STALENESS_CHECK_INTERVAL, STALE_BAR_THRESHOLD, STALE_DETECTION_THRESHOLD)
```

- [ ] **Step 4: Cancel the staleness task on shutdown**

In the shutdown section, after `log.info("MIRROR backend shutting down…")` and before `state._shutdown_event.set()`, add:
```python
    staleness_task.cancel()
    try:
        await staleness_task
    except asyncio.CancelledError:
        pass
```

- [ ] **Step 5: Restart server and verify staleness checker logs**

Run:
```bash
launchctl bootout gui/$(id -u)/com.a8ra.mirror && sleep 2 && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.a8ra.mirror.plist && sleep 5 && tail -20 ~/logs/mirror.stderr.log | grep -E "Staleness|Market state"
```
Expected: Log line showing "Staleness checker started" with thresholds

- [ ] **Step 6: Commit**

```bash
cd ~/research_accelerator
git add mirror/backend/server.py
git commit -m "feat(mirror): add periodic staleness checker — sole authority for market state transitions"
```

---

### Task 5: Add STALE Badge to Frontend

**Files:**
- Modify: `mirror/mirror.html:97-127` (CSS section)
- Modify: `mirror/js/mirror-app.js:274-276` (WebSocket status handler)
- Modify: `mirror/js/mirror-app.js:628` (classList.remove)
- Modify: `mirror/js/mirror-app.js:631-649` (updateLiveBadge switch)

- [ ] **Step 1: Add stale CSS to mirror.html**

After the `#live-badge.disconnected` block (after line 101), add:
```css
  #live-badge.stale {
    color: #ff9800;
    background: rgba(255, 152, 0, 0.15);
  }
```

After the `#live-badge.disconnected .live-dot` block (after line 127), add:
```css
  #live-badge.stale .live-dot {
    background: #ff9800;
    animation: pulse-dot 0.8s ease-in-out infinite;
  }
```

- [ ] **Step 2: Add 'stale' to classList.remove in updateLiveBadge**

At `mirror-app.js:628`, change:
```javascript
  badge.classList.remove('live', 'closed', 'connecting', 'disconnected');
```
To:
```javascript
  badge.classList.remove('live', 'closed', 'connecting', 'disconnected', 'stale');
```

- [ ] **Step 3: Add stale case to updateLiveBadge switch**

In the switch statement, before the `case 'disconnected':` block (before line 644), add:
```javascript
    case 'stale':
      badge.className = 'stale';
      badge.innerHTML = '<span class="live-dot"></span><span class="live-text">STALE</span>';
      break;
```

- [ ] **Step 4: Add STALE handling to WebSocket status handler**

At `mirror-app.js:274-276`, change:
```javascript
      if (st === 'LIVE') updateLiveBadge('live');
      else if (st === 'MARKET_CLOSED') updateLiveBadge('closed');
      else updateLiveBadge('connecting');
```
To:
```javascript
      if (st === 'LIVE') updateLiveBadge('live');
      else if (st === 'STALE') updateLiveBadge('stale');
      else if (st === 'MARKET_CLOSED') updateLiveBadge('closed');
      else updateLiveBadge('connecting');
```

- [ ] **Step 5: Restart server and verify in browser**

Run:
```bash
launchctl bootout gui/$(id -u)/com.a8ra.mirror && sleep 2 && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.a8ra.mirror.plist
```
Then open `https://mirror.a8ra.com` — badge should show LIVE (teal) if both river and runner are healthy.

- [ ] **Step 6: Commit**

```bash
cd ~/research_accelerator
git add mirror/mirror.html mirror/js/mirror-app.js
git commit -m "feat(mirror): add amber STALE badge state to LIVE indicator"
```

---

### Task 6: End-to-End Verification

- [ ] **Step 1: Verify all three launchd jobs are running**

Run:
```bash
launchctl print gui/$(id -u)/com.a8ra.river 2>&1 | head -3
launchctl print gui/$(id -u)/com.a8ra.mirror 2>&1 | head -3
launchctl print gui/$(id -u)/com.a8ra.mirror-runner 2>&1 | head -3
```
Expected: All three show `state = running`

- [ ] **Step 2: Verify detection output is updating**

Run: `cat ~/.mirror-runner-status.json | python3 -m json.tool`
Expected: `last_run` is recent, `error` is null, `detections_written` > 0

- [ ] **Step 3: Verify badge shows LIVE in browser**

Open `https://mirror.a8ra.com` — badge should be teal "LIVE" with pulsing dot.

- [ ] **Step 4: Test STALE detection — stop runner**

Run: `launchctl bootout gui/$(id -u)/com.a8ra.mirror-runner`
Wait 10 minutes, then check browser — badge should show amber "STALE" with fast pulse.

- [ ] **Step 5: Restore runner**

Run: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.a8ra.mirror-runner.plist`
After next detection cycle (~5 min), badge should return to teal "LIVE".

- [ ] **Step 6: Test STALE detection — stop river (bar staleness path)**

Run: `launchctl bootout gui/$(id -u)/com.a8ra.river`
Wait 2-3 minutes, then check browser — badge should show amber "STALE" with fast pulse.
This exercises the 2-minute bar threshold (distinct from the 10-minute detection threshold in Step 4).

Restore: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.a8ra.river.plist`
Wait ~60s, badge should return to LIVE.

- [ ] **Step 7: Verify no process duplication**

Run:
```bash
ps aux | grep detection_runner | grep -v grep | wc -l
ps aux | grep "river.streamer" | grep -v grep | wc -l
ps aux | grep "server.py" | grep -v grep | wc -l
```
Expected: Each returns exactly `1`

- [ ] **Step 8: Verify server restart doesn't flash STALE**

Run:
```bash
launchctl bootout gui/$(id -u)/com.a8ra.mirror && sleep 2 && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.a8ra.mirror.plist
```
Check browser immediately after reconnect — badge should go CONNECTING → LIVE (never STALE).
This validates the mtime seeding on startup.
