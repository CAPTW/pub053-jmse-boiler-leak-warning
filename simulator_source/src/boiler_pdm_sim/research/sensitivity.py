"""Sensitivity analysis utilities for Phase 1.5."""

from __future__ import annotations

from typing import Any, Callable, Mapping

import numpy as np


def compute_local_signal_sensitivity(
    signal: list[float],
    *,
    epsilon: float = 1e-3,
    window: int = 10,
) -> dict[str, float]:
    """Estimate local sensitivity metrics from a single signal."""
    if not signal:
        return {"status": "empty", "mean_sensitivity": 0.0, "max_sensitivity": 0.0}

    arr = np.asarray([float(v) for v in signal], dtype=float)
    if arr.size < 3:
        return {"status": "insufficient_data", "mean_sensitivity": 0.0, "max_sensitivity": 0.0}

    grad = np.abs(np.gradient(arr))
    if window > 1:
        kernel = np.ones(window) / window
        grad = np.convolve(grad, kernel, mode="same")
    scale = max(epsilon, float(np.nanmax(np.abs(arr))) * 1e-3)
    sensitivity = float(np.nanmean(np.abs(grad) / scale))
    return {
        "status": "ok",
        "mean_sensitivity": float(sensitivity),
        "max_sensitivity": float(np.nanmax(np.abs(grad) / scale)),
        "scale": float(scale),
    }


def estimate_parameter_sensitivity(
    simulate_fn: Callable[[Mapping[str, float]], list[dict]],
    *,
    base_params: Mapping[str, float],
    perturbations: Mapping[str, float],
    signal_key: str = "obs/drum_level",
    metric_fn: Callable[[list[float], list[float]], float] | None = None,
) -> dict[str, Any]:
    """Finite-difference sensitivity by resimulating each perturbed parameter set."""
    metric_fn = metric_fn or _rmse
    base_params = dict(base_params)
    base_rows = simulate_fn(dict(base_params))
    base_signal = _extract_signal(base_rows, signal_key)
    if not base_signal:
        return {"status": "empty", "scores": {}}

    baseline_metric = float(metric_fn(base_signal, base_signal))
    scores: dict[str, float] = {}
    for pname, rel_step in perturbations.items():
        step = float(rel_step)
        if step <= 0.0:
            continue

        forward = dict(base_params)
        forward[pname] = float(base_params[pname]) * (1.0 + step)
        forward_rows = simulate_fn(forward)
        forward_signal = _extract_signal(forward_rows, signal_key)

        backward = dict(base_params)
        backward[pname] = float(base_params[pname]) * (1.0 - step)
        backward_rows = simulate_fn(backward)
        backward_signal = _extract_signal(backward_rows, signal_key)

        if not forward_signal or not backward_signal:
            continue

        fp = metric_fn(base_signal, forward_signal)
        fm = metric_fn(base_signal, backward_signal)
        denom = max(1e-9, 2.0 * abs(base_params[pname]) * step)
        scores[str(pname)] = float((abs(fp - baseline_metric) + abs(fm - baseline_metric)) / denom)

    if not scores:
        return {"status": "failed", "scores": {}}
    return {"status": "ok", "scores": scores, "baseline_metric": baseline_metric, "signal_key": signal_key}


def _extract_signal(rows: list[dict], key: str) -> list[float]:
    out: list[float] = []
    for row in rows:
        if key not in row:
            continue
        try:
            out.append(float(row[key]))
        except (TypeError, ValueError):
            continue
    return out


def _rmse(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    a_arr = np.asarray(a[:n], dtype=float)
    b_arr = np.asarray(b[:n], dtype=float)
    return float(np.sqrt(np.mean((a_arr - b_arr) ** 2)))

