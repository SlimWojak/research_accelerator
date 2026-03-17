# Environment

Environment variables, external dependencies, and setup notes.

**What belongs here:** Required env vars, external API keys/services, dependency quirks, platform-specific notes.
**What does NOT belong here:** Service ports/commands (use `.factory/services.yaml`).

---

## Python Environment

- Python 3.12.6 on macOS (darwin 25.3.0, Apple Silicon)
- 16 cores, 64 GB RAM
- No virtual environment — system Python with packages installed globally

## Dependencies

All pre-installed:
- pandas 2.2.3
- duckdb 1.0.0
- pydantic 2.12.4 (v2)
- pyyaml 6.0.3
- pytest 9.0.1
- pyarrow 22.0.0

## Data Paths

- CSV dataset: `data/eurusd_1m_2024-01-07_to_2024-01-12.csv` (7,177 1m bars)
- Baseline fixtures: `tests/fixtures/baseline_output/` (32 JSON files)
- Reference pipeline: `pipeline/preprocess_data_v2.py` (2,816 lines, read-only)
- Canonical spec: `SYNTHETIC_OLYA_METHOD_vLOCK.yaml` (read-only)
- Detection data: `site/data/detections/` (25 weeks, all TFs including 1D, 105,917 detections)
- Candle data: `site/data/candles/` (25 weeks, TFs 1m–1D)
- Ground truth: `research/ground_truth/annotated_trades.yaml` (4 annotated trades)
- State detection spec: `research/STATE_DETECTION_LOGIC_v2.yaml` (v2.1, 937 lines)
- AutoResearch: `tools/autoresearch/evaluate.py` + `sweep.py`
- Architecture docs: `docs/ARCHITECTURE.md`, `docs/TOOL_GUIDE.md`

## Known Quirks

- **pyproject.toml build-backend**: Must use `setuptools.build_meta` (not `setuptools.backends._legacy:_Backend`). The latter is an internal setuptools path that breaks `pip install -e`.
- **Daily detection ATR limitation**: 1D displacement/MSS rarely fire because weekly 5-day windows provide insufficient bars for ATR(14). 4H serves as proxy. Fix: cross-week bar loading.

## Environment Variables

- `RIVER_ROOT`: Path to phoenix-river directory (default: `~/phoenix-river`). Not needed for Phase 1 (CSV fallback).
