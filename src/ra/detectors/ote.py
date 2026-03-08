"""OTE (Optimal Trade Entry) detector — fib retracement zones anchored to MSS events.

Implements:
- One fib retracement zone per MSS event
- Three levels: 0.618 (lower), 0.705 (sweet_spot), 0.79 (upper)
- Fib levels computed from the MSS "dealing range" (swing-to-break)
- Kill zone gate: zones only flagged actionable in LOKZ/NYOKZ
- Zones outside kill zones exist but are not actionable

Reference: build_plan/02_MODULE_MANIFEST.md OTE section,
           build_plan/01_RUNTIME_CONFIG_SCHEMA.yaml ote section.
"""

import logging
from typing import Optional

import pandas as pd

from ra.detectors._common import map_session
from ra.engine.base import (
    Detection,
    DetectionResult,
    PrimitiveDetector,
    make_detection_id,
)

logger = logging.getLogger(__name__)

# Kill zone sessions for the actionable gate
_KILL_ZONES = {"lokz", "nyokz"}


class OTEDetector(PrimitiveDetector):
    """OTE detector — fib retracement zones anchored to MSS dealing ranges.

    For each MSS event, computes a retracement zone with three fib levels:
    - 0.618 (lower boundary)
    - 0.705 (sweet spot / optimal entry)
    - 0.79 (upper boundary)

    The dealing range is from the broken swing price to the MSS break bar price.
    For a bullish MSS (breaks above swing high), the retracement zone is
    BELOW the break — trader expects price to dip into the zone before continuing.
    For a bearish MSS (breaks below swing low), the retracement zone is
    ABOVE the break — trader expects price to rally into the zone before continuing.

    Kill zone gate: zones are only flagged `actionable` if the MSS occurred
    during LOKZ (02:00-05:00 NY) or NYOKZ (07:00-10:00 NY).
    """

    primitive_name = "ote"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """Run OTE detection on MSS events.

        Args:
            bars: Bar DataFrame (used for session context).
            params: OTE params from config (fib_levels, kill_zone_gate).
            upstream: Must contain "mss" DetectionResult.
            context: Optional context with "timeframe".

        Returns:
            DetectionResult with one Detection per MSS event.
        """
        tf = (context or {}).get("timeframe", "5m")

        if upstream is None or "mss" not in upstream:
            logger.warning("OTE detector requires 'mss' upstream — returning empty result")
            return DetectionResult(
                primitive="ote",
                variant="a8ra_v1",
                timeframe=tf,
                detections=[],
                metadata={"total_count": 0},
                params_used=params,
            )

        mss_result = upstream["mss"]
        fib_config = params.get("fib_levels", {})
        fib_lower = fib_config.get("lower", 0.618)
        fib_sweet = fib_config.get("sweet_spot", 0.705)
        fib_upper = fib_config.get("upper", 0.79)
        kill_zone_gate = params.get("kill_zone_gate", True)

        detections = []

        for mss_det in mss_result.detections:
            mss_props = mss_det.properties
            mss_direction = mss_props.get("direction", "").upper()
            mss_bar_index = mss_props.get("bar_index")
            mss_time = mss_props.get("time", "")
            broken_swing = mss_props.get("broken_swing", {})
            swing_price = broken_swing.get("price")
            session = mss_props.get("session", "")
            forex_day = mss_props.get("forex_day", "")

            if swing_price is None or mss_bar_index is None:
                continue

            # The dealing range is from the broken swing to the break bar
            # For bullish MSS: swing is a high, break closes above it
            # For bearish MSS: swing is a low, break closes below it
            # The MSS detection's price is the broken swing price
            break_price = mss_det.price  # swing price that was broken

            # We need the actual break bar close to define the dealing range
            # The MSS bar_index is the bar that broke the swing
            if mss_bar_index < len(bars):
                if mss_direction == "BULLISH":
                    # Bullish: broke above swing high
                    # Dealing range: from the swing low before to the break high
                    # But per spec: the dealing range is from broken swing to break bar
                    # Swing was a high that got broken → the OTE zone is a retracement
                    # from the swing origin to the break point
                    break_bar_price = bars.iloc[mss_bar_index]["close"]

                    # For bullish MSS, the swing origin is the low preceding the swing high
                    # Actually the v0.5 spec says: dealing range = swing_price to break_close
                    # The retracement is measured from the dealing range
                    range_high = break_bar_price
                    range_low = swing_price

                    # But wait - this can be inverted for bullish MSS
                    # A bullish MSS breaks ABOVE a swing high
                    # The dealing range is from a lower point to the break
                    # The OTE zone is where price retraces DOWN into

                    # Let's use the dealing range as the distance from swing to close
                    dealing_range = abs(range_high - range_low)
                    if dealing_range < 1e-10:
                        continue

                    # Fib retracement from the high back down
                    # 0.618 = 61.8% retracement = closer to the swing (lower boundary)
                    # 0.79  = 79% retracement = deeper retracement (upper boundary)
                    # For bullish: zone is below break, prices go DOWN from high
                    level_lower = range_high - fib_lower * dealing_range
                    level_sweet = range_high - fib_sweet * dealing_range
                    level_upper = range_high - fib_upper * dealing_range

                elif mss_direction == "BEARISH":
                    # Bearish: broke below swing low
                    break_bar_price = bars.iloc[mss_bar_index]["close"]

                    range_high = swing_price
                    range_low = break_bar_price

                    dealing_range = abs(range_high - range_low)
                    if dealing_range < 1e-10:
                        continue

                    # Fib retracement from the low back up
                    # For bearish: zone is above break, prices go UP from low
                    level_lower = range_low + fib_lower * dealing_range
                    level_sweet = range_low + fib_sweet * dealing_range
                    level_upper = range_low + fib_upper * dealing_range

                else:
                    continue
            else:
                continue

            # Kill zone gate
            mapped_session = map_session(session)
            actionable = mapped_session in _KILL_ZONES if kill_zone_gate else True

            dir_lower = mss_direction.lower()
            det_time = pd.Timestamp(mss_time)
            det_id = make_detection_id(
                primitive="ote",
                timeframe=tf,
                timestamp_ny=det_time,
                direction=dir_lower,
            )

            fib_levels = {
                "lower": round(level_lower, 6),
                "sweet_spot": round(level_sweet, 6),
                "upper": round(level_upper, 6),
            }

            detection = Detection(
                id=det_id,
                time=det_time,
                direction=dir_lower,
                type="ote_zone",
                price=round(level_sweet, 6),  # sweet spot as the primary price
                properties={
                    "fib_levels": fib_levels,
                    "swing_price": swing_price,
                    "break_price": break_bar_price,
                    "dealing_range": round(dealing_range, 6),
                    "mss_bar_index": mss_bar_index,
                    "mss_direction": dir_lower,
                    "mss_time": mss_time,
                    "mss_break_type": mss_props.get("break_type", ""),
                    "actionable": actionable,
                    "session": mapped_session,
                    "forex_day": forex_day,
                    "tf": tf,
                },
                tags={
                    "session": mapped_session,
                    "forex_day": forex_day,
                },
                upstream_refs=[mss_det.id],
            )
            detections.append(detection)

        # Build metadata
        actionable_count = sum(
            1 for d in detections if d.properties.get("actionable")
        )
        metadata = {
            "total_count": len(detections),
            "actionable_count": actionable_count,
            "non_actionable_count": len(detections) - actionable_count,
        }

        return DetectionResult(
            primitive="ote",
            variant="a8ra_v1",
            timeframe=tf,
            detections=detections,
            metadata=metadata,
            params_used=params,
        )

    def required_upstream(self) -> list[str]:
        """OTE depends on MSS events."""
        return ["mss"]
