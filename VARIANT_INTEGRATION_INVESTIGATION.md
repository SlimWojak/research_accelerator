# Variant Integration Investigation Report

**Date:** 2026-03-10  
**Goal:** Map exact changes needed to support named algorithm variants in RA engine

---

## Executive Summary

The RA engine has **partial variant infrastructure** in place but requires **6 critical integrations** to support multiple algorithm variants (e.g., `a8ra_v1`, `tradingfinder_v1`) end-to-end. The `variant_name` field exists in `PrimitiveDetector` and flows through to `DetectionResult`, but the config schema, evaluation runner, comparison logic, and UI do not yet expose or handle variants.

**Critical Path (Minimum Changes):**  
1. Config schema: Add `variant` field to per-primitive config (1 file)  
2. Registry: Allow multiple registrations per primitive (1 file)  
3. Cascade engine: Pass variant from config to registry lookup (1 file)  
4. JSON export: Surface variant in Schema 4B output (1 file)  
5. Compare.html: Display variant labels in UI (1 file)  

---

## 1. PrimitiveDetector Registration

### Current State

**Files:**
- `src/ra/engine/base.py` — `PrimitiveDetector` ABC
- `src/ra/engine/registry.py` — Registry class
- `src/ra/engine/cascade.py` — `CascadeEngine` + `build_default_registry()`

**How it works:**
- Each detector class declares `primitive_name`, `variant_name`, `version` as class attributes
- Example: `DisplacementDetector` has `primitive_name = "displacement"`, `variant_name = "a8ra_v1"`
- `Registry.register(detector_cls)` stores detectors by tuple `(primitive_name, variant_name)`
- `Registry.get(primitive, variant)` returns an instance of the registered class
- `CascadeEngine.__init__()` takes a `variant` arg (default `"a8ra_v1"`) and uses it for ALL primitives in `build_default_registry()`

**Current limitation:**
- `build_default_registry()` hardcodes a single variant for all primitives
- Registry **can** hold multiple variants per primitive (the key is a tuple), but cascade engine doesn't choose different variants per primitive

### Gap for Variant Support

**Missing:**
1. Config-driven variant selection per primitive (currently hardcoded to `"a8ra_v1"`)
2. Cascade engine needs to read `config.primitives.displacement.variant` and pass it to `registry.get()`
3. No way to register multiple implementations of the same primitive with different variants

**Example:** If we want to run `displacement: {variant: tradingfinder_v1}` and `fvg: {variant: a8ra_v1}` together:
- Need to register both `DisplacementDetector_a8ra_v1` and `DisplacementDetector_tradingfinder_v1`
- Cascade engine must look up the correct variant per primitive based on config

### Estimated Change Scope

**MEDIUM**

**Files to change:**
1. `src/ra/engine/cascade.py`:
   - Modify `CascadeEngine.__init__()` to accept a dict of `variant_by_primitive: dict[str, str]` instead of single `variant: str`
   - Update `_run_global()` and `_run_per_tf()` to use `variant_by_primitive[primitive]` when calling `registry.get()`
2. `src/ra/engine/registry.py`:
   - Already supports multiple variants per primitive (no change needed)
3. `src/ra/detectors/displacement.py` (and other detectors):
   - When adding TradingFinder variant, create new class:
     ```python
     class DisplacementDetectorTF(PrimitiveDetector):
         primitive_name = "displacement"
         variant_name = "tradingfinder_v1"
         version = "1.0.0"
     ```
   - Register it in `build_default_registry()`

---

## 2. Config Schema

### Current State

**Files:**
- `src/ra/config/schema.py` — Pydantic v2 models
- `src/ra/config/loader.py` — YAML loading + validation
- `configs/locked_baseline.yaml` — Example config

**How it works:**
- Each primitive has a config block with `variant`, `status`, `params`
- Example from `locked_baseline.yaml`:
  ```yaml
  displacement:
    variant: a8ra_v1
    status: LOCKED
    params:
      atr_period: 14
      combination_mode: { locked: AND, options: [AND, OR] }
      ...
  ```
