"""High-level control loops for pressure and drum level."""

from __future__ import annotations

from .pid import PID
from .three_element import ThreeElementCoordinator


class BoilerControl:
    def __init__(self, control_cfg: dict) -> None:
        level_cfg = control_cfg["drum_level_pid"]
        pressure_cfg = control_cfg["pressure_pid"]
        self.level_pid = PID(
            kp=level_cfg["kp"],
            ki=level_cfg["ki"],
            kd=level_cfg.get("kd", 0.0),
            umin=level_cfg["umin"],
            umax=level_cfg["umax"],
            antiwindup_gain=float(level_cfg.get("antiwindup_gain", 1.0)),
        )
        self.pressure_pid = PID(
            kp=pressure_cfg["kp"],
            ki=pressure_cfg["ki"],
            kd=pressure_cfg.get("kd", 0.0),
            umin=pressure_cfg["umin"],
            umax=pressure_cfg["umax"],
            antiwindup_gain=float(pressure_cfg.get("antiwindup_gain", 1.0)),
        )
        self.level_sp = float(level_cfg.get("setpoint_level_m", 3.3))
        self.pressure_sp = float(pressure_cfg.get("setpoint_pressure_bar", 10.0))
        self.level_ff = float(level_cfg.get("out_feedforward", 0.0))
        self._last_events: list[str] = []
        self._last_snapshot: dict[str, float | str] = {}
        self._coordinator = ThreeElementCoordinator(
            control_cfg=control_cfg,
            level_pid=self.level_pid,
            pressure_pid=self.pressure_pid,
        )
        self._sat_duration_s = {
            "level_pid": 0.0,
            "pressure_pid": 0.0,
            "flow_pid": 0.0,
        }

    @classmethod
    def from_config(cls, cfg: dict) -> "BoilerControl":
        return cls(cfg)

    def step(
        self,
        t: float,
        y: dict[str, float],
        dt: float,
        load_cmd: float,
        *,
        degradation: dict | None = None,
    ) -> dict[str, float]:
        self._last_events = []
        control, events, snapshot = self._coordinator.step(
            t=t,
            y=y,
            dt=dt,
            load_cmd=load_cmd,
            degradation=degradation,
        )
        self._last_events.extend(events)
        self._last_snapshot = dict(snapshot)
        for key, active in (
            ("level_pid", bool(snapshot.get("level_pid_saturated", 0.0))),
            ("pressure_pid", bool(snapshot.get("pressure_pid_saturated", 0.0))),
            ("flow_pid", bool(snapshot.get("flow_pid_saturated", 0.0))),
        ):
            self._sat_duration_s[key] = self._sat_duration_s[key] + float(dt) if active else 0.0
        return control

    def pop_events(self) -> list[str]:
        events = list(self._last_events)
        self._last_events = []
        return events

    def snapshot(self) -> dict[str, float | str]:
        out = dict(self._last_snapshot)
        out.update(
            {
                "level_pid_saturation_s": float(self._sat_duration_s["level_pid"]),
                "pressure_pid_saturation_s": float(self._sat_duration_s["pressure_pid"]),
                "flow_pid_saturation_s": float(self._sat_duration_s["flow_pid"]),
            }
        )
        return out
