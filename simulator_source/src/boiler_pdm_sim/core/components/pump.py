"""Pump placeholder for v1."""

from __future__ import annotations


def commanded_flow(u: float, max_flow: float, wear_factor: float = 0.0) -> float:
    return float(max_flow * u * max(0.0, 1.0 - wear_factor))
