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
    river_adapter.py   # Read-only River/parquet consumer (stub for Phase 1)
    bar_types.py       # Bar DataFrame contract
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
