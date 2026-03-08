"""Tests for structured JSON output serialization (Phase 2).

Validates:
- VAL-SO-001: Evaluation run JSON matches Schema 4A
- VAL-SO-002: Per-config result matches Schema 4B
- VAL-SO-003: Pairwise comparison matches Schema 4C
- VAL-SO-004: Grid sweep matches Schema 4D
- VAL-SO-005: Walk-forward matches Schema 4E
- VAL-SO-006: schema_version field in all outputs
- VAL-SO-007: Round-trip JSON fidelity (write→read preserves all fields)
- VAL-SO-008: by_session percentages sum to 100
- VAL-SO-009: Cascade funnel level ordering (leaf→composite→terminal)
- VAL-SO-010: Detection arrays sorted by time
- VAL-SO-011: numpy/pandas type serialization
- VAL-SO-012: by_direction distribution validation
- VAL-SO-013: 1D grid sweep (single-param) format valid
"""

import json
import math
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from ra.engine.base import Detection, DetectionResult
from ra.output.json_export import (
    RAJSONEncoder,
    serialize_evaluation_run,
    serialize_per_config_result,
    serialize_pairwise_comparison,
    serialize_grid_sweep,
    serialize_walk_forward,
    write_json,
    read_json,
)

NY_TZ = ZoneInfo("America/New_York")


# ─── Test Helpers ────────────────────────────────────────────────────────


def _make_detection(
    primitive: str,
    tf: str,
    ts_str: str,
    direction: str = "bullish",
    session: str = "nyokz",
    forex_day: str = "2024-01-08",
    det_type: str = "default",
    upstream_refs: list | None = None,
    price: float = 1.0950,
) -> Detection:
    """Create a test Detection."""
    ts = datetime.fromisoformat(ts_str).replace(tzinfo=NY_TZ)
    dir_short = {"bullish": "bull", "bearish": "bear"}.get(direction, direction)
    det_id = f"{primitive}_{tf}_{ts.strftime('%Y-%m-%dT%H:%M:%S')}_{dir_short}"
    return Detection(
        id=det_id,
        time=ts,
        direction=direction,
        type=det_type,
        price=price,
        properties={"atr_ratio": 1.82},
        tags={"session": session, "forex_day": forex_day, "kill_zone": "NYOKZ"},
        upstream_refs=upstream_refs or [],
    )


def _make_result(
    primitive: str, tf: str, detections: list[Detection]
) -> DetectionResult:
    """Create a test DetectionResult."""
    return DetectionResult(
        primitive=primitive,
        variant="a8ra_v1",
        timeframe=tf,
        detections=detections,
        metadata={},
        params_used={"floor_threshold_pips": 0.5},
    )


