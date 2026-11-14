"""Valve stiction fault helper."""

from __future__ import annotations


def apply_stiction(params: dict, severity: float, deadband: float, gain: float) -> dict:
    p = dict(params)
    p.setdefault("degradation", {})
    p["degradation"]["valve_stiction"] = float(min(1.0, gain * severity))
    p["degradation"]["valve_stiction_deadband"] = float(deadband)
    return p
