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
        self.market_state: str = "CONNECTING"  # LIVE | MARKET_CLOSED | CONNECTING
        self.last_bar_time: str = ""
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
        return [
            {
                "time": bar.bar_time,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
            }
            for bar in agg
        ]
    except Exception as exc:
        log.error("Failed to load bars for %s tf=%s: %s", forex_day, tf, exc)
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


def _determine_market_state() -> str:
    """Decide if the market is currently live based on staging file existence."""
    today = _today_forex_day()
    staging = _staging_path_for(today)
    if staging.exists() and staging.stat().st_size > 0:
        return "LIVE"
    return "MARKET_CLOSED"


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
        log.info(
            "New bars: %d lines from %s (last: %s)",
            len(new_lines), date_str, state.last_bar_time,
        )

        # Transition to LIVE if we were MARKET_CLOSED
        if state.market_state != "LIVE":
            state.market_state = "LIVE"
            await broadcast(state.status_payload)

        # Reload and push all standard timeframes
        for tf in ["1m", "5m", "15m", "1H", "4H"]:
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


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    log.info("MIRROR backend starting on port %d", PORT)

    loop = asyncio.get_running_loop()

    # Determine initial market state
    state.market_state = _determine_market_state()
    today = _today_forex_day()
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

    yield  # ---- app is running ----

    # Shutdown
    log.info("MIRROR backend shutting down…")
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