def _build_sample_cascade_results() -> dict[str, dict[str, DetectionResult]]:
    """Build a sample cascade result for testing output serialization."""
    results = {}

    # displacement/5m: 6 detections across sessions and directions
    disp_dets = [
        _make_detection("displacement", "5m", "2024-01-08T08:15:00", "bullish", "nyokz", "2024-01-08"),
        _make_detection("displacement", "5m", "2024-01-08T09:35:00", "bearish", "nyokz", "2024-01-08"),
        _make_detection("displacement", "5m", "2024-01-08T19:30:00", "bullish", "asia", "2024-01-08"),
        _make_detection("displacement", "5m", "2024-01-09T03:00:00", "bearish", "lokz", "2024-01-09"),
        _make_detection("displacement", "5m", "2024-01-09T06:00:00", "bullish", "other", "2024-01-09"),
        _make_detection("displacement", "5m", "2024-01-09T08:30:00", "bearish", "nyokz", "2024-01-09"),
    ]
    results["displacement"] = {"5m": _make_result("displacement", "5m", disp_dets)}

    # fvg/5m: 4 detections
    fvg_dets = [
        _make_detection("fvg", "5m", "2024-01-08T08:10:00", "bullish", "nyokz", "2024-01-08"),
        _make_detection("fvg", "5m", "2024-01-08T09:30:00", "bearish", "nyokz", "2024-01-08"),
        _make_detection("fvg", "5m", "2024-01-09T03:10:00", "bullish", "lokz", "2024-01-09"),
        _make_detection("fvg", "5m", "2024-01-09T08:25:00", "bearish", "nyokz", "2024-01-09"),
    ]
    results["fvg"] = {"5m": _make_result("fvg", "5m", fvg_dets)}

    # swing_points/5m: 3 detections (high/low directions)
    sp_dets = [
        _make_detection("swing_points", "5m", "2024-01-08T07:00:00", "high", "other", "2024-01-08"),
        _make_detection("swing_points", "5m", "2024-01-08T10:00:00", "low", "nyokz", "2024-01-08"),
        _make_detection("swing_points", "5m", "2024-01-09T04:00:00", "high", "lokz", "2024-01-09"),
    ]
    results["swing_points"] = {"5m": _make_result("swing_points", "5m", sp_dets)}

    # mss/5m: 2 composite detections
    mss_dets = [
        _make_detection("mss", "5m", "2024-01-08T09:40:00", "bearish", "nyokz", "2024-01-08",
                        upstream_refs=["displacement_5m_2024-01-08T09:35:00_bear"]),
        _make_detection("mss", "5m", "2024-01-09T08:35:00", "bearish", "nyokz", "2024-01-09",
                        upstream_refs=["displacement_5m_2024-01-09T08:30:00_bear"]),
    ]
    results["mss"] = {"5m": _make_result("mss", "5m", mss_dets)}

    # order_block/5m: 1 composite detection
    ob_dets = [
        _make_detection("order_block", "5m", "2024-01-08T09:45:00", "bearish", "nyokz", "2024-01-08",
                        upstream_refs=["mss_5m_2024-01-08T09:40:00_bear"]),
    ]
    results["order_block"] = {"5m": _make_result("order_block", "5m", ob_dets)}

    return results


def _build_sample_dep_graph() -> dict[str, list[str]]:
    """Build a sample dependency graph for testing."""
    return {
        "fvg": [],
        "swing_points": [],
        "displacement": [],
        "session_liquidity": [],
        "asia_range": [],
        "reference_levels": [],
        "mss": ["swing_points", "displacement", "fvg"],
        "order_block": ["displacement", "mss"],
        "liquidity_sweep": ["session_liquidity", "reference_levels", "swing_points", "displacement"],
    }


def _build_pairwise_comparison() -> dict:
    """Build a sample pairwise comparison result (Schema 4C structure)."""
    return {
        "config_a": "current_locked",
        "config_b": "candidate_relaxed",
        "per_primitive": {
            "displacement": {
                "5m": {
                    "count_a": 6,
                    "count_b": 8,
                    "agreement_rate": 0.68,
                    "only_in_a": 1,
                    "only_in_b": 3,
                    "by_session_agreement": {
                        "asia": {"agreement": 0.55},
                        "lokz": {"agreement": 0.72},
                        "nyokz": {"agreement": 0.74},
                        "other": {"agreement": 0.61},
                    },
                },
            },
        },
        "divergence_index": [
            {
                "time": "2024-01-08T09:35:00",
                "primitive": "displacement",
                "tf": "5m",
                "in_a": True,
                "in_b": True,
                "detection_id_a": "disp_5m_2024-01-08T09:35:00_bear",
                "detection_id_b": "disp_5m_2024-01-08T09:35:00_bear",
            },
            {
                "time": "2024-01-08T10:15:00",
                "primitive": "displacement",
                "tf": "5m",
                "in_a": False,
                "in_b": True,
                "detection_id_a": None,
                "detection_id_b": "disp_5m_2024-01-08T10:15:00_bull",
            },
        ],
    }


def _build_grid_sweep() -> dict:
    """Build a sample grid sweep result (Schema 4D structure)."""
    return {
        "sweep_id": "sweep_displacement_atr_body_20260309",
        "primitive": "displacement",
        "variant": "a8ra_v1",
        "dataset": "EURUSD_2024_Q1",
        "metric": "detection_count",
        "axes": {
            "x": {"param": "atr_multiplier", "values": [1.0, 1.5, 2.0]},
            "y": {"param": "body_ratio", "values": [0.5, 0.6]},
        },
        "grid": [
            [10, 12],
            [8, 10],
            [6, 7],
        ],
        "current_lock": {"x": 1.5, "y": 0.6, "metric_value": 10},
        "plateau": {
            "detected": True,
            "region": {"x_range": [1.0, 2.0], "y_range": [0.5, 0.6]},
            "metric_variance_within": 3.0,
            "metric_mean_within": 8.8,
            "lock_position": "CENTER",
        },
        "cliff_edges": [
            {"axis": "atr_multiplier", "direction": "above", "threshold": 2.5, "metric_drop_to": 3},
        ],
    }


