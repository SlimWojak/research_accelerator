"""MIRROR — FastAPI WebSocket backend for the a8ra live trading dashboard.

Serves live bar data from phoenix-river staging JSONL, pre-generated
detection JSON from dexter, and pushes real-time updates via WebSocket.

Usage:
    python server.py          # starts on port 8300
    uvicorn server:app --port 8300 --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Dexter path setup — must precede dexter imports
# ---------------------------------------------------------------------------
DEXTER_ROOT = Path(os.environ.get("DEXTER_ROOT", str(Path.home() / "dexter")))
DEXTER_PKG = DEXTER_ROOT / "dexter"
if str(DEXTER_PKG) not in sys.path:
    sys.path.insert(0, str(DEXTER_PKG))

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState

# Watchdog for file-system monitoring
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

# ---------------------------------------------------------------------------
# Dexter imports (after sys.path setup)
# ---------------------------------------------------------------------------
from bead_field.river.river_adapter import RiverBarAdapter
from bead_field.producers.utils.tf_aggregator import (
    aggregate,
    get_forex_day,
    to_ny,
    NY_TZ,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("mirror.server")

# ---------------------------------------------------------------------------
# Constants / Paths
# ---------------------------------------------------------------------------
PORT = 8300
RIVER_ROOT = Path(os.environ.get("RIVER_ROOT", str(Path.home() / "phoenix-river")))
STAGING_DIR = RIVER_ROOT / "EURUSD" / ".staging"
DETECTION_DIR = DEXTER_ROOT / "output" / "detections"
HEARTBEAT_PATH = RIVER_ROOT / ".heartbeat.json"
MIRROR_STATIC_DIR = Path(__file__).resolve().parent.parent  # /mirror/

BAR_PAIR = "EURUSD"

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
adapter = RiverBarAdapter(river_root=RIVER_ROOT, pair=BAR_PAIR)


class ServerState:
    """Mutable singleton holding live dashboard state."""

    def __init__(self) -> None:
        self.connected_clients: set[WebSocket] = set()
        self.last_known_sizes: dict[str, int] = {}  # date_str -> file size
        self.cached_bars_5m: list[dict] = []
        self.cached_detections: dict[str, Any] = {}
        self.cached_world_state: dict[str, Any] = {}
        self.market_state: str = "CONNECTING"  # LIVE | MARKET_CLOSED | STALE | CONNECTING
        self.last_bar_time: str = ""
        self.last_bar_received_at: float = 0.0
        self.last_detection_updated_at: float = 0.0
        self.observer: Observer | None = None
        self.detection_observer: Observer | None = None
        self._shutdown_event = asyncio.Event()

    @property
    def status_payload(self) -> dict:
        return {
            "type": "status",
            "data": {
                "state": self.market_state,
                "last_bar": self.last_bar_time,
                "connected_clients": len(self.connected_clients),
            },
        }


state = ServerState()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_forex_day() -> str:
    """Return today's forex day label (NY-based)."""
    now_ny = datetime.now(NY_TZ)
    return get_forex_day(now_ny)


def _staging_path_for(forex_day: str) -> Path:
    """Path to the staging JSONL for a given forex day."""
    return STAGING_DIR / f"{forex_day}.jsonl"


def _apply_continuity(bars: list[dict]) -> list[dict]:
    """Apply close→open continuity correction to a sorted bar list.

    Matches IBKR's own historical bar reconstruction: open(N+1) = close(N).
    Corrects delivery artifacts from live keepUpToDate stream and
    aggregation boundary mismatches on HTF bars.
    """
    for i in range(1, len(bars)):
        prev_close = bars[i - 1]["close"]
        if abs(bars[i]["open"] - prev_close) > 0.000005:
            bars[i]["open"] = prev_close
    return bars


