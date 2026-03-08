"""Dynamic parameter extraction from pydantic config models.

Replaces the hardcoded extract_locked_params_for_cascade() with generic
extraction that reads from the config model dynamically.

CRITICAL: Locked mode must produce EXACTLY the same dict structure as the
current hardcoded function — detectors expect specific formats including
{locked: value} wrappers.

Functions:
    extract_params(config, primitive, mode='locked'|'sweep')
        - locked: returns the exact param dict for cascade engine consumption
        - sweep: returns sweep_range lists where defined, locked values elsewhere
    extract_sweep_combos(config, primitive, params=None)
        - generates Cartesian product of sweep_range values
        - selective param sweep via params=['ltf.atr_multiplier']
"""

import copy
import itertools
import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from ra.config.schema import RAConfig

logger = logging.getLogger(__name__)


class ParamExtractionError(Exception):
    """Raised when parameter extraction fails."""


# All valid primitive names in the config
_VALID_PRIMITIVES = frozenset({
    "fvg", "ifvg", "bpr", "swing_points", "displacement",
    "session_liquidity", "asia_range", "mss", "order_block",
    "liquidity_sweep", "htf_liquidity", "ote", "reference_levels",
    "equal_hl",
})

# Extra top-level config keys (outside .params) to include for specific
# primitives. Detectors expect these keys in the param dict.
_EXTRA_TOPLEVEL_KEYS: dict[str, list[str]] = {
    "displacement": ["quality_grades", "evaluation_order"],
}

# Primitives that return empty dict in locked mode regardless of config.
# These are virtual nodes or stubs handled by their parent detector.
_EMPTY_LOCKED_PRIMITIVES = frozenset({"ifvg", "bpr", "equal_hl"})

# Keys to strip from locked extraction. These are config-only metadata
# that are NOT part of the detector param contract.
_STRIP_KEYS: dict[str, set[str]] = {
    "asia_range": {"thresholds"},
}

# Param paths where {locked: value} wrapper must be preserved because
# the detector code does `.get("locked", default)` on these.
_PRESERVE_LOCKED_WRAPPERS: set[tuple[str, str]] = {
    # (primitive, dot_path_ending_at_parent.key)
    ("session_liquidity", "four_gate_model.efficiency_threshold"),
    ("session_liquidity", "four_gate_model.mid_cross_min"),
    ("session_liquidity", "four_gate_model.balance_score_min"),
    ("liquidity_sweep", "rejection_wick_pct"),
}

# Keys to strip from nested dicts during locked extraction.
# These are metadata annotations, not runtime params.
_NESTED_STRIP_KEYS = {"note"}


def _load_raw_yaml(config_path: str | Path) -> dict:
    """Load raw YAML data to preserve original types (int vs float)."""
    path = Path(config_path)
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_raw_primitive_data(config: RAConfig, primitive: str) -> dict:
    """Get the raw YAML data for a primitive's section.

    Uses the config's source path to reload raw YAML, preserving
    original types (int vs float, etc.).

    Falls back to pydantic model_dump() if the source path is unavailable.
    """
    # Try to find config path. RAConfig doesn't store it, so we try
    # the default locked_baseline.yaml path.
    # In practice, configs are always loaded from a file, and the
    # raw data is needed to preserve types.
    prim_config = getattr(config.primitives, primitive, None)
    if prim_config is None:
        return {}

    # Use pydantic model_dump as base, since we can't reliably get
    # the raw YAML path from the config object alone.
    prim_dict = prim_config.model_dump()
    return prim_dict