def _build_walk_forward() -> dict:
    """Build a sample walk-forward result (Schema 4E structure)."""
    return {
        "config": "current_locked",
        "primitive": "displacement",
        "metric": "detection_count",
        "window_config": {"train_months": 3, "test_months": 1, "step_months": 1},
        "windows": [
            {
                "window_index": 0,
                "train_period": {"start": "2024-01-01", "end": "2024-03-31"},
                "test_period": {"start": "2024-04-01", "end": "2024-04-30"},
                "train_metric": 100.0,
                "test_metric": 95.0,
                "delta": -5.0,
                "delta_pct": -5.0,
                "regime_tags": [],
                "passed": True,
            },
            {
                "window_index": 1,
                "train_period": {"start": "2024-02-01", "end": "2024-04-30"},
                "test_period": {"start": "2024-05-01", "end": "2024-05-31"},
                "train_metric": 95.0,
                "test_metric": 90.0,
                "delta": -5.0,
                "delta_pct": -5.26,
                "regime_tags": [],
                "passed": True,
            },
        ],
        "summary": {
            "windows_total": 2,
            "windows_passed": 2,
            "windows_failed": 0,
            "mean_test_metric": 92.5,
            "std_test_metric": 2.5,
            "mean_delta": -5.0,
            "worst_window": {
                "window_index": 1,
                "test_period": "May 2024",
                "test_metric": 90.0,
                "regime": "",
            },
            "degradation_flag": False,
            "pass_threshold_pct": 15.0,
            "verdict": "STABLE",
        },
    }


# ─── VAL-SO-011: numpy/pandas type serialization ─────────────────────────


class TestNumpyPandasSerialization:
    """Test that numpy/pandas types are correctly serialized to JSON."""

    def test_numpy_int64_serialized_as_int(self):
        """numpy.int64 → plain JSON integer."""
        encoder = RAJSONEncoder()
        result = json.loads(json.dumps({"val": np.int64(42)}, cls=RAJSONEncoder))
        assert result["val"] == 42
        assert isinstance(result["val"], int)

    def test_numpy_float64_serialized_as_float(self):
        """numpy.float64 → plain JSON number."""
        result = json.loads(json.dumps({"val": np.float64(3.14)}, cls=RAJSONEncoder))
        assert result["val"] == pytest.approx(3.14)
        assert isinstance(result["val"], float)

    def test_numpy_nan_serialized_as_null(self):
        """numpy.nan → JSON null."""
        result = json.loads(json.dumps({"val": np.nan}, cls=RAJSONEncoder))
        assert result["val"] is None

    def test_float_nan_serialized_as_null(self):
        """float('nan') → JSON null."""
        result = json.loads(json.dumps({"val": float("nan")}, cls=RAJSONEncoder))
        assert result["val"] is None

    def test_pandas_timestamp_serialized_as_iso(self):
        """pandas.Timestamp → ISO 8601 string."""
        ts = pd.Timestamp("2024-01-08T09:35:00", tz="America/New_York")
        result = json.loads(json.dumps({"val": ts}, cls=RAJSONEncoder))
        assert "2024-01-08" in result["val"]
        assert "09:35" in result["val"]

    def test_pandas_nat_serialized_as_null(self):
        """pandas.NaT → JSON null."""
        result = json.loads(json.dumps({"val": pd.NaT}, cls=RAJSONEncoder))
        assert result["val"] is None

    def test_numpy_bool_serialized_as_bool(self):
        """numpy.bool_ → JSON true/false."""
        result = json.loads(json.dumps({"val": np.bool_(True)}, cls=RAJSONEncoder))
        assert result["val"] is True

    def test_datetime_serialized_as_iso(self):
        """datetime → ISO 8601 string."""
        ts = datetime(2024, 1, 8, 9, 35, 0, tzinfo=NY_TZ)
        result = json.loads(json.dumps({"val": ts}, cls=RAJSONEncoder))
        assert "2024-01-08" in result["val"]
        assert "09:35" in result["val"]

    def test_numpy_array_serialized_as_list(self):
        """numpy array → JSON list."""
        arr = np.array([1.0, 2.0, 3.0])
        result = json.loads(json.dumps({"val": arr}, cls=RAJSONEncoder))
        assert result["val"] == [1.0, 2.0, 3.0]

    def test_mixed_types_in_nested_dict(self):
        """Complex nested dict with numpy/pandas types serializes without error."""
        data = {
            "count": np.int64(100),
            "rate": np.float64(0.75),
            "missing": np.nan,
            "ts": pd.Timestamp("2024-01-08"),
            "flag": np.bool_(False),
            "nested": {
                "arr": np.array([1, 2, 3]),
                "val": np.float64(float("nan")),
            },
        }
        text = json.dumps(data, cls=RAJSONEncoder)
        parsed = json.loads(text)
        assert parsed["count"] == 100
        assert parsed["rate"] == pytest.approx(0.75)
        assert parsed["missing"] is None
        assert parsed["flag"] is False
        assert parsed["nested"]["val"] is None


