"""Typed runtime configuration views over raw simulator mappings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


def _as_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if k is not None}


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


@dataclass(frozen=True)
class SimSettings:
    dt: float
    horizon_s: float
    solver: str
    seed: int
    fmt: str | None
    collect_performance: bool
    timestamp_jitter_s: float
    controller_dt_s: float
    sensor_dt_s: float
    logger_dt_s: float

    @property
    def horizon_steps(self) -> int:
        return int(float(self.horizon_s) / max(float(self.dt), 1e-12))


@dataclass(frozen=True)
class CalibrationSettings:
    enabled: bool
    mode: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BoilerSettings:
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SensorSettings:
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RandomizationSettings:
    enabled: bool
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CoreBackendSettings:
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FaultSettings:
    instances: tuple[Any, ...] = ()
    raw: tuple[Any, ...] = ()


@dataclass(frozen=True)
class PerformanceSettings:
    enabled: bool
    collect_memory: bool
    log_path: str | None
    bottleneck: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GovernanceSettings:
    enabled: bool
    inline_gate: bool
    policy_path: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PIDSettings:
    kp: float
    ki: float
    kd: float
    umin: float
    umax: float
    antiwindup_gain: float
    max_step_rate_per_s: float
    setpoint: float | None
    feedforward: float | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlSettings:
    drum_level_pid: PIDSettings
    pressure_pid: PIDSettings
    raw: dict[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> dict[str, Any]:
        return dict(self.raw)


@dataclass(frozen=True)
class SafetySettings:
    lockout_on_trip: bool
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DAEValidationSettings:
    enabled: bool
    residual_tol: float | None
    min_feasible_ratio: float | None
    max_residual_ratio: float | None
    max_gap_negative: float | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationSettings:
    schema_strict: bool
    raw: dict[str, Any] = field(default_factory=dict)
    dae: DAEValidationSettings = field(default_factory=lambda: DAEValidationSettings(False, None, None, None, None, {}))


@dataclass(frozen=True)
class ScenarioSettings:
    type: str
    seed: int | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SplitSettings:
    enabled: bool
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationBatterySettings:
    enabled: bool
    log_path: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisCalibrationSettings:
    enabled: bool
    report_path: str | None
    include_in_analysis: bool
    include_in_provenance: bool
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisSettings:
    calibration: AnalysisCalibrationSettings
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeConfig:
    sim: SimSettings
    boiler: BoilerSettings
    sensors: SensorSettings
    randomization: RandomizationSettings
    core_backend: CoreBackendSettings
    faults: FaultSettings
    calibration: CalibrationSettings
    performance: PerformanceSettings
    governance: GovernanceSettings
    control: ControlSettings
    safety: SafetySettings
    validation: ValidationSettings
    scenario: ScenarioSettings
    split: SplitSettings
    validation_battery: ValidationBatterySettings
    analysis: AnalysisSettings
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, cfg: Mapping[str, Any]) -> "RuntimeConfig":
        raw = _as_dict(dict(cfg))
        sim = _as_dict(raw.get("sim"))
        boiler = _as_dict(raw.get("boiler"))
        sensors = _as_dict(raw.get("sensors"))
        randomization = _as_dict(raw.get("randomization"))
        core_backend = _as_dict(raw.get("core_backend"))
        fault_instances_raw = raw.get("fault_instances", ())
        calibration = _as_dict(raw.get("calibration"))
        performance = _as_dict(raw.get("performance"))
        governance = _as_dict(raw.get("governance"))
        control = _as_dict(raw.get("control"))
        safety = _as_dict(raw.get("safety"))
        validation = _as_dict(raw.get("validation"))
        scenario = _as_dict(raw.get("scenario"))
        split = _as_dict(sim.get("train_val_test") or sim.get("dataset_split") or raw.get("dataset_split"))
        validation_battery = _as_dict(raw.get("validation_battery"))
        if not validation_battery:
            validation_battery = _as_dict(raw.get("phase6"))
        analysis = _as_dict(raw.get("analysis"))
        analysis_calibration = _as_dict(analysis.get("calibration"))
        timebase = _as_dict(sim.get("timebase"))
        sim_dt = _as_float(sim.get("dt", 1.0), 1.0)

        sim_settings = SimSettings(
            dt=sim_dt,
            horizon_s=_as_float(sim.get("horizon_s", 0.0), 0.0),
            solver=str(sim.get("solver", "BDF")),
            seed=_as_int(sim.get("seed", 42), 42),
            fmt=str(sim.get("format")) if sim.get("format") is not None else None,
            collect_performance=_as_bool(sim.get("collect_performance", False), default=False),
            timestamp_jitter_s=_as_float(sim.get("timestamp_jitter_s", 0.0), 0.0),
            controller_dt_s=_as_float(timebase.get("controller_dt_s", sim.get("controller_dt_s", sim_dt)), sim_dt),
            sensor_dt_s=_as_float(timebase.get("sensor_dt_s", sim.get("sensor_dt_s", sim_dt)), sim_dt),
            logger_dt_s=_as_float(timebase.get("logger_dt_s", sim.get("logger_dt_s", sim_dt)), sim_dt),
        )
        boiler_settings = BoilerSettings(raw=boiler)
        sensor_settings = SensorSettings(raw=sensors)
        randomization_settings = RandomizationSettings(
            enabled=_as_bool(randomization.get("enable", True), default=True),
            raw=randomization,
        )
        core_backend_settings = CoreBackendSettings(raw=core_backend)
        if isinstance(fault_instances_raw, (list, tuple)):
            fault_instances = tuple(fault_instances_raw)
        else:
            fault_instances = ()
        fault_settings = FaultSettings(
            instances=fault_instances,
            raw=fault_instances,
        )
        calibration_settings = CalibrationSettings(
            enabled=_as_bool(calibration.get("enabled", False), default=False),
            mode=str(calibration.get("mode", "static")).strip().lower() or "static",
            raw=calibration,
        )
        performance_settings = PerformanceSettings(
            enabled=_as_bool(performance.get("enabled", False), default=False),
            collect_memory=_as_bool(performance.get("collect_memory", False), default=False),
            log_path=str(performance.get("log_path")) if performance.get("log_path") is not None else None,
            bottleneck=_as_dict(performance.get("bottleneck")),
            raw=performance,
        )
        governance_settings = GovernanceSettings(
            enabled=bool(governance),
            inline_gate=_as_bool(governance.get("inline_gate", True), default=True),
            policy_path=str(governance.get("policy_path")) if governance.get("policy_path") is not None else None,
            raw=governance,
        )
        drum_level_pid = _as_dict(control.get("drum_level_pid"))
        pressure_pid = _as_dict(control.get("pressure_pid"))
        control_settings = ControlSettings(
            drum_level_pid=PIDSettings(
                kp=_as_float(drum_level_pid.get("kp", 0.0), 0.0),
                ki=_as_float(drum_level_pid.get("ki", 0.0), 0.0),
                kd=_as_float(drum_level_pid.get("kd", 0.0), 0.0),
                umin=_as_float(drum_level_pid.get("umin", 0.0), 0.0),
                umax=_as_float(drum_level_pid.get("umax", 1.0), 1.0),
                antiwindup_gain=_as_float(drum_level_pid.get("antiwindup_gain", 1.0), 1.0),
                max_step_rate_per_s=_as_float(drum_level_pid.get("max_step_rate_per_s", 0.0), 0.0),
                setpoint=_as_float(drum_level_pid.get("setpoint_level_m", 0.0), 0.0) if "setpoint_level_m" in drum_level_pid else None,
                feedforward=_as_float(drum_level_pid.get("out_feedforward", 0.0), 0.0) if "out_feedforward" in drum_level_pid else None,
                raw=drum_level_pid,
            ),
            pressure_pid=PIDSettings(
                kp=_as_float(pressure_pid.get("kp", 0.0), 0.0),
                ki=_as_float(pressure_pid.get("ki", 0.0), 0.0),
                kd=_as_float(pressure_pid.get("kd", 0.0), 0.0),
                umin=_as_float(pressure_pid.get("umin", 0.0), 0.0),
                umax=_as_float(pressure_pid.get("umax", 1.0), 1.0),
                antiwindup_gain=_as_float(pressure_pid.get("antiwindup_gain", 1.0), 1.0),
                max_step_rate_per_s=_as_float(pressure_pid.get("max_step_rate_per_s", 0.0), 0.0),
                setpoint=_as_float(pressure_pid.get("setpoint_pressure_bar", 0.0), 0.0) if "setpoint_pressure_bar" in pressure_pid else None,
                feedforward=None,
                raw=pressure_pid,
            ),
            raw=control,
        )
        dae = _as_dict(validation.get("dae"))
        validation_settings = ValidationSettings(
            schema_strict=_as_bool(validation.get("schema_strict", False), default=False),
            raw=validation,
            dae=DAEValidationSettings(
                enabled=_as_bool(dae.get("enabled", False), default=False),
                residual_tol=_as_float(dae.get("residual_tol", 0.0), 0.0) if "residual_tol" in dae else None,
                min_feasible_ratio=_as_float(dae.get("min_feasible_ratio", 0.0), 0.0) if "min_feasible_ratio" in dae else None,
                max_residual_ratio=_as_float(dae.get("max_residual_ratio", 0.0), 0.0) if "max_residual_ratio" in dae else None,
                max_gap_negative=_as_float(dae.get("max_gap_negative", 0.0), 0.0) if "max_gap_negative" in dae else None,
                raw=dae,
            ),
        )
        safety_settings = SafetySettings(
            lockout_on_trip=_as_bool(safety.get("lockout_on_trip", True), default=True),
            raw=safety,
        )
        scenario_seed = scenario.get("seed")
        scenario_settings = ScenarioSettings(
            type=str(scenario.get("type", "")).strip(),
            seed=_as_int(scenario_seed, 0) if scenario_seed is not None else None,
            raw=scenario,
        )
        split_settings = SplitSettings(
            enabled=bool(split) and _as_bool(split.get("enabled", True), default=True),
            raw=split,
        )
        validation_battery_settings = ValidationBatterySettings(
            enabled=_as_bool(validation_battery.get("enabled", False), default=False),
            log_path=str(validation_battery.get("log_path")) if validation_battery.get("log_path") is not None else None,
            raw=validation_battery,
        )
        analysis_settings = AnalysisSettings(
            calibration=AnalysisCalibrationSettings(
                enabled=_as_bool(analysis_calibration.get("enabled", False), default=False),
                report_path=str(analysis_calibration.get("report_path")) if analysis_calibration.get("report_path") is not None else None,
                include_in_analysis=_as_bool(analysis_calibration.get("include_in_analysis", True), default=True),
                include_in_provenance=_as_bool(analysis_calibration.get("include_in_provenance", True), default=True),
                raw=analysis_calibration,
            ),
            raw=analysis,
        )
        return cls(
            sim=sim_settings,
            boiler=boiler_settings,
            sensors=sensor_settings,
            randomization=randomization_settings,
            core_backend=core_backend_settings,
            faults=fault_settings,
            calibration=calibration_settings,
            performance=performance_settings,
            governance=governance_settings,
            control=control_settings,
            safety=safety_settings,
            validation=validation_settings,
            scenario=scenario_settings,
            split=split_settings,
            validation_battery=validation_battery_settings,
            analysis=analysis_settings,
            raw=raw,
        )
