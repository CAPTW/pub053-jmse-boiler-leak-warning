"""Drum-level instrumentation validation helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd


def validate_level_instrumentation(
    rows: list[dict[str, Any]] | pd.DataFrame,
    *,
    min_raw_comp_diff: float = 1e-5,
    min_truth_obs_diff: float = 1e-5,
) -> dict[str, Any]:
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    required = {
        "truth/level_true",
        "obs/drum_level",
        "obs/drum_level_dp_raw",
        "obs/drum_level_compensated",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        return {"passed": False, "reason": "missing_columns", "missing": missing}
    raw = pd.to_numeric(df["obs/drum_level_dp_raw"], errors="coerce")
    comp = pd.to_numeric(df["obs/drum_level_compensated"], errors="coerce")
    truth = pd.to_numeric(df["truth/level_true"], errors="coerce")
    obs = pd.to_numeric(df["obs/drum_level"], errors="coerce")
    raw_comp_span = float((raw - comp).abs().max(skipna=True) or 0.0)
    truth_obs_span = float((truth - obs).abs().max(skipna=True) or 0.0)
    passed = raw_comp_span >= float(min_raw_comp_diff) and truth_obs_span >= float(min_truth_obs_diff)
    return {
        "passed": bool(passed),
        "raw_comp_diff_max": raw_comp_span,
        "truth_obs_diff_max": truth_obs_span,
        "has_radar": "obs/drum_level_radar" in df.columns,
    }


__all__ = ["validate_level_instrumentation"]
