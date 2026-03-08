"""Equal HL detector — DEFERRED stub.

This module is a placeholder for future Equal High/Low detection.
It raises NotImplementedError when detect() is called, but is
registered in the registry so the dependency graph accounts for it.

Status: DEFERRED — build when EQL/EQH detection is finalized.
"""

import logging
from typing import Optional

import pandas as pd

from ra.engine.base import (
    DetectionResult,
    PrimitiveDetector,
)

logger = logging.getLogger(__name__)


class EqualHLDetector(PrimitiveDetector):
    """DEFERRED stub for Equal High/Low detection.

    Raises NotImplementedError on detect(). Registered in registry
    so cascade engine can handle it gracefully.
    """

    primitive_name = "equal_hl"
    variant_name = "a8ra_v1"
    version = "1.0.0"

    def detect(
        self,
        bars: pd.DataFrame,
        params: dict,
        upstream: Optional[dict[str, DetectionResult]] = None,
        context: Optional[dict] = None,
    ) -> DetectionResult:
        """DEFERRED — raises NotImplementedError.

        Equal HL detection is not yet implemented. This stub exists
        so the cascade engine's dependency graph is complete.
        """
        raise NotImplementedError(
            "EqualHLDetector is DEFERRED. "
            "Equal High/Low detection is not yet implemented."
        )

    def required_upstream(self) -> list[str]:
        """Depends on swing_points for pivot input."""
        return ["swing_points"]