# ─── VAL-SO-006: schema_version in all outputs ───────────────────────────


class TestSchemaVersion:
    """Test that schema_version is present in all output types."""

    def test_schema_version_in_evaluation_run(self):
        """Schema 4A output has schema_version."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_evaluation_run(
            results_by_config={"locked": results},
            dataset_name="test_dataset",
            bars_1m_count=1000,
            date_range=("2024-01-08", "2024-01-12"),
            dep_graph=dep_graph,
        )
        assert "schema_version" in output
        assert isinstance(output["schema_version"], str)
        assert len(output["schema_version"]) > 0

    def test_schema_version_in_grid_sweep(self):
        """Schema 4D output has schema_version."""
        grid_data = _build_grid_sweep()
        output = serialize_grid_sweep(grid_data)
        assert "schema_version" in output
        assert isinstance(output["schema_version"], str)

    def test_schema_version_in_walk_forward(self):
        """Schema 4E output has schema_version."""
        wf_data = _build_walk_forward()
        output = serialize_walk_forward(wf_data)
        assert "schema_version" in output
        assert isinstance(output["schema_version"], str)


# ─── VAL-SO-001: Schema 4A ───────────────────────────────────────────────


class TestSchema4A:
    """Test evaluation run output matches Schema 4A."""

    def test_top_level_fields_present(self):
        """Schema 4A has all required top-level fields."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_evaluation_run(
            results_by_config={"locked": results},
            dataset_name="test_dataset",
            bars_1m_count=7200,
            date_range=("2024-01-08", "2024-01-12"),
            dep_graph=dep_graph,
        )
        assert "schema_version" in output
        assert "run_id" in output
        assert "dataset" in output
        assert "configs" in output
        assert "timestamp" in output
        assert "per_config" in output
        assert "pairwise" in output

    def test_dataset_fields(self):
        """Schema 4A dataset has name, bars_1m, range."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_evaluation_run(
            results_by_config={"locked": results},
            dataset_name="EURUSD_test",
            bars_1m_count=7200,
            date_range=("2024-01-08", "2024-01-12"),
            dep_graph=dep_graph,
        )
        ds = output["dataset"]
        assert ds["name"] == "EURUSD_test"
        assert ds["bars_1m"] == 7200
        assert ds["range"] == ["2024-01-08", "2024-01-12"]

    def test_per_config_keyed_by_name(self):
        """per_config dict is keyed by config name."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_evaluation_run(
            results_by_config={"locked": results},
            dataset_name="test",
            bars_1m_count=100,
            date_range=("2024-01-08", "2024-01-12"),
            dep_graph=dep_graph,
        )
        assert "locked" in output["per_config"]

    def test_configs_list(self):
        """configs list reflects all evaluated configs."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_evaluation_run(
            results_by_config={"locked": results, "candidate": results},
            dataset_name="test",
            bars_1m_count=100,
            date_range=("2024-01-08", "2024-01-12"),
            dep_graph=dep_graph,
        )
        assert sorted(output["configs"]) == ["candidate", "locked"]

    def test_pairwise_generated_for_multi_config(self):
        """pairwise section generated for multiple configs."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_evaluation_run(
            results_by_config={"locked": results, "candidate": results},
            dataset_name="test",
            bars_1m_count=100,
            date_range=("2024-01-08", "2024-01-12"),
            dep_graph=dep_graph,
        )
        assert len(output["pairwise"]) > 0

    def test_grid_sweep_and_walk_forward_nullable(self):
        """grid_sweep and walk_forward can be null."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_evaluation_run(
            results_by_config={"locked": results},
            dataset_name="test",
            bars_1m_count=100,
            date_range=("2024-01-08", "2024-01-12"),
            dep_graph=dep_graph,
        )
        assert output.get("grid_sweep") is None
        assert output.get("walk_forward") is None


# ─── VAL-SO-002: Schema 4B ───────────────────────────────────────────────


class TestSchema4B:
    """Test per-config result matches Schema 4B."""

    def test_per_config_fields(self):
        """Schema 4B per-config has config_name, params, per_primitive, cascade_funnel."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_per_config_result(
            config_name="locked",
            results=results,
            params={"displacement": {"atr_multiplier": 1.5}},
            dep_graph=dep_graph,
        )
        assert output["config_name"] == "locked"
        assert "params" in output
        assert "per_primitive" in output
        assert "cascade_funnel" in output

    def test_per_primitive_per_tf_fields(self):
        """Each per_primitive.per_tf block has required stats fields."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_per_config_result(
            config_name="locked",
            results=results,
            params={},
            dep_graph=dep_graph,
        )
        disp_5m = output["per_primitive"]["displacement"]["per_tf"]["5m"]
        assert "detection_count" in disp_5m
        assert "detections_per_day" in disp_5m
        assert "by_session" in disp_5m
        assert "by_direction" in disp_5m
        assert "detections" in disp_5m

    def test_detections_array_structure(self):
        """Detections array items have required fields."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_per_config_result(
            config_name="locked",
            results=results,
            params={},
            dep_graph=dep_graph,
        )
        det = output["per_primitive"]["displacement"]["per_tf"]["5m"]["detections"][0]
        assert "id" in det
        assert "time" in det
        assert "direction" in det
        assert "type" in det
        assert "price" in det
        assert "properties" in det
        assert "tags" in det
        assert "upstream_refs" in det


