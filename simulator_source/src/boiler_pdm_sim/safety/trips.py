"""Process trip evaluation with latch/reset behavior."""

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
class TripEvaluation:
    state: str
    active: list[str] = field(default_factory=list)
    latched: bool = False
    reset_ready: bool = False
    events: list[str] = field(default_factory=list)
    reset_condition: list[str] = field(default_factory=list)


class ProcessTripMonitor:
    def __init__(self, cfg: dict[str, Any]) -> None:
        process = _coerce_dict(_coerce_dict(cfg).get("process"))
        trip_cfg = _coerce_dict(process.get("trip"))
        self.level_lll = _as_float(trip_cfg.get("level_LLL"), 2.60)
        self.level_hh = _as_float(trip_cfg.get("level_HH"), 4.25)
        self.pressure_h = _as_float(trip_cfg.get("pressure_H"), 14.5)
        self.feedwater_low = _as_float(trip_cfg.get("feedwater_low"), 0.20)
        self.controller_saturation_timeout = _as_float(trip_cfg.get("controller_saturation_timeout_s"), 180.0)
        self.trip_on_sensor_bad_quality = bool(trip_cfg.get("trip_on_sensor_bad_quality", False))
        self.auto_reset = bool(trip_cfg.get("auto_reset", False))
        self.reset_hold_s = _as_float(trip_cfg.get("reset_hold_s"), 60.0)
        self._latched = False
        self._last_active: set[str] = set()
        self._clear_since: float | None = None

    def evaluate(
        self,
        *,
        t: float,
        truth: dict[str, float],
        alarms: list[str],
        controller_snapshot: dict[str, float | str] | None = None,
    ) -> TripEvaluation:
        active: set[str] = set()
        level = float(truth.get("drum_level", 0.0))
        pressure = float(truth.get("drum_pressure", 0.0))
        feedwater = float(truth.get("feedwater_flow", 0.0))
        steam_flow = float(truth.get("steam_flow", truth.get("steam_flow_true", 0.0)))

        if level <= self.level_lll:
            active.add("level_LLL")
        if level >= self.level_hh:
            active.add("level_HH")
        if pressure >= self.pressure_h:
            active.add("pressure_H")
        if feedwater <= self.feedwater_low and steam_flow > self.feedwater_low:
            active.add("feedwater_low")
        if controller_snapshot and max(
            float(controller_snapshot.get("level_pid_saturation_s", 0.0)),
            float(controller_snapshot.get("pressure_pid_saturation_s", 0.0)),
            float(controller_snapshot.get("flow_pid_saturation_s", 0.0)),
        ) >= self.controller_saturation_timeout:
            active.add("controller_saturation_timeout")
        if self.trip_on_sensor_bad_quality and "sensor_bad_quality" in alarms:
            active.add("sensor_bad_quality")

        events: list[str] = []
        newly_active = sorted(active - self._last_active)
        if newly_active:
            events.extend([f"{name}_trip_t={t:.1f}" for name in newly_active])
        self._last_active = set(active)

        if active:
            self._latched = True
            self._clear_since = None
        elif self._latched:
            if self._clear_since is None:
                self._clear_since = float(t)
            if self.auto_reset and (t - self._clear_since) >= self.reset_hold_s:
                self._latched = False
                events.append(f"trip_reset_condition_met_t={t:.1f}")

        reset_ready = bool(self._latched and self._clear_since is not None and (t - self._clear_since) >= self.reset_hold_s)
        reset_condition = []
        if not active:
            reset_condition.append("trip_reset_condition")
        state = "trip" if self._latched or active else ("alarm" if alarms else "safe")
        return TripEvaluation(
            state=state,
            active=sorted(active),
            latched=bool(self._latched or active),
            reset_ready=reset_ready,
            events=events,
            reset_condition=reset_condition,
        )