def _load_bars_as_dicts(forex_day: str, tf: str = "5m") -> list[dict]:
    """Load bars for a forex day via the adapter, aggregate to TF, and return dicts."""
    try:
        dt = date.fromisoformat(forex_day)
        raw_1m = adapter.load_date_range(dt, dt)
        if not raw_1m:
            return []
        if tf == "1m":
            agg = aggregate(raw_1m, "1m")
        else:
            agg = aggregate(raw_1m, tf)
        bars = [
            {
                "time": bar.bar_time,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
            }
            for bar in agg
        ]
        return _apply_continuity(bars)
    except Exception as exc:
        log.error("Failed to load bars for %s tf=%s: %s", forex_day, tf, exc)
        return []


def _load_bars_range(start_day: str, end_day: str, tf: str = "5m") -> list[dict]:
    """Load bars across a date range, aggregate to TF, deduplicate and sort."""
    try:
        dt_start = date.fromisoformat(start_day)
        dt_end = date.fromisoformat(end_day)
        raw_1m = adapter.load_date_range(dt_start, dt_end)
        if not raw_1m:
            return []
        agg = aggregate(raw_1m, tf)
        seen = set()
        result = []
        for bar in agg:
            if bar.bar_time not in seen:
                seen.add(bar.bar_time)
                result.append({
                    "time": bar.bar_time,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                })
        return _apply_continuity(result)
    except Exception as exc:
        log.error("Failed to load bars range %s→%s tf=%s: %s", start_day, end_day, tf, exc)
        return []


def _load_detections(forex_day: str) -> dict:
    """Load detection JSON for a forex day from dexter output."""
    path = DETECTION_DIR / f"{forex_day}.json"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:
        log.error("Failed to load detections for %s: %s", forex_day, exc)
        return {}


def _load_heartbeat() -> dict:
    """Read the phoenix-river heartbeat file."""
    if not HEARTBEAT_PATH.exists():
        return {"state": "UNKNOWN", "connected": False}
    try:
        with open(HEARTBEAT_PATH) as f:
            return json.load(f)
    except Exception as exc:
        log.error("Failed to read heartbeat: %s", exc)
        return {"state": "ERROR", "error": str(exc)}


def _available_detection_dates() -> list[str]:
    """List available detection date files (YYYY-MM-DD only)."""
    if not DETECTION_DIR.exists():
        return []
    dates = []
    for p in sorted(DETECTION_DIR.iterdir()):
        name = p.stem
        # Only include single-date files (not summary ranges)
        if p.suffix == ".json" and len(name) == 10 and name[4] == "-" and name != "latest":
            dates.append(name)
    return dates


def _compute_session_bands(forex_day: str) -> list[dict]:
    """Compute session bands for a forex day using canonical NY hours.

    Canonical sessions (NY time, from session_tagger.py):
      Asia:   19:00 - 00:00
      LOKZ:   02:00 - 05:00
      NYOKZ:  07:00 - 10:00
    Only these three are displayed (pre_london, pre_ny, other are hidden).
    """
    from zoneinfo import ZoneInfo

    ny = ZoneInfo("America/New_York")
    dt = date.fromisoformat(forex_day)

    sessions = [
        {
            "key": "asia",
            "label": "Asia 19:00\u201300:00",
            "start_h": 19, "start_m": 0,
            "end_h": 0, "end_m": 0,
            "color": "rgba(156, 39, 176, 0.08)",
            "border": "rgba(156, 39, 176, 0.25)",
        },
        {
            "key": "lokz",
            "label": "LOKZ 02:00\u201305:00",
            "start_h": 2, "start_m": 0,
            "end_h": 5, "end_m": 0,
            "color": "rgba(41, 98, 255, 0.08)",
            "border": "rgba(41, 98, 255, 0.25)",
        },
        {
            "key": "nyokz",
            "label": "NYOKZ 07:00\u201310:00",
            "start_h": 7, "start_m": 0,
            "end_h": 10, "end_m": 0,
            "color": "rgba(247, 197, 72, 0.08)",
            "border": "rgba(247, 197, 72, 0.25)",
        },
    ]

    bands = []
    for s in sessions:
        if s["start_h"] >= 17:
            # Session starts on previous calendar day (Asia 19:00)
            prev_day = dt - timedelta(days=1)
            start_ny = datetime(prev_day.year, prev_day.month, prev_day.day,
                                s["start_h"], s["start_m"], tzinfo=ny)
        else:
            start_ny = datetime(dt.year, dt.month, dt.day,
                                s["start_h"], s["start_m"], tzinfo=ny)

        if s["end_h"] == 0 and s["end_m"] == 0:
            # Midnight = start of forex day
            end_ny = datetime(dt.year, dt.month, dt.day, 0, 0, tzinfo=ny)
        else:
            end_ny = datetime(dt.year, dt.month, dt.day,
                              s["end_h"], s["end_m"], tzinfo=ny)

        start_utc = start_ny.astimezone(timezone.utc)
        end_utc = end_ny.astimezone(timezone.utc)

        bands.append({
            "session": s["key"],
            "label": s["label"],
            "forex_day": forex_day,
            "start_time": start_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_time": end_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            "color": s["color"],
            "border": s["border"],
        })

    return bands


