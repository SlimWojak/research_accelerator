---
name: ra-engine-worker
description: Implements detection engine modules with TDD against regression baseline fixtures
---

# RA Engine Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for detection engine features: project scaffolding, config system, data layer, individual detector modules, cascade engine, integration tests, AND Phase 4 variant detectors (LuxAlgo MSS, LuxAlgo OB, variant cascade integration).

## Work Procedure

### Step 1: Understand the Feature

Read the feature description thoroughly. Identify:
- Which module(s) to build
- What upstream dependencies are needed (already built by prior features)
- What regression targets to hit (exact counts from baseline fixtures)

### Step 2: Study the Specifications

Read the relevant specification documents in this order:
1. `build_plan/02_MODULE_MANIFEST.md` — module interface, detection logic, regression expectations
2. `build_plan/01_RUNTIME_CONFIG_SCHEMA.yaml` — config params this module consumes
3. `build_plan/05_ADVISORY_SYNTHESIS.yaml` — resolved review feedback, temporal gating table, edge cases
4. `pipeline/preprocess_data_v2.py` — reference implementation (this is the ground truth code)
5. `SYNTHETIC_OLYA_METHOD_v0.5.yaml` — L1 pseudocode (canonical spec, consult for algorithm details)

For a8ra_v1 detector modules: find the relevant function in `preprocess_data_v2.py` and read it completely. The RA module must reproduce its behavior exactly at locked params.

For Phase 4 variant detectors (LuxAlgo MSS, LuxAlgo OB):
- Read `.factory/research/luxalgo-smc-analysis.md` — full algorithm spec with pseudocode
- Study existing a8ra_v1 detector as interface template (e.g., `src/ra/detectors/mss.py` for LuxAlgo MSS)
- Clean-room implementation: follow the algorithm description in the research doc, NOT original PineScript
- Register as `(primitive_name, "luxalgo_v1")` in the Registry
- New files go in `src/ra/detectors/` (e.g., `luxalgo_mss.py`, `luxalgo_ob.py`)
- Do NOT modify existing a8ra_v1 detectors

### Step 3: Study the Baseline Fixture

Read the relevant baseline fixture(s) from `tests/fixtures/baseline_output/` to understand the exact JSON structure you must match:
- What fields are in each detection?
- How are detections organized (list, dict by day, etc.)?
- What metadata/stats accompany the detections?

This is critical — the regression test compares against this exact structure.

### Step 4: Write Failing Tests FIRST (Red Phase)

Before writing any implementation code, create test files with regression tests:

```python
def test_fvg_5m_count(five_day_bars_5m, fvg_baseline_5m):
    detector = FVGDetector()
    result = detector.detect(five_day_bars_5m, locked_params)
    assert len(result.detections) == 345  # exact count from baseline
    bull = [d for d in result.detections if d.direction == "bullish"]
    bear = [d for d in result.detections if d.direction == "bearish"]
    assert len(bull) == 179
    assert len(bear) == 166
```

Write tests for:
- Total count match per timeframe
- Bull/bear (or high/low, or rev/cont) split match
- Per-detection field match (time, price) for a sample of detections
- Edge cases specific to the module

Run the tests — they must FAIL (red). If they pass, the test is wrong.

### Step 5: Implement the Module

Now implement the module:
- Follow the v0.5 L1 pseudocode exactly for the algorithm
- Accept ALL parameters from the config dict — no hardcoded values
- Return `DetectionResult` with properly constructed `Detection` objects
- Generate deterministic IDs: `{primitive}_{tf}_{timestamp_ny}_{direction}`
- Skip ghost bars (`is_ghost == True`)
- Use the existing base classes from `src/ra/engine/base.py`
- Register the module in the registry

Implementation tips:
- Work iteratively: get the count right first, then fix per-detection field matching
- If counts are off, compare your logic line-by-line against `preprocess_data_v2.py`
- Pay attention to: boundary conditions, >= vs >, index offsets, NY time conversion
- For composites: wire upstream results correctly via the `upstream` parameter

### Step 6: Run Tests Until Green

