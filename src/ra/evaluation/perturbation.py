"""Config perturbation engine for parameter search.

Reads a search-space definition (YAML/JSON) specifying per-parameter:
  - numeric: base, min, max, step (optional). Perturbation ±10-20% of base,
    clamped to [min, max], snapped to step grid.
  - categorical: options list. Random selection from options.
  - boolean: base value. Random toggle.

Reproducible with seed: uses random.Random instance (not global state).

Usage:
    from ra.evaluation.perturbation import perturb_config, load_search_space

    space = load_search_space("search_space.yaml")
    perturbed = perturb_config(space, seed=42)
    # perturbed is a dict: {"param.path": perturbed_value, ...}
"""

import json
import logging
import math
import random
from pathlib import Path
from typing import Any, Optional, Union

import yaml

logger = logging.getLogger(__name__)


class PerturbationError(Exception):
    """Raised when perturbation fails."""


def load_search_space(path: Union[str, Path]) -> dict[str, Any]:
    """Load search-space definition from YAML or JSON file.

    Args:
        path: Path to YAML or JSON file with parameter definitions.

    Returns:
        Search-space dict with 'parameters' key mapping param paths
        to their type, bounds, and options.

    Raises:
        PerturbationError: If file not found or parse error.
    """
    path = Path(path)
    if not path.exists():
        raise PerturbationError(f"Search-space file not found: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise PerturbationError(f"Cannot read search-space file: {e}") from e

    # Try YAML first (superset of JSON)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        # Fall back to JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise PerturbationError(
                f"Cannot parse search-space file {path}: {e}"
            ) from e

    if not isinstance(data, dict):
        raise PerturbationError("Search-space must be a YAML/JSON mapping (dict)")

    if "parameters" not in data:
        raise PerturbationError("Search-space must have a 'parameters' key")

    return data


def _snap_to_step(value: float, min_val: float, step: float) -> float:
    """Snap a value to the nearest step grid point.

    Grid is defined by: min_val, min_val+step, min_val+2*step, ...

    Args:
        value: Raw value to snap.
        min_val: Start of the grid.
        step: Grid spacing.

    Returns:
        Nearest grid point.
    """
    if step <= 0:
        return value
    steps_from_min = round((value - min_val) / step)
    snapped = min_val + steps_from_min * step
    return snapped


def _perturb_numeric(
    rng: random.Random,
    base: float,
    min_val: float,
    max_val: float,
    step: Optional[float] = None,
) -> float:
    """Perturb a numeric parameter.

    Perturbation magnitude: ±10-20% of base value.
    Result clamped to [min_val, max_val].
    If step is provided, snapped to step grid.

    Args:
        rng: Random instance for reproducibility.
        base: Base value.
        min_val: Minimum allowed value.
        max_val: Maximum allowed value.
        step: Optional step size for grid snapping.

    Returns:
        Perturbed value.
    """
    # Generate perturbation factor: uniform in [-0.20, -0.10] ∪ [0.10, 0.20]
    # This ensures at least 10% perturbation magnitude
    magnitude = rng.uniform(0.10, 0.20)
    direction = rng.choice([-1, 1])
    factor = direction * magnitude

    perturbed = base * (1.0 + factor)

    # Clamp to bounds
    perturbed = max(min_val, min(max_val, perturbed))

    # Snap to step grid if provided
    if step is not None and step > 0:
        perturbed = _snap_to_step(perturbed, min_val, step)
        # Re-clamp after snapping (edge case: snapping pushed beyond bounds)
        perturbed = max(min_val, min(max_val, perturbed))

    return perturbed


def _perturb_categorical(
    rng: random.Random,
    options: list[Any],
    base: Any = None,
) -> Any:
    """Perturb a categorical parameter by selecting from options.

    Args:
        rng: Random instance.
        options: List of valid values.
        base: Current base value (unused, included for API consistency).

    Returns:
        Randomly selected option.
    """
    return rng.choice(options)