def extract_params(
    config: RAConfig,
    primitive: str,
    mode: str = "locked",
) -> dict[str, Any]:
    """Extract parameters for a primitive from config.

    Args:
        config: Validated RAConfig instance.
        primitive: Primitive name (e.g., "fvg", "displacement").
        mode: 'locked' for production values, 'sweep' for sweep_range lists.

    Returns:
        Dict of parameters. In locked mode, this is identical to
        extract_locked_params_for_cascade(config)[primitive].
        In sweep mode, sweep_range lists replace locked values where defined.

    Raises:
        ParamExtractionError: If primitive is unknown or mode is invalid.
    """
    if primitive not in _VALID_PRIMITIVES:
        raise ParamExtractionError(
            f"Unknown primitive '{primitive}'. "
            f"Valid primitives: {sorted(_VALID_PRIMITIVES)}"
        )

    if mode not in ("locked", "sweep"):
        raise ParamExtractionError(
            f"Invalid mode '{mode}'. Must be 'locked' or 'sweep'."
        )

    prim_config = getattr(config.primitives, primitive, None)
    if prim_config is None:
        raise ParamExtractionError(
            f"Primitive '{primitive}' not found in config.primitives"
        )

    if mode == "locked":
        return _extract_locked(config, primitive, prim_config)
    else:
        return _extract_sweep(config, primitive, prim_config)


def _extract_locked(
    config: RAConfig,
    primitive: str,
    prim_config: Any,
) -> dict[str, Any]:
    """Extract locked parameter values, preserving exact dict structure.

    This must produce EXACTLY the same output as the hardcoded
    extract_locked_params_for_cascade() for backward compatibility.
    """
    # Virtual/stub primitives return empty dict
    if primitive in _EMPTY_LOCKED_PRIMITIVES:
        return {}

    # Get params dict
    params_obj = prim_config.params
    if hasattr(params_obj, "model_dump"):
        raw_params = params_obj.model_dump()
    elif isinstance(params_obj, dict):
        raw_params = dict(params_obj)
    else:
        raw_params = {}

    # Apply the locked extraction logic
    result = _resolve_locked_recursive(raw_params, primitive, "")

    # Strip primitive-specific keys that aren't part of detector contract
    for key in _STRIP_KEYS.get(primitive, set()):
        result.pop(key, None)

    # Add extra top-level keys from the primitive config
    if primitive in _EXTRA_TOPLEVEL_KEYS:
        prim_dict = prim_config.model_dump()
        for key in _EXTRA_TOPLEVEL_KEYS[primitive]:
            if key in prim_dict:
                result[key] = prim_dict[key]

    return result


def _resolve_locked_recursive(
    d: dict, primitive: str, path: str
) -> dict:
    """Recursively resolve locked values from a param dict.

    Rules (matching hardcoded extract_locked_params_for_cascade behavior):
    1. {locked: val, sweep_range: [...]} → val (simple locked param)
       EXCEPT for params in _PRESERVE_LOCKED_WRAPPERS → {locked: val}
    2. {per_tf: {tf: {locked: val}}, sweep_range: ...} → {tf: val}
    3. {per_tf: {tf: val}} without locked → {per_tf: {tf: val}}
    4. Nested dicts without locked/per_tf → recurse
    5. Scalars/lists → keep as-is
    """
    result: dict[str, Any] = {}

    for key, value in d.items():
        full_path = f"{path}.{key}" if path else key

        if not isinstance(value, dict):
            # Scalar or list - keep as-is
            result[key] = value
            continue

        # Check for per_tf structure with locked sub-values
        if "per_tf" in value and _has_locked_in_per_tf(value["per_tf"]):
            # {per_tf: {tf: {locked: val}}, sweep_range: ...} → {tf: val}
            result[key] = {
                tf: (v["locked"] if isinstance(v, dict) and "locked" in v else v)
                for tf, v in value["per_tf"].items()
            }
            continue

        # Check for per_tf structure WITHOUT locked sub-values
        # These keep the {per_tf: {tf: val}} wrapper
        if "per_tf" in value and not _has_locked_in_per_tf(value["per_tf"]):
            result[key] = {"per_tf": value["per_tf"]}
            continue

        # Check for simple {locked: val, sweep_range: [...]} or {locked: val}
        if "locked" in value and "per_tf" not in value:
            if (primitive, full_path) in _PRESERVE_LOCKED_WRAPPERS:
                # Preserve the wrapper but strip sweep_range and options
                result[key] = {"locked": value["locked"]}
            else:
                # Unwrap to just the value
                result[key] = value["locked"]
            continue

        # Nested dict without locked or per_tf → recurse
        nested = _resolve_locked_recursive(value, primitive, full_path)
        # Strip metadata keys (like 'note') from nested results
        result[key] = {
            k: v for k, v in nested.items() if k not in _NESTED_STRIP_KEYS
        }

    return result