# ─── VAL-SO-003: Schema 4C ───────────────────────────────────────────────


class TestSchema4C:
    """Test pairwise comparison matches Schema 4C."""

    def test_pairwise_fields(self):
        """Schema 4C has config_a, config_b, per_primitive, divergence_index."""
        comparison = _build_pairwise_comparison()
        output = serialize_pairwise_comparison(comparison)
        assert "config_a" in output
        assert "config_b" in output
        assert "per_primitive" in output
        assert "divergence_index" in output

    def test_divergence_index_entry_fields(self):
        """Divergence index entries have required fields."""
        comparison = _build_pairwise_comparison()
        output = serialize_pairwise_comparison(comparison)
        entry = output["divergence_index"][0]
        assert "time" in entry
        assert "primitive" in entry
        assert "tf" in entry
        assert "in_a" in entry
        assert "in_b" in entry
        assert "detection_id_a" in entry
        assert "detection_id_b" in entry


# ─── VAL-SO-004: Schema 4D ───────────────────────────────────────────────


class TestSchema4D:
    """Test grid sweep matches Schema 4D."""

    def test_grid_sweep_fields(self):
        """Schema 4D has all required fields."""
        grid_data = _build_grid_sweep()
        output = serialize_grid_sweep(grid_data)
        assert "schema_version" in output
        assert "sweep_id" in output
        assert "primitive" in output
        assert "metric" in output
        assert "axes" in output
        assert "grid" in output
        assert "current_lock" in output

    def test_grid_dimensions(self):
        """Grid dimensions match axes values."""
        grid_data = _build_grid_sweep()
        output = serialize_grid_sweep(grid_data)
        x_len = len(output["axes"]["x"]["values"])
        y_len = len(output["axes"]["y"]["values"])
        assert len(output["grid"]) == x_len
        assert all(len(row) == y_len for row in output["grid"])

    def test_plateau_and_cliff_fields(self):
        """Plateau and cliff_edges present when provided."""
        grid_data = _build_grid_sweep()
        output = serialize_grid_sweep(grid_data)
        assert "plateau" in output
        assert output["plateau"]["detected"] is True
        assert "cliff_edges" in output
        assert len(output["cliff_edges"]) > 0


