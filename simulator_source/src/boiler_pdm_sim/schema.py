"""Project-level schema/version metadata and lightweight label-schema validators."""

from __future__ import annotations

import fnmatch
from numbers import Real
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "v1.1.1"
SCHEMA_NAME = "boiler-pdm-sim-schema-v1.1"
SCHEMA_FREEZE_DATE = "2026-03-08"
SCHEMA_SPEC_SOURCE = "docs/spec_boiler_pdm_sim.md"

SCHEMA_LABEL_KEYS = [
    "label/fault_type",
    "label/fault_types",
    "label/fault_type_count",
    "label/fault_severity",
    "label/anomaly_flag",
    "label/RUL",
    "label/RUL_current_mission",
    "label/RUL_reference_mission",
    "label/censored",
    "label/failure_threshold_name",
    "label/fault_onset",
    "label/symptom_onset",
    "label/anomaly_detectable_onset",
    "label/threshold_crossing",
    "label/trip_time",
    "label/safety_state",
    "label/safety_active",
    "label/alarm_count",
    "label/trip_count",
    "label/fault_names",
    "label/alarm_faults",
    "label/trip_faults",
    "label/event_log",
    "label/event_log_history",
    "label/event_log_latest",
]
_SCHEMA_LABEL_KEYS_TUPLE = tuple(SCHEMA_LABEL_KEYS)

CALIBRATION_REPORT_SCHEMA = "boiler-pdm-sim-calibration-report-v1"
CALIBRATION_REPORT_SCHEMA_VERSION = "1.0.0"
CALIBRATION_SUMMARY_KEYS = (
    "enabled",
    "mode",
    "status",
    "use_observations",
    "pressure_channel",
    "level_channel",
    "target_pressure",
    "target_level_m",
    "pilot_horizon_s",
    "warmup_fraction",
    "probe_rows",
    "sample_counts",
    "bias",
    "applied_offsets",
)
CALIBRATION_SUMMARY_BIAS_KEYS = ("pressure_bar", "level_m")
CALIBRATION_SUMMARY_OFFSET_KEYS = (
    "nominal_pressure_bar_offset",
    "nominal_level_fraction_offset",
)

SCHEMA_LOCK = {
    "schema_name": SCHEMA_NAME,
    "schema_version": SCHEMA_VERSION,
    "freeze_date": SCHEMA_FREEZE_DATE,
    "status": "frozen",
    "label_contract": SCHEMA_LABEL_KEYS,
    "event_patterns": [
        "*_onset_t=*",
        "*_threshold_t=*",
        "*_trip_t=*",
        "*_enter_t=*",
        "*_alarm_t=*",
        "*_alarm_clear_t=*",
        "*_step_up_t=*",
        "*_step_down_t=*",
        "algebraic_*_t=*",
        "solver_*_t=*",
        "state_clamp_t=*",
        "control_mode_*_to_*_t=*",
        "control_strategy_*_to_*_t=*",
        "trip_reset_condition*_t=*",
    ],
    "core_columns": ["time", "scenario_id", "truth/*", "obs/*", "meta/*"],
}
_SCHEMA_EVENT_PATTERNS = tuple(SCHEMA_LOCK["event_patterns"])


_LABEL_STR_KEYS = {
    "label/fault_type",
    "label/failure_threshold_name",
    "label/safety_state",
}

_LABEL_FLOAT_KEYS = {
    "label/fault_severity",
    "label/anomaly_flag",
    "label/RUL",
    "label/RUL_current_mission",
    "label/RUL_reference_mission",
    "label/censored",
    "label/fault_onset",
    "label/symptom_onset",
    "label/anomaly_detectable_onset",
    "label/threshold_crossing",
    "label/trip_time",
    "label/safety_active",
    "label/alarm_count",
    "label/trip_count",
}

_LABEL_LIST_STR_KEYS = {
    "label/fault_types",
    "label/fault_names",
    "label/alarm_faults",
    "label/trip_faults",
    "label/event_log",
    "label/event_log_history",
    "label/event_log_latest",
}

_EVENT_FIELDS = {
    "label/event_log",
    "label/event_log_history",
    "label/event_log_latest",
}

