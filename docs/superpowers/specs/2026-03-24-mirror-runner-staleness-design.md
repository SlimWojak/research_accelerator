# Mirror Runner Launchd + Staleness Detection

**Date**: 2026-03-24
**Status**: Approved
**Author**: COO (a8ra-m3)
**Approved by**: G

## Problem

The mirror detection runner (`detection_runner.py`) is not managed by launchd. It was designed to run via `start-mirror.sh` (a foreground supervisor script), but launchd only manages `server.py`. When the runner dies, detections freeze and there is no visual indication to Olya that data is stale — the LIVE badge stays green because it only checks whether a staging file exists, not whether data is flowing.

## Solution

Two changes:

1. **Dedicated launchd job** for the detection runner (`com.a8ra.mirror-runner`)
2. **Staleness detection** in `server.py` with visual feedback via the LIVE badge

## Architecture

```
launchd
  |
  +-- com.a8ra.river          (river.streamer → staging JSONL)
  +-- com.a8ra.mirror         (server.py → port 8300, WebSocket)
  +-- com.a8ra.mirror-runner  (detection_runner.py → detection JSON) [NEW]

Data flow:
  river → staging/*.jsonl → [server.py watches] → WebSocket → browser
  runner → detections/*.json → [server.py watches] → WebSocket → browser
  server.py tracks freshness of BOTH data streams → STALE badge if either dies
```

## Component 1: Launchd Plist

### File: `~/Library/LaunchAgents/com.a8ra.mirror-runner.plist`

Properties:
- **Label**: `com.a8ra.mirror-runner`
- **ProgramArguments**: `/bin/bash launch_runner.sh` (wrapper script pattern, consistent with `com.a8ra.river`)
- **WorkingDirectory**: `~/research_accelerator/mirror/backend`
- **KeepAlive**: true (auto-restart on crash)
- **ThrottleInterval**: 60 (prevents rapid restart loops; runner cycles are 5m+ anyway)
- **RunAtLoad**: true (starts on login/bootstrap)
- **StandardOutPath**: `~/logs/mirror-runner.stdout.log`
- **StandardErrorPath**: `~/logs/mirror-runner.stderr.log`
- **EnvironmentVariables**: PATH (pyenv/homebrew), RIVER_ROOT, DEXTER_ROOT

**Why a launcher script (not raw python)?** The runner needs `PYTHONPATH` set to `~/dexter/dexter:~/dexter/scripts` for the `daily_detection_export` import. A launcher script cleanly sets this alongside `PYTHONUNBUFFERED=1` and venv selection — matching the `com.a8ra.river` pattern which uses `launch_river.sh`. The `com.a8ra.mirror` plist runs python directly because `server.py` has no special PYTHONPATH requirements.

### File: `~/research_accelerator/mirror/backend/launch_runner.sh`

Launcher script (consistent with `~/phoenix/scripts/launch_river.sh` pattern):
- Sets `DEXTER_ROOT`, `RIVER_ROOT`, `PYTHONPATH` (dexter/dexter + dexter/scripts)
- Sets `PYTHONUNBUFFERED=1` for clean log output
- Uses `exec` to replace shell with python (launchd tracks the right PID)
- Uses dexter venv: `~/dexter/.venv/bin/python3` (verified: has all dexter pipeline dependencies; `start-mirror.sh` also uses this venv for the runner)

### Operations

```bash
# Bootstrap (first time or after plist edit)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.a8ra.mirror-runner.plist

# Restart
launchctl bootout gui/$(id -u)/com.a8ra.mirror-runner
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.a8ra.mirror-runner.plist

# Check status
launchctl print gui/$(id -u)/com.a8ra.mirror-runner

# Logs
tail -f ~/logs/mirror-runner.stdout.log
tail -f ~/logs/mirror-runner.stderr.log
```

## Component 2: Staleness Detection (server.py)

### State Tracking

Add two timestamps to `DashboardState.__init__`:
- `self.last_bar_received_at: float = 0.0`
- `self.last_detection_updated_at: float = 0.0`

### Timestamp Assignment Points

**Bars** — in `StagingFileHandler._handle_new_bars`, after the existing `state.last_bar_time = ...` assignment (line ~463):
```python
state.last_bar_received_at = time.time()
```

**Detections** — in `DetectionFileHandler._handle_detection_update`, after the existing log line (line ~538):
```python
state.last_detection_updated_at = time.time()
```

### Single Authority for State Transitions

Remove the existing `state.market_state = "LIVE"` assignment in `_handle_new_bars` (line ~471). The staleness checker (below) becomes the **sole authority** for setting `market_state`. This prevents a race between direct assignment and the periodic checker.

### Periodic Staleness Checker

Add a new asyncio background task started in the `lifespan` function:

```python
STALE_BAR_THRESHOLD = 120       # 2 minutes (river writes every 60s)
STALE_DETECTION_THRESHOLD = 600  # 10 minutes (runner cycles every 5m)
STALENESS_CHECK_INTERVAL = 30   # check every 30 seconds

async def _staleness_checker():
    """Periodic task: evaluate data freshness, broadcast state changes."""
    while True:
        await asyncio.sleep(STALENESS_CHECK_INTERVAL)
        new_state = _determine_market_state()
        if new_state != state.market_state:
            log.info("Market state: %s → %s", state.market_state, new_state)
            state.market_state = new_state
            await broadcast(state.status_payload)
```

This task is started in `lifespan` alongside the existing watchdog observers:
```python
staleness_task = asyncio.create_task(_staleness_checker())
```

And cancelled on shutdown:
```python
staleness_task.cancel()
```

