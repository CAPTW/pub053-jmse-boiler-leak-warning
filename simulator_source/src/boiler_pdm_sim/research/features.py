"""Feature extraction utilities for research and benchmark studies."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..validation.step_response import has_shrink_swell, check_shrink_swell_event_consistency


def _to_array(values: Any) -> np.ndarray:
    return np.asarray([float(v) for v in values], dtype=float)


def extract_research_features(
    *,
    level: list[float],
    pressure: list[float],
    steam_cmd: list[float],
    event_log: list[object] | None = None,
    dt: float,
) -> dict[str, Any]:
    """Return compact features used by benchmark/analysis notebooks."""
    level_arr = _to_array(level)
    pressure_arr = _to_array(pressure)

    len_min = min(level_arr.size, pressure_arr.size, len(steam_cmd))
    level_arr = level_arr[:len_min]
    pressure_arr = pressure_arr[:len_min]
    steam_arr = _to_array(steam_cmd)[:len_min]

    acc = check_shrink_swell_event_consistency(
        level_arr.tolist(),
        steam_arr.tolist(),
        dt=dt,
        event_log=event_log or [],
    )

    return {
        "n_points": int(len_min),
        "level_mean": float(np.nanmean(level_arr)),
        "level_std": float(np.nanstd(level_arr)),
        "pressure_mean": float(np.nanmean(pressure_arr)),
        "pressure_std": float(np.nanstd(pressure_arr)),
        "steam_cmd_std": float(np.nanstd(steam_arr)),
        "shrink_swell_detected": bool(has_shrink_swell(level_arr.tolist())),
        "shrink_swell_event_consistency": bool(acc.get("passed", False)),
        "shrink_swell_event_coverage": float(acc.get("coverage", 0.0)),
    }
