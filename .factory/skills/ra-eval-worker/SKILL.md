---
name: ra-eval-worker
description: Implements evaluation engine modules with TDD for Phase 2 (runner, comparison, output, walk-forward)
---

# RA Evaluation Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for all Phase 2 Evaluation Engine features: param extraction refactor, River adapter, evaluation runner, comparison statistics, walk-forward validation, structured output, and CLI integration.

## Work Procedure

### Step 1: Understand the Feature

Read the feature description thoroughly. Identify:
- Which module(s) to build or modify
- What Phase 1 interfaces to consume (CascadeEngine, DetectionResult, config schema)
- What output schemas to conform to (see `.factory/library/output_schemas.md`)
- What upstream Phase 2 modules this feature depends on

### Step 2: Study the Specifications

Read relevant specification documents:
1. `.factory/library/output_schemas.md` — THE interface contract for all JSON output (Schemas 4A-4E)
2. `.factory/library/architecture.md` — project structure, PrimitiveDetector interface
3. `build_plan/01_RUNTIME_CONFIG_SCHEMA.yaml` — evaluation config section, sweep_range fields
4. `build_plan/03_RIVER_ADAPTER_SPEC.md` — River adapter spec (for River-related features)
5. `configs/locked_baseline.yaml` — config structure with sweep_range values

For param extraction: read `src/ra/engine/cascade.py` (`extract_locked_params_for_cascade()`) and all detector files to understand expected param dict format. CRITICAL: detectors expect specific dict structures including `{locked: value}` wrappers — do NOT change the format.

For River adapter: read `src/ra/data/river_adapter.py` (stub), `src/ra/data/csv_loader.py`, `src/ra/data/tf_aggregator.py`, `src/ra/data/session_tagger.py`.

### Step 3: Write Failing Tests FIRST (Red Phase)

Before writing any implementation code, create test files:

```python
def test_locked_extraction_equivalence():
    """New extract_params must produce identical output to hardcoded function."""
    config = load_config("configs/locked_baseline.yaml")
    old_params = extract_locked_params_for_cascade(config)
    for primitive in old_params:
        new_params = extract_params(config, primitive, mode="locked")
        assert new_params == old_params[primitive]
```

Write tests covering:
- Exact behavioral assertions from the feature's `expectedBehavior`
- Edge cases (empty data, zero detections, null params)
- Schema conformance for any JSON output (validate field presence and types)
- Backward compatibility (Phase 1 tests still pass)

Run tests — they must FAIL (red). If they pass, the test is wrong.

### Step 4: Implement the Module

Now implement:
- Follow the output schemas in `.factory/library/output_schemas.md` exactly
- Do NOT modify Phase 1 detector code in `src/ra/detectors/`
- Do NOT modify existing test files in `tests/test_*.py`
- Use existing Phase 1 interfaces: `CascadeEngine.run()`, `on_param_change()`, `DetectionResult`
- Place new code in `src/ra/evaluation/`, `src/ra/output/`, or `src/ra/data/`
- Handle numpy/pandas type serialization in JSON output (int64 → int, float64 → float, NaN → null)

### Step 5: Run Tests Until Green

Run the module's tests:
```bash
python3 -m pytest tests/test_<module>.py -v --tb=long
```

Then run the FULL test suite to verify no Phase 1 regressions:
```bash
python3 -m pytest tests/ -v --tb=short -x -p no:cacheprovider
```

ALL tests must pass (378 Phase 1 + new Phase 2 tests). Zero regressions.

### Step 6: Manual Verification

After tests pass, do a manual sanity check:
- For param extraction: run `extract_params()` for a few primitives, print and verify
- For River adapter: load bars from parquet, verify timestamps, counts, column schema
- For evaluation runner: run a small sweep, verify output JSON structure
- For comparison: compare two configs, check divergence_index makes sense
- For walk-forward: run with 5-day CSV, verify Schema 4E output
- For CLI: run eval.py subcommands, verify output files created

### Step 7: Commit

Commit all new/modified files with a descriptive message.

## Example Handoff

```json
{
  "salientSummary": "Implemented EvaluationRunner with locked replay, single-param sweep, and multi-param grid modes. Cache reuse verified: 7-step displacement sweep calls FVG.detect() once (cache hit). Full suite green (420 tests, 378 Phase 1 + 42 new).",
  "whatWasImplemented": "src/ra/evaluation/runner.py — EvaluationRunner class with run_locked(), run_sweep(), run_grid() methods. Wraps CascadeEngine for parameter exploration with cache-aware incremental re-runs via on_param_change(). Tests in tests/test_evaluation_runner.py covering locked equivalence, sweep variation, grid Cartesian product, cache reuse via mock call counts, params_used provenance.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {
        "command": "python3 -m pytest tests/test_evaluation_runner.py -v --tb=short",
        "exitCode": 0,
        "observation": "18 tests passed: locked equivalence (1), sweep variation (3), grid product (2), cache reuse (2), params_used (3), data windowing (2), DEFERRED handling (1), per-TF sweep (2), empty range (1), River data (1)"
      },
      {
        "command": "python3 -m pytest tests/ -v --tb=short -x -p no:cacheprovider",
        "exitCode": 0,
        "observation": "420 tests pass (378 Phase 1 + 42 Phase 2). Zero regressions."
      }
    ],
    "interactiveChecks": [
      {
        "action": "Ran locked baseline through eval runner, compared detection counts against run.py output",
        "observed": "Identical: FVG 5m=345, MSS 5m=44, OB 5m=37. Total 9784."
      }
    ]
  },
  "tests": {
    "added": [
      {
        "file": "tests/test_evaluation_runner.py",
        "cases": [
          {"name": "test_locked_matches_phase1", "verifies": "VAL-EVAL-001"},
          {"name": "test_single_param_sweep", "verifies": "VAL-EVAL-002"},
          {"name": "test_cache_reuse_mock", "verifies": "VAL-EVAL-004"}
        ]
      }
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Phase 1 CascadeEngine API doesn't support required operation (e.g., cache inspection)
- Config schema needs changes that would affect Phase 1 modules
- Output schema in `.factory/library/output_schemas.md` is ambiguous or contradictory
- River parquet data at `~/phoenix-river/` is inaccessible or has unexpected format
- Phase 1 regression tests fail after Phase 2 changes and root cause is unclear
- Walk-forward produces unexpected results on real River data (e.g., memory issues with multi-month)