Run the module's tests repeatedly until they pass:
```bash
python3 -m pytest tests/test_<module>.py -v --tb=long
```

Then run the FULL test suite to check for regressions:
```bash
python3 -m pytest tests/ -v --tb=short -x
```

ALL tests must pass. No regressions allowed.

### Step 7: Manual Verification

After tests pass, do a quick manual sanity check:
```python
python3 -c "
from ra.detectors.<module> import <Detector>
# ... load data, run detector, print a few detections
# Compare visually against baseline fixture
"
```

Check:
- First and last detection times look reasonable
- Detection count matches expected
- A few spot-checked detections have correct field values

### Step 8: Commit

Commit all new/modified files with a descriptive message.

## Example Handoff

```json
{
  "salientSummary": "Implemented FVGDetector with FVG + IFVG state tracking + BPR overlap detection. Regression tests pass on all 3 TFs: 1m=2017, 5m=345, 15m=118 (exact match). Full test suite green (12 tests, 0 failures).",
  "whatWasImplemented": "src/ra/detectors/fvg.py — FVGDetector implementing 3-candle gap detection with floor threshold from config, CE/boundary state machine tracking, IFVG promotion on boundary close, BPR geometric overlap of bull+bear FVGs. Tests in tests/test_fvg.py covering count regression per TF, per-detection field match, state transitions, and BPR zones.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {
        "command": "python3 -m pytest tests/test_fvg.py -v --tb=short",
        "exitCode": 0,
        "observation": "9 tests passed: 3 count regression (1m/5m/15m), 3 field match, 1 IFVG state, 1 BPR, 1 config-driven params"
      },
      {
        "command": "python3 -m pytest tests/ -v --tb=short -x",
        "exitCode": 0,
        "observation": "All 24 tests pass (including prior data layer tests). No regressions."
      }
    ],
    "interactiveChecks": [
      {
        "action": "Ran python3 -c to load 5m bars, run FVG detector, print first 3 detections",
        "observed": "First FVG at 2024-01-08T00:25:00 NY, bullish, gap_pips=1.2. Matches baseline fixture fvg_data_5m.json first entry."
      },
      {
        "action": "Compared FVG count breakdown against BASELINE_MANIFEST.md table",
        "observed": "1m: 2017 (1026b/991r) ✓, 5m: 345 (179b/166r) ✓, 15m: 118 (58b/60r) ✓. Exact match on all."
      }
    ]
  },
  "tests": {
    "added": [
      {
        "file": "tests/test_fvg.py",
        "cases": [
          {"name": "test_fvg_1m_count", "verifies": "FVG 1m count = 2017 (1026 bull, 991 bear)"},
          {"name": "test_fvg_5m_count", "verifies": "FVG 5m count = 345 (179 bull, 166 bear)"},
          {"name": "test_fvg_15m_count", "verifies": "FVG 15m count = 118 (58 bull, 60 bear)"},
          {"name": "test_fvg_5m_field_match", "verifies": "Per-detection fields match baseline fixture"},
          {"name": "test_fvg_1m_field_match", "verifies": "Per-detection fields match baseline fixture"},
          {"name": "test_fvg_15m_field_match", "verifies": "Per-detection fields match baseline fixture"},
          {"name": "test_ifvg_state_transitions", "verifies": "CE_TOUCHED and BOUNDARY_CLOSED states tracked"},
          {"name": "test_bpr_overlap", "verifies": "BPR zones computed from overlapping bull+bear FVGs"},
          {"name": "test_fvg_config_driven", "verifies": "Floor threshold from config, not hardcoded"}
        ]
      }
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Baseline fixture has unexpected structure that doesn't match the module manifest description
- Regression count is off by more than 2% after thorough debugging and you cannot identify the cause
- A required upstream module is missing or broken (not built by a prior feature)
- The reference implementation in `preprocess_data_v2.py` contradicts the v0.5 spec in a way that affects regression
- Config schema needs changes that would affect other modules
- You discover an issue in the data layer (wrong bar counts, incorrect session tags) that was not caught previously
