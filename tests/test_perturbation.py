"""Tests for config perturbation engine (src/ra/evaluation/perturbation.py).

Covers validation assertions:
  VAL-PERT-001: Numeric params stay within bounds — perturbed values never exceed
                min/max from search space config. ±10-20% perturbation clamped.
  VAL-PERT-002: Categorical params toggle between options — only take values from
                defined options list.
  VAL-PERT-003: Reproducible with seed — same seed identical results across runs;
                different seed produces different results.

Also covers feature expectedBehavior:
  - Numeric params: perturbation ±10-20% of base (pre-clamp)
  - Numeric params: snapped to step grid when step is provided
  - Returns complete config dict with perturbed values
  - load_search_space reads YAML and JSON
  - compute_param_deltas computes per-parameter deltas
  - apply_perturbation_to_config applies perturbation to config dict
  - Error handling for invalid search-space files
"""

import json
import math
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from ra.evaluation.perturbation import (
    PerturbationError,
    apply_perturbation_to_config,
    compute_param_deltas,
    load_search_space,
    perturb_config,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def numeric_search_space() -> dict[str, Any]:
    """Search space with only numeric parameters."""
    return {
        "parameters": {
            "displacement.ltf.atr_multiplier": {
                "type": "numeric",
                "base": 1.5,
                "min": 1.0,
                "max": 3.0,
                "step": 0.25,
            },
            "displacement.ltf.body_ratio": {
                "type": "numeric",
                "base": 0.60,
                "min": 0.50,
                "max": 0.80,
                "step": 0.05,
            },
            "swing_points.N": {
                "type": "numeric",
                "base": 5,
                "min": 2,
                "max": 10,
                "step": 1,
            },
        }
    }


@pytest.fixture
def categorical_search_space() -> dict[str, Any]:
    """Search space with only categorical parameters."""
    return {
        "parameters": {
            "displacement.combination_mode": {
                "type": "categorical",
                "options": ["AND", "OR"],
                "base": "AND",
            },
            "quality_gate": {
                "type": "categorical",
                "options": ["strict", "relaxed", "off"],
                "base": "strict",
            },
        }
    }


@pytest.fixture
def mixed_search_space() -> dict[str, Any]:
    """Search space with numeric, categorical, and boolean parameters."""
    return {
        "parameters": {
            "displacement.ltf.atr_multiplier": {
                "type": "numeric",
                "base": 1.5,
                "min": 1.0,
                "max": 3.0,
                "step": 0.25,
            },
            "displacement.ltf.body_ratio": {
                "type": "numeric",
                "base": 0.60,
                "min": 0.50,
                "max": 0.80,
                "step": 0.05,
            },
            "displacement.combination_mode": {
                "type": "categorical",
                "options": ["AND", "OR"],
                "base": "AND",
            },
            "quality_gate": {
                "type": "categorical",
                "options": ["strict", "relaxed", "off"],
                "base": "strict",
            },
            "cluster.cluster_2_enabled": {
                "type": "boolean",
                "base": True,
            },
        }
    }


@pytest.fixture
def tight_bounds_search_space() -> dict[str, Any]:
    """Search space where ±10-20% exceeds [min, max] — tests clamping."""
    return {
        "parameters": {
            "tight_param": {
                "type": "numeric",
                "base": 1.0,
                "min": 0.95,  # base - 5% < base - 10%
                "max": 1.05,  # base + 5% < base + 10%
                "step": 0.01,
            },
        }
    }


@pytest.fixture
def no_step_search_space() -> dict[str, Any]:
    """Search space with numeric params without step (continuous)."""
    return {
        "parameters": {
            "continuous_param": {
                "type": "numeric",
                "base": 2.0,
                "min": 1.0,
                "max": 4.0,
                # no step — continuous perturbation
            },
        }
    }


# ── VAL-PERT-001: Numeric params stay within bounds ──────────────────────────


class TestNumericBounds:
    """VAL-PERT-001: Perturbed values never exceed min/max."""

    def test_all_numeric_within_bounds_many_seeds(self, numeric_search_space):
        """Over 200 seeds, every numeric param stays within [min, max]."""
        for seed in range(200):
            result = perturb_config(numeric_search_space, seed=seed)
            for param_path, param_def in numeric_search_space["parameters"].items():
                val = result[param_path]
                min_val = param_def["min"]
                max_val = param_def["max"]
                assert min_val <= val <= max_val, (
                    f"seed={seed}, {param_path}: {val} not in "
                    f"[{min_val}, {max_val}]"
                )

    def test_tight_bounds_clamped(self, tight_bounds_search_space):
        """When ±10-20% would exceed bounds, value is clamped to [min, max]."""
        for seed in range(200):
            result = perturb_config(tight_bounds_search_space, seed=seed)
            val = result["tight_param"]
            assert 0.95 <= val <= 1.05, (
                f"seed={seed}: {val} not in [0.95, 1.05]"
            )

    def test_perturbation_magnitude_10_to_20_pct(self, no_step_search_space):
        """Pre-clamp perturbation is ±10-20% of base (verified on wide bounds)."""
        # With base=2.0, min=1.0, max=4.0: the bounds are wide enough
        # that clamping won't interfere, so the perturbation should be
        # between base*0.80 and base*0.90 or base*1.10 and base*1.20.
        base = 2.0
        lower_band_lo = base * 0.80   # -20%
        lower_band_hi = base * 0.90   # -10%
        upper_band_lo = base * 1.10   # +10%
        upper_band_hi = base * 1.20   # +20%

        for seed in range(200):
            result = perturb_config(no_step_search_space, seed=seed)
            val = result["continuous_param"]
            in_lower = lower_band_lo <= val <= lower_band_hi
            in_upper = upper_band_lo <= val <= upper_band_hi
            assert in_lower or in_upper, (
                f"seed={seed}: {val} not in [{lower_band_lo}, {lower_band_hi}] "
                f"or [{upper_band_lo}, {upper_band_hi}]"
            )

    def test_numeric_snapped_to_step_grid(self, numeric_search_space):
        """When step is defined, values snap to min + N*step grid."""
        for seed in range(100):
            result = perturb_config(numeric_search_space, seed=seed)
            for param_path, param_def in numeric_search_space["parameters"].items():
                val = result[param_path]
                step = param_def["step"]
                min_val = param_def["min"]
                # (val - min) should be a multiple of step
                remainder = (val - min_val) % step
                assert abs(remainder) < 1e-9 or abs(remainder - step) < 1e-9, (
                    f"seed={seed}, {param_path}: {val} not on step grid "
                    f"(min={min_val}, step={step}, remainder={remainder})"
                )

    def test_no_step_continuous_values(self, no_step_search_space):
        """Without step, values are continuous (not snapped)."""
        # Collect values and check they are NOT all on some round grid
        values = set()
        for seed in range(50):
            result = perturb_config(no_step_search_space, seed=seed)
            values.add(result["continuous_param"])
        # With continuous perturbation and different seeds, we expect
        # many unique values (at least 10 out of 50)
        assert len(values) >= 10, (
            f"Only {len(values)} unique values — expected continuous distribution"
        )

    def test_integer_step_produces_integers(self):
        """Step=1 with integer base yields integer-like values."""
        space = {
            "parameters": {
                "swing_N": {
                    "type": "numeric",
                    "base": 5,
                    "min": 2,
                    "max": 10,
                    "step": 1,
                },
            }
        }
        for seed in range(100):
            result = perturb_config(space, seed=seed)
            val = result["swing_N"]
            assert 2 <= val <= 10
            assert abs(val - round(val)) < 1e-9, (
                f"seed={seed}: {val} not an integer (step=1)"
            )


# ── VAL-PERT-002: Categorical params toggle between options ──────────────────


class TestCategoricalOptions:
    """VAL-PERT-002: Categorical params only take values from options list."""

    def test_all_values_from_options_list(self, categorical_search_space):
        """Every perturbed categorical value is in its options list."""
        for seed in range(200):
            result = perturb_config(categorical_search_space, seed=seed)
            for param_path, param_def in categorical_search_space["parameters"].items():
                val = result[param_path]
                assert val in param_def["options"], (
                    f"seed={seed}, {param_path}: '{val}' not in "
                    f"{param_def['options']}"
                )

    def test_all_options_reachable(self, categorical_search_space):
        """Over many seeds, all options appear at least once."""
        seen: dict[str, set] = {}
        for param_path in categorical_search_space["parameters"]:
            seen[param_path] = set()

        for seed in range(200):
            result = perturb_config(categorical_search_space, seed=seed)
            for param_path in categorical_search_space["parameters"]:
                seen[param_path].add(result[param_path])

        for param_path, param_def in categorical_search_space["parameters"].items():
            expected = set(param_def["options"])
            assert seen[param_path] == expected, (
                f"{param_path}: saw {seen[param_path]}, expected {expected}"
            )

    def test_boolean_only_true_or_false(self, mixed_search_space):
        """Boolean params only produce True or False."""
        seen = set()
        for seed in range(100):
            result = perturb_config(mixed_search_space, seed=seed)
            val = result["cluster.cluster_2_enabled"]
            assert isinstance(val, bool), f"seed={seed}: {val} is not bool"
            seen.add(val)
        # Both values should appear
        assert seen == {True, False}, f"Only saw {seen}"


# ── VAL-PERT-003: Reproducible with seed ─────────────────────────────────────


class TestSeedReproducibility:
    """VAL-PERT-003: Same seed → same sequence. Different seed → different."""

    def test_same_seed_same_result(self, mixed_search_space):
        """Identical seed produces identical perturbation dict."""
        r1 = perturb_config(mixed_search_space, seed=42)
        r2 = perturb_config(mixed_search_space, seed=42)
        assert r1 == r2

    def test_same_seed_same_result_multiple_calls(self, mixed_search_space):
        """Multiple calls with same seed return identical results every time."""
        results = [perturb_config(mixed_search_space, seed=12345) for _ in range(10)]
        for r in results[1:]:
            assert r == results[0]

    def test_different_seed_different_result(self, mixed_search_space):
        """Different seeds produce different perturbation dicts."""
        # Use seeds that are very different to avoid coincidental matches
        r1 = perturb_config(mixed_search_space, seed=1)
        r2 = perturb_config(mixed_search_space, seed=100)
        assert r1 != r2, "Seeds 1 and 100 produced identical configs"

    def test_no_seed_varies(self, mixed_search_space):
        """No seed (None) should still produce results (non-deterministic)."""
        r1 = perturb_config(mixed_search_space, seed=None)
        # Just verify it returns a valid result with all params
        assert set(r1.keys()) == set(mixed_search_space["parameters"].keys())

    def test_seed_sequence_independence(self, numeric_search_space):
        """Seed-based RNG is instance-local, not global state.

        Two calls with different seeds don't contaminate each other's state.
        """
        # Call with seed=1, then seed=2, then seed=1 again
        r1_first = perturb_config(numeric_search_space, seed=1)
        _ = perturb_config(numeric_search_space, seed=2)
        r1_again = perturb_config(numeric_search_space, seed=1)
        assert r1_first == r1_again, (
            "Seed=1 produced different results after seed=2 call — "
            "global state contamination"
        )


# ── Complete config dict ─────────────────────────────────────────────────────


class TestCompleteConfigDict:
    """Returns complete config dict with perturbed values for ALL params."""

    def test_all_params_present_in_output(self, mixed_search_space):
        """Every parameter in search space appears in the output dict."""
        result = perturb_config(mixed_search_space, seed=42)
        expected_keys = set(mixed_search_space["parameters"].keys())
        assert set(result.keys()) == expected_keys

    def test_single_param_returns_single_key(self):
        """Single-parameter search space returns dict with one key."""
        space = {
            "parameters": {
                "only_param": {
                    "type": "numeric",
                    "base": 10,
                    "min": 5,
                    "max": 20,
                },
            }
        }
        result = perturb_config(space, seed=42)
        assert len(result) == 1
        assert "only_param" in result

    def test_empty_params_returns_empty_dict(self):
        """Empty parameters dict returns empty result."""
        space = {"parameters": {}}
        result = perturb_config(space, seed=42)
        assert result == {}


# ── load_search_space ─────────────────────────────────────────────────────────


class TestLoadSearchSpace:
    """Tests for load_search_space() file loading."""

    def test_load_yaml(self, tmp_path):
        """Loads YAML search-space file."""
        space = {
            "parameters": {
                "some_param": {
                    "type": "numeric",
                    "base": 1.0,
                    "min": 0.5,
                    "max": 2.0,
                },
            }
        }
        path = tmp_path / "space.yaml"
        path.write_text(yaml.dump(space))

        loaded = load_search_space(path)
        assert "parameters" in loaded
        assert "some_param" in loaded["parameters"]

    def test_load_json(self, tmp_path):
        """Loads JSON search-space file."""
        space = {
            "parameters": {
                "another_param": {
                    "type": "categorical",
                    "options": ["a", "b"],
                },
            }
        }
        path = tmp_path / "space.json"
        path.write_text(json.dumps(space))

        loaded = load_search_space(path)
        assert "parameters" in loaded
        assert "another_param" in loaded["parameters"]

    def test_file_not_found_raises(self, tmp_path):
        """Missing file raises PerturbationError."""
        with pytest.raises(PerturbationError, match="not found"):
            load_search_space(tmp_path / "nonexistent.yaml")

    def test_missing_parameters_key_raises(self, tmp_path):
        """File without 'parameters' key raises PerturbationError."""
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.dump({"foo": "bar"}))
        with pytest.raises(PerturbationError, match="parameters"):
            load_search_space(path)

    def test_non_dict_raises(self, tmp_path):
        """File with non-dict content raises PerturbationError."""
        path = tmp_path / "bad.yaml"
        path.write_text("- just\n- a\n- list\n")
        with pytest.raises(PerturbationError, match="mapping"):
            load_search_space(path)


