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
```

## Flow Validator Guidance: pytest

Each flow validator subagent runs python3 -c inline checks. Since this is a pure Python library:
- No shared state between tests (each Python invocation is isolated)
- No accounts, sessions, or credentials needed
- No isolation concerns between parallel subagents — each runs independent Python processes
- All assertions can be verified by importing modules and checking outputs against expected values
- Price comparisons use tolerance of 1e-6 (abs(actual - expected) < 1e-6)
- Count assertions must be exact matches

## Quirks

- Session labels: RA tagger uses 6 categories but baseline uses 4. Detectors map `pre_london`/`pre_ny` → `"other"`.
- Ghost bars: volume==0 bars are included in DataFrame but skipped by candle-pattern detectors.
- The `EqualHLDetector` is a DEFERRED stub that raises `NotImplementedError`.
