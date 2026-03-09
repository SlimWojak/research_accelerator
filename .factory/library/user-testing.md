# User Testing Guide — RA Phase 1: Detection Engine

## Testing Surface

This is a **pure Python library** with no web UI, no services, no databases. Testing is done through:

1. **pytest** — `python3 -m pytest tests/ -v --tb=short -x -q --no-header -p no:cacheprovider`
2. **Python inline checks** — `python3 -c "..."` for assertion-specific verification
3. **CLI** (when cascade is built) — `python3 run.py --config configs/locked_baseline.yaml --data data/... --output results/`

## Environment Setup

- Python 3.12.6
- Install: `cd /Users/echopeso/research_accelerator && python3 -m pip install -e ".[dev]" --quiet`
- No services to start/stop
- No external dependencies

## Data

- Source CSV: `data/eurusd_1m_2024-01-07_to_2024-01-12.csv` (7,177 1m bars)
- Baseline fixtures: `tests/fixtures/baseline_output/*.json` (read-only, regression ground truth)
- Config: `configs/locked_baseline.yaml`

## Key Imports

```python
from ra.config.loader import load_config
from ra.data.csv_loader import load_csv
from ra.data.tf_aggregator import aggregate_tf
from ra.data.session_tagger import tag_sessions
from ra.detectors.fvg import FVGDetector
from ra.detectors.swing_points import SwingPointDetector
from ra.detectors.displacement import DisplacementDetector
from ra.detectors.session_liquidity import SessionLiquidityDetector
from ra.detectors.asia_range import AsiaRangeDetector
from ra.detectors.reference_levels import ReferenceLevelDetector
from ra.detectors.equal_hl import EqualHLDetector
from ra.detectors.mss import MSSDetector
from ra.detectors.order_block import OrderBlockDetector
from ra.detectors.htf_liquidity import HTFLiquidityDetector
from ra.detectors.ote import OTEDetector
from ra.detectors.liquidity_sweep import LiquiditySweepDetector
from ra.engine.cascade import CascadeEngine
```

## Composite Detector Testing Notes

### MSS Detector
- Depends on: swing_points, displacement, fvg (for tagging)
- Config section: `mss`
- Key fields: direction, break_type (reversal/continuation), broken_swing, fvg_created, window_used
- Regression: 1m=179, 5m=44, 15m=20

### Order Block Detector
- Depends on: mss, displacement
- Config section: `order_block`
- Key fields: zone (top/bottom body-based), anchor_time, trigger_mss, retests list
- Regression: 1m=138, 5m=37, 15m=17

### HTF Liquidity Detector
- Uses higher timeframes: H1, H4, D1, W1
- Fractal swing detection with touch counting and rotation gate
- Regression: H1=3 pools, H4=1 pool, D1=0, W1=0

### OTE Detector
- Depends on: mss results
- Fib levels: 0.618, 0.705, 0.79
- Kill zone gate: only actionable within LOKZ/NYOKZ

### Liquidity Sweep Detector
- Depends on: session_liquidity, reference_levels, htf_liquidity, swing_points (promoted)
- Multi-source level pool with temporal gating
- Types: base, qualified, delayed, continuation

### Cascade Engine
- Topological sort of dependency graph
- Caching of unchanged upstream
- CLI entry point: `python3 run.py --config ... --data ... --output ...`

## Flow Validator Guidance: pytest

Each flow validator subagent runs python3 -c inline checks. Since this is a pure Python library:
- No shared state between tests (each Python invocation is isolated)
- No accounts, sessions, or credentials needed
- No isolation concerns between parallel subagents — each runs independent Python processes
- All assertions can be verified by importing modules and checking outputs against expected values
- Price comparisons use tolerance of 1e-6 (abs(actual - expected) < 1e-6)
- Count assertions must be exact matches

## Phase 2 — Evaluation Engine Testing

### Additional Imports (Phase 2)

```python
from ra.evaluation.param_extraction import extract_params, extract_sweep_combos
from ra.evaluation.runner import EvaluationRunner
from ra.evaluation.comparison import compute_stats, compare_pairwise
from ra.evaluation.cascade_stats import cascade_funnel
from ra.evaluation.walk_forward import WalkForwardRunner
from ra.output.json_export import (
    export_evaluation_run, export_grid_sweep, export_walk_forward,
    RAJSONEncoder
)
from ra.data.river_adapter import RiverAdapter
```

### CLI Testing (Phase 2)

```bash
# Sweep
python3 eval.py sweep --config configs/locked_baseline.yaml --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv --primitive fvg --x-param floor_threshold_pips --output /tmp/test_sweep/

# Compare
python3 eval.py compare --config configs/locked_baseline.yaml --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv --output /tmp/test_compare/

# Walk-forward (CSV)
python3 eval.py walk-forward --config configs/locked_baseline.yaml --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv --output /tmp/test_wf/

# Walk-forward (River)
python3 eval.py walk-forward --config configs/locked_baseline.yaml --river EURUSD --start 2024-01-01 --end 2024-06-30 --output /tmp/test_wf_river/

# Phase 1 backward compatibility
python3 run.py --config configs/locked_baseline.yaml --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv --output /tmp/test_phase1/
```

### River Data

- Parquet data: `~/phoenix-river/EURUSD/{year}/{mm}/{dd}.parquet`
- Asia/Bangkok timezone → normalized to UTC → NY time
- RIVER_ROOT env var override supported

### Output Schemas

All output JSON conforms to schemas in `.factory/library/output_schemas.md`:
- Schema 4A: Evaluation Run (top-level envelope)
- Schema 4B: Per-Config Result
- Schema 4C: Pairwise Comparison
- Schema 4D: Grid Sweep
- Schema 4E: Walk-Forward

## Flow Validator Guidance: pytest

Each flow validator subagent runs python3 -c inline checks or python3 -m pytest for targeted tests. Since this is a pure Python library:
- No shared state between tests (each Python invocation is isolated)
- No accounts, sessions, or credentials needed
- No isolation concerns between parallel subagents — each runs independent Python processes
- All assertions can be verified by importing modules and checking outputs against expected values
- Price comparisons use tolerance of 1e-6 (abs(actual - expected) < 1e-6)
- Count assertions must be exact matches
- CLI tests should use separate /tmp/ output directories per subagent to avoid file conflicts
- Each subagent should use a unique temp directory prefix (e.g., /tmp/flow_comp_*, /tmp/flow_wf_*, /tmp/flow_cli_*)

## Quirks

- Session labels: RA tagger uses 6 categories but baseline uses 4. Detectors map `pre_london`/`pre_ny` → `"other"`.
- Ghost bars: volume==0 bars are included in DataFrame but skipped by candle-pattern detectors.
- The `EqualHLDetector` is a DEFERRED stub that raises `NotImplementedError`.
- numpy/pandas types must be serialized carefully in JSON: int64→int, float64→float, NaN→null, Timestamp→ISO string.
- Walk-forward with 5-day CSV produces tiny windows — structural smoke test only.