def _perturb_boolean(rng: random.Random, base: bool = True) -> bool:
    """Perturb a boolean parameter.

    Args:
        rng: Random instance.
        base: Current base value.

    Returns:
        Randomly selected True or False.
    """
    return rng.choice([True, False])


def perturb_config(
    search_space: dict[str, Any],
    seed: Optional[int] = None,
) -> dict[str, Any]:
    """Perturb all parameters in the search space.

    Each parameter is perturbed independently based on its type:
    - numeric: ±10-20% of base, clamped, snapped to step
    - categorical: random selection from options
    - boolean: random True/False

    Args:
        search_space: Search-space dict with 'parameters' key.
        seed: Optional seed for reproducibility.

    Returns:
        Dict mapping param paths to perturbed values.
    """
    rng = random.Random(seed)
    parameters = search_space.get("parameters", {})
    result: dict[str, Any] = {}

    for param_path in sorted(parameters.keys()):
        param_def = parameters[param_path]
        param_type = param_def.get("type", "numeric")

        if param_type == "numeric":
            base = float(param_def["base"])
            min_val = float(param_def.get("min", base * 0.5))
            max_val = float(param_def.get("max", base * 2.0))
            step = param_def.get("step")
            if step is not None:
                step = float(step)
            result[param_path] = _perturb_numeric(rng, base, min_val, max_val, step)

        elif param_type == "categorical":
            options = param_def["options"]
            base = param_def.get("base")
            result[param_path] = _perturb_categorical(rng, options, base)

        elif param_type == "boolean":
            base = param_def.get("base", True)
            result[param_path] = _perturb_boolean(rng, base)

        else:
            logger.warning("Unknown param type '%s' for %s, skipping", param_type, param_path)

    return result


def apply_perturbation_to_config(
    config_dict: dict[str, Any],
    perturbation: dict[str, Any],
) -> dict[str, Any]:
    """Apply perturbed parameter values to a config dict.

    Takes a base config dict and applies the perturbed values at their
    dot-separated paths. Creates a deep copy of the config before modifying.

    Args:
        config_dict: Base config as a nested dict.
        perturbation: Dict mapping dot-separated param paths to new values.

    Returns:
        New config dict with perturbed values applied.
    """
    import copy
    result = copy.deepcopy(config_dict)

    for param_path, value in perturbation.items():
        _set_nested(result, param_path, value)

    return result


def _set_nested(d: dict, path: str, value: Any) -> None:
    """Set a value at a dot-separated path in a nested dict.

    Creates intermediate dicts if needed.

    Args:
        d: Dict to modify in-place.
        path: Dot-separated path (e.g., "displacement.ltf.atr_multiplier").
        value: Value to set.
    """
    parts = path.split(".")
    current = d
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def compute_param_deltas(
    perturbation: dict[str, Any],
    search_space: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Compute per-parameter deltas from base values.

    Args:
        perturbation: Dict of perturbed param values.
        search_space: Search-space definition with base values.

    Returns:
        Dict mapping param paths to delta info:
        {base, value, delta, pct_change} for numeric,
        {base, value} for categorical/boolean.
    """
    parameters = search_space.get("parameters", {})
    deltas: dict[str, dict[str, Any]] = {}

    for param_path, perturbed_value in perturbation.items():
        param_def = parameters.get(param_path, {})
        base = param_def.get("base")
        param_type = param_def.get("type", "numeric")

        if param_type == "numeric" and base is not None:
            base_val = float(base)
            delta = perturbed_value - base_val
            pct_change = (delta / base_val * 100) if base_val != 0 else 0.0
            deltas[param_path] = {
                "base": base_val,
                "value": perturbed_value,
                "delta": round(delta, 6),
                "pct_change": round(pct_change, 2),
            }
        else:
            deltas[param_path] = {
                "base": base,
                "value": perturbed_value,
            }

    return deltas
