"""Pump wear fault helpers."""

from __future__ import annotations

from typing import Any


def apply_pump_wear(params: dict[str, Any], severity: float, max_wear: float) -> dict[str, Any]:
    p = dict(params)
    p.setdefault("degradation", {})
    sev = float(max(0.0, min(1.0, severity)))
    max_wear = float(max(0.0, min(1.0, max_wear)))
    wear = max_wear * (sev ** 1.15)
    p["degradation"]["pump_wear"] = wear
    p["degradation"]["pump_wear_severity"] = sev
    return p
