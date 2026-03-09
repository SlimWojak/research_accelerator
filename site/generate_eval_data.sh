#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# generate_eval_data.sh — Generate Phase 2 evaluation fixture data for the
# comparison interface. Produces Schema 4A, 4D, and 4E JSON in site/eval/.
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EVAL_DIR="$SCRIPT_DIR/eval"

CONFIG="$ROOT_DIR/configs/locked_baseline.yaml"
DATA="$ROOT_DIR/data/eurusd_1m_2024-01-07_to_2024-01-12.csv"

mkdir -p "$EVAL_DIR"

echo "=== Generating Phase 2 evaluation data ==="
echo "Config: $CONFIG"
echo "Data:   $DATA"
echo "Output: $EVAL_DIR"
echo ""

# 1. Compare — produces Schema 4A (evaluation_run.json)
echo "[1/3] Running eval.py compare ..."
python3 "$ROOT_DIR/eval.py" compare \
  --config "$CONFIG" \
  --data "$DATA" \
  --output "$EVAL_DIR"
echo "  ✓ compare done"

# 2. Sweep — produces Schema 4D (sweep JSON)
echo "[2/3] Running eval.py sweep (displacement: atr_multiplier × body_ratio) ..."
python3 "$ROOT_DIR/eval.py" sweep \
  --config "$CONFIG" \
  --data "$DATA" \
  --primitive displacement \
  --x-param ltf.atr_multiplier \
  --y-param ltf.body_ratio \
  --metric detection_count \
  --output "$EVAL_DIR"
echo "  ✓ sweep done"

# 3. Walk-forward — produces Schema 4E (walk_forward JSON)
echo "[3/3] Running eval.py walk-forward ..."
python3 "$ROOT_DIR/eval.py" walk-forward \
  --config "$CONFIG" \
  --data "$DATA" \
  --primitive displacement \
  --metric detection_count \
  --output "$EVAL_DIR"
echo "  ✓ walk-forward done"

echo ""
echo "=== Generated files ==="
ls -la "$EVAL_DIR"/*.json 2>/dev/null || echo "(no JSON files found)"
echo ""
echo "Done."