# ── compute_param_deltas ─────────────────────────────────────────────────────


class TestComputeParamDeltas:
    """Tests for compute_param_deltas() delta computation."""

    def test_numeric_delta_computed(self, numeric_search_space):
        """Numeric params get base, value, delta, pct_change."""
        perturbation = perturb_config(numeric_search_space, seed=42)
        deltas = compute_param_deltas(perturbation, numeric_search_space)

        for param_path in numeric_search_space["parameters"]:
            d = deltas[param_path]
            assert "base" in d
            assert "value" in d
            assert "delta" in d
            assert "pct_change" in d
            base = numeric_search_space["parameters"][param_path]["base"]
            assert d["base"] == float(base)
            assert d["value"] == perturbation[param_path]
            assert abs(d["delta"] - (d["value"] - d["base"])) < 1e-6

    def test_categorical_delta_has_base_and_value(self, categorical_search_space):
        """Categorical params get base and value (no numeric delta)."""
        perturbation = perturb_config(categorical_search_space, seed=42)
        deltas = compute_param_deltas(perturbation, categorical_search_space)

        for param_path in categorical_search_space["parameters"]:
            d = deltas[param_path]
            assert "base" in d
            assert "value" in d
            # Categorical deltas should NOT have numeric fields
            assert "delta" not in d
            assert "pct_change" not in d


