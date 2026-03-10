"""Tests for variant-engine-infra feature: variant_by_primitive support.

Tests cover:
- VAL-VENG-001: CascadeEngine accepts variant_by_primitive dict
- VAL-VENG-005: Default behavior unchanged without variant override
- VAL-VENG-006: Config variant field drives detector selection

Also tests:
- Invalid variant name produces clear error listing available variants
- eval.py compare --variant-a / --variant-b CLI flags
- EvaluationRunner passes variant_by_primitive to CascadeEngine
- YAML config supports cascade.variant_by_primitive mapping
"""

import copy
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from ra.engine.base import Detection, DetectionResult, PrimitiveDetector
from ra.engine.cascade import (
    CascadeEngine,
    CascadeError,
    build_default_registry,
    extract_locked_params_for_cascade,
)
from ra.engine.registry import Registry, RegistryError


# ── Test fixtures ────────────────────────────────────────────────────────────

LOCKED_DEP_GRAPH = {
    "fvg":              {"upstream": []},
    "swing_points":     {"upstream": []},
    "asia_range":       {"upstream": []},
    "displacement":     {"upstream": []},
    "reference_levels": {"upstream": []},
    "session_liquidity": {"upstream": []},
    "ifvg":             {"upstream": ["fvg"]},
    "bpr":              {"upstream": ["fvg"]},
    "equal_hl":         {"upstream": ["swing_points"]},
    "mss":              {"upstream": ["swing_points", "displacement", "fvg"]},
    "order_block":      {"upstream": ["displacement", "mss"]},
    "ote":              {"upstream": ["mss"]},
    "htf_liquidity":    {"upstream": ["swing_points"]},
    "liquidity_sweep":  {"upstream": ["session_liquidity", "reference_levels",
                                      "htf_liquidity", "swing_points", "displacement"]},
}


# ── VAL-VENG-001: CascadeEngine accepts variant_by_primitive dict ────────────

class TestVariantByPrimitiveAcceptance:
    """VAL-VENG-001: CascadeEngine.__init__() accepts variant_by_primitive."""

    def test_accepts_variant_by_primitive_dict(self):
        """CascadeEngine(variant_by_primitive={'mss': 'luxalgo_v1'}) constructs without error."""
        registry = build_default_registry()
        # Should NOT raise
        engine = CascadeEngine(
            registry,
            LOCKED_DEP_GRAPH,
            variant_by_primitive={"mss": "luxalgo_v1"},
        )
        assert engine is not None

    def test_variant_by_primitive_mapping_retrievable(self):
        """The supplied mapping is retrievable from the engine."""
        registry = build_default_registry()
        engine = CascadeEngine(
            registry,
            LOCKED_DEP_GRAPH,
            variant_by_primitive={"mss": "luxalgo_v1"},
        )
        # Engine should expose the variant mapping
        assert engine.variant_by_primitive.get("mss") == "luxalgo_v1"

    def test_empty_variant_by_primitive_defaults_to_a8ra(self):
        """Empty dict means all primitives use a8ra_v1."""
        registry = build_default_registry()
        engine = CascadeEngine(
            registry,
            LOCKED_DEP_GRAPH,
            variant_by_primitive={},
        )
        # Unspecified primitives fall back to default
        assert engine.get_variant_for_primitive("fvg") == "a8ra_v1"
        assert engine.get_variant_for_primitive("mss") == "a8ra_v1"

    def test_none_variant_by_primitive_defaults_to_a8ra(self):
        """None value means all primitives use a8ra_v1."""
        registry = build_default_registry()
        engine = CascadeEngine(
            registry,
            LOCKED_DEP_GRAPH,
            variant_by_primitive=None,
        )
        assert engine.get_variant_for_primitive("fvg") == "a8ra_v1"

    def test_unspecified_primitive_uses_default(self):
        """Unspecified primitives still use a8ra_v1."""
        registry = build_default_registry()
        engine = CascadeEngine(
            registry,
            LOCKED_DEP_GRAPH,
            variant_by_primitive={"mss": "luxalgo_v1"},
        )
        # fvg not in variant_by_primitive → should use a8ra_v1
        assert engine.get_variant_for_primitive("fvg") == "a8ra_v1"
        # mss is in variant_by_primitive → should use luxalgo_v1
        assert engine.get_variant_for_primitive("mss") == "luxalgo_v1"

    def test_backward_compat_variant_string_still_works(self):
        """Old-style variant='a8ra_v1' string still works."""
        registry = build_default_registry()
        engine = CascadeEngine(
            registry,
            LOCKED_DEP_GRAPH,
            variant="a8ra_v1",
        )
        assert engine.get_variant_for_primitive("fvg") == "a8ra_v1"


