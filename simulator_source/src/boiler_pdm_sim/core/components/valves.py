"""Valve algebraic flow relations."""

from __future__ import annotations

import numpy as np


def valve_flow(Cv: float, opening: float, dp: float) -> float:
    """Very small quasi-steady flow model."""
    return float(Cv * max(opening, 0.0) * np.sqrt(max(dp, 0.0)))


def valve_flow_from_pressure(Cv: float, opening: float, p_upstream: float, p_downstream: float = 1.0) -> float:
    """Flow from pressure drop with automatic clipping of non-positive differential pressure."""
    return valve_flow(Cv, opening, max(float(p_upstream) - float(p_downstream), 1e-6))


def feedwater_valve_flow(Cv: float, opening: float, p_sys: float) -> float:
    # Feedwater pressure maintained high on suction side, so pressure drop proxy is system pressure.
    return valve_flow(Cv, opening, max(p_sys, 1e-6) + 1.0)
