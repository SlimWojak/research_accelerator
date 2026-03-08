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

378 tests covering every detector plus a **master regression suite** that replays the locked baseline config against 32 fixture files to guarantee bit-exact reproduction.

### Config

`configs/locked_baseline.yaml` — single source of truth for all production parameters. Key features:

- Pydantic v2 schema with `extra='forbid'` (typo = instant error)
- Per-primitive locked values and sweep ranges
- Per-timeframe overrides
- Full dependency graph declaration

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
│   ├── evaluation/                # (placeholder)
│   └── output/                    # (placeholder)
│
├── tests/                         # 378 pytest tests
│   ├── fixtures/baseline_output/  # 32 golden-file regression fixtures
│   └── test_*.py                  # Per-module + cascade + regression suites
│
├── configs/
│   └── locked_baseline.yaml       # Production config (locked params, dep graph)
│
├── run.py                         # CLI entry point for cascade pipeline
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