def _compute_sessions_range(start_day: str, end_day: str) -> list[dict]:
    """Compute session bands across a date range."""
    dt_start = date.fromisoformat(start_day)
    dt_end = date.fromisoformat(end_day)
    bands = []
    d = dt_start
    while d <= dt_end:
        bands.extend(_compute_session_bands(d.isoformat()))
        d += timedelta(days=1)
    return bands


def _available_river_range() -> dict:
    """Scan River parquet dirs for earliest/latest available dates."""
    pair_dir = RIVER_ROOT / BAR_PAIR
    if not pair_dir.exists():
        return {"pair": BAR_PAIR, "earliest": None, "latest": None}
    dates = []
    for year_dir in sorted(pair_dir.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for day_file in sorted(month_dir.iterdir()):
                if day_file.suffix == ".parquet":
                    try:
                        d = date(int(year_dir.name), int(month_dir.name), int(day_file.stem))
                        dates.append(d.isoformat())
                    except ValueError:
                        continue
    if not dates:
        return {"pair": BAR_PAIR, "earliest": None, "latest": None}
    return {"pair": BAR_PAIR, "earliest": dates[0], "latest": dates[-1]}


def _build_week_manifest() -> list[dict]:
    """Group available detection dates into forex weeks (Mon-Fri)."""
    det_dates = _available_detection_dates()
    if not det_dates:
        return []
    weeks: dict[str, list[str]] = {}
    for ds in det_dates:
        d = date.fromisoformat(ds)
        # ISO week: Monday is day 1
        week_start = d - timedelta(days=d.weekday())
        week_key = week_start.isoformat()
        if week_key not in weeks:
            weeks[week_key] = []
        weeks[week_key].append(ds)
    result = []
    for week_start_str in sorted(weeks.keys()):
        days = sorted(weeks[week_start_str])
        week_end = date.fromisoformat(week_start_str) + timedelta(days=4)
        result.append({
            "week": week_start_str,
            "start": days[0],
            "end": days[-1],
            "week_end": week_end.isoformat(),
            "forex_days": days,
            "detection_count": len(days),
        })
    return result


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


def _last_available_date() -> str | None:
    """Find the last detection date when market is closed."""
    dates = _available_detection_dates()
    return dates[-1] if dates else None

# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------

async def broadcast(message: dict) -> None:
    """Send a JSON message to all connected WebSocket clients."""
    if not state.connected_clients:
        return
    payload = json.dumps(message)
    disconnected: set[WebSocket] = set()
    for ws in state.connected_clients.copy():
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_text(payload)
        except Exception:
            disconnected.add(ws)
    state.connected_clients -= disconnected

# ---------------------------------------------------------------------------
# Staging file watcher (watchdog)
# ---------------------------------------------------------------------------

class StagingFileHandler(FileSystemEventHandler):
    """Watches staging JSONL files for growth (new bars appended)."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._loop = loop

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix != ".jsonl":
            return
        # Schedule async handler on the event loop
        asyncio.run_coroutine_threadsafe(
            self._handle_new_bars(path), self._loop
        )

    async def _handle_new_bars(self, path: Path) -> None:
        """Read newly-appended lines from a staging file."""
        date_str = path.stem  # e.g. "2026-03-20"
        try:
            current_size = path.stat().st_size
        except FileNotFoundError:
            return

        last_size = state.last_known_sizes.get(date_str, 0)
        if current_size <= last_size:
            return

        # Read new bytes
        new_lines: list[dict] = []
        try:
            with open(path, "rb") as f:
                f.seek(last_size)
                chunk = f.read(current_size - last_size)
            for raw_line in chunk.decode("utf-8", errors="replace").splitlines():
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    new_lines.append(json.loads(raw_line))
                except json.JSONDecodeError:
                    continue
        except Exception as exc:
            log.error("Error reading new bars from %s: %s", path, exc)
            return

        state.last_known_sizes[date_str] = current_size

        if not new_lines:
            return

        last = new_lines[-1]
        state.last_bar_time = last.get("timestamp", "")
        state.last_bar_received_at = time.time()
        log.info(
            "New bars: %d lines from %s (last: %s)",
            len(new_lines), date_str, state.last_bar_time,
        )

        # Reload and push all standard timeframes
        # LTF: single day. HTF: 10-day window for seamless scrolling.
        htf_start = (date.fromisoformat(date_str) - timedelta(days=9)).isoformat()
        for tf in ["1m", "5m", "15m", "1H", "4H"]:
            if tf in ("1H", "4H"):
                bars = _load_bars_range(htf_start, date_str, tf)
            else:
                bars = _load_bars_as_dicts(date_str, tf)
            if tf == "5m":
                state.cached_bars_5m = bars
            await broadcast({"type": "bars", "tf": tf, "data": bars})
        await broadcast(state.status_payload)


def _start_file_watcher(loop: asyncio.AbstractEventLoop) -> Observer:
    """Start watchdog observer on the staging directory."""
    observer = Observer()
    handler = StagingFileHandler(loop)
    watch_path = str(STAGING_DIR)
    log.info("Starting staging file watcher on %s", watch_path)
    observer.schedule(handler, watch_path, recursive=False)
    observer.daemon = True
    observer.start()
    return observer


# ---------------------------------------------------------------------------
# Detection file watcher (watchdog)
# ---------------------------------------------------------------------------

class DetectionFileHandler(FileSystemEventHandler):
    """Watches detection JSON files for updates from the runner."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._loop = loop
        self._last_mtime: dict[str, float] = {}

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix != ".json":
            return
        # Only process per-day files (YYYY-MM-DD.json), skip summaries
        if len(path.stem) != 10 or path.stem[4] != "-":
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
        state.last_detection_updated_at = time.time()
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


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

async def _staleness_checker():
    """Periodic task: evaluate data freshness, broadcast state changes."""
    while True:
        await asyncio.sleep(STALENESS_CHECK_INTERVAL)
        new_state = _determine_market_state()
        if new_state != state.market_state:
            log.info("Market state: %s -> %s", state.market_state, new_state)
            state.market_state = new_state
            await broadcast(state.status_payload)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    log.info("MIRROR backend starting on port %d", PORT)

    loop = asyncio.get_running_loop()

    # Determine initial market state
    state.market_state = _determine_market_state()
    today = _today_forex_day()

    # Seed freshness timestamps from file mtimes (prevents false STALE on restart)
    staging = _staging_path_for(today)
    if staging.exists():
        state.last_bar_received_at = staging.stat().st_mtime
    det_path = DETECTION_DIR / f"{today}.json"
    if det_path.exists():
        state.last_detection_updated_at = det_path.stat().st_mtime

    log.info("Forex day: %s — Market state: %s", today, state.market_state)

    # Seed initial staging file sizes so watcher only sees new data
    if STAGING_DIR.exists():
        for f in STAGING_DIR.iterdir():
            if f.suffix == ".jsonl":
                state.last_known_sizes[f.stem] = f.stat().st_size

    # Pre-load today's bars if live, otherwise last available date
    load_date = today if state.market_state == "LIVE" else _last_available_date()
    if load_date:
        state.cached_bars_5m = _load_bars_as_dicts(load_date, "5m")
        state.cached_detections = _load_detections(load_date)
        # If today has no detections yet, fall back to last available
        if not state.cached_detections and load_date == today:
            fallback = _last_available_date()
            if fallback and fallback != today:
                log.info("No detections for %s, falling back to %s", today, fallback)
                state.cached_detections = _load_detections(fallback)
        # Extract WorldState from detection JSON
        if isinstance(state.cached_detections, dict):
            ws = state.cached_detections.get("world_state")
            if ws:
                state.cached_world_state = ws
        if state.cached_bars_5m:
            state.last_bar_time = state.cached_bars_5m[-1].get("time", "")

    log.info(
        "Pre-loaded %d bars, %d detection keys",
        len(state.cached_bars_5m),
        len(state.cached_detections),
    )

    # Start file watcher
    try:
        state.observer = _start_file_watcher(loop)
    except Exception as exc:
        log.warning("Could not start staging file watcher: %s", exc)

    # Start detection file watcher
    try:
        state.detection_observer = _start_detection_watcher(loop)
    except Exception as exc:
        log.warning("Could not start detection file watcher: %s", exc)

    # Start periodic staleness checker
    staleness_task = asyncio.create_task(_staleness_checker())
    log.info("Staleness checker started (interval=%ds, bar_threshold=%ds, det_threshold=%ds)",
             STALENESS_CHECK_INTERVAL, STALE_BAR_THRESHOLD, STALE_DETECTION_THRESHOLD)

    yield  # ---- app is running ----

    # Shutdown
    log.info("MIRROR backend shutting down…")
    staleness_task.cancel()
    try:
        await staleness_task
    except asyncio.CancelledError:
        pass
    state._shutdown_event.set()

    if state.detection_observer:
        state.detection_observer.stop()
        state.detection_observer.join(timeout=5)

    if state.observer:
        state.observer.stop()
        state.observer.join(timeout=5)

    # Close all WebSocket connections
    for ws in state.connected_clients.copy():
        try:
            await ws.close()
        except Exception:
            pass
    state.connected_clients.clear()
    log.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="MIRROR",
    description="Live trading dashboard backend — a8ra system state projection",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/api/bars/{forex_day}")
async def get_bars(forex_day: str, tf: str = Query("5m", description="Timeframe: 1m, 5m, 15m, 1H, 4H, 1D")):
    """Serve candle data for a date via RiverBarAdapter + tf_aggregator."""
    try:
        date.fromisoformat(forex_day)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid date format: {forex_day}. Use YYYY-MM-DD."},
        )
    bars = _load_bars_as_dicts(forex_day, tf)
    return {"forex_day": forex_day, "tf": tf, "count": len(bars), "data": bars}


