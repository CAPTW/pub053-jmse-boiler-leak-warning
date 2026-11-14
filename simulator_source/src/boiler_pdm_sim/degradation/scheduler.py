"""Fault scheduler with severity progression and label state."""

from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
from typing import Any

from . import burner_deg
from . import fouling
from . import pump_wear
from . import sensor_faults
from . import tube_leak
from . import valve_stiction


def _severity_from_cfg(cfg: dict[str, Any], t: float) -> float:
    onset = float(cfg.get("onset_s", 0.0))
    duration = float(cfg.get("duration_s", 1.0))
    sev_cfg = cfg.get("severity", {})
    kind = str(sev_cfg.get("kind", "linear"))
    s_min = float(sev_cfg.get("min", 0.0))
    s_max = float(sev_cfg.get("max", 1.0))
    if t < onset:
        return 0.0
    if duration <= 1e-9:
        return float(s_max)
    x = max(0.0, min(1.0, (t - onset) / duration))
    if kind == "exp":
        sev = 1.0 - (1.0 - x) ** 2
    else:
        sev = x
    return float(s_min + (s_max - s_min) * sev)


@dataclass
class FaultState:
    active_types: list[str] = field(default_factory=list)
    fault_types: list[str] = field(default_factory=list)
    safety_state: str = "safe"
    safety_trip_faults: list[str] = field(default_factory=list)
    safety_alarm_faults: list[str] = field(default_factory=list)
    severity: float = 0.0
    anomaly: int = 0
    latest_events: list[str] = field(default_factory=list)
    event_log: list[str] = field(default_factory=list)
    fault_last_severity: dict[str, float] = field(default_factory=dict)
    fault_last_schedule: dict[str, float] = field(default_factory=dict)
    fault_feature_values: dict[str, float] = field(default_factory=dict)
    fault_feature_names: dict[str, str] = field(default_factory=dict)
    fault_feature_references: dict[str, float] = field(default_factory=dict)


