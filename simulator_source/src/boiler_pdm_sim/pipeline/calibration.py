"""Runtime calibration helpers for the simulation pipeline."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from ..research.calibration import derive_nominal_offsets_from_rows
from ..schema import SCHEMA_FREEZE_DATE, SCHEMA_NAME, SCHEMA_VERSION, schema_contract_snapshot


CALIBRATION_REPORT_SCHEMA = "boiler-pdm-sim-calibration-report-v1"
CALIBRATION_REPORT_SCHEMA_VERSION = "1.0.0"


def _coerce_dict_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if k is not None}


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def normalize_calibration_config(raw_cfg: Mapping[str, Any] | None, cfg: Mapping[str, Any]) -> dict[str, Any]:
    raw = _coerce_dict_payload(raw_cfg)
    sim_cfg = _coerce_dict_payload(cfg.get("sim"))
    boiler_cfg = _coerce_dict_payload(cfg.get("boiler"))
    nominal_cfg = _coerce_dict_payload(boiler_cfg.get("nominal"))
    geometry_cfg = _coerce_dict_payload(boiler_cfg.get("geometry"))
    control_cfg = _coerce_dict_payload(cfg.get("control"))
    pressure_cfg = _coerce_dict_payload(control_cfg.get("pressure_pid"))
    level_cfg = _coerce_dict_payload(control_cfg.get("drum_level_pid"))
    use_observations = _coerce_bool(raw.get("use_observations", True), default=True)
    default_horizon = min(_coerce_float(sim_cfg.get("horizon_s", 300.0), 300.0), 300.0)
    drum_length_m = max(1e-6, _coerce_float(geometry_cfg.get("drum_length_m", 6.0), 6.0))
    max_level_bias = abs(_coerce_float(raw.get("max_level_bias", drum_length_m * 0.2), drum_length_m * 0.2))

    probe_requested = _coerce_bool(raw.get("probe", False), default=False)
    mode = str(raw.get("mode", "probe" if probe_requested else "static")).strip().lower() or "static"
    if mode not in {"static", "probe"}:
        mode = "static"

    return {
        "enabled": _coerce_bool(raw.get("enabled", False), default=False),
        "mode": mode,
        "use_observations": use_observations,
        "pressure_channel": str(
            raw.get("pressure_channel", "obs/drum_pressure" if use_observations else "truth/drum_pressure")
        ),
        "level_channel": str(
            raw.get("level_channel", "obs/drum_level" if use_observations else "truth/drum_level")
        ),
        "target_pressure": _coerce_float(
            raw.get("target_pressure", pressure_cfg.get("setpoint_pressure_bar", nominal_cfg.get("pressure_bar", 10.0))),
            10.0,
        ),
        "target_level_m": _coerce_float(
            raw.get("target_level_m", level_cfg.get("setpoint_level_m", 3.3)),
            3.3,
        ),
        "pilot_horizon_s": max(30.0, _coerce_float(raw.get("pilot_horizon_s", default_horizon), default_horizon)),
        "pilot_seed": _coerce_int(raw.get("pilot_seed", sim_cfg.get("seed", 42)), 42),
        "warmup_fraction": min(max(_coerce_float(raw.get("warmup_fraction", 0.25), 0.25), 0.0), 0.95),
        "max_pressure_bias": abs(_coerce_float(raw.get("max_pressure_bias", 2.0), 2.0)),
        "max_level_bias": max_level_bias,
        "ignore_faults": _coerce_bool(raw.get("ignore_faults", True), default=True),
        "disable_randomization": _coerce_bool(raw.get("disable_randomization", True), default=True),
        "nominal_pressure_bar_offset": _coerce_float(raw.get("nominal_pressure_bar_offset", 0.0), 0.0),
        "nominal_level_fraction_offset": _coerce_float(raw.get("nominal_level_fraction_offset", 0.0), 0.0),
    }


def build_calibration_probe_config(cfg: Mapping[str, Any], calibration_cfg: Mapping[str, Any]) -> dict[str, Any]:
    probe_cfg = deepcopy(dict(cfg))
    probe_cfg["calibration"] = {"enabled": False}
    probe_cfg.setdefault("sim", {})
    probe_cfg["sim"]["horizon_s"] = float(calibration_cfg.get("pilot_horizon_s", probe_cfg["sim"].get("horizon_s", 300.0)))
    probe_cfg["sim"]["seed"] = int(calibration_cfg.get("pilot_seed", probe_cfg["sim"].get("seed", 42)))
    probe_cfg["sim"]["collect_performance"] = False
    probe_cfg["analysis"] = {}
    probe_cfg["validation_battery"] = {"enabled": False}
    probe_cfg["phase6"] = {"enabled": False}
    probe_cfg["performance"] = {"enabled": False}
    if bool(calibration_cfg.get("ignore_faults", True)):
        probe_cfg["fault_instances"] = []
    if bool(calibration_cfg.get("disable_randomization", True)):
        probe_cfg.setdefault("randomization", {})
        probe_cfg["randomization"]["enable"] = False
    return probe_cfg


def resolve_runtime_calibration(
    cfg: Mapping[str, Any],
    *,
    default_seed: int,
    run_probe: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    calibration_cfg = normalize_calibration_config(cfg.get("calibration", {}), cfg)
    if not calibration_cfg.get("enabled", False) or calibration_cfg.get("mode") != "probe":
        return calibration_cfg, {}

    probe_cfg = build_calibration_probe_config(cfg, calibration_cfg)
    probe_seed = int(probe_cfg.get("sim", {}).get("seed", default_seed))
    probe_rows = run_probe(probe_cfg, probe_seed)
    return derive_runtime_calibration(calibration_cfg, probe_rows, cfg)


def derive_runtime_calibration(
    calibration_cfg: Mapping[str, Any],
    probe_rows: list[dict[str, Any]],
    cfg: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    out_cfg = dict(calibration_cfg)
    boiler_cfg = _coerce_dict_payload(cfg.get("boiler"))
    geometry_cfg = _coerce_dict_payload(boiler_cfg.get("geometry"))
    report = derive_nominal_offsets_from_rows(
        probe_rows,
        pressure_key=str(out_cfg.get("pressure_channel", "obs/drum_pressure")),
        level_key=str(out_cfg.get("level_channel", "obs/drum_level")),
        target_pressure=_coerce_float(out_cfg.get("target_pressure", 10.0), 10.0),
        target_level=_coerce_float(out_cfg.get("target_level_m", 3.3), 3.3),
        drum_length_m=max(1e-6, _coerce_float(geometry_cfg.get("drum_length_m", 6.0), 6.0)),
        warmup_fraction=_coerce_float(out_cfg.get("warmup_fraction", 0.25), 0.25),
        max_pressure_bias=abs(_coerce_float(out_cfg.get("max_pressure_bias", 2.0), 2.0)),
        max_level_bias=abs(_coerce_float(out_cfg.get("max_level_bias", 1.0), 1.0)),
    )
    out_cfg["nominal_pressure_bar_offset"] = _coerce_float(report.get("nominal_pressure_bar_offset", 0.0), 0.0)
    out_cfg["nominal_level_fraction_offset"] = _coerce_float(report.get("nominal_level_fraction_offset", 0.0), 0.0)
    return out_cfg, {
        "mode": "probe",
        "status": str(report.get("status", "unknown")),
        "probe_rows": int(len(probe_rows)),
        "pressure_channel": str(out_cfg.get("pressure_channel", "")),
        "level_channel": str(out_cfg.get("level_channel", "")),
        "pressure_bias": float(report.get("pressure_bias", 0.0)),
        "level_bias": float(report.get("level_bias", 0.0)),
        "nominal_pressure_bar_offset": float(out_cfg.get("nominal_pressure_bar_offset", 0.0)),
        "nominal_level_fraction_offset": float(out_cfg.get("nominal_level_fraction_offset", 0.0)),
        "sample_counts": dict(report.get("sample_counts", {})),
    }


def apply_calibration_to_boiler(
    boiler_cfg: Mapping[str, Any],
    calibration_cfg: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    applied = False
    if not calibration_cfg:
        return dict(boiler_cfg), applied
    cfg = _coerce_dict_payload(calibration_cfg)
    if cfg.get("enabled", True) is False:
        return dict(boiler_cfg), applied

    out = deepcopy(dict(boiler_cfg))
    nominal = dict(_coerce_dict_payload(out.get("nominal", {})))
    cal_nominal = _coerce_dict_payload(cfg.get("nominal"))
    for key, value in cal_nominal.items():
        if key in ("pressure_bar", "steam_flow_kg_s", "feedwater_mass_kg", "level_fraction", "level_target"):
            nominal[key] = value
    if "nominal_pressure_bar_offset" in cfg and "pressure_bar" in nominal:
        nominal["pressure_bar"] = float(nominal["pressure_bar"]) + float(cfg["nominal_pressure_bar_offset"])
    if "nominal_level_fraction_offset" in cfg and "level_fraction" in nominal:
        nominal["level_fraction"] = float(nominal["level_fraction"]) + float(cfg["nominal_level_fraction_offset"])
    if nominal:
        out["nominal"] = nominal
        applied = True
    return out, applied


def build_calibration_report_payload(
    calibration_cfg: Mapping[str, Any] | None,
    calibration_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    cfg = _coerce_dict_payload(calibration_cfg)
    report = _coerce_dict_payload(calibration_report)
    enabled = _coerce_bool(cfg.get("enabled", False), default=False)
    mode = str(report.get("mode", cfg.get("mode", "static"))).strip().lower() or "static"
    status_default = "disabled" if not enabled else ("static" if mode == "static" else "pending")
    return {
        "enabled": enabled,
        "mode": mode,
        "status": str(report.get("status", status_default)),
        "use_observations": _coerce_bool(cfg.get("use_observations", True), default=True),
        "pressure_channel": str(cfg.get("pressure_channel", "")),
        "level_channel": str(cfg.get("level_channel", "")),
        "target_pressure": _coerce_float(cfg.get("target_pressure", 0.0), 0.0),
        "target_level_m": _coerce_float(cfg.get("target_level_m", 0.0), 0.0),
        "pilot_horizon_s": _coerce_float(cfg.get("pilot_horizon_s", 0.0), 0.0),
        "warmup_fraction": _coerce_float(cfg.get("warmup_fraction", 0.0), 0.0),
        "probe_rows": _coerce_int(report.get("probe_rows", 0), 0),
        "sample_counts": _coerce_dict_payload(report.get("sample_counts")),
        "bias": {
            "pressure_bar": _coerce_float(report.get("pressure_bias", 0.0), 0.0),
            "level_m": _coerce_float(report.get("level_bias", 0.0), 0.0),
        },
        "applied_offsets": {
            "nominal_pressure_bar_offset": _coerce_float(cfg.get("nominal_pressure_bar_offset", 0.0), 0.0),
            "nominal_level_fraction_offset": _coerce_float(cfg.get("nominal_level_fraction_offset", 0.0), 0.0),
        },
    }


def attach_calibration_analysis(
    analysis: Mapping[str, Any] | None,
    calibration_summary: Mapping[str, Any] | None,
    *,
    include_in_analysis: bool,
) -> dict[str, Any]:
    base = dict(analysis) if isinstance(analysis, Mapping) else {}
    summary = _coerce_dict_payload(calibration_summary)
    if include_in_analysis and summary:
        base["calibration"] = summary
    return base


def build_calibration_report_document(
    pipeline_meta: Mapping[str, Any],
    analysis_cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    calibration = _coerce_dict_payload(pipeline_meta.get("calibration"))
    if not calibration:
        return None
    analysis_root = _coerce_dict_payload(analysis_cfg)
    calibration_analysis_cfg = _coerce_dict_payload(analysis_root.get("calibration"))
    if calibration_analysis_cfg and not _coerce_bool(calibration_analysis_cfg.get("enabled", False), default=False):
        return None
    analysis_summary = _coerce_dict_payload(_coerce_dict_payload(pipeline_meta.get("analysis")).get("calibration"))
    return {
        "schema_name": CALIBRATION_REPORT_SCHEMA,
        "schema_version": CALIBRATION_REPORT_SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_schema": {
            "name": SCHEMA_NAME,
            "version": SCHEMA_VERSION,
            "freeze_date": SCHEMA_FREEZE_DATE,
        },
        "schema_contract": schema_contract_snapshot(),
        "pipeline_order": list(pipeline_meta.get("order", [])),
        "analysis_options": calibration_analysis_cfg,
        "calibration": calibration,
        "analysis_summary": analysis_summary,
    }
