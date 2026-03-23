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

# --- Check port availability ---
if lsof -i :8300 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[MIRROR] ERROR: Port 8300 already in use. Kill the existing process first:"
    lsof -i :8300 -sTCP:LISTEN
    exit 1
fi

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
SERVER_FAILS=0
RUNNER_FAILS=0
MAX_CONSECUTIVE_FAILS=3

while true; do
    # Check server
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        SERVER_FAILS=$((SERVER_FAILS + 1))
        if [[ $SERVER_FAILS -ge $MAX_CONSECUTIVE_FAILS ]]; then
            echo "[MIRROR] ERROR: Server failed $SERVER_FAILS times consecutively. Giving up."
            echo "[MIRROR] Check if port 8300 is in use: lsof -i :8300"
            break
        fi
        echo "[MIRROR] WARNING: Server died (attempt $SERVER_FAILS/$MAX_CONSECUTIVE_FAILS), restarting in 5s..."
        sleep 5
        cd "$BACKEND_DIR"
        "$SERVER_PYTHON" server.py &
        SERVER_PID=$!
        echo "[MIRROR] Server restarted (PID $SERVER_PID)"
    else
        SERVER_FAILS=0
    fi

    # Check runner
    if ! kill -0 "$RUNNER_PID" 2>/dev/null; then
        RUNNER_FAILS=$((RUNNER_FAILS + 1))
        if [[ $RUNNER_FAILS -ge $MAX_CONSECUTIVE_FAILS ]]; then
            echo "[MIRROR] ERROR: Runner failed $RUNNER_FAILS times consecutively. Giving up."
            break
        fi
        echo "[MIRROR] WARNING: Runner died (attempt $RUNNER_FAILS/$MAX_CONSECUTIVE_FAILS), restarting in 5s..."
        sleep 5
        DEXTER_ROOT="$HOME/dexter" \
        PYTHONPATH="$RUNNER_PYTHONPATH" \
        "$RUNNER_PYTHON" "$BACKEND_DIR/detection_runner.py" &
        RUNNER_PID=$!
        echo "[MIRROR] Runner restarted (PID $RUNNER_PID)"
    else
        RUNNER_FAILS=0
    fi

    sleep 10
done
