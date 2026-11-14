"""High-level simulation orchestrator."""

from __future__ import annotations

import json
import warnings
from time import perf_counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .core.solver import normalize_method
from .core.backend_factory import build_core_backend
from .control.loops import BoilerControl
from .degradation.scheduler import DegradationScheduler
from .dataset.generator import DatasetGenerator
from .dataset.writer import write_dataset
from .interface.fmu import build_fmu_contract
from .pipeline.calibration import (
    apply_calibration_to_boiler,
    build_calibration_report_payload,
    resolve_runtime_calibration,
)
from .pipeline.config_types import RuntimeConfig
from .pipeline.postprocess import (
    enforce_inline_governance,
    record_performance_outputs,
    write_calibration_sidecar,
)
from .pipeline.runtime import (
    _as_event_list,
    _coerce_bool,
    _coerce_dict_payload,
    _coerce_float,
    _coerce_list,
    _coerce_non_negative_int,
    _coerce_phase15_analysis_config,
    _coerce_scalars,
    _deep_update,
    _extract_profile,
    _safe_ratio,
    _safe_hash_config,
)
from .pipeline.run_to_file import build_provenance, record_analysis, resolve_split_config, run_optional_validation_battery
from .pipeline.step_loop import execute_step_loop
from .schema import (
    SCHEMA_LOCK,
    SCHEMA_FREEZE_DATE,
    SCHEMA_LABEL_KEYS,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    schema_contract_snapshot,
    validate_analysis_phase15_config,
    validate_label_contract_row,
)
from .scenarios.scenario import build_profile
from .scenarios.randomization import apply_randomization
from .sensors.sensor_model import SensorModel
from .safety import ProcessSafetyMonitor
from .validation.phase6 import run_validation_battery


