# User Testing

Testing surface: tools, URLs, setup steps, isolation notes, known quirks.

**What belongs here:** How to manually test and validate the detection engine.

---

## Testing Surface

This is a Python library + CLI project. No web UI, no API server, no database.

### Primary Testing Method: pytest
```bash
python3 -m pytest tests/ -v --tb=short -x
```

### CLI Entry Point
```bash
python3 run.py --config configs/locked_baseline.yaml \
               --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv \
               --output results/
```

### Python Import Checks
```python
# Example: verify a detector produces correct count
from ra.config.loader import load_config
from ra.data.csv_loader import load_csv
from ra.detectors.fvg import FVGDetector

config = load_config('configs/locked_baseline.yaml')
bars_5m = load_csv('data/eurusd_1m_2024-01-07_to_2024-01-12.csv', timeframe='5m')
result = FVGDetector().detect(bars_5m, config.primitives.fvg.params)
print(f"FVG count: {len(result.detections)}")  # Should be 345
```

## Baseline Comparison

Ground truth: `tests/fixtures/baseline_output/` (32 JSON files)
Manifest: `tests/fixtures/BASELINE_MANIFEST.md` (exact counts per primitive per TF)

## Tools Available

- `python3` (3.12.6) — run scripts, import modules
- `pytest` (9.0.1) — run test suite
- Standard CLI tools (diff, cat, etc.)

## No Browser/TUI Testing Needed

This mission has no web frontend, API endpoints, or terminal UI. All validation is through pytest output and CLI execution.

## Flow Validator Guidance: python-check

**Testing tool:** Direct Python script execution via `python3 -c "..."` commands.

**Isolation:** No shared state between subagents. Each subagent runs independent Python scripts that read-only from the installed `ra` package and CSV data. No writes to shared resources. No accounts or credentials needed.

**How to test assertions:**
1. For `python-check` evidence: Write a Python script that imports from `ra`, loads data/config, runs the relevant operation, and asserts the expected outcome.
2. For `pytest-output` evidence: Run `python3 -m pytest tests/<specific_test_file>.py -v --tb=short -k <test_pattern>` and check output.
3. All paths are absolute from `/Users/echopeso/research_accelerator/`.
4. The CSV data file is at `data/eurusd_1m_2024-01-07_to_2024-01-12.csv`.
5. Config file is at `configs/locked_baseline.yaml`.

**Key imports:**
```python
from ra.config.loader import load_config
from ra.data.csv_loader import load_csv
from ra.data.tf_aggregator import aggregate_tf
from ra.data.session_tagger import tag_sessions
```

**No modifications allowed:** Do not edit any source files. Testing is read-only validation.