_EVENT_ALLOWED_LITERALS = {
    "actuator_lockout_active",
    "feedwater_actuator_saturation",
    "feedwater_actuator_rate_limit",
    "feedwater_actuator_stiction",
    "fuel_actuator_saturation",
    "fuel_actuator_rate_limit",
    "fuel_actuator_stiction",
    "steam_actuator_saturation",
    "steam_actuator_rate_limit",
    "steam_actuator_stiction",
    "safety_alarm_limited",
    "safety_trip_hard_stop",
    "sat_feedwater_flow_pid_lower",
    "sat_feedwater_flow_pid_upper",
    "sat_level_pid_lower",
    "sat_level_pid_upper",
    "sat_pressure_pid_lower",
    "sat_pressure_pid_upper",
}


def _as_list(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return value
    return (value,)


def _is_finite_number(value: object) -> bool:
    return isinstance(value, Real) and (value == value)


def _is_list_of_str(value: object) -> bool:
    return isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value)


def _validate_label_contract_event(
    event: Any,
    event_patterns: Iterable[str],
) -> str | None:
    if not isinstance(event, str):
        return f"label event entry must be str: {type(event).__name__}"
    patterns = event_patterns if isinstance(event_patterns, tuple) else tuple(event_patterns)
    if "_t=" in event:
        if patterns and not any(fnmatch.fnmatch(event, pattern) for pattern in patterns):
            return f"event '{event}' does not match any schema event pattern"
        return None

    if event not in _EVENT_ALLOWED_LITERALS:
        return f"event '{event}' does not match any schema event pattern"
    return None


def validate_label_contract_row(
    row: Mapping[str, Any],
    *,
    required_keys: Iterable[str] | None = None,
    event_patterns: Iterable[str] | None = None,
    require_type: bool = True,
) -> list[str]:
    """Validate a row-level flattened label contract.

    Args:
        row: flattened simulation row (``label/*`` fields already expanded).
        required_keys: override required keys. defaults to SCHEMA_LABEL_KEYS.
        event_patterns: override event wildcard patterns.
        require_type: when False only enforces required key presence.
    """

    keys = _SCHEMA_LABEL_KEYS_TUPLE if required_keys is None else tuple(required_keys)
    patterns = _SCHEMA_EVENT_PATTERNS if event_patterns is None else tuple(event_patterns)
    failures: list[str] = []

    for key in keys:
        if key not in row:
            failures.append(f"missing required key: {key}")

    if not require_type:
        return failures

    for key in keys:
        value = row.get(key)
        if key == "label/fault_type_count":
            if not _is_finite_number(value):
                failures.append("label/fault_type_count must be numeric")
            continue
        if key in _LABEL_STR_KEYS:
            if value is None:
                failures.append(f"{key} must be str")
            elif isinstance(value, (list, tuple)):
                failures.append(f"{key} must be str")
            elif not isinstance(value, str):
                failures.append(f"{key} must be str")
            continue
        if key in _LABEL_FLOAT_KEYS:
            if not _is_finite_number(value):
                failures.append(f"{key} must be finite number")
            continue
        if key in _LABEL_LIST_STR_KEYS:
            if not _is_list_of_str(value):
                failures.append(f"{key} must be list[str]")
            continue

    for key in _EVENT_FIELDS:
        if key not in row:
            continue
        events = _as_list(row.get(key))
        for event in events:
            message = _validate_label_contract_event(event, patterns)
            if message:
                failures.append(f"{key}: {message}")
    return failures


def schema_manifest() -> dict[str, object]:
    """Return a copy-friendly schema lock payload."""
    return dict(SCHEMA_LOCK)


def schema_contract_snapshot() -> dict[str, object]:
    """Return immutable contract values used by tooling and docs alignment checks."""
    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "freeze_date": SCHEMA_FREEZE_DATE,
        "source": SCHEMA_SPEC_SOURCE,
    }