class DegradationScheduler:
    """Apply fault parameter drift and produce PdM labels."""

    def __init__(self, fault_configs: list[dict[str, Any]], rng=None) -> None:
        self.fault_configs = list(fault_configs)
        self.rng = rng
        self._entered: set[str] = set()
        self._threshold_reached: set[str] = set()
        self._trip_reached: set[str] = set()
        self._alarm_reached: set[str] = set()
        self._onset_times: dict[str, float] = {}
        self._symptom_onset_times: dict[str, float] = {}
        self._detectable_onset_times: dict[str, float] = {}
        self._threshold_times: dict[str, float] = {}
        self._trip_times: dict[str, float] = {}
        self._base_params: dict[str, Any] | None = None
        self.state = FaultState()

    def _feature_proxy(self, cfg: dict[str, Any], params: dict[str, Any]) -> tuple[str, float, float, float]:
        ftype = str(cfg.get("type", "none"))
        degradation = params.get("degradation", {}) if isinstance(params, dict) else {}
        feature_name = "none"
        feature_value = 0.0
        reference = 1.0

        if ftype == "fouling":
            feature_name = "ua_loss_ratio"
            feature_value = max(0.0, 1.0 - float(degradation.get("ua_scale", 1.0)))
            reference = max(1e-6, float(cfg.get("alpha", 0.35)))
        elif ftype == "tube_leak":
            feature_name = "tube_leak_coeff"
            feature_value = max(0.0, float(degradation.get("tube_leak_coeff", 0.0)))
            reference = max(1e-6, float(cfg.get("k_leak_kg_s_per_sqrtbar", 0.003)))
        elif ftype == "valve_stiction":
            feature_name = "valve_stiction"
            feature_value = max(0.0, float(degradation.get("valve_stiction", 0.0)))
            reference = max(1e-6, float(cfg.get("stiction_gain", 0.20)))
        elif ftype == "sensor_drift":
            feature_name = "sensor_drift_per_hour"
            targets = cfg.get("targets", [])
            current_sensors = params.get("sensors", {}) if isinstance(params.get("sensors", {}), dict) else {}
            base_sensors = {}
            if self._base_params is not None and isinstance(self._base_params.get("sensors", {}), dict):
                base_sensors = self._base_params.get("sensors", {})
            max_delta = 0.0
            for target in targets if isinstance(targets, (list, tuple)) else []:
                current_cfg = current_sensors.get(target, {})
                base_cfg = base_sensors.get(target, {})
                if not isinstance(current_cfg, dict) or not isinstance(base_cfg, dict):
                    continue
                current = float(current_cfg.get("drift_per_hour", 0.0))
                base = float(base_cfg.get("drift_per_hour", 0.0))
                max_delta = max(max_delta, abs(current - base))
            feature_value = max_delta
            reference = max(1e-6, abs(float(cfg.get("drift_per_hour", 0.0))) or 1e-6)
        elif ftype == "burner_deg":
            feature_name = "combustion_efficiency_loss"
            if self._base_params is not None:
                base_eta = float(self._base_params["boiler"]["parameters"]["combustion"]["eta"])
            else:
                base_eta = 1.0
            eta_now = float(degradation.get("eta_comb", base_eta))
            feature_value = max(0.0, 1.0 - eta_now / max(base_eta, 1e-6))
            reference = max(1e-6, float(cfg.get("max_eta_drop", 0.30)))
        elif ftype == "pump_wear":
            feature_name = "pump_wear"
            feature_value = max(0.0, float(degradation.get("pump_wear", 0.0)))
            reference = max(1e-6, float(cfg.get("max_wear", 0.45)))

        severity = max(0.0, min(1.0, feature_value / max(reference, 1e-6)))
        return feature_name, float(feature_value), float(reference), float(severity)

    def update(self, t: float, params: dict[str, Any]) -> dict[str, Any]:
        if self._base_params is None:
            self._base_params = deepcopy(params)

        p = dict(self._base_params)
        p["degradation"] = {}

        combined = 0.0
        event_log = []
        active_types: list[str] = []
        active_faults: list[str] = []

        for cfg in self.fault_configs:
            ftype = str(cfg.get("type", "none"))
            name = str(cfg.get("name", ftype))
            schedule_sev = _severity_from_cfg(cfg, t)
            prev_sev = self.state.fault_last_severity.get(name, 0.0)
            if schedule_sev <= 0.0:
                self.state.fault_last_severity[name] = 0.0
                self.state.fault_last_schedule[name] = 0.0
                self.state.fault_feature_values[name] = 0.0
                continue

            self.state.fault_last_schedule[name] = float(schedule_sev)
            active_types.append(ftype)
            active_faults.append(name)
            if name not in self._entered:
                self._entered.add(name)
                self._onset_times.setdefault(name, float(t))
                self._symptom_onset_times.setdefault(name, float(t))
                event_log.append(f"{name}_onset_t={t:.1f}")

            if ftype == "fouling":
                p = fouling.apply_fouling(
                    p,
                    schedule_sev,
                    alpha=float(cfg.get("alpha", 0.35)),
                    target=str(cfg.get("target")) if cfg.get("target") is not None else None,
                )
            elif ftype == "tube_leak":
                p = tube_leak.apply_tube_leak(
                    p,
                    schedule_sev,
                    coeff=float(cfg.get("k_leak_kg_s_per_sqrtbar", 0.003)),
                )
            elif ftype == "valve_stiction":
                p = valve_stiction.apply_stiction(
                    p,
                    schedule_sev,
                    deadband=float(cfg.get("deadband", 0.05)),
                    gain=float(cfg.get("stiction_gain", 0.20)),
                )
            elif ftype == "sensor_drift":
                p = sensor_faults.apply_sensor_drift(
                    p,
                    schedule_sev,
                    targets=cfg.get("targets", []),
                    drift_per_hour=float(cfg.get("drift_per_hour", 0.0)),
                    overrides=cfg,
                )
            elif ftype == "burner_deg":
                p = burner_deg.apply_burner_deg(
                    p,
                    schedule_sev,
                    eta_drop=float(cfg.get("max_eta_drop", 0.30)),
                    qmax_drop=float(cfg.get("max_qmax_drop", 0.20)),
                )
            elif ftype == "pump_wear":
                p = pump_wear.apply_pump_wear(
                    p,
                    schedule_sev,
                    max_wear=float(cfg.get("max_wear", 0.45)),
                )

            feature_name, feature_value, feature_ref, feature_sev = self._feature_proxy(cfg, p)
            combined = max(combined, feature_sev)
            self.state.fault_last_severity[name] = float(feature_sev)
            self.state.fault_feature_values[name] = float(feature_value)
            self.state.fault_feature_names[name] = str(feature_name)
            self.state.fault_feature_references[name] = float(feature_ref)

            if feature_sev > 0.02 and name not in self._detectable_onset_times:
                self._detectable_onset_times[name] = float(t)

            threshold = float(cfg.get("rul_threshold", 0.0))
            if threshold > 0.0 and prev_sev < threshold <= feature_sev and name not in self._threshold_reached:
                self._threshold_reached.add(name)
                self._threshold_times[name] = float(t)
                event_log.append(f"{name}_threshold_t={t:.1f}")
            trip_threshold = float(cfg.get("trip_threshold", 1.0))
            if trip_threshold > 0.0 and prev_sev < trip_threshold <= feature_sev and name not in self._trip_reached:
                self._trip_reached.add(name)
                self._trip_times[name] = float(t)
                event_log.append(f"{name}_trip_t={t:.1f}")

            alarm_threshold = float(cfg.get("alarm_threshold", 0.0))
            if alarm_threshold <= 0.0:
                alarm_threshold = threshold if threshold > 0.0 else 0.7
            if alarm_threshold > 0.0 and prev_sev < alarm_threshold <= feature_sev and name not in self._alarm_reached:
                self._alarm_reached.add(name)
                event_log.append(f"{name}_alarm_t={t:.1f}")

        alarm_faults = sorted(self._alarm_reached)
        trip_faults = sorted(self._trip_reached)
        safety_state = "trip" if trip_faults else ("alarm" if alarm_faults else "safe")

        self.state.latest_events = event_log
        self.state.active_types = active_types
        self.state.fault_types = active_faults
        self.state.safety_state = safety_state
        self.state.safety_alarm_faults = list(alarm_faults)
        self.state.safety_trip_faults = list(trip_faults)
        self.state.severity = combined
        self.state.anomaly = int(combined > 0.02)
        self.state.event_log.extend(event_log)
        return p

    def truth_labels(self, t: float, params: dict[str, Any], *, load_cmd: float | None = None) -> dict[str, Any]:
        # RUL = distance to threshold from currently active highest-severity diagnostic feature.
        _ = params
        rul = float("inf")
        active_faults: list[str] = []
        active_types: list[str] = []
        fault_severity = 0.0
        active_fault_weights: list[tuple[float, str, str]] = []
        dominant_fault_name = "none"
        failure_threshold_name = "none"

        for cfg in self.fault_configs:
            fault_type = str(cfg.get("type", "none"))
            name = str(cfg.get("name", fault_type))
            sev = float(self.state.fault_last_severity.get(name, 0.0))
            if sev <= 0.0:
                continue
            active_faults.append(name)
            active_types.append(fault_type)
            fault_severity = max(fault_severity, sev)
            active_fault_weights.append((sev, name, fault_type))

            thr = float(cfg.get("rul_threshold", 1.0))
            if sev <= 0.0 or thr <= 0.0:
                continue
            growth_rate = 1.0 / max(1.0, float(cfg.get("duration_s", 1.0)))
            remaining = 0.0 if sev >= thr else max(0.0, (thr - sev) / max(1e-6, growth_rate))
            rul = min(rul, remaining)

        if rul == float("inf"):
            rul = 1e9

        if active_fault_weights:
            _, dominant_fault_name, fault_type = sorted(active_fault_weights, key=lambda t: t[0], reverse=True)[0]
            active_faults = list(dict.fromkeys(active_faults))
            active_types = list(dict.fromkeys(active_types))
            feature_name = str(self.state.fault_feature_names.get(dominant_fault_name, "fault_feature"))
            failure_threshold_name = f"{dominant_fault_name}:{feature_name}"
        else:
            fault_type = "none"
            active_faults = []
            active_types = []
            feature_name = "none"

        safety_state = self.state.safety_state
        if safety_state is None:
            safety_state = "safe"
        if safety_state == "safe" and self.state.safety_alarm_faults:
            safety_state = "alarm"
        if safety_state == "alarm" and self.state.safety_trip_faults:
            safety_state = "trip"

        onset_t = float(self._onset_times.get(dominant_fault_name, -1.0))
        symptom_onset_t = float(self._symptom_onset_times.get(dominant_fault_name, onset_t))
        detectable_onset_t = float(self._detectable_onset_times.get(dominant_fault_name, -1.0))
        threshold_crossing_t = float(self._threshold_times.get(dominant_fault_name, -1.0))
        trip_t = float(self._trip_times.get(dominant_fault_name, -1.0))
        censored = 0.0 if threshold_crossing_t >= 0.0 or trip_t >= 0.0 else 1.0
        mission_load = 0.6 if load_cmd is None else float(max(0.0, min(1.2, load_cmd)))
        mission_factor = 1.0 + 0.35 * mission_load
        reference_rul = float(rul)
        current_rul = float(reference_rul / mission_factor) if reference_rul < 1e9 else float(reference_rul)
        dominant_feature_value = float(self.state.fault_feature_values.get(dominant_fault_name, 0.0))
        dominant_feature_reference = float(self.state.fault_feature_references.get(dominant_fault_name, 1.0))

        return {
            "fault_type": fault_type,
            "fault_severity": float(fault_severity),
            "anomaly_flag": float(self.state.anomaly),
            "RUL": float(current_rul),
            "RUL_current_mission": float(current_rul),
            "RUL_reference_mission": float(reference_rul),
            "censored": float(censored),
            "failure_threshold_name": str(failure_threshold_name),
            "fault_onset": float(onset_t),
            "symptom_onset": float(symptom_onset_t),
            "anomaly_detectable_onset": float(detectable_onset_t),
            "threshold_crossing": float(threshold_crossing_t),
            "trip_time": float(trip_t),
            "fault_types": active_types,
            "fault_names": active_faults,
            "event_log": list(self.state.event_log),
            "event_log_history": list(self.state.event_log),
            "event_log_latest": list(self.state.latest_events),
            "safety_state": safety_state,
            "safety_active": 1.0 if safety_state != "safe" else 0.0,
            "alarm_faults": list(self.state.safety_alarm_faults),
            "trip_faults": list(self.state.safety_trip_faults),
            "trip_count": float(len(self.state.safety_trip_faults)),
            "alarm_count": float(len(self.state.safety_alarm_faults)),
            "fault_feature_name": str(feature_name),
            "fault_feature_value": float(dominant_feature_value),
            "fault_feature_reference": float(dominant_feature_reference),
            "fault_schedule_severity": float(self.state.fault_last_schedule.get(dominant_fault_name, 0.0)),
            "fault_mission_factor": float(mission_factor),
            "raw_faults": [
                {
                    "name": c.get("name"),
                    "type": c.get("type"),
                    "severity": float(self.state.fault_last_severity.get(str(c.get("name", c.get("type", "none"))), 0.0)),
                }
                for c in self.fault_configs
            ],
        }