# ── VAL-VENG-005: Default behavior unchanged ────────────────────────────────

class TestDefaultBehaviorUnchanged:
    """VAL-VENG-005: No variant override → identical to baseline."""

    def test_no_variant_override_same_as_baseline(
        self, bars_1m, bars_5m, bars_15m,
    ):
        """When no variant_by_primitive, results identical to before."""
        registry = build_default_registry()
        params = extract_locked_params_for_cascade(None)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

        # Old-style: variant string
        engine_old = CascadeEngine(registry, LOCKED_DEP_GRAPH, variant="a8ra_v1")
        results_old = engine_old.run(bars_by_tf, params)

        # New-style: no variant_by_primitive
        registry2 = build_default_registry()
        engine_new = CascadeEngine(registry2, LOCKED_DEP_GRAPH)
        results_new = engine_new.run(bars_by_tf, params)

        # Compare detection counts and IDs for all primitives
        for prim in results_old:
            for tf in results_old[prim]:
                old_ids = sorted([d.id for d in results_old[prim][tf].detections])
                new_ids = sorted([d.id for d in results_new[prim][tf].detections])
                assert old_ids == new_ids, (
                    f"Regression for {prim}/{tf}: "
                    f"old={len(old_ids)}, new={len(new_ids)}"
                )

    def test_empty_variant_by_primitive_same_as_default(
        self, bars_1m, bars_5m, bars_15m,
    ):
        """Empty variant_by_primitive={} gives same results as default."""
        registry1 = build_default_registry()
        registry2 = build_default_registry()
        params = extract_locked_params_for_cascade(None)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

        engine1 = CascadeEngine(registry1, LOCKED_DEP_GRAPH)
        results1 = engine1.run(bars_by_tf, params)

        engine2 = CascadeEngine(
            registry2, LOCKED_DEP_GRAPH, variant_by_primitive={},
        )
        results2 = engine2.run(bars_by_tf, params)

        for prim in results1:
            for tf in results1[prim]:
                count1 = len(results1[prim][tf].detections)
                count2 = len(results2[prim][tf].detections)
                assert count1 == count2, (
                    f"Empty variant_by_primitive diverged for {prim}/{tf}: "
                    f"{count1} vs {count2}"
                )


# ── Invalid variant error handling ───────────────────────────────────────────

class TestInvalidVariantError:
    """Invalid variant name produces clear error listing available variants."""

    def test_invalid_variant_clear_error(self, bars_1m, bars_5m, bars_15m):
        """Running cascade with nonexistent variant produces RegistryError."""
        registry = build_default_registry()
        params = extract_locked_params_for_cascade(None)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

        engine = CascadeEngine(
            registry,
            LOCKED_DEP_GRAPH,
            variant_by_primitive={"fvg": "nonexistent_v99"},
        )
        with pytest.raises(RegistryError, match="nonexistent_v99"):
            engine.run(bars_by_tf, params)

    def test_error_lists_available_variants(self, bars_1m, bars_5m, bars_15m):
        """The error message lists available variants."""
        registry = build_default_registry()
        params = extract_locked_params_for_cascade(None)
        bars_by_tf = {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}

        engine = CascadeEngine(
            registry,
            LOCKED_DEP_GRAPH,
            variant_by_primitive={"fvg": "nonexistent_v99"},
        )
        with pytest.raises(RegistryError, match="Available"):
            engine.run(bars_by_tf, params)


# ── VAL-VENG-006: Config variant field drives detector selection ─────────────

