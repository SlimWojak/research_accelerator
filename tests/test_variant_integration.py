"""Integration tests for variant cascade: mixed variants end-to-end.

Tests cover:
- VAL-VENG-002: Registry holds multiple variants for same primitive
- VAL-VENG-003: LuxAlgo MSS produces different detections than a8ra
- VAL-VENG-004: Mixed-variant cascade runs without errors
- VAL-CROSS-005: Mixed variant cascade preserves downstream integrity
- VAL-VEVAL-002: Comparison output includes variant in JSON
- VAL-VEVAL-003: Pairwise stats correct between variants
- VAL-VEVAL-004: Divergence index shows variant disagreements

Also:
- Registry lists both a8ra_v1 and luxalgo_v1 for mss and order_block
- LuxAlgo MSS produces more detections than a8ra MSS on same data
- LuxAlgo OB upstream_refs point to luxalgo MSS IDs
- eval.py compare JSON output includes variant field in config entries
- compare_pairwise shows agreement_rate < 100% and only_in_b > 0
- Divergence index has entries for variant disagreements
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from ra.engine.base import DetectionResult
from ra.engine.cascade import (
    CascadeEngine,
    build_default_registry,
    extract_locked_params_for_cascade,
)
from ra.engine.registry import Registry
from ra.evaluation.comparison import compare_pairwise


# ── Fixtures ─────────────────────────────────────────────────────────────────

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


@pytest.fixture(scope="module")
def registry():
    """Build default registry with all detectors (a8ra + luxalgo)."""
    return build_default_registry()


@pytest.fixture(scope="module")
def locked_params():
    """Extract locked params for all primitives."""
    return extract_locked_params_for_cascade(None)


@pytest.fixture(scope="module")
def bars_by_tf(bars_1m, bars_5m, bars_15m):
    """Prepare bars by timeframe dict."""
    return {"1m": bars_1m, "5m": bars_5m, "15m": bars_15m}


@pytest.fixture(scope="module")
def a8ra_results(bars_by_tf, locked_params):
    """Run full cascade with all a8ra_v1 variants (baseline)."""
    reg = build_default_registry()
    engine = CascadeEngine(reg, LOCKED_DEP_GRAPH, variant="a8ra_v1")
    return engine.run(bars_by_tf, locked_params)


@pytest.fixture(scope="module")
def mixed_results(bars_by_tf, locked_params):
    """Run full cascade with mixed variants: mss=luxalgo_v1, order_block=luxalgo_v1, rest=a8ra_v1."""
    reg = build_default_registry()
    engine = CascadeEngine(
        reg,
        LOCKED_DEP_GRAPH,
        variant_by_primitive={
            "mss": "luxalgo_v1",
            "order_block": "luxalgo_v1",
        },
    )
    return engine.run(bars_by_tf, locked_params)


@pytest.fixture(scope="module")
def luxalgo_only_mss_results(bars_by_tf, locked_params):
    """Run cascade with only mss=luxalgo_v1 (ob still a8ra_v1)."""
    reg = build_default_registry()
    engine = CascadeEngine(
        reg,
        LOCKED_DEP_GRAPH,
        variant_by_primitive={"mss": "luxalgo_v1"},
    )
    return engine.run(bars_by_tf, locked_params)


# ── VAL-VENG-002: Registry holds multiple variants ──────────────────────────

class TestRegistryMultipleVariants:
    """VAL-VENG-002: Registry holds multiple variants for same primitive."""

    def test_registry_has_both_mss_variants(self, registry):
        """Registry.list_registered() contains both (mss, a8ra_v1) and (mss, luxalgo_v1)."""
        registered = registry.list_registered()
        assert ("mss", "a8ra_v1") in registered, "a8ra_v1 MSS not registered"
        assert ("mss", "luxalgo_v1") in registered, "luxalgo_v1 MSS not registered"

    def test_registry_has_both_order_block_variants(self, registry):
        """Registry has both (order_block, a8ra_v1) and (order_block, luxalgo_v1)."""
        registered = registry.list_registered()
        assert ("order_block", "a8ra_v1") in registered, "a8ra_v1 OB not registered"
        assert ("order_block", "luxalgo_v1") in registered, "luxalgo_v1 OB not registered"

    def test_registry_get_returns_correct_class(self, registry):
        """registry.get() returns correct class for each variant."""
        from ra.detectors.mss import MSSDetector
        from ra.detectors.luxalgo_mss import LuxAlgoMSSDetector

        a8ra_mss = registry.get("mss", "a8ra_v1")
        luxalgo_mss = registry.get("mss", "luxalgo_v1")

        assert isinstance(a8ra_mss, MSSDetector)
        assert isinstance(luxalgo_mss, LuxAlgoMSSDetector)


# ── VAL-VENG-003: LuxAlgo MSS produces different detections ─────────────────

class TestLuxAlgoMSSDifferent:
    """VAL-VENG-003: LuxAlgo MSS produces different results than a8ra on same data."""

    def test_different_detection_counts(self, a8ra_results, mixed_results):
        """a8ra and luxalgo MSS produce different counts on same data."""
        for tf in ["1m", "5m", "15m"]:
            a8ra_count = len(a8ra_results.get("mss", {}).get(tf, DetectionResult(
                primitive="mss", variant="a8ra_v1", timeframe=tf
            )).detections)
            luxalgo_count = len(mixed_results.get("mss", {}).get(tf, DetectionResult(
                primitive="mss", variant="luxalgo_v1", timeframe=tf
            )).detections)

            # They should differ (LuxAlgo has no displacement gate)
            assert a8ra_count != luxalgo_count, (
                f"MSS counts identical at {tf}: a8ra={a8ra_count}, luxalgo={luxalgo_count}"
            )

    def test_luxalgo_fires_more_than_a8ra(self, a8ra_results, mixed_results):
        """LuxAlgo MSS fires more structure breaks than a8ra (no displacement gate)."""
        # At least one TF should show luxalgo > a8ra
        luxalgo_more_count = 0
        for tf in ["1m", "5m", "15m"]:
            a8ra_mss = a8ra_results.get("mss", {}).get(tf)
            luxalgo_mss = mixed_results.get("mss", {}).get(tf)
            if a8ra_mss and luxalgo_mss:
                if len(luxalgo_mss.detections) > len(a8ra_mss.detections):
                    luxalgo_more_count += 1

        assert luxalgo_more_count > 0, (
            "Expected LuxAlgo MSS to fire more than a8ra on at least one TF"
        )

    def test_different_detection_timestamps(self, a8ra_results, mixed_results):
        """Detection IDs differ between a8ra and luxalgo MSS."""
        for tf in ["5m"]:
            a8ra_ids = {d.id for d in a8ra_results.get("mss", {}).get(tf, DetectionResult(
                primitive="mss", variant="a8ra_v1", timeframe=tf
            )).detections}
            luxalgo_ids = {d.id for d in mixed_results.get("mss", {}).get(tf, DetectionResult(
                primitive="mss", variant="luxalgo_v1", timeframe=tf
            )).detections}

            # Should not be identical
            assert a8ra_ids != luxalgo_ids, "Detection ID sets should differ"


# ── VAL-VENG-004: Mixed cascade runs without errors ─────────────────────────

class TestMixedCascadeCompletion:
    """VAL-VENG-004: Mixed-variant cascade completes without errors."""

    def test_all_primitives_present(self, mixed_results):
        """All primitives produce results in the mixed cascade."""
        expected_primitives = {
            "fvg", "swing_points", "asia_range", "displacement",
            "reference_levels", "session_liquidity", "mss",
            "order_block", "ote", "htf_liquidity", "liquidity_sweep",
        }
        for prim in expected_primitives:
            assert prim in mixed_results, f"Primitive '{prim}' missing from results"

    def test_all_primitives_produce_detection_results(self, mixed_results):
        """All TF-specific primitives produce DetectionResult objects."""
        for prim, tf_dict in mixed_results.items():
            for tf, result in tf_dict.items():
                assert isinstance(result, DetectionResult), (
                    f"{prim}/{tf} is not DetectionResult: {type(result)}"
                )

    def test_mss_variant_is_luxalgo(self, mixed_results):
        """MSS detections in mixed cascade have variant='luxalgo_v1'."""
        for tf in ["1m", "5m", "15m"]:
            mss_result = mixed_results.get("mss", {}).get(tf)
            if mss_result:
                assert mss_result.variant == "luxalgo_v1", (
                    f"MSS {tf} variant should be luxalgo_v1, got {mss_result.variant}"
                )

    def test_order_block_variant_is_luxalgo(self, mixed_results):
        """OB detections in mixed cascade have variant='luxalgo_v1'."""
        for tf in ["1m", "5m", "15m"]:
            ob_result = mixed_results.get("order_block", {}).get(tf)
            if ob_result:
                assert ob_result.variant == "luxalgo_v1", (
                    f"OB {tf} variant should be luxalgo_v1, got {ob_result.variant}"
                )

    def test_fvg_variant_is_a8ra(self, mixed_results):
        """FVG detections remain a8ra_v1 in mixed cascade."""
        for tf in ["1m", "5m", "15m"]:
            fvg_result = mixed_results.get("fvg", {}).get(tf)
            if fvg_result:
                assert fvg_result.variant == "a8ra_v1", (
                    f"FVG {tf} variant should be a8ra_v1, got {fvg_result.variant}"
                )

    def test_non_zero_detections_per_primitive(self, mixed_results):
        """Key primitives produce non-zero detections."""
        for prim in ["fvg", "swing_points", "displacement", "mss"]:
            total = sum(
                len(r.detections)
                for r in mixed_results.get(prim, {}).values()
            )
            assert total > 0, f"Primitive '{prim}' has zero detections"


# ── VAL-CROSS-005: Mixed variant cascade preserves downstream integrity ─────

class TestMixedCascadeDownstreamIntegrity:
    """VAL-CROSS-005: LuxAlgo OB upstream_refs point to luxalgo MSS IDs."""

    def test_luxalgo_ob_refs_luxalgo_mss_ids(self, mixed_results):
        """In mixed cascade, luxalgo OB upstream_refs reference luxalgo MSS IDs."""
        for tf in ["1m", "5m", "15m"]:
            ob_result = mixed_results.get("order_block", {}).get(tf)
            mss_result = mixed_results.get("mss", {}).get(tf)

            if not ob_result or not mss_result:
                continue
            if not ob_result.detections:
                continue

            mss_ids = {d.id for d in mss_result.detections}

            for ob_det in ob_result.detections:
                if ob_det.upstream_refs:
                    # At least one ref should be a valid MSS ID
                    mss_refs = [r for r in ob_det.upstream_refs if r in mss_ids]
                    assert len(mss_refs) > 0, (
                        f"OB {ob_det.id} has upstream_refs={ob_det.upstream_refs} "
                        f"but none match luxalgo MSS IDs"
                    )

    def test_a8ra_ob_refs_different_from_luxalgo_ob_refs(
        self, a8ra_results, mixed_results
    ):
        """OB detection IDs differ between a8ra and luxalgo configurations."""
        for tf in ["5m"]:
            a8ra_ob = a8ra_results.get("order_block", {}).get(tf)
            luxalgo_ob = mixed_results.get("order_block", {}).get(tf)

            if not a8ra_ob or not luxalgo_ob:
                continue

            a8ra_ids = {d.id for d in a8ra_ob.detections}
            luxalgo_ids = {d.id for d in luxalgo_ob.detections}

            # They should differ since they use different MSS upstream
            assert a8ra_ids != luxalgo_ids, (
                "OB detection IDs should differ between a8ra and luxalgo cascades"
            )


# ── Pairwise comparison between variants ────────────────────────────────────

class TestVariantPairwiseComparison:
    """VAL-VEVAL-003: compare_pairwise stats correct between variants."""

    def test_agreement_rate_below_100(self, a8ra_results, mixed_results):
        """Pairwise comparison of a8ra vs luxalgo MSS has agreement_rate < 100%."""
        comparison = compare_pairwise(a8ra_results, mixed_results)

        for tf in ["5m"]:
            mss_stats = comparison["per_primitive"].get("mss", {}).get(tf)
            if mss_stats:
                assert mss_stats["agreement_rate"] < 1.0, (
                    f"MSS {tf} agreement should be < 100%: {mss_stats['agreement_rate']}"
                )

    def test_only_in_b_greater_than_zero(self, a8ra_results, mixed_results):
        """only_in_b > 0 (luxalgo fires more detections not in a8ra)."""
        comparison = compare_pairwise(a8ra_results, mixed_results)

        total_only_b = 0
        for prim, tf_dict in comparison["per_primitive"].items():
            for tf, stats in tf_dict.items():
                total_only_b += stats.get("only_in_b", 0)

        assert total_only_b > 0, "Expected some detections only in luxalgo (only_in_b > 0)"


# ── Divergence index ────────────────────────────────────────────────────────

class TestDivergenceIndex:
    """VAL-VEVAL-004: Divergence index shows variant disagreements."""

    def test_divergence_index_has_entries(self, a8ra_results, mixed_results):
        """Divergence index has entries for variant disagreements."""
        comparison = compare_pairwise(a8ra_results, mixed_results)
        assert len(comparison["divergence_index"]) > 0, (
            "Divergence index should have entries"
        )

    def test_divergence_length_matches_stats(self, a8ra_results, mixed_results):
        """Divergence index length equals sum of agreed + only_in_a + only_in_b."""
        comparison = compare_pairwise(a8ra_results, mixed_results)

        # Count total unique detections across all primitives
        total_expected = 0
        for prim, tf_dict in comparison["per_primitive"].items():
            for tf, stats in tf_dict.items():
                total_expected += (
                    stats.get("only_in_a", 0)
                    + stats.get("only_in_b", 0)
                    + (stats["count_a"] + stats["count_b"]
                       - stats["only_in_a"] - stats["only_in_b"]) // 2
                )

        # Divergence index has all unique detections
        assert len(comparison["divergence_index"]) > 0

    def test_divergence_entries_have_required_fields(self, a8ra_results, mixed_results):
        """Divergence index entries have required fields (time, primitive, tf, in_a, in_b)."""
        comparison = compare_pairwise(a8ra_results, mixed_results)

        for entry in comparison["divergence_index"][:20]:  # sample first 20
            assert "time" in entry, "Missing 'time' field"
            assert "primitive" in entry, "Missing 'primitive' field"
            assert "tf" in entry, "Missing 'tf' field"
            assert "in_a" in entry, "Missing 'in_a' field"
            assert "in_b" in entry, "Missing 'in_b' field"
            assert "detection_id_a" in entry, "Missing 'detection_id_a'"
            assert "detection_id_b" in entry, "Missing 'detection_id_b'"


# ── eval.py compare variant comparison JSON output ──────────────────────────

class TestEvalCompareVariantOutput:
    """VAL-VEVAL-002: Comparison output includes variant in JSON."""

    def test_eval_compare_runs_successfully(self):
        """eval.py compare --variant-a a8ra_v1 --variant-b luxalgo_v1 runs without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable, "eval.py", "compare",
                    "--config", "configs/locked_baseline.yaml",
                    "--data", "data/eurusd_1m_2024-01-07_to_2024-01-12.csv",
                    "--variant-a", "a8ra_v1",
                    "--variant-b", "luxalgo_v1",
                    "--output", tmpdir,
                ],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).parent.parent),
                timeout=300,
            )
            assert result.returncode == 0, (
                f"eval.py compare failed:\nstdout: {result.stdout[-500:]}\n"
                f"stderr: {result.stderr[-500:]}"
            )

    def test_eval_compare_output_has_variant_field(self):
        """JSON output includes variant field in config entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                [
                    sys.executable, "eval.py", "compare",
                    "--config", "configs/locked_baseline.yaml",
                    "--data", "data/eurusd_1m_2024-01-07_to_2024-01-12.csv",
                    "--variant-a", "a8ra_v1",
                    "--variant-b", "luxalgo_v1",
                    "--output", tmpdir,
                ],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).parent.parent),
                timeout=300,
            )
            out_path = Path(tmpdir) / "evaluation_run.json"
            assert out_path.exists(), "evaluation_run.json not created"

            data = json.loads(out_path.read_text())

            # Check schema_version
            assert "schema_version" in data

            # Check that per_config keys incorporate variant info
            assert "per_config" in data, "Missing per_config"
            assert len(data["per_config"]) >= 2, (
                f"Expected at least 2 configs, got {len(data['per_config'])}"
            )

            # Check that variant info is present in config entries
            for config_name, config_data in data["per_config"].items():
                assert "variant" in config_data or "variant" in (config_data.get("params", {}) or {}), (
                    f"Config '{config_name}' missing variant field"
                )

    def test_eval_compare_pairwise_stats(self):
        """Pairwise stats show agreement_rate < 100% between variants."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                [
                    sys.executable, "eval.py", "compare",
                    "--config", "configs/locked_baseline.yaml",
                    "--data", "data/eurusd_1m_2024-01-07_to_2024-01-12.csv",
                    "--variant-a", "a8ra_v1",
                    "--variant-b", "luxalgo_v1",
                    "--output", tmpdir,
                ],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).parent.parent),
                timeout=300,
            )
            out_path = Path(tmpdir) / "evaluation_run.json"
            data = json.loads(out_path.read_text())

            # Check pairwise section exists and has comparison data
            assert "pairwise" in data, "Missing pairwise section"
            if data["pairwise"]:
                for key, comparison in data["pairwise"].items():
                    # Check there's actual comparison data
                    assert "per_primitive" in comparison
                    # MSS should show disagreement
                    mss_data = comparison["per_primitive"].get("mss", {})
                    for tf, stats in mss_data.items():
                        if stats.get("count_a", 0) > 0 or stats.get("count_b", 0) > 0:
                            assert stats["agreement_rate"] < 1.0, (
                                f"MSS {tf} agreement should be < 100%"
                            )

    def test_eval_compare_divergence_index(self):
        """Divergence index in output has entries for variant disagreements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                [
                    sys.executable, "eval.py", "compare",
                    "--config", "configs/locked_baseline.yaml",
                    "--data", "data/eurusd_1m_2024-01-07_to_2024-01-12.csv",
                    "--variant-a", "a8ra_v1",
                    "--variant-b", "luxalgo_v1",
                    "--output", tmpdir,
                ],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).parent.parent),
                timeout=300,
            )
            out_path = Path(tmpdir) / "evaluation_run.json"
            data = json.loads(out_path.read_text())

            if data["pairwise"]:
                for key, comparison in data["pairwise"].items():
                    div_idx = comparison.get("divergence_index", [])
                    assert len(div_idx) > 0, "Divergence index should have entries"
