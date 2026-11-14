"""Control strategy helpers for single/two/three-element drum control."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Any

from .pid import PID


def _clamp(value: float, lower: float, upper: float) -> float:
    return float(max(lower, min(upper, float(value))))


def _coerce_schedule(schedule: object) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(schedule, list):
        return out
    for item in schedule:
        if not isinstance(item, dict):
            continue
        out.append({str(k): v for k, v in item.items() if k is not None})
    out.sort(key=lambda item: float(item.get("start_s", 0.0)))
    return out


def resolve_control_mode(
    cfg: dict[str, Any],
    *,
    t: float,
) -> str:
    mode = str(cfg.get("mode", "auto")).strip().lower() or "auto"
    for item in _coerce_schedule(cfg.get("mode_schedule")):
        start = float(item.get("start_s", 0.0))
        duration = item.get("duration_s")
        if t < start:
            continue
        if duration is not None and t >= start + float(duration):
            continue
        item_mode = str(item.get("mode", mode)).strip().lower()
        if item_mode:
            mode = item_mode
    if mode not in {"manual", "auto", "cascade"}:
        return "auto"
    return mode


@dataclass
class ActuatorConfig:
    name: str
    command_lag_s: float = 0.0
    rate_limit: float = 10.0
    deadband: float = 0.0
    saturation_min: float = 0.0
    saturation_max: float = 1.0
    stiction_deadband: float = 0.0
    stiction_gain: float = 1.0
    position_feedback_available: bool = True

    @classmethod
    def from_mapping(cls, name: str, cfg: object) -> "ActuatorConfig":
        raw = cfg if isinstance(cfg, dict) else {}
        saturation = raw.get("saturation", {})
        if isinstance(saturation, (list, tuple)) and len(saturation) >= 2:
            sat_min = float(saturation[0])
            sat_max = float(saturation[1])
        elif isinstance(saturation, dict):
            sat_min = float(saturation.get("min", raw.get("umin", 0.0)))
            sat_max = float(saturation.get("max", raw.get("umax", 1.0)))
        else:
            sat_min = float(raw.get("umin", 0.0))
            sat_max = float(raw.get("umax", 1.0))
        stiction = raw.get("stiction_params", {})
        if not isinstance(stiction, dict):
            stiction = {}
        return cls(
            name=str(name),
            command_lag_s=float(raw.get("command_lag_s", 0.0)),
            rate_limit=float(raw.get("rate_limit", raw.get("max_step_rate_per_s", 10.0))),
            deadband=float(raw.get("deadband", 0.0)),
            saturation_min=float(min(sat_min, sat_max)),
            saturation_max=float(max(sat_min, sat_max)),
            stiction_deadband=float(stiction.get("deadband", raw.get("stiction_deadband", 0.0))),
            stiction_gain=float(stiction.get("gain", raw.get("stiction_gain", 1.0))),
            position_feedback_available=bool(raw.get("position_feedback_available", True)),
        )


class ActuatorChain:
    def __init__(self, cfg: ActuatorConfig, *, initial_position: float) -> None:
        self.cfg = cfg
        self._command = _clamp(initial_position, cfg.saturation_min, cfg.saturation_max)
        self._position = self._command

    @property
    def position(self) -> float:
        return float(self._position)

    def track(self, target: float) -> None:
        tracked = _clamp(target, self.cfg.saturation_min, self.cfg.saturation_max)
        self._command = tracked
        self._position = tracked

    def update(
        self,
        command: float,
        dt: float,
        *,
        degradation: dict[str, Any] | None = None,
    ) -> tuple[float, list[str]]:
        events: list[str] = []
        dt = max(1e-6, float(dt))
        target = _clamp(command, self.cfg.saturation_min, self.cfg.saturation_max)
        if abs(target - command) > 1e-9:
            events.append(f"{self.cfg.name}_actuator_saturation")

        if abs(target - self._command) < self.cfg.deadband:
            target = self._command
        else:
            max_delta = max(0.0, self.cfg.rate_limit) * dt
            if max_delta > 0.0 and abs(target - self._command) > max_delta:
                target = self._command + max_delta * (1.0 if target > self._command else -1.0)
                events.append(f"{self.cfg.name}_actuator_rate_limit")

        tau = max(0.0, self.cfg.command_lag_s)
        if tau > 1e-6:
            alpha = 1.0 - exp(-dt / tau)
            target_pos = self._position + alpha * (target - self._position)
        else:
            target_pos = target

        stiction = 0.0
        stiction_deadband = self.cfg.stiction_deadband
        if isinstance(degradation, dict):
            stiction = float(degradation.get("valve_stiction", 0.0))
            stiction_deadband = max(stiction_deadband, float(degradation.get("valve_stiction_deadband", 0.0)))
        travel = float(target_pos - self._position)
        if abs(travel) < stiction_deadband:
            target_pos = self._position
            if stiction_deadband > 0.0:
                events.append(f"{self.cfg.name}_actuator_stiction")
        elif stiction > 0.0:
            target_pos = self._position + travel * max(0.0, 1.0 - stiction * max(0.1, self.cfg.stiction_gain))
            events.append(f"{self.cfg.name}_actuator_stiction")

        self._command = target
        self._position = _clamp(target_pos, self.cfg.saturation_min, self.cfg.saturation_max)
        return float(self._position), events


class ThreeElementCoordinator:
    """Coordinator around drum level/pressure/flow loops and actuator chains."""

    def __init__(
        self,
        *,
        control_cfg: dict[str, Any],
        level_pid: PID,
        pressure_pid: PID,
    ) -> None:
        flow_cfg = control_cfg.get("feedwater_flow_pid", {})
        if not isinstance(flow_cfg, dict):
            flow_cfg = {}
        self.level_pid = level_pid
        self.pressure_pid = pressure_pid
        self.flow_pid = PID(
            kp=float(flow_cfg.get("kp", 0.35)),
            ki=float(flow_cfg.get("ki", 0.04)),
            kd=float(flow_cfg.get("kd", 0.0)),
            umin=float(flow_cfg.get("umin", 0.0)),
            umax=float(flow_cfg.get("umax", 1.0)),
            out_init=float(flow_cfg.get("out_init", control_cfg.get("drum_level_pid", {}).get("out_feedforward", 0.55))),
            antiwindup_gain=float(flow_cfg.get("antiwindup_gain", 1.0)),
        )
        actuator_cfg = control_cfg.get("actuator", {})
        if not isinstance(actuator_cfg, dict):
            actuator_cfg = {}
        self.fuel_actuator = ActuatorChain(
            ActuatorConfig.from_mapping("fuel", actuator_cfg.get("fuel")),
            initial_position=float(control_cfg.get("manual_outputs", {}).get("fuel_cmd", 0.4)),
        )
        self.feedwater_actuator = ActuatorChain(
            ActuatorConfig.from_mapping("feedwater", actuator_cfg.get("feedwater")),
            initial_position=float(control_cfg.get("manual_outputs", {}).get("fw_cmd", control_cfg.get("drum_level_pid", {}).get("out_feedforward", 0.55))),
        )
        self.steam_actuator = ActuatorChain(
            ActuatorConfig.from_mapping("steam", actuator_cfg.get("steam")),
            initial_position=float(control_cfg.get("manual_outputs", {}).get("steam_demand", 0.6)),
        )
        self.strategy = str(control_cfg.get("strategy", "three_element")).strip().lower() or "three_element"
        if self.strategy not in {"single_element", "two_element", "three_element"}:
            self.strategy = "three_element"
        self.low_load_threshold = float(control_cfg.get("low_load_fallback_threshold", 0.58))
        self.level_feedforward = float(control_cfg.get("drum_level_pid", {}).get("out_feedforward", 0.55))
        self.max_steam_flow = max(1e-6, float(control_cfg.get("steam_flow_nominal_kg_s", 2.0)))
        self.level_trim_gain = float(control_cfg.get("level_trim_to_flow_gain", 0.22))
        self.mode_cfg = control_cfg
        manual = control_cfg.get("manual_outputs", {})
        if not isinstance(manual, dict):
            manual = {}
        self.manual_outputs = {
            "fuel_cmd": float(manual.get("fuel_cmd", 0.4)),
            "fw_cmd": float(manual.get("fw_cmd", self.level_feedforward)),
            "steam_demand": float(manual.get("steam_demand", 0.6)),
        }
        self._last_mode = "auto"
        self._last_strategy = self.strategy

    def _effective_strategy(self, requested: str, load_cmd: float, y: dict[str, float]) -> str:
        steam_flow = float(y.get("steam_flow", y.get("steam_flow_true", 0.0)))
        if requested in {"two_element", "three_element"} and max(load_cmd, steam_flow / self.max_steam_flow) < self.low_load_threshold:
            return "single_element"
        return requested

    def _track_bumpless_transfer(
        self,
        *,
        level_error: float,
        pressure_error: float,
    ) -> None:
        self.level_pid.track(self.feedwater_actuator.position, error=level_error)
        self.flow_pid.track(self.feedwater_actuator.position, error=0.0)
        self.pressure_pid.track(self.fuel_actuator.position, error=pressure_error)

    def step(
        self,
        *,
        t: float,
        y: dict[str, float],
        dt: float,
        load_cmd: float,
        degradation: dict[str, Any] | None = None,
    ) -> tuple[dict[str, float], list[str], dict[str, float | str]]:
        events: list[str] = []
        mode = resolve_control_mode(self.mode_cfg, t=t)
        requested_strategy = self.strategy
        strategy = self._effective_strategy(requested_strategy, load_cmd, y)

        level = float(y.get("drum_level", 0.0))
        pressure = float(y.get("drum_pressure", 0.0))
        steam_flow = float(y.get("steam_flow", y.get("steam_flow_true", 0.0)))
        feedwater_flow = float(y.get("feedwater_flow", 0.0))
        level_sp = float(self.mode_cfg.get("drum_level_pid", {}).get("setpoint_level_m", 3.3))
        pressure_sp = float(self.mode_cfg.get("pressure_pid", {}).get("setpoint_pressure_bar", 10.0))
        level_error = level_sp - level
        pressure_error = pressure_sp - pressure

        if mode != self._last_mode or strategy != self._last_strategy:
            self._track_bumpless_transfer(level_error=level_error, pressure_error=pressure_error)
            if mode != self._last_mode:
                events.append(f"control_mode_{self._last_mode}_to_{mode}_t={t:.1f}")
            if strategy != self._last_strategy:
                events.append(f"control_strategy_{self._last_strategy}_to_{strategy}_t={t:.1f}")
            self._last_mode = mode
            self._last_strategy = strategy

        level_trim = self.level_pid.update(level_error, dt)
        steam_ratio = _clamp(steam_flow / self.max_steam_flow, 0.0, 1.2)

        if strategy == "single_element":
            feedwater_target = self.level_feedforward + level_trim
        elif strategy == "two_element":
            feedwater_target = self.level_feedforward + steam_ratio + self.level_trim_gain * level_trim
        else:
            flow_sp = steam_flow + self.level_trim_gain * level_trim * self.max_steam_flow
            flow_error = flow_sp - feedwater_flow
            if mode == "cascade":
                feedwater_target = self.flow_pid.update(flow_error, dt)
            else:
                feedwater_target = self.level_feedforward + steam_ratio + self.level_trim_gain * level_trim

        fuel_target = self.pressure_pid.update(pressure_error, dt)

        if mode == "manual":
            fuel_target = self.manual_outputs["fuel_cmd"]
            feedwater_target = self.manual_outputs["fw_cmd"]
            steam_target = self.manual_outputs.get("steam_demand", load_cmd)
        else:
            steam_target = load_cmd

        fuel_cmd, fuel_events = self.fuel_actuator.update(fuel_target, dt, degradation=degradation)
        fw_cmd, fw_events = self.feedwater_actuator.update(feedwater_target, dt, degradation=degradation)
        steam_cmd, steam_events = self.steam_actuator.update(steam_target, dt, degradation=degradation)
        events.extend(fuel_events)
        events.extend(fw_events)
        events.extend(steam_events)

        for name, pid in (("level", self.level_pid), ("pressure", self.pressure_pid), ("feedwater_flow", self.flow_pid)):
            sat = pid.pop_saturation_event()
            if sat:
                events.append(f"sat_{name}_pid_{sat}")

        snapshot: dict[str, float | str] = {
            "mode": mode,
            "strategy": strategy,
            "fuel_position": fuel_cmd,
            "feedwater_position": fw_cmd,
            "steam_position": steam_cmd,
            "level_pid_saturated": float(1.0 if self.level_pid.saturated else 0.0),
            "pressure_pid_saturated": float(1.0 if self.pressure_pid.saturated else 0.0),
            "flow_pid_saturated": float(1.0 if self.flow_pid.saturated else 0.0),
        }
        return {
            "fuel_cmd": float(fuel_cmd),
            "fw_cmd": float(fw_cmd),
            "steam_demand": float(steam_cmd),
        }, events, snapshot
