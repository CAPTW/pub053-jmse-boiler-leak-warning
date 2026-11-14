"""Validation helpers for acceptance thresholds and regression gates."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np


def _coerce_float(value: Any) -> float | None:
    try:
        value_f = float(value)
    except Exception:
        return None
    return value_f


def _safe_max_abs_delta(a: float, b: float) -> float:
    return abs(a - b)


def _safe_relative_delta(a: float, b: float) -> float:
    denom = abs(a)
    if not np.isfinite(denom) or denom == 0.0:
        return float("inf") if abs(b) > 1e-12 else 0.0
    return abs(a - b) / denom


def acceptance_thresholds(metrics: dict[str, Any], cfg: object) -> dict[str, Any]:
    """Evaluate scalar metrics against acceptance thresholds.

    Config formats:
      - {"metric_name": 12.0}  -> max threshold
      - {"metric_name": {"max": 12.0, "min": 0.5}}
    """
    raw = cfg if isinstance(cfg, dict) else {}
    result: dict[str, Any] = {"passed": True, "failures": [], "details": {}}
    failures: list[str] = []

    for metric_name, rule in raw.items():
        value = _coerce_float(metrics.get(str(metric_name)))
        if value is None:
            failures.append(f"{metric_name}=missing")
            result["details"][str(metric_name)] = {"value": None, "ok": False}
            continue

        if isinstance(rule, (int, float)):
            max_val = _coerce_float(rule)
            ok = float(value) <= float(max_val) if max_val is not None else False
            result["details"][str(metric_name)] = {
                "value": float(value),
                "max": max_val,
                "ok": bool(ok),
            }
            if not ok:
                failures.append(f"{metric_name}={value} > max={max_val}")
            continue

        if not isinstance(rule, dict):
            failures.append(f"{metric_name}=invalid_rule")
            result["details"][str(metric_name)] = {"value": float(value), "ok": False}
            continue

        max_val = _coerce_float(rule.get("max"))
        min_val = _coerce_float(rule.get("min"))
        ok = True
        if max_val is not None:
            ok = ok and (value <= max_val)
        if min_val is not None:
            ok = ok and (value >= min_val)
        result["details"][str(metric_name)] = {"value": float(value), "min": min_val, "max": max_val, "ok": bool(ok)}
        if not ok:
            if max_val is not None and value > max_val:
                failures.append(f"{metric_name}={value} > max={max_val}")
            if min_val is not None and value < min_val:
                failures.append(f"{metric_name}={value} < min={min_val}")

    result["passed"] = len(failures) == 0
    result["failures"] = failures
    return result


def summarize_rows(
    rows: list[dict[str, Any]],
    *,
    channels: list[str] | tuple[str, ...] | None = None,
    use_nan_safe: bool = True,
) -> dict[str, Any]:
    import pandas as pd

    if not rows:
        return {"n_rows": 0}
    df = pd.DataFrame(rows)
    if channels is None:
        channels = [
            "truth/drum_pressure",
            "truth/drum_level",
            "obs/drum_pressure",
            "obs/drum_level",
            "truth/steam_flow",
            "obs/steam_flow",
        ]
    summary: dict[str, float | int] = {"n_rows": int(len(df))}

    for channel in channels:
        if channel not in df.columns:
            continue
        vals = pd.to_numeric(df[channel], errors="coerce").to_numpy(dtype=float)
        if vals.size == 0:
            continue
        if use_nan_safe:
            vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            continue
        summary[f"{channel}_mean"] = float(np.mean(vals))
        summary[f"{channel}_std"] = float(np.std(vals))
        summary[f"{channel}_min"] = float(np.min(vals))
        summary[f"{channel}_max"] = float(np.max(vals))
    return summary


def seed_sweep_battery(
    run_fn: Any,
    cfg: dict[str, Any],
    seeds: list[int] | tuple[int, ...],
    *,
    summary_channels: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Execute the same config across multiple seeds and summarize signatures."""
    summaries: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    base_cfg = deepcopy(cfg)

    for seed in seeds:
        seed_cfg = deepcopy(base_cfg)
        sim_cfg = seed_cfg.setdefault("sim", {})
        sim_cfg["seed"] = int(seed)
        try:
            rows = run_fn(seed_cfg)
        except Exception as exc:
            failures.append(f"seed={seed} failed: {exc}")
            continue
        summaries[str(seed)] = summarize_rows(rows, channels=summary_channels)

    passed = len(failures) == 0 and len(summaries) == len(seeds)
    return {
        "passed": bool(passed),
        "failures": failures,
        "seeds": [int(s) for s in seeds],
        "n_runs": int(len(summaries)),
        "summaries": summaries,
    }


def regression_gate(reference: dict[str, Any], candidate: dict[str, Any], tolerances: dict[str, Any]) -> dict[str, Any]:
    """Compare two signatures with absolute/relative tolerances."""
    details: dict[str, Any] = {}
    failures: list[str] = []

    for metric, tol in tolerances.items():
        tol_rule = {}
        if isinstance(tol, dict):
            tol_rule = tol
        elif isinstance(tol, (int, float)):
            tol_rule = {"max_abs": float(tol)}

        if not isinstance(metric, str):
            continue
        ref = _coerce_float(reference.get(metric))
        cur = _coerce_float(candidate.get(metric))
        if ref is None or cur is None:
            failures.append(f"{metric}=missing")
            details[metric] = {"ref": reference.get(metric), "cur": candidate.get(metric), "ok": False}
            continue

        max_abs = _coerce_float(tol_rule.get("max_abs"))
        max_rel = _coerce_float(tol_rule.get("max_rel"))
        if max_abs is None:
            max_abs = float("inf")
        if max_rel is None:
            max_rel = float("inf")
        abs_delta = _safe_max_abs_delta(ref, cur)
        rel_delta = _safe_relative_delta(ref, cur)
        ok = (abs_delta <= max_abs) and (rel_delta <= max_rel)
        details[metric] = {
            "ref": ref,
            "cur": cur,
            "abs_delta": abs_delta,
            "rel_delta": rel_delta,
            "max_abs": max_abs,
            "max_rel": max_rel,
            "ok": bool(ok),
        }
        if not ok:
            failures.append(f"{metric} delta={abs_delta}/{rel_delta} > max({max_abs},{max_rel})")

    return {"passed": len(failures) == 0, "failures": failures, "details": details}

