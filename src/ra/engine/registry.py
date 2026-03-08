"""Module registry for detector lookup by primitive_name + variant_name.

Usage:
    from ra.engine.registry import Registry

    registry = Registry()
    registry.register(FVGDetector)
    detector = registry.get("fvg", "a8ra_v1")
"""

import logging
from typing import Optional

from ra.engine.base import PrimitiveDetector

logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """Raised when registry operations fail."""


class Registry:
    """Registry for PrimitiveDetector modules.

    Detectors are registered by (primitive_name, variant_name) tuple.
    Lookup returns an instance of the registered detector class.
    """

    def __init__(self) -> None:
        self._registry: dict[tuple[str, str], type[PrimitiveDetector]] = {}

    def register(self, detector_cls: type[PrimitiveDetector]) -> None:
        """Register a detector class.

        Args:
            detector_cls: A PrimitiveDetector subclass with primitive_name
                and variant_name class attributes.

        Raises:
            RegistryError: If the detector class is missing required attributes
                or a detector with the same key is already registered.
        """
        if not hasattr(detector_cls, "primitive_name") or not hasattr(
            detector_cls, "variant_name"
        ):
            raise RegistryError(
                f"Detector class {detector_cls.__name__} must define "
                "'primitive_name' and 'variant_name' class attributes."
            )

        key = (detector_cls.primitive_name, detector_cls.variant_name)

        if key in self._registry:
            raise RegistryError(
                f"Detector already registered: "
                f"primitive={key[0]}, variant={key[1]} "
                f"(existing: {self._registry[key].__name__}, "
                f"new: {detector_cls.__name__})"
            )

        self._registry[key] = detector_cls
        logger.debug(
            "Registered detector: %s/%s -> %s",
            key[0],
            key[1],
            detector_cls.__name__,
        )

    def get(
        self,
        primitive_name: str,
        variant_name: str = "a8ra_v1",
    ) -> PrimitiveDetector:
        """Look up and instantiate a detector by primitive + variant.

        Args:
            primitive_name: The primitive name (e.g., "fvg").
            variant_name: The variant name (default "a8ra_v1").

        Returns:
            An instance of the registered PrimitiveDetector subclass.

        Raises:
            RegistryError: If no detector is registered for the given key.
        """
        key = (primitive_name, variant_name)
        if key not in self._registry:
            available = [
                f"{k[0]}/{k[1]}" for k in sorted(self._registry.keys())
            ]
            raise RegistryError(
                f"No detector registered for primitive={primitive_name}, "
                f"variant={variant_name}. "
                f"Available: {available}"
            )
        return self._registry[key]()

    def list_registered(self) -> list[tuple[str, str]]:
        """Return all registered (primitive_name, variant_name) keys."""
        return sorted(self._registry.keys())

    def has(
        self,
        primitive_name: str,
        variant_name: str = "a8ra_v1",
    ) -> bool:
        """Check if a detector is registered for the given key."""
        return (primitive_name, variant_name) in self._registry

    def __len__(self) -> int:
        return len(self._registry)

    def __repr__(self) -> str:
        entries = ", ".join(
            f"{k[0]}/{k[1]}" for k in sorted(self._registry.keys())
        )
        return f"Registry([{entries}])"
