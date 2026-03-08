"""Base classes for the RA detection engine.

Defines:
- Detection: a single detected event with deterministic ID
- DetectionResult: collection of detections from one module run
- PrimitiveDetector: ABC that all detector modules implement
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd


def make_detection_id(
    primitive: str,
    timeframe: str,
    timestamp_ny: datetime,
    direction: str,
) -> str:
    """Generate a deterministic detection ID.

    Format: {primitive}_{tf}_{timestamp_ny}_{direction}
    Example: fvg_5m_2024-01-08T09:10:00_bull

    The direction is abbreviated: bullish->bull, bearish->bear,
    high->high, low->low, neutral->neutral.
    """
    dir_map = {"bullish": "bull", "bearish": "bear"}
    dir_short = dir_map.get(direction, direction)
    ts_str = timestamp_ny.strftime("%Y-%m-%dT%H:%M:%S")
    return f"{primitive}_{timeframe}_{ts_str}_{dir_short}"


@dataclass
class Detection:
    """A single detected event (e.g., one FVG, one swing point).

    Attributes:
        id: Deterministic ID following {primitive}_{tf}_{timestamp_ny}_{direction}.
        time: Detection timestamp in NY timezone.
        direction: "bullish", "bearish", "high", "low", "neutral", etc.
        type: Primitive-specific subtype (e.g., "fvg", "ifvg", "bpr").
        price: Primary price level for this detection.
        properties: Primitive-specific data (gap_pips, height_pips, etc.).
        tags: Contextual tags (session, kill_zone, forex_day, etc.).
        upstream_refs: IDs of consumed upstream detections.
    """

    id: str
    time: datetime
    direction: str
    type: str
    price: float
    properties: dict = field(default_factory=dict)
    tags: dict = field(default_factory=dict)
    upstream_refs: list[str] = field(default_factory=list)


@dataclass
class DetectionResult:
    """Result from running one detector on one timeframe.

    Attributes:
        primitive: Primitive name (e.g., "fvg", "displacement").
        variant: Variant name (e.g., "a8ra_v1").
        timeframe: Timeframe string (e.g., "5m").
        detections: List of Detection objects.
        metadata: Counts, distributions, algo-specific summary data.
        params_used: Echo of the config params used for provenance.
    """

    primitive: str
    variant: str
    timeframe: str
    detections: list[Detection] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    params_used: dict = field(default_factory=dict)


class PrimitiveDetector(ABC):
    """Abstract base class for all detector modules.

    Every detector MUST:
    - Set primitive_name, variant_name, version as class attributes
    - Implement detect() returning DetectionResult
    - Implement required_upstream() returning list of upstream primitive names
    - Be deterministic: same inputs -> same outputs
    """

    primitive_name: str
    variant_name: str
    version: str = "1.0.0"

    @abstractmethod
    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, "DetectionResult"]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Run detection on the given bars with the given params.

        Args:
            bars: DataFrame with integer index and bar contract columns.
            params: Config params for this primitive (from YAML).
            upstream: Dict of upstream DetectionResults keyed by primitive name.
            context: Optional context dict (timeframe, forex_day, etc.).

        Returns:
            DetectionResult with all detections found.
        """
        ...

    @abstractmethod
    def required_upstream(self) -> list[str]:
        """Declare upstream primitive dependencies.

        Returns:
            List of primitive names this detector depends on.
            Empty list for leaf nodes (no upstream).
        """
        ...
