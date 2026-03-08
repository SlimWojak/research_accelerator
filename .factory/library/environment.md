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
- Canonical spec: `SYNTHETIC_OLYA_METHOD_v0.5.yaml` (read-only)

## Environment Variables

- `RIVER_ROOT`: Path to phoenix-river directory (default: `~/phoenix-river`). Not needed for Phase 1 (CSV fallback).
