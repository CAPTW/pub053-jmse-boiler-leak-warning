"""Numerical stepping utilities."""

from __future__ import annotations

from typing import Callable

import numpy as np

try:
    from scipy.integrate import solve_ivp
except Exception:  # pragma: no cover - scipy optional in docs but required here
    solve_ivp = None  # type: ignore


_FIXED_STEP_METHODS = {"euler", "fixed"}
_SCIPY_METHODS = {
    "rk45": "RK45",
    "rk23": "RK23",
    "dop853": "DOP853",
    "radau": "Radau",
    "bdf": "BDF",
    "lsoda": "LSODA",
}


def normalize_method(method: str) -> str:
    """Map a config solver name to its canonical form, case-insensitively.

    Unknown names raise instead of silently degrading to the Euler fallback
    later in the retry loop.
    """
    key = str(method).strip().lower()
    if key in _FIXED_STEP_METHODS:
        return key
    if key in _SCIPY_METHODS:
        return _SCIPY_METHODS[key]
    raise ValueError(
        f"unknown solver method {method!r}; expected one of "
        f"{sorted(_FIXED_STEP_METHODS | set(_SCIPY_METHODS))}"
    )


def integrate_step(
    fun: Callable[[float, np.ndarray], np.ndarray],
    t: float,
    x: np.ndarray,
    dt: float,
    method: str,
    *,
    max_step: float | None = None,
    max_retries: int = 3,
    dt_reduction: float = 0.5,
    min_dt: float = 1e-6,
    return_diagnostics: bool = False,
) -> np.ndarray | tuple[np.ndarray, dict[str, float | int | str | bool]]:
    requested = str(method)
    method = normalize_method(method)
    diagnostics: dict[str, float | int | str | bool] = {
        "requested_method": requested,
        "solver_used": "euler" if method in _FIXED_STEP_METHODS or solve_ivp is None else str(method),
        "retry_count": 0,
        "rejected_steps": 0,
        "fallback_used": False,
        "status": "ok",
    }
    if dt <= 0.0:
        out = np.asarray(x, dtype=float)
        return (out, diagnostics) if return_diagnostics else out

    if method in _FIXED_STEP_METHODS or solve_ivp is None:
        out = x + dt * fun(t, x)
        return (out, diagnostics) if return_diagnostics else out

    dt = float(dt)
    try_dt = dt
    for _ in range(max(0, int(max_retries)) + 1):
        if try_dt < min_dt:
            break
        try:
            n_steps = max(1, int(np.ceil(dt / try_dt)))
            step_dt = dt / n_steps
            x_curr = np.asarray(x, dtype=float)
            t_curr = float(t)
            for _ in range(n_steps):
                sol = solve_ivp(
                    fun=fun,
                    t_span=(t_curr, t_curr + step_dt),
                    y0=x_curr,
                    method=method,
                    t_eval=[t_curr + step_dt],
                    max_step=max_step or step_dt,
                    rtol=1e-5,
                    atol=1e-8,
                )
                if not sol.success or len(sol.t) == 0:
                    raise RuntimeError("solver_failure")
                x_curr = sol.y[:, -1]
                t_curr += step_dt
            diagnostics["solver_used"] = str(method)
            diagnostics["status"] = "ok"
            return (x_curr, diagnostics) if return_diagnostics else x_curr
        except Exception:
            diagnostics["retry_count"] = int(diagnostics["retry_count"]) + 1
            diagnostics["rejected_steps"] = int(diagnostics["rejected_steps"]) + 1
            try_dt *= dt_reduction

    diagnostics["fallback_used"] = True
    diagnostics["solver_used"] = "euler_fallback"
    diagnostics["status"] = "fallback_euler"
    out = np.asarray(x, dtype=float) + dt * fun(t, np.asarray(x, dtype=float))
    return (out, diagnostics) if return_diagnostics else out
