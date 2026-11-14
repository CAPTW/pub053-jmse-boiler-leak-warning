"""Benchmark helpers for Phase 5 research utilities."""

from __future__ import annotations

from typing import Any

from .calibration import calibrate_control_offsets
from .baseline import build_baseline_profile
from .identifiability import compute_identifiability
from .sensitivity import compute_local_signal_sensitivity
from .features import extract_research_features


def _select_col(rows: list[dict], key: str) -> list[float]:
    return [float(r[key]) for r in rows if key in r and r[key] is not None]


def run_phase5_benchmark(rows: list[dict], *, dt: float) -> dict[str, Any]:
    """Run a lightweight benchmark on an in-memory simulation result."""
    level = _select_col(rows, "obs/drum_level")
    pressure = _select_col(rows, "obs/drum_pressure")
    steam_cmd = _select_col(rows, "meta/steam_demand_cmd")
    event_log = [r.get("label/event_log", []) for r in rows]

    feature = extract_research_features(
        level=level,
        pressure=pressure,
        steam_cmd=steam_cmd,
        event_log=event_log,
        dt=dt,
    )
    offset = calibrate_control_offsets(pressure=pressure, level=level)
    return {
        "features": feature,
        "calibration": offset,
    }


def run_phase15_benchmark(rows: list[dict], *, dt: float) -> dict[str, Any]:
    """Run baseline/identify/sensitivity convenience checks."""
    baseline = build_baseline_profile(rows)
    identify = compute_identifiability(rows)
    sensitivity = compute_local_signal_sensitivity(
        [float(r) for r in [row.get("obs/drum_level") for row in rows] if r is not None],
        epsilon=1e-3,
        window=max(5, int(dt * 10)) if dt > 0 else 10,
    )
    return {
        "baseline": baseline,
        "identifiability": identify,
        "sensitivity": sensitivity,
    }
