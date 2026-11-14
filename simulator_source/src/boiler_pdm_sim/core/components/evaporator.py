"""Evaporator placeholder utilities."""

from __future__ import annotations


def boil_rate(q_evap_W: float, h_fg: float, npsh: float = 1.0) -> float:
    """Convert heat to boilup mass flow."""
    return max(0.0, q_evap_W * npsh / max(h_fg, 1.0))
