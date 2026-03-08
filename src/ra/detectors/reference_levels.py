"""Reference Levels detector — PDH/PDL, Midnight Open, Equilibrium, PWH/PWL.

Implements:
- PDH/PDL: Previous Day High/Low using 17:00 NY forex day boundary, wick-based
- Midnight Open: Open price of first bar at or after 00:00 NY
- Equilibrium: Midpoint of PDH and PDL
- PWH/PWL: Previous Week High/Low (max/min of all bars in dataset)

Reference: pipeline/preprocess_data_v2.py compute_pdh_pdl() function.
"""

import logging
from typing import Optional

import pandas as pd

from ra.engine.base import (
    Detection,
    DetectionResult,
    PrimitiveDetector,
    make_detection_id,
)

logger = logging.getLogger(__name__)

PIP = 0.0001


class ReferenceLevelDetector(PrimitiveDetector):
    """Deterministic computation of reference price levels.

    Computes per forex day:
      - day_high / day_low: session wick extremes
      - pdh / pdl: previous day's high/low (from day 2 onward)
      - midnight_open: open of first bar at/after 00:00 NY
      - equilibrium: midpoint of pdh and pdl (when available)

    Also computes dataset-level:
      - PWH (Previous Week High): max high across all bars
      - PWL (Previous Week Low): min low across all bars
    """

    primitive_name = "reference_levels"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Compute reference levels per forex day.

        Args:
            bars: 1m bar DataFrame with session tagging.
            params: reference_levels params from config.
            upstream: Not used (leaf detector).
            context: Optional context dict.

        Returns:
            DetectionResult with one Detection per forex day,
            plus dataset-level PWH/PWL in metadata.
        """
        forex_days = sorted(bars["forex_day"].unique())
        levels_by_day = {}

        for day in forex_days:
            day_bars = bars[bars["forex_day"] == day]
            if day_bars.empty:
                continue

            day_high = day_bars["high"].max()
            day_low = day_bars["low"].min()

            # Midnight open: first bar at or after 00:00 NY with hour < 17
            midnight_open = None
            ny_hours = day_bars["timestamp_ny"].dt.hour
            eligible = day_bars[(ny_hours >= 0) & (ny_hours < 17)]
            if not eligible.empty:
                midnight_open = eligible.iloc[0]["open"]
            elif not day_bars.empty:
                midnight_open = day_bars.iloc[0]["open"]

            levels_by_day[day] = {
                "day_high": day_high,
                "day_low": day_low,
                "midnight_open": midnight_open,
            }

        # Compute PDH/PDL (previous day's levels)
        days_sorted = sorted(levels_by_day.keys())
        for i, day in enumerate(days_sorted):
            if i > 0:
                prev_day = days_sorted[i - 1]
                levels_by_day[day]["pdh"] = levels_by_day[prev_day]["day_high"]
                levels_by_day[day]["pdl"] = levels_by_day[prev_day]["day_low"]

        # Compute PWH/PWL from all bars
        pwh = bars["high"].max()
        pwl = bars["low"].min()

        # Create Detection objects
        detections = []
        for day in days_sorted:
            lvl = levels_by_day[day]
            day_bars = bars[bars["forex_day"] == day]
            det_time = day_bars.iloc[0]["timestamp_ny"].to_pydatetime()

            det_id = make_detection_id(
                "reference_levels", "1m", det_time, "neutral"
            )

            # Equilibrium: midpoint of PDH and PDL (if available)
            equilibrium = None
            if "pdh" in lvl and "pdl" in lvl:
                equilibrium = (lvl["pdh"] + lvl["pdl"]) / 2

            detection = Detection(
                id=det_id,
                time=det_time,
                direction="neutral",
                type="reference_levels",
                price=lvl.get("pdh", lvl["day_high"]),
                properties={
                    **lvl,
                    "equilibrium": equilibrium,
                },
                tags={"forex_day": day},
            )
            detections.append(detection)

        return DetectionResult(
            primitive="reference_levels",
            variant="a8ra_v1",
            timeframe="1m",
            detections=detections,
            metadata={
                "total_days": len(detections),
                "pwh": pwh,
                "pwl": pwl,
                "levels_by_day": levels_by_day,
            },
            params_used=params,
        )

    def required_upstream(self) -> list[str]:
        """No upstream dependencies (leaf detector)."""
        return []