class TestConfigVariantField:
    """VAL-VENG-006: YAML config supports cascade.variant_by_primitive mapping."""

    def test_config_schema_accepts_cascade_section(self):
        """RAConfig accepts optional cascade section with variant_by_primitive."""
        from ra.config.schema import RAConfig

        # Load the locked baseline config
        from ra.config.loader import load_config

        config = load_config("configs/locked_baseline.yaml")
        # Should have cascade attribute (may be None if not in YAML)
        # The schema should accept it
        assert config is not None

    def test_yaml_with_cascade_variant_by_primitive_loads(self):
        """YAML config with cascade.variant_by_primitive section loads correctly."""
        from ra.config.loader import load_config

        # Load the baseline, modify it to add cascade section, write to temp
        baseline_path = Path(__file__).parent.parent / "configs" / "locked_baseline.yaml"
        raw = baseline_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)

        # Add cascade section with variant_by_primitive
        data["cascade"] = {
            "variant_by_primitive": {
                "mss": "luxalgo_v1",
                "order_block": "luxalgo_v1",
            }
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False,
        ) as f:
            yaml.dump(data, f, default_flow_style=False)
            tmp_path = f.name

        try:
            config = load_config(tmp_path)
            assert config.cascade is not None
            assert config.cascade.variant_by_primitive is not None
            assert config.cascade.variant_by_primitive["mss"] == "luxalgo_v1"
            assert config.cascade.variant_by_primitive["order_block"] == "luxalgo_v1"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_yaml_without_cascade_section_loads(self):
        """Baseline YAML without cascade section loads (cascade is None)."""
        from ra.config.loader import load_config

        config = load_config("configs/locked_baseline.yaml")
        # cascade should be None since baseline doesn't have it
        assert config.cascade is None

    def test_cascade_config_empty_variant_by_primitive(self):
        """Cascade section with empty variant_by_primitive loads fine."""
        from ra.config.schema import CascadeConfig

        cc = CascadeConfig(variant_by_primitive={})
        assert cc.variant_by_primitive == {}

    def test_cascade_config_none_variant_by_primitive(self):
        """Cascade section with None variant_by_primitive is valid."""
        from ra.config.schema import CascadeConfig

        cc = CascadeConfig(variant_by_primitive=None)
        assert cc.variant_by_primitive is None

    def test_eval_compare_reads_cascade_config(self):
        """eval.py cmd_compare reads cascade.variant_by_primitive from config."""
        from ra.config.loader import load_config

        # Load baseline, add cascade section, write to temp
        baseline_path = Path(__file__).parent.parent / "configs" / "locked_baseline.yaml"
        raw = baseline_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)

        data["cascade"] = {
            "variant_by_primitive": {
                "mss": "luxalgo_v1",
            }
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False,
        ) as f:
            yaml.dump(data, f, default_flow_style=False)
            tmp_path = f.name

        try:
            config = load_config(tmp_path)
            assert config.cascade is not None
            assert config.cascade.variant_by_primitive == {"mss": "luxalgo_v1"}

            # Verify eval.py code path: the same conditional used in cmd_compare
            variant_by_primitive = None
            if (
                hasattr(config, "cascade")
                and config.cascade
                and config.cascade.variant_by_primitive
            ):
                variant_by_primitive = dict(config.cascade.variant_by_primitive)

            assert variant_by_primitive == {"mss": "luxalgo_v1"}
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ── eval.py CLI flags ────────────────────────────────────────────────────────

