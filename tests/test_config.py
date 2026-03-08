"""Tests for config loading, validation error cases, and per-TF resolution.

Covers VAL-CFG-001 through VAL-CFG-006.
"""

import copy
import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ra.config.loader import (
    ConfigError,
    SchemaVersionError,
    load_config,
    resolve_per_tf,
)
from ra.config.schema import RAConfig


# ─── Fixtures ─────────────────────────────────────────────────────────────

LOCKED_BASELINE_PATH = Path(__file__).parent.parent / "configs" / "locked_baseline.yaml"


@pytest.fixture
def locked_config() -> RAConfig:
    """Load the locked baseline config."""
    return load_config(LOCKED_BASELINE_PATH)


@pytest.fixture
def raw_config_data() -> dict:
    """Load raw YAML data for mutation tests."""
    with open(LOCKED_BASELINE_PATH) as f:
        return yaml.safe_load(f)


def _write_temp_yaml(data: dict) -> Path:
    """Write a dict to a temp YAML file and return its path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(data, tmp, default_flow_style=False)
    tmp.close()
    return Path(tmp.name)


# ─── VAL-CFG-001: Config loads from YAML file ────────────────────────────

def test_config_loads_successfully(locked_config: RAConfig):
    """VAL-CFG-001: Loading locked_baseline.yaml produces a valid config."""
    assert locked_config is not None
    assert isinstance(locked_config, RAConfig)
    assert locked_config.schema_version == "1.0"
    assert locked_config.instrument == "EURUSD"


def test_config_has_all_primitives(locked_config: RAConfig):
    """VAL-CFG-001: Config has all primitive sections populated."""
    prims = locked_config.primitives
    assert prims.fvg is not None
    assert prims.swing_points is not None
    assert prims.displacement is not None
    assert prims.mss is not None
    assert prims.order_block is not None
    assert prims.liquidity_sweep is not None
    assert prims.htf_liquidity is not None
    assert prims.ote is not None
    assert prims.reference_levels is not None
    assert prims.session_liquidity is not None
    assert prims.asia_range is not None
    assert prims.equal_hl is not None
    assert prims.ifvg is not None
    assert prims.bpr is not None


def test_config_has_dependency_graph(locked_config: RAConfig):
    """VAL-CFG-001: Config has dependency graph."""
    dg = locked_config.dependency_graph
    assert "fvg" in dg
    assert "mss" in dg
    assert dg["fvg"].upstream == []
    assert "swing_points" in dg["mss"].upstream
    assert "displacement" in dg["mss"].upstream


def test_config_has_constants(locked_config: RAConfig):
    """VAL-CFG-001: Config has constants section."""
    c = locked_config.constants
    assert c.pip == 0.0001
    assert c.forex_day_boundary_ny == "17:00"
    assert c.sessions.asia.start_ny == "19:00"


# ─── VAL-CFG-002: Unknown params rejected ────────────────────────────────

def test_unknown_param_in_fvg_rejected(raw_config_data: dict):
    """VAL-CFG-002: Unknown param in fvg.params raises ValidationError."""
    data = copy.deepcopy(raw_config_data)
    data["primitives"]["fvg"]["params"]["bogus_field"] = 99

    path = _write_temp_yaml(data)
    with pytest.raises(ValidationError) as exc_info:
        load_config(path)
    assert "bogus_field" in str(exc_info.value)
    path.unlink()


def test_unknown_top_level_field_rejected(raw_config_data: dict):
    """VAL-CFG-002: Unknown top-level field raises ValidationError."""
    data = copy.deepcopy(raw_config_data)
    data["unknown_section"] = {"foo": "bar"}

    path = _write_temp_yaml(data)
    with pytest.raises(ValidationError) as exc_info:
        load_config(path)
    assert "unknown_section" in str(exc_info.value)
    path.unlink()


def test_unknown_primitive_rejected(raw_config_data: dict):
    """VAL-CFG-002: Unknown primitive in primitives section raises ValidationError."""
    data = copy.deepcopy(raw_config_data)
    data["primitives"]["nonexistent_detector"] = {
        "variant": "test",
        "status": "LOCKED",
        "params": {},
    }

    path = _write_temp_yaml(data)
    with pytest.raises(ValidationError) as exc_info:
        load_config(path)
    assert "nonexistent_detector" in str(exc_info.value)
    path.unlink()


# ─── VAL-CFG-003: Per-TF override resolution ─────────────────────────────

def test_swing_n_per_tf_resolution(locked_config: RAConfig):
    """VAL-CFG-003: swing_points.N resolves to 5 for 1m, 3 for 5m, 2 for 15m."""
    n_1m = resolve_per_tf(locked_config, "swing_points", "N", "1m")
    n_5m = resolve_per_tf(locked_config, "swing_points", "N", "5m")
    n_15m = resolve_per_tf(locked_config, "swing_points", "N", "15m")

    assert n_1m == 5
    assert n_5m == 3
    assert n_15m == 2


def test_swing_height_filter_per_tf(locked_config: RAConfig):
    """VAL-CFG-003: swing_points.height_filter_pips resolves per TF."""
    h_1m = resolve_per_tf(locked_config, "swing_points", "height_filter_pips", "1m")
    h_5m = resolve_per_tf(locked_config, "swing_points", "height_filter_pips", "5m")
    h_15m = resolve_per_tf(locked_config, "swing_points", "height_filter_pips", "15m")

    assert h_1m == 0.5
    assert h_5m == 3.0
    assert h_15m == 3.0


def test_fvg_floor_threshold_locked(locked_config: RAConfig):
    """VAL-CFG-003: fvg.floor_threshold_pips resolves to 0.5 (no per-TF)."""
    floor = resolve_per_tf(locked_config, "fvg", "floor_threshold_pips", "5m")
    assert floor == 0.5


def test_resolve_nonexistent_tf_raises(locked_config: RAConfig):
    """VAL-CFG-003: Resolving unknown TF raises ConfigError."""
    with pytest.raises(ConfigError, match="No per-TF value"):
        resolve_per_tf(locked_config, "swing_points", "N", "1H")


def test_resolve_nonexistent_param_raises(locked_config: RAConfig):
    """VAL-CFG-003: Resolving unknown param raises ConfigError."""
    with pytest.raises(ConfigError, match="Unknown param"):
        resolve_per_tf(locked_config, "swing_points", "nonexistent", "5m")


# ─── VAL-CFG-004: Schema version mismatch rejected ───────────────────────

def test_schema_version_mismatch_rejected(raw_config_data: dict):
    """VAL-CFG-004: Config with schema_version '99.0' raises error."""
    data = copy.deepcopy(raw_config_data)
    data["schema_version"] = "99.0"

    path = _write_temp_yaml(data)
    with pytest.raises(SchemaVersionError, match="99.0"):
        load_config(path)
    path.unlink()


def test_schema_version_none_rejected(raw_config_data: dict):
    """VAL-CFG-004: Config with missing schema_version raises error."""
    data = copy.deepcopy(raw_config_data)
    del data["schema_version"]

    path = _write_temp_yaml(data)
    with pytest.raises(SchemaVersionError):
        load_config(path)
    path.unlink()


# ─── VAL-CFG-005: Missing required param rejected ────────────────────────

def test_missing_fvg_floor_threshold_rejected(raw_config_data: dict):
    """VAL-CFG-005: Missing fvg.params.floor_threshold_pips raises ValidationError."""
    data = copy.deepcopy(raw_config_data)
    del data["primitives"]["fvg"]["params"]["floor_threshold_pips"]

    path = _write_temp_yaml(data)
    with pytest.raises(ValidationError) as exc_info:
        load_config(path)
    assert "floor_threshold_pips" in str(exc_info.value)
    path.unlink()


def test_missing_primitives_section_rejected(raw_config_data: dict):
    """VAL-CFG-005: Missing entire primitives section raises ValidationError."""
    data = copy.deepcopy(raw_config_data)
    del data["primitives"]

    path = _write_temp_yaml(data)
    with pytest.raises(ValidationError) as exc_info:
        load_config(path)
    assert "primitives" in str(exc_info.value)
    path.unlink()


def test_missing_displacement_atr_period_rejected(raw_config_data: dict):
    """VAL-CFG-005: Missing displacement.params.atr_period raises ValidationError."""
    data = copy.deepcopy(raw_config_data)
    del data["primitives"]["displacement"]["params"]["atr_period"]

    path = _write_temp_yaml(data)
    with pytest.raises(ValidationError) as exc_info:
        load_config(path)
    assert "atr_period" in str(exc_info.value)
    path.unlink()


# ─── VAL-CFG-006: Type mismatch rejected ─────────────────────────────────

def test_type_mismatch_string_for_float_rejected(raw_config_data: dict):
    """VAL-CFG-006: floor_threshold_pips.locked = 'abc' raises ValidationError."""
    data = copy.deepcopy(raw_config_data)
    data["primitives"]["fvg"]["params"]["floor_threshold_pips"]["locked"] = "abc"

    path = _write_temp_yaml(data)
    with pytest.raises(ValidationError) as exc_info:
        load_config(path)
    # Pydantic should catch the type error
    err_str = str(exc_info.value)
    assert "floor_threshold_pips" in err_str or "float" in err_str.lower()
    path.unlink()


def test_type_mismatch_string_for_int_rejected(raw_config_data: dict):
    """VAL-CFG-006: displacement.params.atr_period = 'not_a_number' raises ValidationError."""
    data = copy.deepcopy(raw_config_data)
    data["primitives"]["displacement"]["params"]["atr_period"] = "not_a_number"

    path = _write_temp_yaml(data)
    with pytest.raises(ValidationError) as exc_info:
        load_config(path)
    err_str = str(exc_info.value)
    assert "atr_period" in err_str or "int" in err_str.lower()
    path.unlink()


def test_type_mismatch_bool_for_list_rejected(raw_config_data: dict):
    """VAL-CFG-006: swing_points.params.strength_cap = 'high' raises ValidationError."""
    data = copy.deepcopy(raw_config_data)
    data["primitives"]["swing_points"]["params"]["strength_cap"] = "high"

    path = _write_temp_yaml(data)
    with pytest.raises(ValidationError) as exc_info:
        load_config(path)
    err_str = str(exc_info.value)
    assert "strength_cap" in err_str or "int" in err_str.lower()
    path.unlink()


# ─── Additional edge case tests ──────────────────────────────────────────

def test_file_not_found_raises():
    """Config loader raises ConfigError for missing file."""
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/path/config.yaml")


def test_invalid_yaml_raises():
    """Config loader raises ConfigError for invalid YAML."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    tmp.write("{{invalid: yaml: [[[")
    tmp.close()
    with pytest.raises(ConfigError, match="YAML parse error"):
        load_config(tmp.name)
    Path(tmp.name).unlink()


def test_non_dict_yaml_raises():
    """Config loader raises ConfigError for non-dict YAML."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    tmp.write("- just\n- a\n- list\n")
    tmp.close()
    with pytest.raises(ConfigError, match="must be a YAML mapping"):
        load_config(tmp.name)
    Path(tmp.name).unlink()