# ─── VAL-SO-013: 1D grid sweep ───────────────────────────────────────────


class TestSchema4D_1D:
    """Test 1D grid sweep (degenerate y-axis) format."""

    def test_1d_sweep_format(self):
        """Single-param sweep produces valid 1D grid."""
        grid_data = {
            "sweep_id": "sweep_fvg_floor_20260309",
            "primitive": "fvg",
            "variant": "a8ra_v1",
            "dataset": "EURUSD_test",
            "metric": "detection_count",
            "axes": {
                "x": {"param": "floor_threshold_pips", "values": [0.0, 0.5, 1.0, 1.5, 2.0]},
                "y": {"param": "_single", "values": [0]},
            },
            "grid": [[345, 345, 340, 330, 300]],
            "current_lock": {"x": 0.5, "y": 0, "metric_value": 345},
            "plateau": None,
            "cliff_edges": [],
        }
        output = serialize_grid_sweep(grid_data)
        assert output["axes"]["y"]["param"] == "_single"
        assert output["axes"]["y"]["values"] == [0]
        assert len(output["grid"]) == 1
        assert len(output["grid"][0]) == 5


# ─── VAL-SO-005: Schema 4E ───────────────────────────────────────────────


class TestSchema4E:
    """Test walk-forward matches Schema 4E."""

    def test_walk_forward_fields(self):
        """Schema 4E has all required fields."""
        wf_data = _build_walk_forward()
        output = serialize_walk_forward(wf_data)
        assert "schema_version" in output
        assert "config" in output
        assert "primitive" in output
        assert "metric" in output
        assert "window_config" in output
        assert "windows" in output
        assert "summary" in output

    def test_window_fields(self):
        """Each window has required per-window fields."""
        wf_data = _build_walk_forward()
        output = serialize_walk_forward(wf_data)
        win = output["windows"][0]
        assert "window_index" in win
        assert "train_period" in win
        assert "test_period" in win
        assert "train_metric" in win
        assert "test_metric" in win
        assert "delta" in win
        assert "delta_pct" in win
        assert "regime_tags" in win
        assert "passed" in win

    def test_summary_fields(self):
        """Summary has all required fields including verdict."""
        wf_data = _build_walk_forward()
        output = serialize_walk_forward(wf_data)
        s = output["summary"]
        assert "windows_total" in s
        assert "windows_passed" in s
        assert "windows_failed" in s
        assert "mean_test_metric" in s
        assert "std_test_metric" in s
        assert "mean_delta" in s
        assert "worst_window" in s
        assert "degradation_flag" in s
        assert "pass_threshold_pct" in s
        assert "verdict" in s
        assert s["verdict"] in ("STABLE", "CONDITIONALLY_STABLE", "UNSTABLE")


# ─── VAL-SO-008: by_session percentages sum to 100 ───────────────────────


class TestBySessionPctSum:
    """Test that by_session percentages sum to 100%."""

    def test_by_session_pct_sum(self):
        """All by_session pct values sum to 100.0 (±0.1)."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_per_config_result(
            config_name="locked",
            results=results,
            params={},
            dep_graph=dep_graph,
        )
        for prim_name, prim_data in output["per_primitive"].items():
            for tf, tf_data in prim_data["per_tf"].items():
                by_sess = tf_data["by_session"]
                total_pct = sum(v["pct"] for v in by_sess.values())
                if tf_data["detection_count"] > 0:
                    assert abs(total_pct - 100.0) < 0.2, (
                        f"{prim_name}/{tf}: by_session pct sum={total_pct}"
                    )


# ─── VAL-SO-012: by_direction percentages sum to 100 ─────────────────────


class TestByDirectionPctSum:
    """Test that by_direction percentages sum to 100%."""

    def test_by_direction_pct_sum(self):
        """by_direction pct values sum to 100.0 (±0.1) for primitives with bullish/bearish."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_per_config_result(
            config_name="locked",
            results=results,
            params={},
            dep_graph=dep_graph,
        )
        # Check displacement which uses bullish/bearish
        disp_5m = output["per_primitive"]["displacement"]["per_tf"]["5m"]
        by_dir = disp_5m["by_direction"]
        total_pct = sum(v["pct"] for v in by_dir.values())
        if disp_5m["detection_count"] > 0:
            assert abs(total_pct - 100.0) < 0.2