# ── apply_perturbation_to_config ──────────────────────────────────────────────


class TestApplyPerturbation:
    """Tests for apply_perturbation_to_config()."""

    def test_applies_perturbation_to_nested_dict(self):
        """Perturbation values are set at correct nested paths."""
        config = {
            "displacement": {
                "ltf": {
                    "atr_multiplier": 1.5,
                    "body_ratio": 0.6,
                },
            },
        }
        perturbation = {
            "displacement.ltf.atr_multiplier": 2.0,
        }
        result = apply_perturbation_to_config(config, perturbation)
        assert result["displacement"]["ltf"]["atr_multiplier"] == 2.0
        # Unperturbed value unchanged
        assert result["displacement"]["ltf"]["body_ratio"] == 0.6

    def test_does_not_mutate_original(self):
        """Original config dict is not modified."""
        config = {"a": {"b": 1}}
        perturbation = {"a.b": 99}
        result = apply_perturbation_to_config(config, perturbation)
        assert config["a"]["b"] == 1  # Original unchanged
        assert result["a"]["b"] == 99

    def test_creates_intermediate_keys(self):
        """Missing intermediate dict keys are created."""
        config = {}
        perturbation = {"a.b.c": 42}
        result = apply_perturbation_to_config(config, perturbation)
        assert result["a"]["b"]["c"] == 42