@app.get("/api/bars-range")
async def get_bars_range(
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
    tf: str = Query("5m", description="Timeframe: 1m, 5m, 15m, 1H, 4H, 1D"),
):
    """Serve candle data across a date range for seamless multi-day scrolling."""
    try:
        date.fromisoformat(start)
        date.fromisoformat(end)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid date format. Use YYYY-MM-DD."})
    bars = _load_bars_range(start, end, tf)
    return {"start": start, "end": end, "tf": tf, "count": len(bars), "data": bars}


@app.get("/api/detections/{forex_day}")
async def get_detections(forex_day: str):
    """Serve detection JSON from dexter output."""
    try:
        date.fromisoformat(forex_day)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid date format: {forex_day}. Use YYYY-MM-DD."},
        )
    detections = _load_detections(forex_day)
    if not detections:
        return JSONResponse(
            status_code=404,
            content={"error": f"No detections found for {forex_day}"},
        )
    return detections


@app.get("/api/dates")
async def get_dates():
    """List available detection dates."""
    dates = _available_detection_dates()
    return {"dates": dates, "count": len(dates)}


@app.get("/api/sessions/{forex_day}")
async def get_sessions(forex_day: str):
    """Compute session bands for a forex day (DST-correct via zoneinfo)."""
    try:
        date.fromisoformat(forex_day)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": f"Invalid date: {forex_day}"})
    bands = _compute_session_bands(forex_day)
    return {"forex_day": forex_day, "sessions": bands}


