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

# 2. Sweep (1D) — produces Schema 4D (sweep JSON, 1D line, y.param='_single')
echo "[2/4] Running eval.py sweep 1D (displacement: atr_multiplier only) ..."
python3 "$ROOT_DIR/eval.py" sweep \
  --config "$CONFIG" \
  --data "$DATA" \
  --primitive displacement \
  --x-param ltf.atr_multiplier \
  --metric detection_count \
  --output "$EVAL_DIR"
# Rename 1D sweep so it doesn't collide with the 2D filename
mv "$EVAL_DIR/sweep_displacement_ltf_atr_multiplier.json" \
   "$EVAL_DIR/sweep_displacement_1d_atr_multiplier.json"
echo "  ✓ 1D sweep done"

# 3. Sweep (2D) — produces Schema 4D (sweep JSON, 2D grid)
echo "[3/4] Running eval.py sweep 2D (displacement: atr_multiplier × body_ratio) ..."
python3 "$ROOT_DIR/eval.py" sweep \
  --config "$CONFIG" \
  --data "$DATA" \
  --primitive displacement \
  --x-param ltf.atr_multiplier \
  --y-param ltf.body_ratio \
  --metric detection_count \
  --output "$EVAL_DIR"
echo "  ✓ 2D sweep done"

# 4. Walk-forward — produces Schema 4E (walk_forward JSON)
echo "[4/4] Running eval.py walk-forward ..."
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
