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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_forex_day() -> str:
    """Return today's forex day label (NY-based)."""
    from bead_field.producers.utils.tf_aggregator import get_forex_day
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


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

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