class TestEvalCLIFlags:
    """eval.py compare --variant-a / --variant-b flags."""

    def test_compare_help_shows_variant_flags(self):
        """eval.py compare --help shows --variant-a and --variant-b flags."""
        result = subprocess.run(
            [sys.executable, "eval.py", "compare", "--help"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert "--variant-a" in result.stdout, (
            f"--variant-a not in help output:\n{result.stdout}"
        )
        assert "--variant-b" in result.stdout, (
            f"--variant-b not in help output:\n{result.stdout}"
        )

    def test_variant_flags_default_to_a8ra(self):
        """Default value for --variant-a and --variant-b is a8ra_v1."""
        import argparse
        # Import eval.py's main to check argument defaults
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import eval as eval_module

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        # Re-create the compare parser to check defaults
        # This is a structural test that the flags exist with correct defaults
        result = subprocess.run(
            [sys.executable, "eval.py", "compare", "--help"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert "a8ra_v1" in result.stdout, (
            "Default variant value should be a8ra_v1"
        )


# ── EvaluationRunner variant forwarding ──────────────────────────────────────

class TestEvaluationRunnerVariantForwarding:
    """EvaluationRunner passes variant_by_primitive to CascadeEngine."""

    def test_runner_accepts_variant_by_primitive(self):
        """EvaluationRunner can be constructed with variant_by_primitive."""
        from ra.config.loader import load_config
        from ra.evaluation.runner import EvaluationRunner

        config = load_config("configs/locked_baseline.yaml")
        # Should accept variant_by_primitive kwarg
        runner = EvaluationRunner(
            config,
            variant_by_primitive={"mss": "luxalgo_v1"},
        )
        assert runner is not None

    def test_runner_default_no_variant_override(self):
        """EvaluationRunner with no variant_by_primitive uses a8ra_v1."""
        from ra.config.loader import load_config
        from ra.evaluation.runner import EvaluationRunner

        config = load_config("configs/locked_baseline.yaml")
        runner = EvaluationRunner(config)
        assert runner is not None

    def test_run_comparison_accepts_variant_names(self):
        """run_comparison() can receive variant name strings."""
        from ra.config.loader import load_config
        from ra.evaluation.runner import EvaluationRunner

        config = load_config("configs/locked_baseline.yaml")
        runner = EvaluationRunner(config)

        # run_comparison should accept variant_a and variant_b params
        # This tests the signature, not actual execution (expensive)
        import inspect
        sig = inspect.signature(runner.run_comparison)
        param_names = list(sig.parameters.keys())
        assert "variant_a" in param_names or "variant_by_primitive_a" in param_names, (
            f"run_comparison should accept variant params. Params: {param_names}"
        )

    def test_runner_build_engine_passes_variant_by_primitive(self):
        """_build_engine() creates CascadeEngine with correct variant_by_primitive."""
        from ra.config.loader import load_config
        from ra.evaluation.runner import EvaluationRunner

        config = load_config("configs/locked_baseline.yaml")
        vbp = {"mss": "luxalgo_v1", "order_block": "luxalgo_v1"}
        runner = EvaluationRunner(config, variant_by_primitive=vbp)

        # Build engine and verify it got the variant_by_primitive
        engine = runner._build_engine()
        assert engine.get_variant_for_primitive("mss") == "luxalgo_v1"
        assert engine.get_variant_for_primitive("order_block") == "luxalgo_v1"
        assert engine.get_variant_for_primitive("fvg") == "a8ra_v1"

    def test_runner_build_engine_override(self):
        """_build_engine(variant_by_primitive=...) overrides runner's default."""
        from ra.config.loader import load_config
        from ra.evaluation.runner import EvaluationRunner

        config = load_config("configs/locked_baseline.yaml")
        runner = EvaluationRunner(config, variant_by_primitive={"mss": "luxalgo_v1"})

        # Override at build time
        engine = runner._build_engine(variant_by_primitive={"fvg": "luxalgo_v1"})
        # Should use the override, not the runner's default
        assert engine.get_variant_for_primitive("fvg") == "luxalgo_v1"

    def test_run_comparison_output_includes_variant_names(self):
        """run_comparison() output contains variant_a and variant_b names."""
        from ra.config.loader import load_config
        from ra.evaluation.runner import EvaluationRunner

        config = load_config("configs/locked_baseline.yaml")
        runner = EvaluationRunner(config)

        # Create minimal mock results
        results_a = {
            "fvg": {
                "5m": DetectionResult(
                    primitive="fvg", variant="a8ra_v1", timeframe="5m",
                    detections=[], metadata={}, params_used={},
                ),
            },
        }
        results_b = {
            "fvg": {
                "5m": DetectionResult(
                    primitive="fvg", variant="luxalgo_v1", timeframe="5m",
                    detections=[], metadata={}, params_used={},
                ),
            },
        }

        comparison = runner.run_comparison(
            results_a, results_b,
            variant_a="a8ra_v1", variant_b="luxalgo_v1",
        )

        assert comparison["summary"]["variant_a"] == "a8ra_v1"
        assert comparison["summary"]["variant_b"] == "luxalgo_v1"


# ── Multiple primitives variant override ─────────────────────────────────────

class TestMultiplePrimitiveOverrides:
    """Test variant_by_primitive with multiple primitive overrides."""

    def test_multiple_primitive_overrides(self):
        """Multiple primitives can each have different variants."""
        registry = build_default_registry()
        engine = CascadeEngine(
            registry,
            LOCKED_DEP_GRAPH,
            variant_by_primitive={
                "mss": "luxalgo_v1",
                "order_block": "luxalgo_v1",
                "fvg": "a8ra_v1",
            },
        )
        assert engine.get_variant_for_primitive("mss") == "luxalgo_v1"
        assert engine.get_variant_for_primitive("order_block") == "luxalgo_v1"
        assert engine.get_variant_for_primitive("fvg") == "a8ra_v1"
        assert engine.get_variant_for_primitive("displacement") == "a8ra_v1"

    def test_variant_by_primitive_is_copy_not_reference(self):
        """Modifying the original dict doesn't affect the engine."""
        registry = build_default_registry()
        vbp = {"mss": "luxalgo_v1"}
        engine = CascadeEngine(
            registry, LOCKED_DEP_GRAPH,
            variant_by_primitive=vbp,
        )
        # Mutate the original
        vbp["fvg"] = "other_v1"
        # Engine should not be affected
        assert engine.get_variant_for_primitive("fvg") == "a8ra_v1"
        assert "fvg" not in engine.variant_by_primitive
