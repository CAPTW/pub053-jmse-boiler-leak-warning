"""Domain randomization helpers."""

from __future__ import annotations

from typing import Any
from copy import deepcopy

import numpy as np


def _coerce_numeric(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _coerce_numeric(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_numeric(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_coerce_numeric(v) for v in obj)
    if isinstance(obj, str):
        s = obj.strip()
        if not s:
            return obj
        try:
            return float(s)
        except ValueError:
            return obj
    return obj


def apply_randomization(params: dict[str, Any], cfg: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    p = _coerce_numeric(deepcopy(params))
    cfg = _coerce_numeric(cfg)
    if not cfg.get("enable", False):
        return p

    wrapped = False
    if _is_boiler_root(p):
        params_root = p
    elif isinstance(p.get("boiler"), dict):
        params_root = p["boiler"]
        wrapped = True
    else:
        params_root = p
        wrapped = False

    diagnostics = params_root.setdefault("diagnostics", {})
    ident_cfg = cfg.get("identifiability_constraints", {})
    locked = {str(v) for v in ident_cfg.get("lock_keys", []) if str(v).strip()}
    raw_groups = ident_cfg.get("groups", {})
    groups: dict[str, list[str]] = {}
    if isinstance(raw_groups, dict):
        for group_name, members in raw_groups.items():
            if isinstance(members, (list, tuple, set)):
                cleaned = [str(item) for item in members if str(item).strip()]
                if cleaned:
                    groups[str(group_name)] = cleaned

    drift = cfg.get("drift_std_pct", {})
    applied_scales: dict[str, float] = {}
    group_scales: dict[str, float] = {}

    def _draw_scale(key: str) -> float:
        if key in applied_scales:
            return float(applied_scales[key])
        for group_name, members in groups.items():
            if key in members:
                if group_name not in group_scales:
                    group_sigma = max(float(drift.get(member, 0.0)) for member in members)
                    group_scales[group_name] = 1.0 + rng.normal(0.0, group_sigma)
                applied_scales[key] = float(group_scales[group_name])
                return float(applied_scales[key])
        applied_scales[key] = 1.0 + rng.normal(0.0, float(drift[key]))
        return float(applied_scales[key])

    if "UA_evap" in drift and "UA_evap" not in locked:
        _update_nested(params_root, ["parameters", "UA", "evaporator"], _mul(_draw_scale("UA_evap")))
    if "combustion_eta" in drift and "combustion_eta" not in locked:
        _update_nested(params_root, ["parameters", "combustion", "eta"], _mul(_draw_scale("combustion_eta")))
    if "feedwater_max" in drift and "feedwater_max" not in locked:
        _update_nested(params_root, ["parameters", "limits", "mdot_fw_max_kg_s"], _mul(_draw_scale("feedwater_max")))

    diagnostics["randomization"] = {
        "locked_keys": sorted(locked),
        "grouped_keys": {name: list(members) for name, members in groups.items()},
        "applied_scales": {key: float(value) for key, value in applied_scales.items()},
    }

    if wrapped:
        p["boiler"] = params_root
    return p


def _mul(scale: float):
    return lambda x: float(x * max(0.2, scale))


def _update_nested(d: dict[str, Any], path: list[str], fn) -> dict[str, Any]:
    cur = d
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = fn(cur.get(path[-1], 1.0))
    return d


def _is_boiler_root(params: dict[str, Any]) -> bool:
    required = {"geometry", "nominal", "parameters"}
    return required.issubset(set(params.keys()))
