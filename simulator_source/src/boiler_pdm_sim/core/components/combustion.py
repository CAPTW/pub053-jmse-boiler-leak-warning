"""Combustion/heat input relation."""

from __future__ import annotations


def heat_release_MW(eta: float, qmax_MW: float, fuel_cmd: float) -> float:
    return float(qmax_MW * eta * max(0.0, min(1.0, fuel_cmd)))