@app.get("/api/sessions-range")
async def get_sessions_range(
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
):
    """Compute session bands across a date range (for HTF multi-day views)."""
    try:
        date.fromisoformat(start)
        date.fromisoformat(end)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid date format."})
    bands = _compute_sessions_range(start, end)
    return {"start": start, "end": end, "sessions": bands}


@app.get("/api/available-range")
async def get_available_range():
    """Return earliest/latest dates in River parquet data."""
    return _available_river_range()


@app.get("/api/weeks")
async def get_weeks():
    """Return week manifest — detection dates grouped into forex weeks."""
    weeks = _build_week_manifest()
    return {"weeks": weeks, "count": len(weeks)}


@app.get("/api/world-state/{forex_day}")
async def get_world_state(forex_day: str):
    """Return WorldState and snapshots for a forex day."""
    try:
        date.fromisoformat(forex_day)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": f"Invalid date: {forex_day}"})
    det = _load_detections(forex_day)
    if not det:
        return JSONResponse(status_code=404, content={"error": f"No detections for {forex_day}"})
    ws = det.get("world_state", {})
    snapshots = det.get("world_state_snapshots", [])
    return {"forex_day": forex_day, "world_state": ws, "snapshots": snapshots}


@app.get("/api/heartbeat")
async def get_heartbeat():
    """Read phoenix-river heartbeat and return streamer status."""
    hb = _load_heartbeat()
    return {
        "heartbeat": hb,
        "mirror": {
            "market_state": state.market_state,
            "last_bar": state.last_bar_time,
            "connected_clients": len(state.connected_clients),
        },
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Live data WebSocket — pushes bars, detections, status in real time."""
    await ws.accept()
    state.connected_clients.add(ws)
    client_id = f"{ws.client.host}:{ws.client.port}" if ws.client else "unknown"
    log.info("WS client connected: %s (total: %d)", client_id, len(state.connected_clients))

    try:
        # Send full current state on connect
        await ws.send_text(json.dumps(state.status_payload))

        if state.cached_bars_5m:
            await ws.send_text(json.dumps({
                "type": "bars",
                "tf": "5m",
                "data": state.cached_bars_5m,
            }))

        if state.cached_detections:
            det_payload = state.cached_detections.get(
                "detections_by_primitive", state.cached_detections
            )
            await ws.send_text(json.dumps({
                "type": "detections",
                "data": det_payload,
            }))

        if state.cached_world_state:
            await ws.send_text(json.dumps({
                "type": "world_state",
                "data": state.cached_world_state,
            }))

        # Push session bands for the current forex day
        try:
            today = _today_forex_day()
            session_bands = _compute_session_bands(today)
            if session_bands:
                await ws.send_text(json.dumps({
                    "type": "sessions",
                    "data": session_bands,
                }))
        except Exception:
            log.warning("Failed to push session bands on WS connect")

        # Push world_state snapshots if available
        if state.cached_detections and isinstance(state.cached_detections, dict):
            snapshots = state.cached_detections.get("world_state_snapshots", [])
            if snapshots:
                await ws.send_text(json.dumps({
                    "type": "world_state_snapshots",
                    "data": snapshots,
                }))

        # Keep connection alive — listen for client pings / messages
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=60)
                # Handle client messages (e.g. ping)
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await ws.send_text(json.dumps({"type": "pong"}))
                    elif msg.get("type") == "subscribe":
                        # Future: handle per-client subscriptions
                        pass
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                # Send a keepalive status
                try:
                    await ws.send_text(json.dumps(state.status_payload))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("WS error for %s: %s", client_id, exc)
    finally:
        state.connected_clients.discard(ws)
        log.info("WS client disconnected: %s (remaining: %d)", client_id, len(state.connected_clients))


# ---------------------------------------------------------------------------
# Static file serving for frontend
# ---------------------------------------------------------------------------

# Mount static files last so API routes take precedence
if MIRROR_STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(MIRROR_STATIC_DIR), html=True), name="static")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=PORT,
        log_level="info",
        reload=False,
    )