### Modified Market State Logic

Replace `_determine_market_state()`:

```python
def _determine_market_state() -> str:
    today = _today_forex_day()
    staging = _staging_path_for(today)

    # No staging file → market is closed
    if not staging.exists() or staging.stat().st_size == 0:
        return "MARKET_CLOSED"

    # Additional time-of-day check: if forex market is closed by schedule,
    # don't flag stale even if staging file lingers from Friday
    now_ny = datetime.now(NY_TZ)
    wd = now_ny.weekday()  # Mon=0 .. Sun=6
    h = now_ny.hour
    if (wd == 4 and h >= 17) or wd == 5 or (wd == 6 and h < 17):
        return "MARKET_CLOSED"

    now = time.time()

    # Bar freshness check
    if state.last_bar_received_at > 0:
        bar_age = now - state.last_bar_received_at
        if bar_age > STALE_BAR_THRESHOLD:
            return "STALE"

    # Detection freshness check
    if state.last_detection_updated_at > 0:
        det_age = now - state.last_detection_updated_at
        if det_age > STALE_DETECTION_THRESHOLD:
            return "STALE"

    return "LIVE"
```

### Initialization

On server startup (in `lifespan`, before starting the staleness checker), seed timestamps from file mtimes to prevent false STALE on restart:

```python
# Seed bar freshness from staging file mtime
staging = _staging_path_for(_today_forex_day())
if staging.exists():
    state.last_bar_received_at = staging.stat().st_mtime

# Seed detection freshness from latest detection JSON mtime
det_path = DETECTION_DIR / f"{_today_forex_day()}.json"
if det_path.exists():
    state.last_detection_updated_at = det_path.stat().st_mtime
```

### WebSocket Integration

No protocol changes needed. The existing `type: "status"` message already sends `state.market_state`. The staleness checker broadcasts on state transitions. The existing WebSocket keepalive (every 60s) also sends `state.status_payload`, so clients that miss the transition broadcast will catch up within 60s.

## Component 3: Frontend Badge (mirror-app.js + mirror.html)

### CSS Addition (mirror.html)

```css
#live-badge.stale {
    color: #ff9800;
    background: rgba(255, 152, 0, 0.15);
}

#live-badge.stale .live-dot {
    background: #ff9800;
    animation: pulse-dot 0.8s ease-in-out infinite;
}
```

Uses **amber/orange** (`#ff9800`) instead of red — visually distinct from `disconnected` (red, solid dot) at a glance. STALE means "data is old but connection is alive" vs DISCONNECTED means "WebSocket is down." The faster pulse (0.8s vs 1.5s) adds urgency.

### Badge State Addition (mirror-app.js)

In `updateLiveBadge()`, add case:
```javascript
case 'stale':
    badge.className = 'stale';
    badge.innerHTML = '<span class="live-dot"></span><span class="live-text">STALE</span>';
    break;
```

In the WebSocket status handler, add:
```javascript
else if (st === 'STALE') updateLiveBadge('stale');
```

## Files Changed

| File | Action | Scope |
|------|--------|-------|
| `~/Library/LaunchAgents/com.a8ra.mirror-runner.plist` | NEW | Launchd job definition |
| `~/research_accelerator/mirror/backend/launch_runner.sh` | NEW | Runner launcher script |
| `~/research_accelerator/mirror/backend/server.py` | MODIFY | Staleness tracking (~35 lines) |
| `~/research_accelerator/mirror/js/mirror-app.js` | MODIFY | STALE badge state (~8 lines) |
| `~/research_accelerator/mirror/mirror.html` | MODIFY | Stale CSS (~6 lines) |

## Files NOT Changed

- `detection_runner.py` — zero modifications. Already writes status JSON.
- `start-mirror.sh` — kept for dev/manual use. Launchd is production path.
- `com.a8ra.mirror` plist — unchanged, manages server.py.
- `com.a8ra.river` plist — unchanged.
- Detection pipeline code (dexter/) — unchanged.

## Thresholds

| Check | Threshold | Rationale |
|-------|-----------|-----------|
| Bar staleness | 2 minutes | River writes every 60s. Missing 2 consecutive = problem. |
| Detection staleness | 10 minutes | Runner cycles every 5m. Missing 2 consecutive = problem. |
| Staleness check interval | 30 seconds | Fast enough to catch issues, light enough to be negligible. |
| Market closed | Schedule-based | Friday 17:00 NY through Sunday 17:00 NY. Prevents false STALE from lingering staging files. |

## Verification Plan

1. Bootstrap runner plist, verify process starts: `ps aux | grep detection_runner`
2. Verify detections update: check `~/.mirror-runner-status.json` timestamp advances
3. Verify detection JSON updates: check `~/dexter/output/detections/2026-03-24.json` generation time
4. Kill runner (`launchctl bootout`), wait 10 min, verify badge shows STALE (amber)
5. Stop river, wait 2 min, verify badge shows STALE (amber)
6. Restart both, verify badge returns to LIVE (teal)
7. Verify market closed state: during weekend/after hours, badge shows MARKET CLOSED (not STALE)
8. Restart server.py (bootout + bootstrap mirror plist) while runner and river are healthy — verify badge does not flash STALE during restart (mtime seeding prevents this)
9. Disconnect WebSocket (e.g., disable network) — verify badge shows DISCONNECTED (red), not STALE (amber)

## Rollback

- Runner plist: `launchctl bootout gui/$(id -u)/com.a8ra.mirror-runner && rm ~/Library/LaunchAgents/com.a8ra.mirror-runner.plist`
- Server + frontend changes: `git revert` the staleness commit