- The `variant` field **is already in the YAML** but is **not used** by the cascade engine
- `DisplacementConfig` in `schema.py` has `variant: str` field (validated but unused)

### Gap for Variant Support

**Missing:**
1. Cascade engine doesn't read `config.primitives.{primitive}.variant`
2. No validation that the requested variant is registered in the registry
3. `extract_locked_params_for_cascade()` in `cascade.py` doesn't pass variant info to the engine

**What needs to change:**
- `CascadeEngine` constructor should read `config.primitives.*.variant` for each primitive
- Build a `variant_by_primitive` dict and pass it through

### Estimated Change Scope

**SMALL**

**Files to change:**
1. `src/ra/config/schema.py`:
   - **No change needed** — `variant` field already exists and is validated
2. `src/ra/config/loader.py`:
   - Add helper function:
     ```python
     def get_variant_map(config: RAConfig) -> dict[str, str]:
         """Extract variant for each primitive."""
         return {
             prim: getattr(config.primitives, prim).variant
             for prim in config.dependency_graph.keys()
         }
     ```

---

## 3. Evaluation Runner

### Current State

**Files:**
- `src/ra/evaluation/runner.py` — `EvaluationRunner` class

**How it works:**
- `EvaluationRunner.__init__(config, variant="a8ra_v1")` creates a cascade engine with single variant
- `run_locked()`, `run_sweep()`, `run_grid()` all use the same single variant for all primitives
- `_build_engine()` passes `self._variant` to `CascadeEngine()`

### Gap for Variant Support

**Missing:**
1. Runner hardcodes a single variant for all primitives
2. No way to specify per-primitive variants
3. Sweep and comparison modes assume all configs use the same variant for a given primitive

**What needs to change:**
- Pass `variant_by_primitive` dict to `CascadeEngine` instead of single `variant`
- For comparison: allow comparing `displacement_a8ra_v1` vs `displacement_tradingfinder_v1`

### Estimated Change Scope

**MEDIUM**

**Files to change:**
1. `src/ra/evaluation/runner.py`:
   - `__init__()`: Build `variant_by_primitive` from config
   - `_build_engine()`: Pass variant map to `CascadeEngine()`
   - `run_locked()`, `run_sweep()`: No logic change, just flow variant map through

---

## 4. Comparison Module

### Current State

**Files:**
- `src/ra/evaluation/comparison.py` — `compare_pairwise()`, `compute_stats()`

**How it works:**
- `compare_pairwise(results_a, results_b)` compares detection IDs across two configs
- ID format: `{primitive}_{tf}_{timestamp_ny}_{direction}` (from `make_detection_id()` in `base.py`)
- **Variant is NOT in the detection ID**, so detections from different variants can be matched if they occur at the same time/direction

### Gap for Variant Support

**Missing:**
1. Comparison assumes both configs use the same variant for a given primitive
2. Divergence index doesn't surface which variant produced each detection
3. No way to compare "same params, different algorithm" (e.g., `a8ra_v1` vs `tradingfinder_v1`)

**What needs to change:**
- Add `variant` field to divergence index entries
- Optionally: Include variant in detection ID to prevent cross-variant matches

### Estimated Change Scope

**SMALL**

**Files to change:**
1. `src/ra/evaluation/comparison.py`:
   - `_build_divergence_entries()`: Add `variant_a`, `variant_b` fields to each entry
   - Pull variant from `DetectionResult.variant` (already present)

---

## 5. JSON Output Schemas

### Current State

**Files:**
- `src/ra/output/json_export.py` — Schema 4A-4E serialization

**How it works:**
- `DetectionResult` has `variant: str` field (set by detector)
- `serialize_per_config_result()` builds Schema 4B output with `per_primitive[prim][tf].detections`
- Each detection is serialized with `id`, `time`, `direction`, `type`, `price`, `properties`, `tags`, `upstream_refs`
- **Variant is NOT included in the serialized detection or per-primitive stats**

