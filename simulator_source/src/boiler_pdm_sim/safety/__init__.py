"""Process safety monitors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .alarms import ProcessAlarmMonitor
from .trips import ProcessTripMonitor


@dataclass
class ProcessSafetyResult:
    state: str
    alarm_names: list[str]
    trip_names: list[str]
    trip_latch: bool
    trip_reset_condition: list[str]
    events: list[str]


class ProcessSafetyMonitor:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.alarms = ProcessAlarmMonitor(cfg)
        self.trips = ProcessTripMonitor(cfg)

    def evaluate(
        self,
        *,
        t: float,
        truth: dict[str, float],
        controller_snapshot: dict[str, float | str] | None = None,
        sensor_quality: dict[str, str] | None = None,
    ) -> ProcessSafetyResult:
        alarm_eval = self.alarms.evaluate(
            t=t,
            truth=truth,
            controller_snapshot=controller_snapshot,
            sensor_quality=sensor_quality,
        )
        trip_eval = self.trips.evaluate(
            t=t,
            truth=truth,
            alarms=alarm_eval.active,
            controller_snapshot=controller_snapshot,
        )
        return ProcessSafetyResult(
            state=trip_eval.state if trip_eval.state == "trip" else alarm_eval.state,
            alarm_names=list(alarm_eval.active),
            trip_names=list(trip_eval.active),
            trip_latch=bool(trip_eval.latched),
            trip_reset_condition=list(trip_eval.reset_condition),
            events=list(alarm_eval.events) + list(trip_eval.events),
        )


__all__ = ["ProcessSafetyMonitor", "ProcessSafetyResult"]