def _has_locked_in_per_tf(per_tf: dict) -> bool:
    """Check if per_tf values contain {locked: val} wrappers."""
    for val in per_tf.values():
        if isinstance(val, dict) and "locked" in val:
            return True
    return False


def _extract_sweep(
    config: RAConfig,
    primitive: str,
    prim_config: Any,
) -> dict[str, Any]:
    """Extract sweep_range values where defined, locked values elsewhere.

    Returns a dict where:
    - Params with sweep_range: the sweep_range list replaces the locked value
    - Params without sweep_range: the locked value is used
    - Per-TF sweep ranges are returned as {tf: [range]} dicts
    """
    # Virtual/stub primitives - still check for sweep_range in config
    if primitive in _EMPTY_LOCKED_PRIMITIVES and primitive != "bpr":
        return {}

    params_obj = prim_config.params

    # Convert pydantic model to dict
    if hasattr(params_obj, "model_dump"):
        raw_params = params_obj.model_dump()
    elif isinstance(params_obj, dict):
        raw_params = dict(params_obj)
    else:
        return {}

    result = _resolve_sweep_recursive(raw_params, primitive)

    # Strip primitive-specific non-detector keys
    for key in _STRIP_KEYS.get(primitive, set()):
        result.pop(key, None)

    # Add extra top-level keys in sweep mode too (at locked values)
    if primitive in _EXTRA_TOPLEVEL_KEYS:
        prim_dict = prim_config.model_dump()
        for key in _EXTRA_TOPLEVEL_KEYS[primitive]:
            if key in prim_dict:
                result[key] = prim_dict[key]

    return result


def _resolve_sweep_recursive(d: dict, primitive: str) -> dict:
    """Recursively extract sweep_range values where defined."""
    result: dict[str, Any] = {}

    for key, value in d.items():
        if not isinstance(value, dict):
            result[key] = value
            continue

        # {locked: val, sweep_range: [...]} → sweep_range list
        if "sweep_range" in value and "per_tf" not in value:
            result[key] = value["sweep_range"]
            continue

        # {per_tf: {...}, sweep_range: {...}} or {per_tf: {...}, sweep_range: [...]}
        if "per_tf" in value and "sweep_range" in value:
            sweep = value["sweep_range"]
            if isinstance(sweep, dict):
                # Per-TF sweep ranges: {tf: [range]}
                result[key] = sweep
            else:
                # Global sweep range shared across TFs
                result[key] = sweep
            continue

        # {per_tf: {...}} without sweep_range → resolve locked values
        if "per_tf" in value and "sweep_range" not in value:
            if _has_locked_in_per_tf(value["per_tf"]):
                result[key] = {
                    tf: (v["locked"] if isinstance(v, dict) and "locked" in v else v)
                    for tf, v in value["per_tf"].items()
                }
            else:
                result[key] = {"per_tf": value["per_tf"]}
            continue

        # {locked: val} without sweep_range → locked value
        if "locked" in value and "sweep_range" not in value:
            result[key] = value["locked"]
            continue

        # Nested dict → recurse
        result[key] = _resolve_sweep_recursive(value, primitive)

    return result


