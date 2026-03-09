# a8ra Research Accelerator

Modular, config-driven detection engine for ICT trading primitives — plus interactive calibration charts.

---

## Phase 1 Detection Engine (`src/ra/`)

The monolithic pipeline has been extracted into **12 independent detector modules**, each implementing a `PrimitiveDetector` ABC. The cascade engine resolves the dependency graph via topological sort and runs every detector in the correct order.

### Quick Start

```bash
pip install -e .

python run.py --config configs/locked_baseline.yaml \
              --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv \
              --output results/
```

Results land as one JSON file per primitive per timeframe in `results/`.

### Architecture

| Layer | Description |
|-------|-------------|
| **PrimitiveDetector ABC** | `detect(bars, params, upstream, context) → DetectionResult`. Every module declares `required_upstream()` for dependency resolution. |
| **CascadeEngine** | Topological-sort over the dependency graph, feeds each detector its upstream results automatically. |
| **Config** | YAML with Pydantic v2 validation (`extra='forbid'`), per-TF overrides, locked param values + sweep ranges. |
| **Data layer** | CSV loader → DuckDB-backed TF aggregation (1m → 5m/15m/1H/4H/1D). Session tagging included. |

### Detector Modules (12)

| # | Module | Upstream | File |
|---|--------|----------|------|
| 1 | **FVG** (+ IFVG, BPR) | — | `fvg.py` |
| 2 | **SwingPoints** | — | `swing_points.py` |
| 3 | **Displacement** | — | `displacement.py` |
| 4 | **SessionLiquidity** | — | `session_liquidity.py` |
| 5 | **AsiaRange** | — | `asia_range.py` |
| 6 | **ReferenceLevels** | — | `reference_levels.py` |
| 7 | **EqualHL** *(deferred)* | SwingPoints | `equal_hl.py` |
| 8 | **MSS** | SwingPoints, Displacement, FVG | `mss.py` |
| 9 | **OrderBlock** | Displacement, MSS | `order_block.py` |
| 10 | **HTFLiquidity** | SwingPoints | `htf_liquidity.py` |
| 11 | **OTE** | MSS | `ote.py` |
| 12 | **LiquiditySweep** | SessionLiq, RefLevels, HTFLiq, SwingPts, Displacement | `liquidity_sweep.py` |

### Testing

```bash
python -m pytest tests/ -v
```

631 tests total (378 Phase 1 + 253 Phase 2) covering every detector, the evaluation engine, and a **master regression suite** that replays the locked baseline config against 32 fixture files to guarantee bit-exact reproduction.

### Config

`configs/locked_baseline.yaml` — single source of truth for all production parameters. Key features:

- Pydantic v2 schema with `extra='forbid'` (typo = instant error)
- Per-primitive locked values and sweep ranges
- Per-timeframe overrides
- Full dependency graph declaration

---

## Phase 2 Evaluation Engine (`src/ra/evaluation/` & `src/ra/output/`)

Parameter sweep, comparison statistics, and walk-forward validation — all driven by the same YAML configs and detection engine from Phase 1.

### Key Components

| Component | Description |
|-----------|-------------|
| **EvaluationRunner** | Sweep (single-param), 2D grid, and locked-replay modes. Drives the cascade engine across parameter ranges. |
| **Comparison Stats** | Side-by-side diff of two configs: detection count deltas, Jaccard overlap, per-primitive breakdown. |
| **Cascade Funnel** | Stage-by-stage attrition stats across the detector dependency graph (how many signals survive each cascade layer). |
| **Walk-Forward Validation** | Sliding-window train/test splits over time. Validates parameter stability across out-of-sample windows. |
| **River Adapter** | Full DuckDB-based parquet reader for `~/phoenix-river` data. Streams tick/bar data by symbol and date range. |
| **JSON Export** | Structured output via 5 schemas (4A–4E), documented in `.factory/library/output_schemas.md`. |

### CLI (`eval.py`)

Three subcommands: `sweep`, `compare`, `walk-forward`.

```bash
# Parameter sweep — single param
python3 eval.py sweep --config configs/locked_baseline.yaml \
                      --data data/eurusd_1m_*.csv \
                      --primitive displacement --x-param ltf.close_gate \
                      --output results/sweep/

# Walk-forward validation via River adapter
python3 eval.py walk-forward --river EURUSD --start 2024-01-01 --end 2024-08-31 \
                             --config configs/locked_baseline.yaml \
                             --output results/wf/

# Compare two configs
python3 eval.py compare --config configs/locked_baseline.yaml \
                        --data data/eurusd_1m_2024-01-07_to_2024-01-12.csv \
                        --output results/compare/
```

### Output Schemas (4A–4E)

All evaluation results are emitted as structured JSON conforming to 5 schemas:

- **4A** — Single sweep result
- **4B** — 2D grid sweep result
- **4C** — Comparison report
- **4D** — Cascade funnel statistics
- **4E** — Walk-forward validation report

Full schema definitions: `.factory/library/output_schemas.md`

---

## Calibration Visual Bible (`site/`)

Interactive threshold calibration tool for visual review of L1.5 parameter tuning on EURUSD data.

```bash
# Open locally — no server needed
open site/index.html
# or
python -m http.server 8000 --directory site
# then visit http://localhost:8000
```

Six chart pages: FVG, Swing Points, Displacement, Order Blocks, NY Windows, Asia Range — each with per-TF sliders and detection markers built on TradingView Lightweight Charts v4.

---

## Repo Structure

```
├── src/ra/                        # Detection engine package
│   ├── config/                    # YAML loader + Pydantic v2 schema
│   ├── data/                      # CSV loader, TF aggregator, session tagger
│   ├── detectors/                 # 12 PrimitiveDetector modules
│   ├── engine/                    # PrimitiveDetector ABC, CascadeEngine, registry
│   ├── evaluation/                # EvaluationRunner, comparison, cascade stats, walk-forward
│   └── output/                    # JSON export (schemas 4A–4E)
│
├── tests/                         # 631 pytest tests (378 Phase 1 + 253 Phase 2)
│   ├── fixtures/baseline_output/  # 32 golden-file regression fixtures
│   └── test_*.py                  # Per-module + cascade + regression + evaluation suites
│
├── configs/
│   └── locked_baseline.yaml       # Production config (locked params, dep graph)
│
├── run.py                         # CLI entry point for cascade pipeline (Phase 1)
├── eval.py                        # CLI entry point for evaluation engine (Phase 2)
├── pyproject.toml                 # Package metadata (Python ≥3.12, pydantic, pandas, duckdb)
│
├── site/                          # Static calibration chart tool
│   ├── index.html                 # Landing page → 6 chart pages
│   └── *.html / *.json            # Chart pages + data
│
├── pipeline/                      # Legacy data processing scripts
├── data/                          # Source 1m EURUSD CSV
├── research/                      # Phase 1 research archive
├── PROJECT_STATE.md               # Full project checkpoint
└── SYNTHETIC_OLYA_METHOD_v0.5.yaml
```

## Technical Details

- **Python ≥ 3.12** — pandas, duckdb, pyarrow, pydantic v2, pyyaml
- **Timestamps**: All NY time (EST = UTC−5 for Jan 2024 data)
- **Forex day boundary**: 17:00 NY
- **Sessions**: Asia 19:00–00:00, LOKZ 02:00–05:00, NYOKZ 07:00–10:00 (NY)
- **Deterministic IDs**: `{primitive}_{tf}_{timestamp_ny}_{direction}`