# ─── VAL-SO-009: Cascade funnel ordering ─────────────────────────────────


class TestCascadeFunnelOrdering:
    """Test cascade funnel levels are ordered leaf→composite→terminal."""

    def test_level_ordering(self):
        """Funnel levels: leaf entries precede composite precede terminal."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_per_config_result(
            config_name="locked",
            results=results,
            params={},
            dep_graph=dep_graph,
        )
        funnel = output["cascade_funnel"]
        levels = funnel["levels"]

        type_order = {"leaf": 0, "composite": 1, "terminal": 2}
        type_indices = [type_order[level["type"]] for level in levels]

        # Verify non-decreasing order
        for i in range(1, len(type_indices)):
            assert type_indices[i] >= type_indices[i - 1], (
                f"Level ordering violated: {levels[i-1]['name']} ({levels[i-1]['type']}) "
                f"before {levels[i]['name']} ({levels[i]['type']})"
            )


# ─── VAL-SO-010: Detection arrays sorted by time ─────────────────────────


class TestDetectionsSortedByTime:
    """Test detection arrays are sorted by time ascending."""

    def test_detections_sorted(self):
        """Detection arrays in per_primitive.per_tf are sorted by time."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_per_config_result(
            config_name="locked",
            results=results,
            params={},
            dep_graph=dep_graph,
        )
        for prim_name, prim_data in output["per_primitive"].items():
            for tf, tf_data in prim_data["per_tf"].items():
                dets = tf_data["detections"]
                times = [d["time"] for d in dets]
                assert times == sorted(times), (
                    f"{prim_name}/{tf}: detections not sorted by time"
                )


# ─── VAL-SO-007: Round-trip JSON fidelity ─────────────────────────────────


class TestRoundTripFidelity:
    """Test write→read preserves all fields."""

    def test_round_trip_evaluation_run(self):
        """Evaluation run output survives JSON write→read round-trip."""
        results = _build_sample_cascade_results()
        dep_graph = _build_sample_dep_graph()
        output = serialize_evaluation_run(
            results_by_config={"locked": results},
            dataset_name="test",
            bars_1m_count=100,
            date_range=("2024-01-08", "2024-01-12"),
            dep_graph=dep_graph,
        )

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            write_json(output, f.name)
            loaded = read_json(f.name)

        # Check all top-level keys preserved
        assert set(output.keys()) == set(loaded.keys())
        assert loaded["schema_version"] == output["schema_version"]
        assert loaded["dataset"] == output["dataset"]
        assert loaded["configs"] == output["configs"]

    def test_round_trip_grid_sweep(self):
        """Grid sweep output survives JSON round-trip."""
        grid_data = _build_grid_sweep()
        output = serialize_grid_sweep(grid_data)

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            write_json(output, f.name)
            loaded = read_json(f.name)

        assert loaded["grid"] == output["grid"]
        assert loaded["axes"] == output["axes"]

    def test_round_trip_walk_forward(self):
        """Walk-forward output survives JSON round-trip."""
        wf_data = _build_walk_forward()
        output = serialize_walk_forward(wf_data)

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            write_json(output, f.name)
            loaded = read_json(f.name)

        assert loaded["windows"] == output["windows"]
        assert loaded["summary"] == output["summary"]

    def test_round_trip_with_numpy_types(self):
        """Round-trip preserves data even with numpy types in source."""
        data = {
            "schema_version": "1.0",
            "count": np.int64(42),
            "rate": np.float64(0.75),
            "missing": float("nan"),
        }

        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            write_json(data, f.name)
            loaded = read_json(f.name)

        assert loaded["count"] == 42
        assert loaded["rate"] == pytest.approx(0.75)
        assert loaded["missing"] is None