def extract_sweep_combos(
    config: RAConfig,
    primitive: str,
    params: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Generate Cartesian product of sweep_range values.

    Args:
        config: Validated RAConfig instance.
        primitive: Primitive name.
        params: Optional list of dot-separated param paths to sweep.
            e.g., ['ltf.atr_multiplier'] to only vary that param.
            If None, sweeps ALL params with sweep_range.

    Returns:
        List of complete param dicts, each representing one sweep combination.
        Each dict is suitable for passing to CascadeEngine.

    Raises:
        ParamExtractionError: If primitive is unknown.
    """
    if primitive not in _VALID_PRIMITIVES:
        raise ParamExtractionError(
            f"Unknown primitive '{primitive}'. "
            f"Valid primitives: {sorted(_VALID_PRIMITIVES)}"
        )

    # Get the locked baseline as the template
    locked = extract_params(config, primitive, mode="locked")

    # Get sweep mode to discover sweep_range values
    sweep = extract_params(config, primitive, mode="sweep")

    # Find all sweepable param paths and their ranges
    sweep_paths = _find_sweep_ranges(locked, sweep, prefix="")

    # Filter to requested params if selective sweep
    if params is not None:
        sweep_paths = {
            path: values
            for path, values in sweep_paths.items()
            if path in params
        }

    # If no sweepable params, return a single combo with locked values
    if not sweep_paths:
        return [copy.deepcopy(locked)]

    # Generate Cartesian product
    paths = sorted(sweep_paths.keys())
    value_lists = [sweep_paths[p] for p in paths]
    combos = []

    for values in itertools.product(*value_lists):
        combo = copy.deepcopy(locked)
        for path, value in zip(paths, values):
            _set_nested(combo, path, value)
        combos.append(combo)

    return combos


def _find_sweep_ranges(
    locked: dict, sweep: dict, prefix: str
) -> dict[str, list]:
    """Find all sweepable param paths by comparing locked and sweep dicts.

    Returns dict of path -> list of sweep values.
    A param is sweepable if its sweep value is a list (in sweep mode)
    while its locked value is not.
    """
    result: dict[str, list] = {}

    for key in sweep:
        if key not in locked:
            # Key only in sweep mode (shouldn't normally happen)
            continue
        locked_val = locked[key]
        sweep_val = sweep[key]
        full_path = f"{prefix}.{key}" if prefix else key

        if isinstance(sweep_val, list) and not isinstance(locked_val, list):
            # Sweepable scalar param
            result[full_path] = sweep_val
        elif isinstance(sweep_val, dict) and isinstance(locked_val, dict):
            # Check if it's a per-TF sweep range dict (values are lists)
            if _is_per_tf_sweep_range(sweep_val, locked_val):
                result[full_path] = _expand_per_tf_sweep(sweep_val)
            else:
                # Recurse into nested dict
                sub = _find_sweep_ranges(locked_val, sweep_val, full_path)
                result.update(sub)

    return result


def _is_per_tf_sweep_range(sweep_val: dict, locked_val: dict) -> bool:
    """Check if a sweep dict represents per-TF sweep ranges.

    Per-TF sweep ranges look like {tf: [values]} where locked is {tf: scalar}.
    Keys must be timeframe-like (e.g., '1m', '5m', '1H') to distinguish from
    nested param dicts (e.g., 'ltf', 'htf') that may also contain lists.
    """
    # All keys in the sweep dict must be timeframe-like for this to be a per-TF sweep
    tf_pattern = {"1m", "5m", "15m", "1H", "4H", "1D", "W1", "MN"}
    if not sweep_val:
        return False
    # At least one key must be a timeframe key with a list value
    has_tf_list = False
    for k, v in sweep_val.items():
        if k not in tf_pattern:
            return False  # Non-TF key found → not a per-TF sweep range
        if isinstance(v, list):
            has_tf_list = True
    return has_tf_list


def _expand_per_tf_sweep(per_tf_ranges: dict) -> list[dict]:
    """Expand per-TF sweep ranges into a list of {tf: value} dicts.

    Given {1m: [0.5, 1.0], 5m: [2.0, 3.0]}, produces the Cartesian product:
    [{1m: 0.5, 5m: 2.0}, {1m: 0.5, 5m: 3.0}, ...]
    """
    tfs = sorted(per_tf_ranges.keys())
    ranges = [
        per_tf_ranges[tf] if isinstance(per_tf_ranges[tf], list)
        else [per_tf_ranges[tf]]
        for tf in tfs
    ]

    combos = []
    for values in itertools.product(*ranges):
        combos.append({tf: val for tf, val in zip(tfs, values)})
    return combos


def _set_nested(d: dict, path: str, value: Any) -> None:
    """Set a value in a nested dict using dot-separated path.

    If the value at the path is currently a {locked: val} wrapper,
    replace just the locked value to preserve the wrapper structure.
    """
    parts = path.split(".")
    current = d
    for part in parts[:-1]:
        current = current[part]
    last_key = parts[-1]

    # Preserve {locked: val} wrapper structure
    if isinstance(current.get(last_key), dict) and "locked" in current[last_key]:
        current[last_key]["locked"] = value
    else:
        current[last_key] = value