class Simulator:
    def __init__(self, seed: int | None = None) -> None:
        self.seed = int(seed) if seed is not None else 42
        self.rng = np.random.default_rng(self.seed)
        self._pipeline_meta: dict[str, Any] = {"order": []}
        self._last_run_timing: dict[str, float] = {}
        self._last_algebraic_timing: dict[str, float] = {}

    def _apply_identifiability(self, boiler_cfg: dict[str, Any], identifiability_cfg: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        report: dict[str, Any] = {
            "enabled": False,
            "applied": False,
            "freeze_level_chain": False,
            "locked_randomization_keys": [],
            "randomization_groups": {},
            "fixed_sensor_channels": [],
        }
        if not identifiability_cfg:
            return boiler_cfg, report
        cfg = _coerce_scalars(deepcopy(identifiability_cfg))
        if cfg.get("enabled", True) is False:
            return boiler_cfg, report

        out = deepcopy(boiler_cfg)
        diagnostics = out.setdefault("diagnostics", {})
        freeze_level_chain = bool(cfg.get("freeze_level_chain", True))
        fixed_sensor_channels = cfg.get("freeze_sensor_channels")
        if not isinstance(fixed_sensor_channels, (list, tuple, set)):
            fixed_sensor_channels = ["drum_level"] if freeze_level_chain else []
        fixed_sensor_channels = [str(item) for item in fixed_sensor_channels if str(item).strip()]

        locked_randomization_keys = cfg.get("lock_randomization_keys")
        if not isinstance(locked_randomization_keys, (list, tuple, set)):
            locked_randomization_keys = ["feedwater_max"] if freeze_level_chain else []
        locked_randomization_keys = [str(item) for item in locked_randomization_keys if str(item).strip()]

        raw_groups = cfg.get("randomization_groups")
        if not isinstance(raw_groups, dict):
            raw_groups = {"thermal_efficiency": ["UA_evap", "combustion_eta"]} if freeze_level_chain else {}
        randomization_groups: dict[str, list[str]] = {}
        for group_name, members in raw_groups.items():
            if not isinstance(members, (list, tuple, set)):
                continue
            cleaned = [str(item) for item in members if str(item).strip()]
            if cleaned:
                randomization_groups[str(group_name)] = cleaned

        diagnostics["level_chain_fixed"] = freeze_level_chain
        diagnostics["identifiability"] = {
            "freeze_level_chain": freeze_level_chain,
            "locked_randomization_keys": locked_randomization_keys,
            "randomization_groups": randomization_groups,
            "fixed_sensor_channels": fixed_sensor_channels,
        }
        report.update(
            {
                "enabled": True,
                "applied": bool(freeze_level_chain or locked_randomization_keys or randomization_groups or fixed_sensor_channels),
                "freeze_level_chain": freeze_level_chain,
                "locked_randomization_keys": locked_randomization_keys,
                "randomization_groups": randomization_groups,
                "fixed_sensor_channels": fixed_sensor_channels,
            }
        )
        return out, report

    def _freeze_sensor_config(self, sensor_cfg: dict[str, Any], level_chain_channels: tuple[str, ...] = ("drum_level",)) -> dict[str, Any]:
        fixed: dict[str, Any] = {}
        cfg = _coerce_scalars(deepcopy(sensor_cfg))
        for key, value in cfg.items():
            if key in level_chain_channels:
                channel = dict(value) if isinstance(value, dict) else {}
                channel["bias"] = 0.0
                channel["drift_per_hour"] = 0.0
                channel["dropout_p"] = 0.0
                channel["spike_p"] = 0.0
                channel["block_dropout_p"] = 0.0
                fixed[str(key)] = channel
                continue
            fixed[str(key)] = dict(value) if isinstance(value, dict) else {}

        for key in level_chain_channels:
            fixed.setdefault(key, {})

        return fixed

    def _coerce_safety_config(self, cfg: object) -> dict[str, Any]:
        raw = _coerce_dict_payload(cfg)
        alarm = _coerce_dict_payload(raw.get("alarm", {}))
        trip = _coerce_dict_payload(raw.get("trip", {}))
        return {
            "enabled": bool(raw.get("enabled", True)),
            "lockout_on_trip": bool(raw.get("lockout_on_trip", True)),
            "process": _coerce_scalars(_coerce_dict_payload(raw.get("process", {}))),
            "alarm": {
                "fuel_cmd_max": float(alarm.get("fuel_cmd_max", 1.0)),
                "fw_cmd_max": float(alarm.get("fw_cmd_max", 1.0)),
                "steam_demand_max": float(alarm.get("steam_demand_max", 1.0)),
            },
            "trip": {
                "fuel_cmd": float(trip.get("fuel_cmd", 0.0)),
                "fw_cmd": float(trip.get("fw_cmd", 0.0)),
                "steam_demand": float(trip.get("steam_demand", 0.0)),
            },
        }

    def _apply_sensor_timebase_defaults(self, sensor_cfg: dict[str, Any], *, sample_period_s: float) -> dict[str, Any]:
        fixed = _coerce_scalars(deepcopy(sensor_cfg))
        for key, value in list(fixed.items()):
            if not isinstance(value, dict):
                fixed[key] = {}
                value = fixed[key]
            value.setdefault("sample_period_s", float(sample_period_s))
            value.setdefault("tau_s", 0.0)
            value.setdefault("dead_time_s", 0.0)
            value.setdefault("quality_flag_logic", "good")
        return fixed

    def _merge_process_safety_labels(self, labels: dict[str, Any], process_eval: Any) -> dict[str, Any]:
        merged = dict(labels)
        alarm_faults = set(_as_event_list(labels.get("alarm_faults", [])))
        trip_faults = set(_as_event_list(labels.get("trip_faults", [])))
        process_alarm_names = list(getattr(process_eval, "alarm_names", []))
        process_trip_names = list(getattr(process_eval, "trip_names", []))
        alarm_faults.update(process_alarm_names)
        trip_faults.update(process_trip_names)

        latest = _as_event_list(labels.get("event_log_latest", [])) + list(getattr(process_eval, "events", []))
        history = _as_event_list(labels.get("event_log_history", [])) + list(getattr(process_eval, "events", []))
        event_log = _as_event_list(labels.get("event_log", [])) + list(getattr(process_eval, "events", []))
        state = str(labels.get("safety_state", "safe"))
        process_state = str(getattr(process_eval, "state", "safe"))
        if process_state == "trip" or trip_faults:
            state = "trip"
        elif process_state == "alarm" or alarm_faults:
            state = "alarm"
        else:
            state = "safe"

        merged["alarm_faults"] = sorted(alarm_faults)
        merged["trip_faults"] = sorted(trip_faults)
        merged["alarm_count"] = float(len(merged["alarm_faults"]))
        merged["trip_count"] = float(len(merged["trip_faults"]))
        merged["safety_state"] = state
        merged["safety_active"] = 1.0 if state != "safe" else 0.0
        merged["event_log"] = event_log
        merged["event_log_latest"] = latest
        merged["event_log_history"] = history
        merged["trip_latch"] = float(1.0 if getattr(process_eval, "trip_latch", False) else 0.0)
        merged["trip_reset_condition"] = list(getattr(process_eval, "trip_reset_condition", []))
        return merged

    def _apply_safety_interlocks(
        self,
        control: dict[str, float],
        safety_state: str,
        safety_cfg: dict[str, Any],
        *,
        lockout_active: bool,
    ) -> tuple[dict[str, float], list[str], bool]:
        effective = dict(control)
        if not safety_cfg.get("enabled", True):
            # no safety action when disabled
            return effective, [], bool(lockout_active)

        state = str(safety_state or "safe").lower()
        alarm_cfg = _coerce_dict_payload(safety_cfg.get("alarm", {}))
        trip_cfg = _coerce_dict_payload(safety_cfg.get("trip", {}))
        enforce_lockout = bool(safety_cfg.get("lockout_on_trip", True))
        in_trip = state == "trip" or (lockout_active and enforce_lockout)

        if state == "alarm" and not in_trip:
            effective["fuel_cmd"] = float(np.clip(float(effective.get("fuel_cmd", 0.0)), 0.0, float(alarm_cfg.get("fuel_cmd_max", 1.0))))
            effective["fw_cmd"] = float(np.clip(float(effective.get("fw_cmd", 0.0)), 0.0, float(alarm_cfg.get("fw_cmd_max", 1.0))))
            effective["steam_demand"] = float(np.clip(float(effective.get("steam_demand", 0.0)), 0.0, float(alarm_cfg.get("steam_demand_max", 1.0))))
            return effective, ["safety_alarm_limited"], False

        if in_trip:
            effective["fuel_cmd"] = float(np.clip(float(trip_cfg.get("fuel_cmd", 0.0)), 0.0, 1.0))
            effective["fw_cmd"] = float(np.clip(float(trip_cfg.get("fw_cmd", 0.0)), 0.0, 1.0))
            effective["steam_demand"] = float(np.clip(float(trip_cfg.get("steam_demand", 0.0)), 0.0, 1.0))
            return effective, ["safety_trip_hard_stop"], enforce_lockout

        return effective, [], False

    def _append_performance_log(self, path: str, payload: dict[str, Any]) -> None:
        perf_path = Path(path)
        perf_path.parent.mkdir(parents=True, exist_ok=True)
        with perf_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _append_jsonl(self, path: str, payload: dict[str, Any]) -> None:
        self._append_performance_log(path, payload)

    def _schema_strict_mode(self, cfg: dict[str, Any]) -> bool:
        validation_cfg = _coerce_dict_payload(cfg.get("validation", {}))
        phase0_cfg = _coerce_dict_payload(cfg.get("phase0", cfg.get("phase_0", {})))
        phase5_cfg = _coerce_dict_payload(cfg.get("phase5", cfg.get("phase_5", {})))
        phase_cfg = _coerce_dict_payload(cfg.get("phase", {}))
        strict = _coerce_bool(phase_cfg.get("schema_strict", False))
        strict = strict or _coerce_bool(phase5_cfg.get("schema_strict", False))
        strict = strict or _coerce_bool(validation_cfg.get("schema_strict", False))
        strict = strict or _coerce_bool(phase0_cfg.get("schema_strict", False))
        strict = strict or _coerce_bool(validation_cfg.get("strict_schema", False))
        return strict

    def _apply_profile_presets(self, cfg: dict[str, Any]) -> dict[str, Any]:
        profile_name, profile_cfg = _extract_profile(cfg)
        if not profile_name:
            return cfg
        if not profile_cfg:
            warnings.warn(
                f"[PROFILE_WARNING] Unknown profile '{profile_name}'. "
                f"Known profiles: {sorted(_coerce_dict_payload(cfg.get('profiles', {})).keys())}",
                RuntimeWarning,
                stacklevel=2,
            )
            return cfg
        merged = _deep_update(cfg, profile_cfg)
        merged["runtime_profile"] = profile_name
        merged["profile"] = profile_name
        return merged

    def _warn_schema_mismatch(self, cfg: dict[str, Any], *, strict: bool = False) -> list[str]:
        schema_cfg = cfg.get("schema")
        if schema_cfg is None:
            schema_cfg = {
                "schema_name": cfg.get("schema_name", ""),
                "schema_version": cfg.get("schema_version", ""),
                "freeze_date": cfg.get("freeze_date", ""),
            }

        schema_cfg = _coerce_dict_payload(schema_cfg)
        schema_name = str(schema_cfg.get("name", schema_cfg.get("schema_name", ""))).strip()
        schema_version = str(schema_cfg.get("version", schema_cfg.get("schema_version", ""))).strip()
        freeze_date = str(schema_cfg.get("freeze_date", schema_cfg.get("freeze_date_text", ""))).strip()
        mismatches: list[str] = []
        snapshot = schema_contract_snapshot()

        if schema_name and schema_name != SCHEMA_NAME:
            msg = f"[SCHEMA_MISMATCH] schema_name='{schema_name}' != expected '{SCHEMA_NAME}'."
            mismatches.append(msg)
            if strict:
                raise RuntimeError(msg)
            warnings.warn(msg, RuntimeWarning, stacklevel=2)
        if schema_version and schema_version != SCHEMA_VERSION:
            msg = f"[SCHEMA_MISMATCH] schema_version='{schema_version}' != expected '{SCHEMA_VERSION}'."
            mismatches.append(msg)
            if strict:
                raise RuntimeError(msg)
            warnings.warn(msg, RuntimeWarning, stacklevel=2)
        if freeze_date and freeze_date != SCHEMA_FREEZE_DATE:
            msg = f"[SCHEMA_MISMATCH] freeze_date='{freeze_date}' != expected '{SCHEMA_FREEZE_DATE}'."
            mismatches.append(msg)
            if strict:
                raise RuntimeError(msg)
            warnings.warn(msg, RuntimeWarning, stacklevel=2)
        if str(snapshot.get("source", "")).strip() and not str(snapshot["source"]).endswith("spec_boiler_pdm_sim.md"):
            msg = f"[SCHEMA_WARNING] unexpected schema source marker: {snapshot['source']}"
            mismatches.append(msg)
            warnings.warn(msg, RuntimeWarning, stacklevel=2)

        return mismatches

    def _validate_label_contract_rows(self, rows: list[dict[str, Any]], *, strict: bool) -> tuple[bool, list[str], dict[str, Any]]:
        if not rows:
            return False, ["empty_rows"], {}
        failures: list[str] = []
        required = SCHEMA_LABEL_KEYS
        for idx, row in enumerate(rows):
            row_failures = validate_label_contract_row(row, required_keys=required, event_patterns=SCHEMA_LOCK["event_patterns"])
            for failure in row_failures:
                failures.append(f"row={idx}:{failure}")

        unique = list(dict.fromkeys(failures))
        if not strict and unique:
            warnings.warn(
                f"[LABEL_SCHEMA_WARNING] {len(unique)} label contract issue(s); first={unique[0]}",
                RuntimeWarning,
                stacklevel=2,
            )
        metrics = {
            "label_contract_failures": unique,
            "label_contract_failure_count": int(len(unique)),
            "label_contract_required_count": int(len(required)),
            "label_contract_valid": int(len(unique) == 0),
        }
        return len(unique) == 0, unique, metrics

    def _validate_algebraic_convergence(self, rows: list[dict[str, Any]], cfg: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
        val_cfg = _coerce_dict_payload(cfg.get("validation", {}))
        dae_cfg = _coerce_dict_payload(val_cfg.get("dae", {}))
        if not _coerce_bool(dae_cfg.get("enabled", False), default=False):
            return True, [], {}

        if not rows:
            return False, ["algebraic_validation_no_rows"], {}

        import pandas as pd  # local import to keep runtime dependency at validation callsite

        df = pd.DataFrame(rows)
        residual_after = pd.to_numeric(df.get("meta/algebraic_residual_m3"), errors="coerce")
        residual_before = pd.to_numeric(df.get("meta/algebraic_residual_before_m3"), errors="coerce")
        residual_gap = pd.to_numeric(df.get("meta/algebraic_residual_gap_m3"), errors="coerce")
        feasible = pd.to_numeric(df.get("meta/algebraic_feasible"), errors="coerce").fillna(0.0)
        if not isinstance(residual_after, pd.Series):
            residual_after = pd.Series([], dtype=float)
        if not isinstance(residual_before, pd.Series):
            residual_before = pd.Series([], dtype=float)
        if not isinstance(residual_gap, pd.Series):
            residual_gap = pd.Series([], dtype=float)

        residual_tol = float(dae_cfg.get("residual_tol", 1e-9))
        min_feasible_ratio = float(dae_cfg.get("min_feasible_ratio", 0.95))
        max_gap_negative = float(dae_cfg.get("max_gap_negative", 1e-12))
        max_ratio = float(dae_cfg.get("max_residual_ratio", 1.05))

        residual_after_valid = residual_after.to_numpy(dtype=float)
        residual_before_valid = residual_before.to_numpy(dtype=float)
        gap = residual_gap.to_numpy(dtype=float)
        finite_after = np.isfinite(residual_after_valid)
        failures: list[str] = []
        metrics: dict[str, Any] = {}

        if len(residual_after_valid) == 0:
            metrics["algebraic_residual_after_max_abs"] = float("inf")
            return False, ["meta/algebraic_residual_m3 missing"], metrics

        finite_after_values = residual_after_valid[np.isfinite(residual_after_valid)]
        if finite_after_values.size == 0:
            metrics["algebraic_residual_after_max_abs"] = float("inf")
            return False, ["meta/algebraic_residual_m3 missing or non-finite"], metrics
        max_after = float(np.max(np.abs(finite_after_values)))
        metrics["algebraic_residual_after_max_abs"] = max_after
        metrics["algebraic_feasible_ratio"] = float(np.mean(feasible.to_numpy(dtype=float)))

        if max_after > residual_tol:
            failures.append(f"algebraic_residual_after_max_abs={max_after:.6g}>{residual_tol}")

        finite_feasible_ratio = float(np.mean(feasible.to_numpy(dtype=float) >= 0.5)) if len(feasible) else 0.0
        if finite_feasible_ratio < min_feasible_ratio:
            failures.append(f"algebraic_feasible_ratio={finite_feasible_ratio:.6g} < {min_feasible_ratio}")
        # convergence check: residual should not increase for finite samples
        converging = np.ones_like(finite_after, dtype=bool)
        with np.errstate(invalid="ignore", divide="ignore"):
            converging = finite_after & np.isfinite(residual_before_valid)
        if converging.any():
            before = np.abs(residual_before_valid[converging])
            after = np.abs(residual_after_valid[converging])
            with np.errstate(invalid="ignore", divide="ignore"):
                ratios = _safe_ratio(after, before, default=np.nan)
            ratios_clean = ratios[np.isfinite(ratios)]
            if ratios_clean.size > 0:
                ratio_max = float(np.max(ratios_clean))
                ratio_min = float(np.min(ratios_clean))
                metrics["algebraic_residual_ratio_max"] = ratio_max
                metrics["algebraic_residual_ratio_min"] = ratio_min
                metrics["algebraic_residual_reduction_ratio"] = float(np.mean(np.nan_to_num(1.0 - ratios_clean)))
                if ratio_max > max_ratio:
                    failures.append(f"algebraic_residual_ratio_max={ratio_max:.6g} > {max_ratio}")
        if gap.size and np.nanmin(gap) < -max_gap_negative:
            failures.append(f"algebraic_residual_gap_min={np.nanmin(gap):.6g} < {-max_gap_negative}")

        return len(failures) == 0, failures, metrics

    def _load_latest_performance_entry(self, path: str) -> dict[str, Any] | None:
        perf_path = Path(path)
        if not perf_path.exists():
            return None
        text = perf_path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        line = text.splitlines()[-1]
        try:
            return json.loads(line)
        except Exception:
            return None

    def _evaluate_bottleneck(self, current_perf: dict[str, Any], bottleneck_cfg: dict[str, Any]) -> dict[str, Any]:
        cfg = _coerce_dict_payload(bottleneck_cfg)
        if not _coerce_bool(cfg.get("enabled", False)):
            return {"enabled": False}

        baseline_path = str(cfg.get("baseline_log_path", ""))
        if not baseline_path:
            return {"enabled": False, "status": "baseline_path_missing"}
        baseline = self._load_latest_performance_entry(baseline_path)
        if not isinstance(baseline, dict):
            return {"enabled": False, "status": "baseline_load_failed", "baseline_log_path": baseline_path}

        base_stage = _coerce_dict_payload(baseline.get("stage_seconds", {}))
        cur_stage = _coerce_dict_payload(current_perf.get("stage_seconds", {}))
        base_total = float(sum(float(v) for v in base_stage.values()))
        cur_total = float(sum(float(v) for v in cur_stage.values()))
        base_rps = float(baseline.get("rows_per_second", 0.0))
        cur_rps = float(current_perf.get("rows_per_second", 0.0))

        throughput_ratio = _safe_ratio(cur_rps, base_rps, default=float("nan"))
        stage_ratio_limit = float(cfg.get("stage_share_ratio_max", 1.30))
        throughput_min_ratio = float(cfg.get("throughput_min_ratio", 0.90))
        fail_on_regression = _coerce_bool(cfg.get("fail_on_regression", False))

        stage_report: dict[str, dict[str, float]] = {}
        failures: list[str] = []
        for stage in sorted(set(base_stage) | set(cur_stage)):
            cur_time = float(cur_stage.get(stage, 0.0))
            base_time = float(base_stage.get(stage, 0.0))
            cur_share = _safe_ratio(cur_time, cur_total, default=0.0)
            base_share = _safe_ratio(base_time, base_total, default=0.0)
            ratio = _safe_ratio(cur_time, base_time, default=float("inf"))
            delta = cur_time - base_time
            stage_report[stage] = {
                "current_seconds": cur_time,
                "baseline_seconds": base_time,
                "current_share": cur_share,
                "baseline_share": base_share,
                "time_ratio": ratio,
                "delta_seconds": delta,
            }
            if base_share > 0.0 and ratio > stage_ratio_limit:
                failures.append(f"stage_{stage}_time_ratio={ratio:.6g}>{stage_ratio_limit}")
            if base_share <= 0.0 < cur_share:
                failures.append(f"stage_{stage}_appeared={cur_share:.6g}")

        report = {
            "enabled": True,
            "baseline_log_path": baseline_path,
            "baseline_rows_per_second": base_rps,
            "current_rows_per_second": cur_rps,
            "throughput_ratio": throughput_ratio,
            "throughput_min_ratio": throughput_min_ratio,
            "stage_ratio_limit": stage_ratio_limit,
            "stage_reports": stage_report,
            "fail_on_regression": fail_on_regression,
            "failures": failures,
            "ci_fail": bool(fail_on_regression and (throughput_ratio < throughput_min_ratio or failures)),
        }

        if throughput_ratio < throughput_min_ratio:
            report["failures"] = [f"rows_per_second_ratio={throughput_ratio:.6g} < {throughput_min_ratio}"] + report["failures"]
        return report

    def _apply_phase15_analysis(self, rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
        analysis_cfg = _coerce_dict_payload(cfg.get("analysis", {}))
        if not analysis_cfg:
            analysis_cfg = _coerce_dict_payload(cfg.get("phase_15", {}))
        if not analysis_cfg:
            return {}
        strict = self._schema_strict_mode(cfg)
        analysis_cfg, issues = _coerce_phase15_analysis_config(analysis_cfg)
        if issues:
            msg = "[PHASE15_SCHEMA] " + "; ".join([str(item) for item in issues[:20]])
            if strict:
                raise RuntimeError(msg)
            warnings.warn(msg, RuntimeWarning, stacklevel=2)
        if not isinstance(analysis_cfg, dict) or not analysis_cfg:
            return {}

        from .research import (
            build_baseline_profile,
            compare_to_baseline,
            compute_identifiability,
            compute_local_signal_sensitivity,
        )

        out: dict[str, Any] = {}
        baseline_cfg = _coerce_dict_payload(analysis_cfg.get("baseline", {}))
        if baseline_cfg.get("enabled", False):
            channels = baseline_cfg.get("channels")
            out["baseline"] = build_baseline_profile(
                rows,
                channels=tuple(channels) if isinstance(channels, (list, tuple)) else None,
            )
            if baseline_cfg.get("compare", False):
                ref = baseline_cfg.get("reference")
                if isinstance(ref, dict):
                    out["baseline"]["reference_match"] = compare_to_baseline(
                        rows,
                        ref,
                        channels=tuple(channels) if isinstance(channels, (list, tuple)) else None,
                        abs_tol=float(baseline_cfg.get("abs_tol", 0.2)),
                    )

        identify_cfg = _coerce_dict_payload(analysis_cfg.get("identify", {}))
        if identify_cfg.get("enabled", False):
            fault_key = str(identify_cfg.get("fault_key", "label/fault_type"))
            channels = identify_cfg.get("channels")
            out["identify"] = compute_identifiability(
                rows,
                fault_key=fault_key,
                channels=tuple(channels) if isinstance(channels, (list, tuple)) else None,
            )

        sensitivity_cfg = _coerce_dict_payload(analysis_cfg.get("sensitivity", {}))
        if sensitivity_cfg.get("enabled", False):
            signal = "obs/drum_level"
            if isinstance(sensitivity_cfg.get("signal"), str):
                signal = str(sensitivity_cfg["signal"])
            values = [float(r[signal]) for r in rows if signal in r and r[signal] is not None]
            out["sensitivity"] = compute_local_signal_sensitivity(
                values,
                epsilon=float(sensitivity_cfg.get("epsilon", 1e-3)),
                window=int(max(3, float(sensitivity_cfg.get("window", 10)))),
            )
        return out

    def _validate_rows(self, rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
        import pandas as pd  # local import to keep runtime dependency only at validation callsite
        from .validation.step_response import check_shrink_swell_event_consistency
        from .validation.regression import acceptance_thresholds

        if not rows:
            return {"passed": False, "failures": ["empty_rows"], "n_rows": 0}

        df = pd.DataFrame(rows)
        strict_schema = self._schema_strict_mode(cfg)
        label_contract_passed, label_contract_failures, label_contract_metrics = self._validate_label_contract_rows(rows, strict=strict_schema)
        val_cfg = _coerce_scalars(deepcopy(cfg.get("validation", {})))
        required_cols = _coerce_list(val_cfg.get("required_output_columns"))
        if not required_cols:
            required_cols = [
                "truth/flue_gas_temp",
                "truth/O2",
                "truth/h_fw",
            ]

        required_failures = [f"required_output_missing:{col}" for col in required_cols if col not in df.columns]

        mass_tol = float(val_cfg.get("mass_tol", 50.0))
        energy_tol = float(val_cfg.get("energy_tol", 3e7))
        failures: list[str] = []
        failures.extend(required_failures)
        metrics: dict[str, Any] = {}
        metrics.update(label_contract_metrics)
        if not label_contract_passed:
            failures.extend([f"label_contract:{msg}" for msg in label_contract_failures[:25]])

        dae_passed, dae_failures, dae_metrics = self._validate_algebraic_convergence(rows, cfg)
        metrics.update(dae_metrics)
        if not dae_passed:
            failures.extend([f"algebraic_convergence:{msg}" for msg in dae_failures])
        dt = float(cfg["sim"].get("dt", 1.0))
        if dt <= 0.0 or not np.isfinite(dt):
            dt = 1.0

        for col, limit in (("truth/mass_balance_residual", mass_tol), ("truth/energy_balance_residual", energy_tol)):
            if col in df.columns:
                vals = pd.to_numeric(df[col], errors="coerce")
                valid = vals.dropna().to_numpy(dtype=float)
                if len(valid) == 0:
                    max_abs = float("inf")
                    mean_abs = float("nan")
                    finite_ratio = 0.0
                else:
                    max_abs = float(np.max(np.abs(valid)))
                    mean_abs = float(np.mean(np.abs(valid)))
                    finite_ratio = float(np.isfinite(valid).mean())

                metrics[f"{col}_max_abs"] = max_abs
                metrics[f"{col}_mean_abs"] = mean_abs
                metrics[f"{col}_finite_ratio"] = finite_ratio
                if max_abs > limit:
                    failures.append(f"{col}_max={max_abs:.6g} > {limit}")

        if "obs/drum_level" in df.columns:
            level = pd.to_numeric(df["obs/drum_level"], errors="coerce").to_numpy(dtype=float)
            level_ok = level[np.isfinite(level)]
            if len(level_ok) > 0:
                metrics["obs_drum_level_mean"] = float(np.mean(level_ok))
                metrics["obs_drum_level_std"] = float(np.std(level_ok))
                metrics["obs_drum_level_span"] = float(np.max(level_ok) - np.min(level_ok))

        drum_level_cfg = _coerce_dict_payload(val_cfg.get("drum_level_kpi", {}))
        if drum_level_cfg.get("enabled", False):
            event_log = df.get("label/event_log", [])
            acc = check_shrink_swell_event_consistency(
                df.get("obs/drum_level", []),
                df.get("meta/steam_demand_cmd", []),
                dt=dt,
                event_log=event_log,
                event_window_s=float(drum_level_cfg.get("event_window_s", 420.0)),
                min_excursion=float(drum_level_cfg.get("min_excursion", 0.003)),
                min_recover=float(drum_level_cfg.get("min_recover", 0.0025)),
                recovery_ratio=float(drum_level_cfg.get("recovery_ratio", 0.35)),
                implicit_window_s=float(drum_level_cfg.get("implicit_window_s", 240.0)),
                implicit_delta=float(drum_level_cfg.get("implicit_delta", 0.06)),
            )
            metrics["drum_level_kpi"] = dict(acc)
            if bool(drum_level_cfg.get("required", False)) and not bool(acc.get("passed", False)):
                failures.append("drum_level_kpi_failed")

        acceptance_cfg = _coerce_dict_payload(val_cfg.get("acceptance", {}))
        if acceptance_cfg:
            acc = acceptance_thresholds(metrics, acceptance_cfg)
            metrics["acceptance"] = acc
            if not bool(acc.get("passed", False)):
                failures.extend([str(item) for item in acc.get("failures", [])])

        if failures:
            return {
                "passed": False,
                "failures": failures,
                "n_rows": int(len(df)),
                "metrics": metrics,
            }
        return {
            "passed": True,
            "failures": [],
            "n_rows": int(len(df)),
            "metrics": metrics,
        }

    def _load_fault_specs(self, fault_instances: list[Any] | tuple[Any, ...]) -> list[dict]:
        specs: list[dict] = []
        for fp in fault_instances or []:
            if isinstance(fp, dict):
                specs.append(_coerce_scalars(deepcopy(fp)))
                continue
            if not isinstance(fp, (str, Path)):
                continue
            path = Path(fp)
            if not path.exists():
                path = Path(__file__).resolve().parents[2] / fp
            if path.exists():
                loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    specs.append(_coerce_scalars(loaded))
        return specs

    def _flatten_row(
        self,
        time_s: float,
        scenario_id: str,
        truth: dict,
        obs: dict,
        labels: dict,
        inv: dict,
        meta: dict,
    ) -> dict:
        labels_get = labels.get
        fault_type = labels_get("fault_type")
        if isinstance(fault_type, (list, tuple)):
            fault_type = str(fault_type[0]) if fault_type else "none"
        elif fault_type in (None, "", "none"):
            fault_type = "none"
        else:
            fault_type = str(fault_type)

        fault_types = labels_get("fault_types")
        if isinstance(fault_types, (list, tuple)):
            fault_types = [str(v) for v in fault_types]
        elif fault_type == "none":
            fault_types = []
        else:
            fault_types = [fault_type]

        # Canonical schema:
        # - label/event_log: only step-local events (fault/control at this timestamp)
        # - label/event_log_latest: alias of step-local events for explicit consumption
        # - label/event_log_history: cumulative event stream from t=0..current
        event_log = _as_event_list(labels_get("event_log", []))
        event_log_latest = _as_event_list(labels_get("event_log_latest", event_log))
        event_log_history = _as_event_list(labels_get("event_log_history", []))
        fault_names = labels_get("fault_names", [])
        alarm_faults = labels_get("alarm_faults", [])
        trip_faults = labels_get("trip_faults", [])
        fault_names_list = [str(v) for v in fault_names] if isinstance(fault_names, (list, tuple)) else []
        alarm_faults_list = [str(v) for v in alarm_faults] if isinstance(alarm_faults, (list, tuple)) else []
        trip_faults_list = [str(v) for v in trip_faults] if isinstance(trip_faults, (list, tuple)) else []
        event_log_list = [str(v) for v in event_log]
        event_log_history_list = [str(v) for v in event_log_history]
        event_log_latest_list = [str(v) for v in event_log_latest]
        numeric_types = (int, float, np.floating)
        truth_prefix = "truth/"
        obs_prefix = "obs/"

        row: dict[str, object] = {"time": time_s, "scenario_id": scenario_id}
        for k, v in truth.items():
            row[truth_prefix + k] = v if type(v) is float else (float(v) if isinstance(v, numeric_types) else v)
        for k, v in obs.items():
            row[obs_prefix + k] = v if type(v) is float else (float(v) if isinstance(v, numeric_types) else v)
        row["label/fault_type"] = fault_type
        row["label/fault_types"] = fault_types
        row["label/fault_type_count"] = float(0 if fault_type == "none" else 1)
        row["label/fault_names"] = fault_names_list
        row["label/fault_severity"] = float(labels["fault_severity"])
        row["label/anomaly_flag"] = float(labels_get("anomaly_flag", 0.0))
        row["label/RUL"] = float(labels["RUL"])
        row["label/RUL_current_mission"] = float(labels_get("RUL_current_mission", labels["RUL"]))
        row["label/RUL_reference_mission"] = float(labels_get("RUL_reference_mission", labels["RUL"]))
        row["label/censored"] = float(labels_get("censored", 1.0))
        row["label/failure_threshold_name"] = str(labels_get("failure_threshold_name", "none"))
        row["label/fault_onset"] = float(labels_get("fault_onset", -1.0))
        row["label/symptom_onset"] = float(labels_get("symptom_onset", -1.0))
        row["label/anomaly_detectable_onset"] = float(labels_get("anomaly_detectable_onset", -1.0))
        row["label/threshold_crossing"] = float(labels_get("threshold_crossing", -1.0))
        row["label/trip_time"] = float(labels_get("trip_time", -1.0))
        row["label/safety_state"] = str(labels_get("safety_state", "safe"))
        row["label/safety_active"] = float(labels_get("safety_active", 0.0))
        row["label/alarm_count"] = float(labels_get("alarm_count", 0.0))
        row["label/trip_count"] = float(labels_get("trip_count", 0.0))
        row["label/trip_latch"] = float(labels_get("trip_latch", 0.0))
        row["label/trip_reset_condition"] = [str(v) for v in labels_get("trip_reset_condition", [])] if isinstance(labels_get("trip_reset_condition", []), (list, tuple)) else []
        row["label/alarm_faults"] = alarm_faults_list
        row["label/trip_faults"] = trip_faults_list
        row["label/event_log"] = event_log_list
        row["label/event_log_history"] = event_log_history_list
        row["label/event_log_latest"] = event_log_latest_list
        if "truth/drum_level" in row and "truth/level_true" not in row:
            row["truth/level_true"] = float(row["truth/drum_level"])
        if "obs/drum_level" in row:
            drum_level_obs = float(row["obs/drum_level"])
            row.setdefault("obs/drum_level_compensated", drum_level_obs)
        row["meta/fault_feature_name"] = str(labels_get("fault_feature_name", "none"))
        row["meta/fault_feature_value"] = float(labels_get("fault_feature_value", 0.0))
        row["meta/fault_feature_reference"] = float(labels_get("fault_feature_reference", 1.0))
        row["meta/fault_schedule_severity"] = float(labels_get("fault_schedule_severity", 0.0))
        row["meta/fault_mission_factor"] = float(labels_get("fault_mission_factor", 1.0))
        for k, v in inv.items():
            row[truth_prefix + k] = float(v)
        for k, v in meta.items():
            row[f"meta/{k}"] = v
        parameter_draw = str(self._pipeline_meta.get("parameter_draw_id", "none"))
        fault_instance_id = str(self._pipeline_meta.get("fault_instance_id", "none"))
        row.setdefault("meta/parameter_draw", parameter_draw)
        row.setdefault("meta/fault_instance_id", fault_instance_id)
        row.setdefault("meta/scenario_group_id", f"{scenario_id}|{parameter_draw}|{fault_instance_id}")
        return row

    def run(self, config: dict | str) -> list[dict]:
        cfg = _coerce_scalars(deepcopy(config))
        if isinstance(config, (str, Path)):
            cfg = _coerce_scalars(yaml.safe_load(Path(config).read_text(encoding="utf-8")))
        cfg = self._apply_profile_presets(_coerce_dict_payload(cfg))
        runtime_cfg = RuntimeConfig.from_mapping(cfg)
        strict_schema = bool(runtime_cfg.validation.schema_strict)
        if isinstance(cfg, dict):
            strict_schema = strict_schema or self._schema_strict_mode(cfg)
            self._warn_schema_mismatch(cfg, strict=strict_schema)

        dt = float(runtime_cfg.sim.dt)
        if dt <= 0.0 or not np.isfinite(dt):
            dt = 1.0
        horizon = int(float(runtime_cfg.sim.horizon_s) / dt)
        self._last_run_timing = {
            "control_seconds": 0.0,
            "model_seconds": 0.0,
            "label_seconds": 0.0,
            "align_seconds": 0.0,
            "write_seconds": 0.0,
        }
        self._last_algebraic_timing = {
            "iterations": 0,
            "residuals": [],
            "feasible_count": 0,
        }
        scenario_cfg = dict(runtime_cfg.scenario.raw)
        scenario_rng_seed = runtime_cfg.scenario.seed
        # Validate the solver name up front so a config typo fails before any
        # expensive preprocessing (and on backend paths that never integrate).
        method = normalize_method(str(runtime_cfg.sim.solver))
        seed = int(runtime_cfg.sim.seed)
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        scenario_rng = np.random.default_rng(int(scenario_rng_seed)) if scenario_rng_seed is not None else self.rng
        time_jitter = max(0.0, float(runtime_cfg.sim.timestamp_jitter_s))
        controller_dt = max(dt, float(runtime_cfg.sim.controller_dt_s)) if float(runtime_cfg.sim.controller_dt_s) > 0.0 else dt
        sensor_dt = max(dt, float(runtime_cfg.sim.sensor_dt_s)) if float(runtime_cfg.sim.sensor_dt_s) > 0.0 else dt
        logger_dt = max(dt, float(runtime_cfg.sim.logger_dt_s)) if float(runtime_cfg.sim.logger_dt_s) > 0.0 else dt
        calibration_cfg, calibration_report = resolve_runtime_calibration(
            cfg,
            default_seed=self.seed,
            run_probe=lambda probe_cfg, probe_seed: Simulator(seed=probe_seed).run(probe_cfg),
        )

        base = _coerce_scalars(deepcopy(runtime_cfg.boiler.raw))
        base, calibration_applied = apply_calibration_to_boiler(base, calibration_cfg)
        base, ident_report = self._apply_identifiability(base, cfg.get("identifiability", {}))
        randomization_cfg = _coerce_scalars(deepcopy(runtime_cfg.randomization.raw))
        if ident_report.get("enabled", False):
            randomization_cfg.setdefault("identifiability_constraints", {})
            randomization_cfg["identifiability_constraints"]["lock_keys"] = list(ident_report.get("locked_randomization_keys", []))
            randomization_cfg["identifiability_constraints"]["groups"] = dict(ident_report.get("randomization_groups", {}))
        base = apply_randomization(base, randomization_cfg, self.rng)
        safety_cfg = self._coerce_safety_config(runtime_cfg.safety.raw)
        self._pipeline_meta = {
            "order": ["calibration", "identifiability", "randomization"],
            "calibration_applied": bool(calibration_applied),
            "calibration": build_calibration_report_payload(calibration_cfg, calibration_report),
            "identifiability_applied": bool(ident_report.get("applied", False)),
            "identifiability": ident_report,
            "randomization_enabled": bool(randomization_cfg.get("enable", True)),
            "timebase": {
                "plant_dt_s": float(dt),
                "controller_dt_s": float(controller_dt),
                "sensor_dt_s": float(sensor_dt),
                "logger_dt_s": float(logger_dt),
            },
            "fmu_contract": build_fmu_contract(runtime_cfg.core_backend.raw),
        }
        system = build_core_backend(base, runtime_cfg.core_backend.raw)
        # freeze sensor model early (sensor chain, especially drum_level)
        fixed_sensor_channels = tuple(str(v) for v in ident_report.get("fixed_sensor_channels", ()))
        sensor_cfg = self._freeze_sensor_config(deepcopy(runtime_cfg.sensors.raw), fixed_sensor_channels)
        sensor_cfg = self._apply_sensor_timebase_defaults(sensor_cfg, sample_period_s=sensor_dt)
        drum_level_cfg = sensor_cfg.setdefault("drum_level", {})
        if isinstance(drum_level_cfg, dict):
            nominal = base.get("nominal", {}) if isinstance(base.get("nominal", {}), dict) else {}
            geometry = base.get("geometry", {}) if isinstance(base.get("geometry", {}), dict) else {}
            drum_level_cfg.setdefault("nominal_pressure_bar", float(nominal.get("pressure_bar", 10.0)))
            drum_level_cfg.setdefault("reference_leg_height_m", float(geometry.get("drum_length_m", 6.0)))
            drum_level_cfg.setdefault("reference_leg_temp_C", 60.0)
            drum_level_cfg.setdefault("reference_leg_temp_shift_C", 0.0)
            drum_level_cfg.setdefault("wet_leg_density_scale", 1.0)
            drum_level_cfg.setdefault("impulse_line_plugging", 0.0)
            drum_level_cfg.setdefault("bad_calibration_bias_m", 0.0)
        # keep params shape expected by model
        params = {"boiler": base, "sensors": deepcopy(sensor_cfg)}
        fault_specs = self._load_fault_specs(list(runtime_cfg.faults.instances))
        self._pipeline_meta["parameter_draw_id"] = _safe_hash_config({"boiler": base})
        self._pipeline_meta["fault_instance_id"] = _safe_hash_config({"fault_instances": fault_specs})
        scheduler = DegradationScheduler(fault_specs, self.rng)
        controller = BoilerControl.from_config(runtime_cfg.control.to_mapping())
        profile = build_profile(scenario_cfg, scenario_rng)
        sensor_model = SensorModel(sensor_cfg, self.rng)
        process_safety = ProcessSafetyMonitor(safety_cfg)
        return execute_step_loop(
            self,
            cfg=cfg,
            system=system,
            controller=controller,
            scheduler=scheduler,
            profile=profile,
            sensor_model=sensor_model,
            process_safety=process_safety,
            params=params,
            safety_cfg=safety_cfg,
            seed=seed,
            dt=dt,
            controller_dt=controller_dt,
            logger_dt=logger_dt,
            horizon=horizon,
            method=method,
            time_jitter=time_jitter,
            strict_schema=strict_schema,
        )

    def run_to_file(self, config: dict | str, out: str, fmt: str | None = None) -> Path:
        cfg = config
        if isinstance(config, (str, Path)):
            cfg = yaml.safe_load(Path(config).read_text(encoding="utf-8"))
        cfg = self._apply_profile_presets(_coerce_dict_payload(cfg))
        runtime_cfg = RuntimeConfig.from_mapping(cfg)
        cfg_fmt = runtime_cfg.sim.fmt if isinstance(cfg, dict) else None
        fmt = fmt if fmt is not None else cfg_fmt
        perf_cfg: dict[str, Any] = {}
        if isinstance(cfg, dict):
            perf_cfg = dict(runtime_cfg.performance.raw)
        split_cfg = resolve_split_config(runtime_cfg) if isinstance(cfg, dict) else None
        perf_enabled = bool(
            isinstance(cfg, dict)
            and (
                runtime_cfg.sim.collect_performance
                or runtime_cfg.performance.enabled
            )
        )
        collect_memory = bool(runtime_cfg.performance.collect_memory) if perf_enabled else False
        phase6_result = run_optional_validation_battery(self, cfg=cfg, runtime_cfg=runtime_cfg, out=out) if isinstance(cfg, dict) else {"enabled": False}

        if perf_enabled and collect_memory:
            import tracemalloc

            tracemalloc.start()
        run_t0 = perf_counter() if perf_enabled else None
        rows = self.run(cfg)
        run_elapsed = (perf_counter() - run_t0) if run_t0 is not None else 0.0
        if isinstance(cfg, dict):
            record_analysis(self, rows=rows, cfg=cfg, runtime_cfg=runtime_cfg)
        validation = self._validate_rows(rows, cfg)
        write_start = perf_counter()
        provenance = build_provenance(
            self,
            cfg=cfg if isinstance(cfg, dict) else {},
            runtime_cfg=runtime_cfg,
            validation=validation,
            phase6_result=phase6_result,
            split_cfg=split_cfg,
        )
        out_path = write_dataset(
            rows,
            out,
            fmt,
            split_cfg=split_cfg,
            split_seed=self.seed,
            provenance=provenance,
            validation=validation,
            validation_battery=phase6_result,
            lock_provenance=True,
        )
        write_elapsed = perf_counter() - write_start
        calibration_sidecar = write_calibration_sidecar(out_path, self._pipeline_meta, dict(runtime_cfg.analysis.raw))
        if calibration_sidecar is not None:
            self._pipeline_meta["calibration_report"] = {"path": str(calibration_sidecar)}
        if perf_enabled:
            bottleneck_report = record_performance_outputs(
                self,
                cfg=cfg,
                perf_cfg=perf_cfg,
                out=out,
                rows=rows,
                validation=validation,
                validation_battery=phase6_result,
                run_elapsed=run_elapsed,
                write_elapsed=write_elapsed,
            )
            if bool(bottleneck_report.get("ci_fail", False)):
                failures = _coerce_list(bottleneck_report.get("failures", []))
                raise RuntimeError(
                    "Performance bottleneck CI policy failed: " + ", ".join(_coerce_list(failures))
                )
        enforce_inline_governance(
            out_path=out_path,
            governance_cfg=dict(runtime_cfg.governance.raw),
            pipeline_meta=self._pipeline_meta,
        )
        if not bool(validation.get("passed", False)):
            failures = validation.get("failures", [])
            raise RuntimeError(f"Validation failed before writing dataset: {failures}")
        return out_path