# ── Edge cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases for the perturbation engine."""

    def test_base_at_min_boundary(self):
        """Base == min: perturbation can only go up."""
        space = {
            "parameters": {
                "low_param": {
                    "type": "numeric",
                    "base": 1.0,
                    "min": 1.0,
                    "max": 5.0,
                },
            }
        }
        for seed in range(100):
            result = perturb_config(space, seed=seed)
            val = result["low_param"]
            assert 1.0 <= val <= 5.0, f"seed={seed}: {val}"

    def test_base_at_max_boundary(self):
        """Base == max: perturbation can only go down."""
        space = {
            "parameters": {
                "high_param": {
                    "type": "numeric",
                    "base": 5.0,
                    "min": 1.0,
                    "max": 5.0,
                },
            }
        }
        for seed in range(100):
            result = perturb_config(space, seed=seed)
            val = result["high_param"]
            assert 1.0 <= val <= 5.0, f"seed={seed}: {val}"

    def test_single_option_categorical(self):
        """Categorical with single option always returns that option."""
        space = {
            "parameters": {
                "only_choice": {
                    "type": "categorical",
                    "options": ["only"],
                },
            }
        }
        for seed in range(20):
            result = perturb_config(space, seed=seed)
            assert result["only_choice"] == "only"

    def test_very_small_base(self):
        """Very small base value still respects bounds."""
        space = {
            "parameters": {
                "tiny": {
                    "type": "numeric",
                    "base": 0.001,
                    "min": 0.0001,
                    "max": 0.01,
                },
            }
        }
        for seed in range(100):
            result = perturb_config(space, seed=seed)
            val = result["tiny"]
            assert 0.0001 <= val <= 0.01, f"seed={seed}: {val}"

    def test_large_base(self):
        """Large base value still respects bounds."""
        space = {
            "parameters": {
                "big": {
                    "type": "numeric",
                    "base": 1000.0,
                    "min": 500.0,
                    "max": 2000.0,
                },
            }
        }
        for seed in range(100):
            result = perturb_config(space, seed=seed)
            val = result["big"]
            assert 500.0 <= val <= 2000.0, f"seed={seed}: {val}"

    def test_unknown_param_type_skipped(self):
        """Unknown parameter type is silently skipped."""
        space = {
            "parameters": {
                "known": {"type": "numeric", "base": 1.0, "min": 0.5, "max": 2.0},
                "unknown": {"type": "magic", "base": "wizardry"},
            }
        }
        result = perturb_config(space, seed=42)
        assert "known" in result
        assert "unknown" not in result
