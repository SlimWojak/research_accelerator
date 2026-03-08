"""Config loader: parse YAML, validate via pydantic, resolve per-TF overrides.

Usage:
    from ra.config.loader import load_config

    config = load_config("configs/locked_baseline.yaml")
    # Access primitives:
    fvg_params = config.primitives.fvg.params
    # Resolve per-TF values:
    swing_n_5m = resolve_per_tf(config, "swing_points", "N", "5m")
"""

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ra.config.schema import SUPPORTED_SCHEMA_VERSION, RAConfig

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when config loading or validation fails."""


class SchemaVersionError(ConfigError):
    """Raised when config schema_version doesn't match engine."""


def load_config(config_path: str | Path) -> RAConfig:
    """Load and validate a YAML config file.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        Validated RAConfig instance.

    Raises:
        ConfigError: If file not found or YAML parse error.
        SchemaVersionError: If schema_version doesn't match engine.
        ValidationError: If config fails pydantic validation
            (unknown params, missing required, type mismatch).
    """
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Cannot read config file: {e}") from e

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML parse error: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError("Config must be a YAML mapping (dict)")

    # Check schema version BEFORE full validation
    config_version = data.get("schema_version")
    if config_version != SUPPORTED_SCHEMA_VERSION:
        raise SchemaVersionError(
            f"Schema version mismatch: config has '{config_version}', "
            f"engine expects '{SUPPORTED_SCHEMA_VERSION}'"
        )

    # Validate with pydantic — raises ValidationError on failure
    config = RAConfig.model_validate(data)

    logger.info("Config loaded and validated: %s", path)
    return config


def resolve_per_tf(
    config: RAConfig,
    primitive: str,
    param_name: str,
    timeframe: str,
) -> Any:
    """Resolve a parameter value for a specific timeframe.

    Handles the per_tf override pattern used in the config schema.
    Looks for param_name.per_tf.{timeframe}.locked first.

    Args:
        config: Validated RAConfig instance.
        primitive: Primitive name (e.g., "swing_points").
        param_name: Parameter name (e.g., "N").
        timeframe: Timeframe string (e.g., "5m").

    Returns:
        The resolved value for the given timeframe.

    Raises:
        ConfigError: If the parameter or timeframe is not found.
    """
    prim_config = getattr(config.primitives, primitive, None)
    if prim_config is None:
        raise ConfigError(f"Unknown primitive: {primitive}")

    params = prim_config.params
    if isinstance(params, dict):
        param_data = params.get(param_name)
    else:
        param_data = getattr(params, param_name, None)

    if param_data is None:
        raise ConfigError(
            f"Unknown param '{param_name}' for primitive '{primitive}'"
        )

    # Handle per_tf structure: {per_tf: {tf: {locked: val}}, sweep_range: ...}
    if isinstance(param_data, dict) and "per_tf" in param_data:
        per_tf = param_data["per_tf"]
        if timeframe not in per_tf:
            raise ConfigError(
                f"No per-TF value for '{param_name}' at timeframe '{timeframe}' "
                f"in primitive '{primitive}'. Available: {list(per_tf.keys())}"
            )
        tf_val = per_tf[timeframe]
        if isinstance(tf_val, dict) and "locked" in tf_val:
            return tf_val["locked"]
        return tf_val

    # Handle simple locked value: {locked: val, sweep_range: ...}
    if isinstance(param_data, dict) and "locked" in param_data:
        return param_data["locked"]

    # Handle pydantic model with locked attribute
    if hasattr(param_data, "locked"):
        return param_data.locked

    # Direct value (rare)
    return param_data


def get_locked_params(config: RAConfig, primitive: str) -> dict[str, Any]:
    """Extract all locked parameter values for a primitive.

    Resolves per-TF values into a flat dict structure suitable
    for passing to a detector's detect() method.

    Args:
        config: Validated RAConfig instance.
        primitive: Primitive name (e.g., "fvg").

    Returns:
        Dict of param_name -> value (with per_tf values nested as {tf: val}).
    """
    prim_config = getattr(config.primitives, primitive, None)
    if prim_config is None:
        raise ConfigError(f"Unknown primitive: {primitive}")

    params_obj = prim_config.params
    if isinstance(params_obj, dict):
        return _extract_locked_from_dict(params_obj)

    # For pydantic models, dump to dict first
    params_dict = params_obj.model_dump()
    return _extract_locked_from_dict(params_dict)


def _extract_locked_from_dict(d: dict) -> dict:
    """Recursively extract locked values from a param dict."""
    result = {}
    for key, value in d.items():
        if isinstance(value, dict):
            if "locked" in value and "per_tf" not in value:
                result[key] = value["locked"]
            elif "per_tf" in value:
                result[key] = {
                    tf: (v["locked"] if isinstance(v, dict) and "locked" in v else v)
                    for tf, v in value["per_tf"].items()
                }
            else:
                result[key] = _extract_locked_from_dict(value)
        else:
            result[key] = value
    return result
