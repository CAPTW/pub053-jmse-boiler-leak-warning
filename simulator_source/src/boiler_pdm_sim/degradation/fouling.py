"""Fouling fault helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


def _scale_by_path(params: dict[str, Any], target: str, scale: float) -> None:
    path = [segment.strip() for segment in target.split(".") if str(segment).strip()]
    if not path:
        return
    cur: Any = params
    for key in path[:-1]:
        if not isinstance(cur, dict):
            return
        cur = cur.get(key)
        if cur is None:
            return

    if not isinstance(cur, dict):
        return
    leaf = path[-1]
    current = cur.get(leaf)
    if isinstance(current, (int, float)):
        cur[leaf] = float(current) * max(0.0, scale)


def _candidate_target_paths(target: str) -> list[str]:
    target = str(target)
    if not target:
        return []
    if target.startswith("boiler."):
        return [target[len("boiler.") :]]
    if target.startswith("parameters."):
        return [target]
    return [f"parameters.{target}", target]


def apply_fouling(
    params: Mapping[str, Any] | dict[str, Any],
    severity: float,
    alpha: float,
    target: str | None = None,
) -> dict[str, Any]:
    p = dict(params)
    p.setdefault("degradation", {})
    ua_scale = float(max(0.05, 1.0 - alpha * severity))
    p["degradation"]["ua_scale"] = ua_scale
    p["degradation"]["fouling_severity"] = float(max(0.0, severity))
    p["degradation"]["qmax_scale"] = float(max(0.25, 1.0 - 0.6 * max(0.0, severity)))
    p["degradation"]["eta_comb"] = float(max(0.55, 1.0 - 0.2 * max(0.0, severity)))
    p["degradation"]["fault_fouling"] = True
    p["degradation"]["fouling_target"] = str(target) if target else None
    if target:
        boiler_cfg = p.get("boiler")
        if isinstance(boiler_cfg, dict):
            boiler_cfg = deepcopy(boiler_cfg)
            p["boiler"] = boiler_cfg
            for candidate in _candidate_target_paths(str(target)):
                _scale_by_path(boiler_cfg, candidate, ua_scale)
    return p
