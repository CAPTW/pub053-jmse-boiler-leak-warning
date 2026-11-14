"""Profile generators."""

from __future__ import annotations

import numpy as np


class ScenarioProfile:
    def value(self, t: float) -> float:
        return 0.5

    def step_event(self, t: float, cmd: float, prev_cmd: float | None, dt: float) -> str | None:
        _ = (t, cmd, prev_cmd, dt)
        return None


class LoadFollowProfile(ScenarioProfile):
    def __init__(self, cfg: dict, rng: np.random.Generator) -> None:
        self.base = float(cfg.get("base", 0.6))
        self.noise = float(cfg.get("noise_std", 0.03))
        self.ramp_per_min = float(cfg.get("ramp_limit_per_min", 0.02))
        self._rng = rng
        self._state = self.base
        self._t_prev = 0.0

    def value(self, t: float) -> float:
        dt_min = max(1e-6, (t - self._t_prev) / 60.0)
        self._t_prev = t
        rw = self._rng.normal(0.0, self.noise)
        target = self._state + rw
        max_delta = self.ramp_per_min * dt_min
        delta = np.clip(target - self._state, -max_delta, max_delta)
        self._state = float(np.clip(self._state + delta, 0.0, 1.0))
        return self._state


class StepProfile(ScenarioProfile):
    def __init__(self, cfg: dict) -> None:
        self.base = float(cfg.get("base", 0.6))
        self.ramp_per_min = float(cfg.get("ramp_limit_per_min", 0.05))
        self.transition_s = float(cfg.get("transition_s", 0.0))
        self.steps = list(cfg.get("steps", []))
        self._state = self.base
        self._pending_event: str | None = None
        self._t_prev = 0.0
        self._target = self.base

    def _update_target(self, t: float) -> None:
        old_target = self._target
        for ev in self.steps:
            if t >= float(ev["start_s"]) and t < float(ev["start_s"]) + float(ev.get("duration_s", 1e9)):
                self._target = float(ev["value"])
        if self._target != old_target:
            self._pending_event = f"steam_step_{'up' if self._target > old_target else 'down'}_t={t:.1f}"

    def value(self, t: float) -> float:
        self._update_target(t)
        dt_s = max(1e-6, t - self._t_prev)
        self._t_prev = t
        if self.transition_s <= 1e-9:
            self._state = float(np.clip(self._target, 0.0, 1.0))
            return self._state
        step_limit = max(1e-6, abs(self._target - self._state))
        ramp_limit = max(self.ramp_per_min / 60.0, step_limit / max(self.transition_s, 1e-6))
        delta = np.clip(self._target - self._state, -ramp_limit * dt_s, ramp_limit * dt_s)
        self._state = float(np.clip(self._state + delta, 0.0, 1.0))
        return self._state

    def step_event(self, t: float, cmd: float, prev_cmd: float | None, dt: float) -> str | None:
        _ = (t, cmd, prev_cmd, dt)
        event = self._pending_event
        self._pending_event = None
        return event
