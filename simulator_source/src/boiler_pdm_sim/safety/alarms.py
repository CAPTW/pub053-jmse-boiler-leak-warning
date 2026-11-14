"""Process alarm evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _coerce_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if k is not None}


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class AlarmEvaluation:
    state: str
    active: list[str] = field(default_factory=list)
    entered: list[str] = field(default_factory=list)
    cleared: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


class ProcessAlarmMonitor:
    def __init__(self, cfg: dict[str, Any]) -> None:
        process = _coerce_dict(_coerce_dict(cfg).get("process"))
        alarm_cfg = _coerce_dict(process.get("alarm"))
        self.level_lll = _as_float(alarm_cfg.get("level_LLL"), 2.70)
        self.level_ll = _as_float(alarm_cfg.get("level_LL"), 2.95)
        self.level_h = _as_float(alarm_cfg.get("level_H"), 3.85)
        self.level_hh = _as_float(alarm_cfg.get("level_HH"), 4.15)
        self.pressure_h = _as_float(alarm_cfg.get("pressure_H"), 13.5)
        self.feedwater_low = _as_float(alarm_cfg.get("feedwater_low"), 0.35)
        self.controller_saturation_timeout = _as_float(alarm_cfg.get("controller_saturation_timeout_s"), 90.0)
        self._active: set[str] = set()

    def evaluate(
        self,
        *,
        t: float,
        truth: dict[str, float],
        controller_snapshot: dict[str, float | str] | None = None,
        sensor_quality: dict[str, str] | None = None,
    ) -> AlarmEvaluation:
        active: set[str] = set()
        level = float(truth.get("drum_level", 0.0))
        pressure = float(truth.get("drum_pressure", 0.0))
        feedwater = float(truth.get("feedwater_flow", 0.0))

        if level <= self.level_lll:
            active.add("level_LLL")
        if level <= self.level_ll:
            active.add("level_LL")
        if level >= self.level_h:
            active.add("level_H")
        if level >= self.level_hh:
            active.add("level_HH")
        if pressure >= self.pressure_h:
            active.add("pressure_H")
        if feedwater <= self.feedwater_low and float(truth.get("steam_flow", truth.get("steam_flow_true", 0.0))) > self.feedwater_low:
            active.add("feedwater_low")

        if controller_snapshot:
            timeout = self.controller_saturation_timeout
            sat_times = (
                float(controller_snapshot.get("level_pid_saturation_s", 0.0)),
                float(controller_snapshot.get("pressure_pid_saturation_s", 0.0)),
                float(controller_snapshot.get("flow_pid_saturation_s", 0.0)),
            )
            if max(sat_times) >= timeout:
                active.add("controller_saturation_timeout")

        if sensor_quality:
            bad = [name for name, status in sensor_quality.items() if str(status) != "good"]
            if bad:
                active.add("sensor_bad_quality")

        entered = sorted(active - self._active)
        cleared = sorted(self._active - active)
        self._active = set(active)
        events = [f"{name}_alarm_t={t:.1f}" for name in entered]
        events.extend([f"{name}_alarm_clear_t={t:.1f}" for name in cleared])
        state = "alarm" if active else "safe"
        return AlarmEvaluation(
            state=state,
            active=sorted(active),
            entered=entered,
            cleared=cleared,
            events=events,
        )
