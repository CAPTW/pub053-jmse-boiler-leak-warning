"""Baseline profile utilities for Phase 1.5."""

from __future__ import annotations

from typing import Any

import numpy as np

DEFAULT_BASELINE_CHANNELS = (
    "obs/drum_level",
    "obs/drum_pressure",
    "obs/steam_flow",
    "obs/drum_temp_sh",
    "meta/final_control_fuel_cmd",
    "label/fault_severity",
)


def _to_series(rows: list[dict], channel: str) -> np.ndarray:
    values: list[float] = []
    for row in rows:
        if channel not in row or row[channel] is None:
            continue
        try:
            values.append(float(row[channel]))
        except (TypeError, ValueError):
            continue
    if not values:
        return np.array([], dtype=float)
    return np.asarray(values, dtype=float)


def build_baseline_profile(
    rows: list[dict],
    *,
    channels: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    channel_list = tuple(channels) if channels is not None else DEFAULT_BASELINE_CHANNELS
    profile: dict[str, Any] = {
        "status": "ok",
        "n_rows": int(len(rows)),
        "channels": {},
    }

    if not rows:
        profile["status"] = "empty"
        return profile

    for channel in channel_list:
        arr = _to_series(rows, channel)
        if arr.size == 0:
            profile["channels"][channel] = {"status": "missing"}
            continue
        profile["channels"][channel] = {
            "status": "ok",
            "n": int(arr.size),
            "mean": float(np.nanmean(arr)),
            "std": float(np.nanstd(arr)),
            "min": float(np.nanmin(arr)),
            "max": float(np.nanmax(arr)),
            "p25": float(np.nanpercentile(arr, 25.0)),
            "p75": float(np.nanpercentile(arr, 75.0)),
            "median": float(np.nanmedian(arr)),
        }

    return profile


def compare_to_baseline(
    rows: list[dict],
    baseline: dict[str, Any],
    *,
    channels: tuple[str, ...] | list[str] | None = None,
    abs_tol: float = 0.2,
) -> dict[str, Any]:
    """Compute channel-wise drift score against a baseline profile."""
    channel_list = tuple(channels) if channels is not None else DEFAULT_BASELINE_CHANNELS
    current = build_baseline_profile(rows, channels=channel_list)
    result: dict[str, Any] = {
        "ok": True,
        "max_norm_delta": 0.0,
        "channel_deltas": {},
    }

    if current.get("status") == "empty" or baseline.get("status") == "empty":
        return {"ok": False, "max_norm_delta": float("inf"), "channel_deltas": {}}

    max_delta = 0.0
    for channel in channel_list:
        b = baseline.get("channels", {}).get(channel, {})
        c = current.get("channels", {}).get(channel, {})
        if b.get("status") != "ok" or c.get("status") != "ok":
            continue
        b_mean = float(b.get("mean", 0.0))
        c_mean = float(c.get("mean", 0.0))
        base_scale = float(max(1e-6, abs(b_mean)))
        delta = abs(c_mean - b_mean) / base_scale
        result["channel_deltas"][channel] = float(delta)
        if delta > max_delta:
            max_delta = delta
        if delta > abs_tol:
            result["ok"] = False

    result["max_norm_delta"] = float(max_delta)
    return result

