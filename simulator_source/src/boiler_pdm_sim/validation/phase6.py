"""Phase-6 validation battery orchestration.

The module executes a seed-sweep battery from configuration and splits KPI failures
into required and warning groups.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .regression import acceptance_thresholds, seed_sweep_battery, summarize_rows


def _coerce_seed_list(value: object) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        try:
            return [int(value)]
        except Exception:
            return []

    seeds: list[int] = []
    if isinstance(value, (list, tuple, set)):
        for item in value:
            try:
                seeds.append(int(item))
            except Exception:
                continue
    return seeds


def _coerce_channels(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    return []


def _coerce_dict_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if k is not None}


def _run_required_optional_eval(
    summaries: dict[str, dict[str, Any]],
    rules: dict[str, Any],
) -> dict[str, Any]:
    if not rules:
        return {"passed": True, "failures": [], "details": {}}

    failures: list[str] = []
    details: dict[str, Any] = {}
    for seed, metrics in summaries.items():
        acc = acceptance_thresholds(metrics, rules)
        details[str(seed)] = acc
        if not acc.get("passed", False):
            failures.extend([f"seed={seed}: {f}" for f in acc.get("failures", [])])
    return {"passed": len(failures) == 0, "failures": failures, "details": details}


def run_validation_battery(
    run_fn,
    cfg: dict[str, Any],
    *,
    phase6_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a configuration-driven validation battery.

    Returns:
        {
          "enabled": bool,
          "status": "passed" | "warning" | "failed" | "disabled",
          "passed": bool,  # required KPI gate only
          "required": {...},
          "warning": {...},
          "summaries": {...},
          "seed_failures": [...],
          "seeds": [...],
          "n_runs": int,
        }
    """
    cfg_norm = _coerce_dict_payload(cfg)
    phase_cfg = _coerce_dict_payload(phase6_cfg)
    enabled = bool(phase_cfg.get("enabled", False))
    if not enabled:
        return {
            "enabled": False,
            "status": "disabled",
            "passed": True,
            "required": {"passed": True, "failures": [], "details": {}},
            "warning": {"passed": True, "failures": [], "details": {}},
            "summaries": {},
            "seed_failures": [],
            "seeds": [],
            "n_runs": 0,
        }

    seeds = _coerce_seed_list(phase_cfg.get("seeds"))
    if not seeds:
        sim_seed = cfg_norm.get("sim", {}).get("seed")
        if sim_seed is not None:
            try:
                seeds = [int(sim_seed)]
            except Exception:
                seeds = []
    if not seeds:
        return {
            "enabled": True,
            "status": "failed",
            "passed": False,
            "required": {"passed": False, "failures": ["no seeds configured"], "details": {}},
            "warning": {"passed": False, "failures": ["no seeds configured"], "details": {}},
            "summaries": {},
            "seed_failures": ["no seeds configured"],
            "seeds": [],
            "n_runs": 0,
        }

    summary_channels = _coerce_channels(
        phase_cfg.get(
            "summary_channels",
            ("truth/drum_pressure", "truth/drum_level", "obs/drum_pressure", "obs/drum_level"),
        )
    )
    required_rules = _coerce_dict_payload(phase_cfg.get("required_kpis"))
    warning_rules = _coerce_dict_payload(phase_cfg.get("warning_kpis"))

    base_cfg = deepcopy(cfg_norm)
    battery = seed_sweep_battery(
        run_fn,
        base_cfg,
        seeds=seeds,
        summary_channels=summary_channels or None,
    )

    required = _run_required_optional_eval(battery.get("summaries", {}), required_rules)
    warning = _run_required_optional_eval(battery.get("summaries", {}), warning_rules)

    seed_failures = list(_coerce_dict_payload(battery).get("failures", []))
    if not battery.get("passed", False):
        for item in battery.get("failures", []):
            msg = str(item)
            if msg.startswith("seed="):
                seed_failures.append(msg)
            else:
                seed_failures.append(f"seed-run failed: {msg}")

    if not required["passed"]:
        status = "failed"
    elif not warning["passed"]:
        status = "warning"
    else:
        status = "passed"

    return {
        "enabled": True,
        "status": status,
        "passed": bool(required["passed"]),
        "required": required,
        "warning": warning,
        "summaries": battery.get("summaries", {}),
        "seed_failures": seed_failures,
        "seeds": list(seeds),
        "n_runs": int(battery.get("n_runs", 0)),
        "run_seeded_summary": bool(battery.get("passed", False)),
    }
