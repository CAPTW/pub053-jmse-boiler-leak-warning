"""Lightweight PID controller."""

from __future__ import annotations


class PID:
    def __init__(
        self,
        kp: float,
        ki: float,
        kd: float,
        umin: float,
        umax: float,
        *,
        out_init: float = 0.0,
        antiwindup_gain: float = 1.0,
    ) -> None:
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.umin = float(umin)
        self.umax = float(umax)
        self.antiwindup_gain = float(antiwindup_gain)
        self._i = 0.0
        self._prev_err = 0.0
        self._out = out_init
        self._sat_state = "none"
        self._prev_sat_state = "none"
        self._pending_sat_event = None
        self._raw_output = out_init

    def reset(self, out_init: float = 0.0) -> None:
        self._i = 0.0
        self._prev_err = 0.0
        self._out = out_init
        self._sat_state = "none"
        self._prev_sat_state = "none"
        self._pending_sat_event = None
        self._raw_output = out_init

    def track(self, out: float, *, error: float = 0.0) -> float:
        """Track an externally selected output for bumpless mode transfer."""
        error = float(error)
        u = max(self.umin, min(self.umax, float(out)))
        self._prev_err = error
        self._i = u - self.kp * error
        self._out = u
        self._raw_output = u
        self._sat_state = "upper" if u >= self.umax else "lower" if u <= self.umin else "none"
        self._prev_sat_state = self._sat_state
        self._pending_sat_event = None
        return self._out

    def update(self, error: float, dt: float) -> float:
        dt = max(1e-6, float(dt))
        error = float(error)

        p = self.kp * error
        d = self.kd * (error - self._prev_err) / dt
        self._prev_err = error

        i_next = self._i + self.ki * error * dt
        raw = p + i_next + d
        u = max(self.umin, min(self.umax, raw))

        self._sat_state = "upper" if u >= self.umax else "lower" if u <= self.umin else "none"
        if self.antiwindup_gain != 0.0 and self._sat_state != "none":
            i_next += self.antiwindup_gain * (u - raw) * dt
            u = max(self.umin, min(self.umax, p + i_next + d))
            self._sat_state = "upper" if u >= self.umax else "lower" if u <= self.umin else "none"

        self._i = i_next
        self._out = u
        self._raw_output = float(p + self._i + d)

        if self._sat_state != self._prev_sat_state:
            if self._sat_state != "none":
                self._pending_sat_event = self._sat_state
            self._prev_sat_state = self._sat_state

        return self._out

    def pop_saturation_event(self) -> str | None:
        event = self._pending_sat_event
        self._pending_sat_event = None
        return event

    @property
    def saturated(self) -> bool:
        return self._sat_state != "none"

    @property
    def sat_state(self) -> str:
        return self._sat_state

    @property
    def raw_output(self) -> float:
        return self._raw_output
