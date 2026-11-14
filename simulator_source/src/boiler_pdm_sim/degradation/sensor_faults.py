"""Sensor fault helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np


def apply_sensor_drift(
    params: dict[str, Any],
    severity: float,
    targets: list[str] | tuple[str, ...],
    drift_per_hour: float,
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    p = dict(params)
    p.setdefault("degradation", {})
    severity = float(max(0.0, min(1.0, severity)))
    drift_per_hour = float(drift_per_hour)
    p["degradation"]["sensor_drift_severity"] = severity
    p.setdefault("sensors", {})
    sensors = deepcopy(p["sensors"])

    for target in targets:
        if not isinstance(target, str) or target not in sensors:
            continue
        cfg = dict(sensors[target]) if isinstance(sensors[target], dict) else {}
        base_drift = float(cfg.get("drift_per_hour", 0.0))
        cfg["drift_per_hour"] = base_drift + np.sign(drift_per_hour) * (abs(drift_per_hour) * (severity ** 1.2))
        if isinstance(overrides, dict):
            for key in (
                "reference_leg_temp_shift_C",
                "impulse_line_plugging",
                "bad_calibration_bias_m",
                "freeze_after_s",
            ):
                if key in overrides:
                    cfg[key] = float(overrides[key]) * severity
            if "wet_leg_density_scale" in overrides:
                mismatch = float(overrides["wet_leg_density_scale"]) - 1.0
                cfg["wet_leg_density_scale"] = 1.0 + mismatch * severity
            if "reverse_action" in overrides:
                cfg["reverse_action"] = bool(overrides["reverse_action"]) and severity >= float(overrides.get("reverse_action_threshold", 0.5))
        sensors[target] = cfg

    p["sensors"] = sensors
    return p