### Gap for Variant Support

**Missing:**
1. Schema 4B `per_primitive` section doesn't show which variant was used
2. Detections don't carry variant metadata
3. Pairwise comparison (Schema 4C) doesn't show variants

**What needs to change:**
- Add `variant` field to Schema 4B `per_primitive[prim]` section
- Add `variant_a`, `variant_b` to Schema 4C pairwise comparison

### Estimated Change Scope

**SMALL**

**Files to change:**
1. `src/ra/output/json_export.py`:
   - `serialize_per_config_result()`: Add `variant` to each `per_primitive[prim]` entry:
     ```python
     per_primitive[prim_name] = {
         "variant": det_result.variant,  # from first tf result
         "per_tf": per_tf
     }
     ```
   - `serialize_pairwise_comparison()`: Add `variant_a`, `variant_b` to output

---

## 6. eval.py CLI

### Current State

**Files:**
- `eval.py` — CLI entry point

**How it works:**
- Subcommands: `sweep`, `compare`, `walk-forward`
- Loads config with `load_config(args.config)`
- Creates `EvaluationRunner(config)` (uses hardcoded `variant="a8ra_v1"`)
- No CLI flag for specifying variant

### Gap for Variant Support

**Missing:**
1. No way to specify variant from CLI
2. Comparison mode can't compare two configs with different variants
3. `eval.py compare --config-a locked_a8ra --config-b locked_tradingfinder` doesn't exist

**What needs to change:**
- Add `--variant` flag (optional, defaults to reading from config)
- For comparison: allow `--config-a <path>` and `--config-b <path>` to load two separate configs
- Currently `compare` only runs locked baseline from a single config

### Estimated Change Scope

**MEDIUM**

**Files to change:**
1. `eval.py`:
   - `cmd_compare()`: Support `--config-a` and `--config-b` flags
   - Load both configs, run locked for each, compare results
   - Pass variant map from each config to runner

---

## 7. compare.html Data Loading

### Current State

**Files:**
- `site/js/shared.js` — Data loading + global state

**How it works:**
- Loads `eval/evaluation_run.json` (Schema 4A)
- Parses `per_config[config_name].per_primitive[prim].per_tf[tf].detections`
- Detections are displayed on chart with markers
- Config names are shown in dropdowns/toggles

### Gap for Variant Support

**Missing:**
1. UI doesn't show variant name for each primitive
2. Config dropdowns don't indicate which variant is used
3. Stats tab doesn't break down metrics by variant

**What needs to change:**
- Display variant label next to primitive name in chart legend
- Show variant in stats tables
- If comparing `a8ra_v1` vs `tradingfinder_v1`, label them clearly

### Estimated Change Scope

**SMALL**

**Files to change:**
1. `site/js/shared.js`:
   - Update `renderMetadata()` to show variant info
2. `site/js/chart-tab.js` (not read yet, but likely):
   - Update marker rendering to include variant in label
   - Example: `"Displacement (a8ra_v1)"` vs `"Displacement (TradingFinder)"`

---

## Critical Path for First Variant End-to-End

**Goal:** Add `tradingfinder_v1` displacement detector and compare it side-by-side with `a8ra_v1`

### Minimum Changes (Ordered)

1. **Create TradingFinder detector class**  
   - File: `src/ra/detectors/displacement_tradingfinder.py`
   - Implement `DisplacementDetectorTF` with `variant_name = "tradingfinder_v1"`
   - Scope: **LARGE** (requires porting TradingFinder algorithm)

2. **Register TradingFinder in registry**  
   - File: `src/ra/engine/cascade.py` → `build_default_registry()`
   - Add `registry.register(DisplacementDetectorTF)`
   - Scope: **SMALL** (1 line)

3. **Pass variant map to CascadeEngine**  
   - File: `src/ra/engine/cascade.py` → `CascadeEngine.__init__()`
   - Change signature: `variant: str` → `variant_by_primitive: dict[str, str]`
   - Update `registry.get()` calls to use `variant_by_primitive[primitive]`
   - Scope: **MEDIUM** (10-15 lines changed)

