"""Thermo compatibility wrappers."""

from .if97 import dhdP_approx, saturation_props
from .steam_props import get_saturation_props

__all__ = ["saturation_props", "dhdP_approx", "get_saturation_props"]
