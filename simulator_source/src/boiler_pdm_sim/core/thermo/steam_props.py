"""Steam property compatibility helpers."""

from __future__ import annotations

from .if97 import saturation_props


def get_saturation_props(pressure_bar: float) -> dict[str, float]:
    return saturation_props(float(pressure_bar))


__all__ = ["get_saturation_props", "saturation_props"]
