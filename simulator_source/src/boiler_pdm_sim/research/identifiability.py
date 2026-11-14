"""Fault separability / identifiability helper functions."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np

DEFAULT_CHANNELS = (
    "obs/drum_pressure",
    "obs/drum_level",
    "obs/steam_flow",
    "obs/drum_temp_sh",
    "obs/feedwater_flow",
)


def _to_signal(rows: list[dict], channel: str) -> np.ndarray:
    values: list[float] = []
    for row in rows:
        if channel not in row or row[channel] is None:
            continue
        try:
            values.append(float(row[channel]))
        except (TypeError, ValueError):
            continue
    return np.asarray(values, dtype=float)


def _fault_key(row: dict, key: str) -> str:
    value = row.get(key, "none")
    if isinstance(value, list):
        value = value[0] if value else "none"
    if value is None:
        return "none"
    value = str(value).strip()
    return value if value else "none"


def compute_identifiability(
    rows: list[dict],
    *,
    fault_key: str = "label/fault_type",
    channels: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    channel_list = tuple(channels) if channels is not None else DEFAULT_CHANNELS
    if not rows:
        return {"status": "empty", "scores": []}

    if len(channel_list) == 0:
        return {"status": "empty", "scores": []}

    faults = [_fault_key(row, fault_key) for row in rows]
    counter = Counter(faults)
    baseline = counter.most_common(1)[0][0]
    if baseline == "none" and len(counter) == 1:
        return {"status": "single_class", "scores": []}

    scores: list[dict[str, Any]] = []

    for channel in channel_list:
        overall = _to_signal(rows, channel)
        if overall.size == 0:
            continue

        baseline_vals = _to_signal(
            [row for row, fault in zip(rows, faults, strict=False) if _fault_key(row, fault_key) == baseline],
            channel,
        )
        if baseline_vals.size == 0:
            continue
        base_mean = float(np.nanmean(baseline_vals))
        base_std = float(np.nanstd(baseline_vals) or 1e-9)

        best_delta = 0.0
        best_fault = ""
        for fault in sorted(counter):
            if fault == baseline:
                continue
            fault_vals = _to_signal(
                [row for row, f in zip(rows, faults, strict=False) if f == fault],
                channel,
            )
            if fault_vals.size == 0:
                continue
            delta = abs(float(np.nanmean(fault_vals)) - base_mean) / (base_std + 1e-9)
            if delta > best_delta:
                best_delta = delta
                best_fault = fault

        scores.append(
            {
                "channel": channel,
                "best_fault": best_fault or "none",
                "effect_size": float(best_delta),
                "baseline_n": int(baseline_vals.size),
                "fault_classes": int(len(counter)),
            }
        )

    scores.sort(key=lambda item: item["effect_size"], reverse=True)
    return {
        "status": "ok",
        "baseline_fault": baseline,
        "n_rows": int(len(rows)),
        "n_fault_classes": int(len(counter)),
        "fault_counts": dict(counter),
        "scores": scores,
    }


def top_identifiable_features(ident: dict[str, Any], *, top_k: int = 3, min_effect: float = 0.0) -> list[str]:
    scores = ident.get("scores", [])
    if not isinstance(scores, list):
        return []
    out: list[str] = []
    for item in scores:
        if not isinstance(item, dict):
            continue
        effect = float(item.get("effect_size", 0.0))
        if effect < min_effect:
            continue
        out.append(str(item.get("channel")))
        if len(out) >= top_k:
            break
    return out