4. **Extract variant map from config**  
   - File: `src/ra/config/loader.py`
   - Add `get_variant_map(config)` helper
   - Scope: **SMALL** (5 lines)

5. **Flow variant map through EvaluationRunner**  
   - File: `src/ra/evaluation/runner.py`
   - Update `__init__()` to build variant map from config
   - Pass to `CascadeEngine()` in `_build_engine()`
   - Scope: **SMALL** (5 lines)

6. **Create second config file**  
   - File: `configs/locked_tradingfinder.yaml`
   - Copy `locked_baseline.yaml`, change `displacement.variant: tradingfinder_v1`
   - Scope: **SMALL** (1 file)

7. **Update eval.py compare command**  
   - File: `eval.py` → `cmd_compare()`
   - Add `--config-a` and `--config-b` flags
   - Run `runner.run_locked()` for each config
   - Call `compare_pairwise(results_a, results_b)`
   - Scope: **MEDIUM** (20-30 lines)

8. **Surface variant in JSON output**  
   - File: `src/ra/output/json_export.py`
   - Add `variant` to `per_primitive[prim]` in Schema 4B
   - Add `variant_a`, `variant_b` to Schema 4C
   - Scope: **SMALL** (5 lines)

9. **Display variant in compare.html**  
   - File: `site/js/chart-tab.js` (assuming it exists)
   - Update marker labels to show variant
   - Scope: **SMALL** (2-3 lines)

### Total Estimated Effort

- **Detector implementation:** 1-2 days (depends on TradingFinder complexity)
- **Engine integration:** 2-3 hours (steps 2-5)
- **CLI + config:** 1-2 hours (steps 6-7)
- **Output + UI:** 1 hour (steps 8-9)

**Total:** 2-3 days for full end-to-end variant support

---

## Discovered Resources (Paper Trail)

### Core engine files
1. `src/ra/engine/base.py` — `PrimitiveDetector` ABC, `DetectionResult`, `Detection`
2. `src/ra/engine/registry.py` — `Registry` class for detector lookup
3. `src/ra/engine/cascade.py` — `CascadeEngine`, `build_default_registry()`, `extract_locked_params_for_cascade()`

### Config files
4. `src/ra/config/schema.py` — Pydantic models (variant field exists)
5. `src/ra/config/loader.py` — `load_config()`, `resolve_per_tf()`, `get_locked_params()`
6. `configs/locked_baseline.yaml` — Example config with `variant: a8ra_v1`

### Evaluation files
7. `src/ra/evaluation/runner.py` — `EvaluationRunner` (run_locked, run_sweep, run_grid)
8. `src/ra/evaluation/comparison.py` — `compare_pairwise()`, `compute_stats()`
9. `src/ra/output/json_export.py` — Schema 4A-4E serialization

### CLI and UI
10. `eval.py` — CLI entry point (sweep, compare, walk-forward)
11. `site/js/shared.js` — Data loading for compare.html

### Example detector
12. `src/ra/detectors/displacement.py` — Reference implementation with `variant_name = "a8ra_v1"`

---

## Conclusion

The RA engine has **good foundational support** for variants through the registry system and `PrimitiveDetector.variant_name`, but **6 integration points** need updates to make variants fully functional:

1. **Cascade engine** — per-primitive variant lookup
2. **Config loader** — extract variant map
3. **Evaluation runner** — pass variant map
4. **Comparison module** — surface variant in divergence
5. **JSON export** — include variant in Schema 4B/4C
6. **UI** — display variant labels

The **critical path** requires changes to 4 core files (`cascade.py`, `loader.py`, `runner.py`, `json_export.py`) plus CLI/UI updates. Once these are in place, adding new variants is straightforward: implement detector class, register it, update config, run comparison.

**Next step:** Implement TradingFinder displacement detector and integrate it using this roadmap.
