"""Tube leak fault helpers."""

from __future__ import annotations


def apply_tube_leak(params: dict, severity: float, coeff: float) -> dict:
    p = dict(params)
    p.setdefault("degradation", {})
    p["degradation"]["tube_leak_coeff"] = float(max(0.0, coeff * severity))
    return p
