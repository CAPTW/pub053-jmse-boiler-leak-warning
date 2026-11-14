"""Steady-state map utilities."""

from __future__ import annotations

from typing import Any

import pandas as pd


def build_steady_state_map(
    rows: list[dict[str, Any]] | pd.DataFrame,
    *,
    load_key: str = "meta/load_cmd",
    pressure_key: str = "truth/drum_pressure",
    level_key: str = "truth/drum_level",
    bins: int = 5,
) -> dict[str, Any]:
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if df.empty or load_key not in df or pressure_key not in df or level_key not in df:
        return {"passed": False, "reason": "missing_columns", "n_bins": 0, "map": []}
    work = df[[load_key, pressure_key, level_key]].dropna().copy()
    if work.empty:
        return {"passed": False, "reason": "empty", "n_bins": 0, "map": []}
    work["load_bin"] = pd.cut(work[load_key], bins=max(2, int(bins)), duplicates="drop")
    grouped = (
        work.groupby("load_bin", observed=True)
        .agg(load_mean=(load_key, "mean"), pressure_mean=(pressure_key, "mean"), level_mean=(level_key, "mean"))
        .reset_index(drop=True)
    )
    monotonic_pressure = bool(grouped["pressure_mean"].is_monotonic_increasing or grouped["pressure_mean"].is_monotonic_decreasing)
    return {
        "passed": bool(len(grouped) >= 2),
        "n_bins": int(len(grouped)),
        "pressure_monotonic": monotonic_pressure,
        "map": grouped.to_dict(orient="records"),
    }


def validate_steady_state_map(rows: list[dict[str, Any]] | pd.DataFrame, **kwargs: Any) -> dict[str, Any]:
    report = build_steady_state_map(rows, **kwargs)
    report["passed"] = bool(report.get("passed", False) and report.get("n_bins", 0) >= 2)
    return report


__all__ = ["build_steady_state_map", "validate_steady_state_map"]
