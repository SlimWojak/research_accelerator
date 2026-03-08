"""Asia Range detector — session range computation with parametric classification.

Implements:
- Asia session range in pips per forex day
- Parametric binary classification (TIGHT/WIDE) at multiple threshold breakpoints
- Max cap from config

Reference: pipeline/preprocess_data_v2.py compute_asia_ranges() function.
"""

import logging
from typing import Optional

import pandas as pd

from ra.detectors._common import PIP
from ra.engine.base import (
    Detection,
    DetectionResult,
    PrimitiveDetector,
    make_detection_id,
)

logger = logging.getLogger(__name__)

# Fallback thresholds if config doesn't specify (matches baseline)
_DEFAULT_THRESHOLDS = [12, 15, 18, 20, 25, 30]


class AsiaRangeDetector(PrimitiveDetector):
    """Asia session range detector with parametric binary classification.

    Computes the high-low range of the Asia session (19:00-00:00 NY)
    for each forex day. Classifies as TIGHT or WIDE at multiple
    configurable threshold breakpoints.
    """

    primitive_name = "asia_range"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Compute Asia range per forex day.

        Args:
            bars: 1m bar DataFrame with session tagging.
            params: asia_range params from config.
            upstream: Not used (leaf detector).
            context: Optional context with thresholds override.

        Returns:
            DetectionResult with one Detection per forex day.
        """
        max_cap = params.get("max_cap_pips", 30)

        # Read thresholds from config; fall back to defaults for compatibility
        thresholds = params.get("thresholds", _DEFAULT_THRESHOLDS)

        # Filter to asia session bars
        asia_bars = bars[bars["session"] == "asia"]
        if asia_bars.empty:
            return DetectionResult(
                primitive="asia_range",
                variant="a8ra_v1",
                timeframe="1m",
                detections=[],
                metadata={"total_days": 0, "thresholds": thresholds},
                params_used=params,
            )

        forex_days = sorted(asia_bars["forex_day"].unique())
        detections = []

        for day in forex_days:
            day_asia = asia_bars[asia_bars["forex_day"] == day]
            if day_asia.empty:
                continue

            h = day_asia["high"].max()
            l = day_asia["low"].min()
            range_pips = round((h - l) / PIP, 1)

            # Parametric binary classification at each threshold
            classifications = {
                str(t): ("TIGHT" if range_pips < t else "WIDE")
                for t in thresholds
            }

            start_time = day_asia.iloc[0]["timestamp_ny"].strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
            end_time = day_asia.iloc[-1]["timestamp_ny"].strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

            range_data = {
                "forex_day": day,
                "high": h,
                "low": l,
                "range_pips": range_pips,
                "bar_count": len(day_asia),
                "start_time": start_time,
                "end_time": end_time,
                "classifications": classifications,
            }

            det_time = day_asia.iloc[0]["timestamp_ny"].to_pydatetime()
            det_id = make_detection_id("asia_range", "1m", det_time, "neutral")

            detection = Detection(
                id=det_id,
                time=det_time,
                direction="neutral",
                type="asia_range",
                price=(h + l) / 2,
                properties=range_data,
                tags={
                    "forex_day": day,
                    "range_pips": range_pips,
                },
            )
            detections.append(detection)

        return DetectionResult(
            primitive="asia_range",
            variant="a8ra_v1",
            timeframe="1m",
            detections=detections,
            metadata={
                "total_days": len(detections),
                "thresholds": thresholds,
            },
            params_used=params,
        )

    def required_upstream(self) -> list[str]:
        """No upstream dependencies (leaf detector)."""
        return []
