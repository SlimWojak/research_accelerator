# Architecture

Architectural decisions, patterns, and conventions for the RA detection engine.

**What belongs here:** Design decisions, module patterns, coding conventions discovered during implementation.

---

## Project Structure

```
src/ra/
  __init__.py
  config/
    loader.py          # Parse + validate YAML config via pydantic v2
    schema.py          # Pydantic models for config validation
  data/
    csv_loader.py      # Load CSV, parse timestamps, convert to NY timezone
    river_adapter.py   # Read-only River/parquet consumer (stub for Phase 1)
    tf_aggregator.py   # 1m -> 5m/15m/1H/4H/1D aggregation
    session_tagger.py  # Tag bars with session/kill zone/forex day
  engine/
    base.py            # PrimitiveDetector ABC + Detection + DetectionResult
    cascade.py         # Dependency resolver + cascade runner
    registry.py        # Module registration + variant lookup
  detectors/
    fvg.py             # FVG + IFVG + BPR
    swing_points.py    # Swing point detection
    displacement.py    # Displacement (single + cluster + override)
    session_liquidity.py
    asia_range.py
    mss.py             # Market Structure Shift (composite)
    order_block.py     # Order Block (composite)
    liquidity_sweep.py # Multi-source composite
    htf_liquidity.py   # HTF EQH/EQL pools
    ote.py             # Optimal Trade Entry zones
    reference_levels.py
    equal_hl.py        # DEFERRED stub
```

## Key Patterns

### PrimitiveDetector Interface
All detectors implement `PrimitiveDetector` ABC from `engine/base.py`:
- `detect(bars, params, upstream=None, context=None) -> DetectionResult`
- `required_upstream() -> list[str]`
- Deterministic: same inputs -> same outputs

### Detection IDs
Format: `{primitive}_{tf}_{timestamp_ny}_{direction}`
Example: `fvg_5m_2024-01-08T09:10:00_bull`

### Config-Driven Params
Every L1.5 parameter comes from YAML config via pydantic models.
No hardcoded thresholds in detector code.
Engine rejects unknown params (pydantic `extra='forbid'`).

### Ghost Bar Handling
Ghost bars (`is_ghost == True`) are included in DataFrames but skipped by all detectors.
A ghost bar never triggers a detection.

### Regression Testing
Each detector has regression tests comparing against baseline fixtures in `tests/fixtures/baseline_output/`.
Tests compare: total count, direction split, per-detection field values (time, price, etc.).

---

## Phase 2 Architecture

### Evaluation Layer
```
src/ra/
  evaluation/
    param_extraction.py  # Dynamic param extraction (locked + sweep modes)
    runner.py            # EvaluationRunner wrapping CascadeEngine
    comparison.py        # Pairwise comparison + per-config stats
    cascade_stats.py     # Cascade funnel + conversion rates
    walk_forward.py      # Walk-forward validation framework
  output/
    json_export.py       # JSON serialization conforming to Schemas 4A-4E
```

### Key Phase 2 Patterns

**Param Extraction**: `extract_params(config, primitive, mode='locked'|'sweep')` replaces hardcoded extraction. Locked mode preserves exact dict format for backward compatibility. Sweep mode exposes sweep_range lists.

**Sweep Combos**: `extract_sweep_combos(config, primitive, params=None)` generates Cartesian product of sweep_range values. Selective param sweep via `params=['ltf.atr_multiplier']`.

**Cache-Aware Sweep**: EvaluationRunner calls `CascadeEngine.on_param_change(primitive)` before each sweep step. Only the changed primitive + downstream are re-run; upstream serves from cache.

**Output Contract**: All JSON output conforms to schemas in `.factory/library/output_schemas.md`. Schema versioning: `schema_version: "1.0"` in every output file.

**River Adapter**: DuckDB-backed parquet reader. Timezone: Asia/Bangkok → UTC → NY. Path: `~/phoenix-river/{pair}/{year}/{mm}/{dd}.parquet`.

### CLI
- `run.py` — Phase 1 cascade-only (unchanged)
- `eval.py` — Phase 2 evaluation (sweep, compare, walk-forward subcommands)
