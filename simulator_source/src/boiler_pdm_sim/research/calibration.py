"""Calibration helpers for runtime and analysis pipelines."""

from __future__ import annotations

from typing import Any

import numpy as np


def _to_array(values: list[float]) -> np.ndarray:
    return np.asarray([float(v) for v in values], dtype=float)


def calibrate_control_offsets(
    *,
    pressure: list[float],
    level: list[float],
    target_pressure: float = 10.0,
    target_level: float = 3.3,
) -> dict[str, float]:
    """Estimate simple additive offsets from target operating points."""
    p = _to_array(pressure)
    l = _to_array(level)
    n = min(p.size, l.size)
    if n == 0:
        return {"pressure_bias": 0.0, "level_bias": 0.0}

    p = p[:n]
    l = l[:n]
    return {
        "pressure_bias": float(np.nanmean(p) - float(target_pressure)),
        "level_bias": float(np.nanmean(l) - float(target_level)),
    }


def _extract_signal(rows: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    for row in rows:
        if key not in row:
            continue
        try:
            out.append(float(row[key]))
        except (TypeError, ValueError):
            continue
    return out


def _trim_warmup(values: list[float], warmup_fraction: float) -> list[float]:
    if not values:
        return []
    fraction = min(max(float(warmup_fraction), 0.0), 0.95)
    start = int(len(values) * fraction)
    trimmed = values[start:]
    return trimmed if trimmed else list(values)


def derive_nominal_offsets_from_rows(
    rows: list[dict[str, Any]],
    *,
    pressure_key: str,
    level_key: str,
    target_pressure: float,
    target_level: float,
    drum_length_m: float,
    warmup_fraction: float = 0.25,
    max_pressure_bias: float = 2.0,
    max_level_bias: float = 1.0,
) -> dict[str, Any]:
    pressure = _trim_warmup(_extract_signal(rows, pressure_key), warmup_fraction)
    level = _trim_warmup(_extract_signal(rows, level_key), warmup_fraction)
    usable = min(len(pressure), len(level))
    if usable == 0:
        return {
            "status": "insufficient_data",
            "pressure_bias": 0.0,
            "level_bias": 0.0,
            "nominal_pressure_bar_offset": 0.0,
            "nominal_level_fraction_offset": 0.0,
            "sample_counts": {
                "pressure": int(len(pressure)),
                "level": int(len(level)),
            },
        }

    offsets = calibrate_control_offsets(
        pressure=pressure[:usable],
        level=level[:usable],
        target_pressure=target_pressure,
        target_level=target_level,
    )
    pressure_bias = float(np.clip(offsets["pressure_bias"], -abs(max_pressure_bias), abs(max_pressure_bias)))
    level_bias = float(np.clip(offsets["level_bias"], -abs(max_level_bias), abs(max_level_bias)))
    length = max(1e-6, float(drum_length_m))
    return {
        "status": "ok",
        "pressure_bias": pressure_bias,
        "level_bias": level_bias,
        "nominal_pressure_bar_offset": float(-pressure_bias),
        "nominal_level_fraction_offset": float(-level_bias / length),
        "sample_counts": {
            "pressure": int(len(pressure)),
            "level": int(len(level)),
            "usable": int(usable),
        },
    }
