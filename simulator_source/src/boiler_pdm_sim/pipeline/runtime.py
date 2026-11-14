"""Shared runtime/config helpers extracted from Simulator."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from hashlib import sha256
from typing import Any

import numpy as np

from ..schema import validate_analysis_phase15_config


_FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _coerce_scalars(cfg: object) -> object:
    if isinstance(cfg, dict):
        return {k: _coerce_scalars(v) for k, v in cfg.items()}
    if isinstance(cfg, list):
        return [_coerce_scalars(v) for v in cfg]
    if isinstance(cfg, tuple):
        return tuple(_coerce_scalars(v) for v in cfg)
    if isinstance(cfg, str):
        s = cfg.strip()
        if _FLOAT_RE.fullmatch(s):
            return float(s)
        try:
            if s.isdigit() or (s.startswith("+") or s.startswith("-")) and s[1:].isdigit():
                return int(s)
        except Exception:
            pass
        return cfg
    return cfg


def _as_event_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if value is None:
        return []
    return [str(value)]


def _merge_event_lists(*event_lists: object) -> list[str]:
    merged: list[str] = []
    for raw in event_lists:
        events = _as_event_list(raw)
        for event in events:
            if event and event not in merged:
                merged.append(event)
    return merged


def _coerce_dict_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if k is not None}


def _deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in override.items():
        current = out.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            out[key] = _deep_update(current, value)
        else:
            out[key] = deepcopy(value)
    return out


def _extract_profile(cfg: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    cfg_payload = _coerce_dict_payload(cfg)
    profile_name = cfg_payload.get("profile")
    if profile_name is None:
        profile_name = cfg_payload.get("runtime_profile")
    if not isinstance(profile_name, str):
        return None, {}
    profile_name = profile_name.strip()
    if not profile_name:
        return None, {}
    profiles = _coerce_dict_payload(cfg_payload.get("profiles", {}))
    profile_cfg = _coerce_dict_payload(profiles.get(profile_name))
    if not profile_cfg:
        return profile_name, {}
    return profile_name, profile_cfg


def _safe_hash_config(value: object) -> str:
    payload = json.dumps(_coerce_dict_payload(value), ensure_ascii=False, sort_keys=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def _coerce_non_negative_int(value: object, default: int = 1) -> int:
    try:
        return max(1, int(value))
    except Exception:
        return default


def _coerce_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _validate_list_of_strings(value: object, *, field_name: str, issues: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        issues.append(f"{field_name} must be a list[str] when provided")
        return []
    items = [str(item) for item in value if str(item).strip()]
    return items


def _coerce_phase15_analysis_config(cfg: object) -> tuple[dict[str, Any], list[str]]:
    raw_cfg = _coerce_dict_payload(cfg)
    if not raw_cfg:
        return {}, []

    _, config_issues = validate_analysis_phase15_config(raw_cfg)
    baseline_cfg = _coerce_dict_payload(raw_cfg.get("baseline", {}))
    identify_cfg = _coerce_dict_payload(raw_cfg.get("identify", {}))
    sensitivity_cfg = _coerce_dict_payload(raw_cfg.get("sensitivity", {}))
    issues: list[str] = list(config_issues)

    baseline: dict[str, Any] = {
        "enabled": _coerce_bool(baseline_cfg.get("enabled", False)),
        "compare": _coerce_bool(baseline_cfg.get("compare", False)),
        "abs_tol": _coerce_float(baseline_cfg.get("abs_tol", 0.2), 0.2),
        "channels": _validate_list_of_strings(
            baseline_cfg.get("channels"),
            field_name="analysis.baseline.channels",
            issues=issues,
        ),
    }
    baseline_reference = baseline_cfg.get("reference")
    if baseline["compare"] and isinstance(baseline_reference, dict):
        baseline["reference"] = _coerce_dict_payload(baseline_reference)
    elif baseline["compare"]:
        issues.append("analysis.baseline.compare=true requires a mapping reference")

    identify: dict[str, Any] = {
        "enabled": _coerce_bool(identify_cfg.get("enabled", False)),
        "fault_key": str(identify_cfg.get("fault_key", "label/fault_type")).strip() or "label/fault_type",
        "channels": _validate_list_of_strings(
            identify_cfg.get("channels"),
            field_name="analysis.identify.channels",
            issues=issues,
        ),
    }

    sensitivity: dict[str, Any] = {
        "enabled": _coerce_bool(sensitivity_cfg.get("enabled", False)),
        "signal": str(sensitivity_cfg.get("signal", "obs/drum_level")).strip() or "obs/drum_level",
        "epsilon": _coerce_float(sensitivity_cfg.get("epsilon", 1e-3), 1e-3),
        "window": max(3, int(_coerce_float(sensitivity_cfg.get("window", 10), 10))),
    }
    if sensitivity["window"] <= 0:
        issues.append("analysis.sensitivity.window must be a positive integer")

    normalized = {
        "baseline": baseline,
        "identify": identify,
        "sensitivity": sensitivity,
    }
    normalized = {k: v for k, v in normalized.items() if isinstance(v, dict)}
    if issues:
        return normalized, issues

    return normalized, []


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _safe_ratio(numerator: float, denominator: float, default: float = float("nan")) -> float:
    if not np.isfinite(denominator) or denominator == 0:
        return default
    return float(numerator / denominator)