def validate_calibration_summary_payload(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    if not isinstance(payload, Mapping):
        return False, ["calibration summary must be a mapping"]
    failures: list[str] = []
    for key in CALIBRATION_SUMMARY_KEYS:
        if key not in payload:
            failures.append(f"missing calibration summary key: {key}")
    bias = payload.get("bias", {})
    if not isinstance(bias, Mapping):
        failures.append("calibration.bias must be a mapping")
    else:
        for key in CALIBRATION_SUMMARY_BIAS_KEYS:
            if key not in bias:
                failures.append(f"missing calibration.bias key: {key}")
            elif not _is_finite_number(bias.get(key)):
                failures.append(f"calibration.bias.{key} must be finite number")
    offsets = payload.get("applied_offsets", {})
    if not isinstance(offsets, Mapping):
        failures.append("calibration.applied_offsets must be a mapping")
    else:
        for key in CALIBRATION_SUMMARY_OFFSET_KEYS:
            if key not in offsets:
                failures.append(f"missing calibration.applied_offsets key: {key}")
            elif not _is_finite_number(offsets.get(key)):
                failures.append(f"calibration.applied_offsets.{key} must be finite number")
    sample_counts = payload.get("sample_counts", {})
    if not isinstance(sample_counts, Mapping):
        failures.append("calibration.sample_counts must be a mapping")
    return len(failures) == 0, failures


def validate_analysis_phase15_config(cfg: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Validate phase-15 analysis section with minimal strictness.

    Args:
        cfg: normalized analysis configuration dictionary.
    Returns:
        (is_valid, list_of_errors)
    """
    if not cfg:
        return True, []
    if not isinstance(cfg, Mapping):
        return False, ["analysis config must be a mapping"]

    allowed_toplevel = {"baseline", "identify", "sensitivity", "calibration"}
    unknown_keys = set(cfg) - allowed_toplevel
    if unknown_keys:
        return False, [f"analysis has unsupported key(s): {', '.join(sorted(unknown_keys))}"]

    for section in ("baseline", "identify", "sensitivity"):
        section_cfg = cfg.get(section, {})
        if not isinstance(section_cfg, Mapping):
            return False, [f"analysis.{section} must be a mapping"]

        enabled = section_cfg.get("enabled", False)
        if enabled not in (True, False):
            return False, [f"analysis.{section}.enabled must be bool"]

        if section == "baseline":
            channels = section_cfg.get("channels")
            if channels is not None and not isinstance(channels, (list, tuple)):
                return False, ["analysis.baseline.channels must be list[str] or omitted"]
            if channels and section_cfg.get("compare", False):
                reference = section_cfg.get("reference")
                if not isinstance(reference, Mapping):
                    return False, ["analysis.baseline.compare=true requires reference mapping"]

        if section == "identify":
            fault_key = section_cfg.get("fault_key", "label/fault_type")
            if not isinstance(fault_key, str):
                return False, ["analysis.identify.fault_key must be string"]
            channels = section_cfg.get("channels")
            if channels is not None and not isinstance(channels, (list, tuple)):
                return False, ["analysis.identify.channels must be list[str] or omitted"]

        if section == "sensitivity":
            signal = section_cfg.get("signal", "obs/drum_level")
            if not isinstance(signal, str):
                return False, ["analysis.sensitivity.signal must be string"]
            if not isinstance(section_cfg.get("epsilon", 1e-3), (int, float)) or section_cfg.get("epsilon", 1e-3) <= 0:
                return False, ["analysis.sensitivity.epsilon must be positive number"]
            try:
                window = float(section_cfg.get("window", 10))
                if int(window) <= 0:
                    return False, ["analysis.sensitivity.window must be positive integer"]
            except Exception:
                return False, ["analysis.sensitivity.window must be numeric"]

    calibration_cfg = cfg.get("calibration", {})
    if calibration_cfg:
        if not isinstance(calibration_cfg, Mapping):
            return False, ["analysis.calibration must be a mapping"]
        enabled = calibration_cfg.get("enabled", False)
        if enabled not in (True, False):
            return False, ["analysis.calibration.enabled must be bool"]
        report_path = calibration_cfg.get("report_path")
        if report_path is not None and not isinstance(report_path, str):
            return False, ["analysis.calibration.report_path must be string or omitted"]
        include_in_analysis = calibration_cfg.get("include_in_analysis")
        if include_in_analysis is not None and include_in_analysis not in (True, False):
            return False, ["analysis.calibration.include_in_analysis must be bool or omitted"]
        include_in_provenance = calibration_cfg.get("include_in_provenance")
        if include_in_provenance is not None and include_in_provenance not in (True, False):
            return False, ["analysis.calibration.include_in_provenance must be bool or omitted"]

    return True, []
