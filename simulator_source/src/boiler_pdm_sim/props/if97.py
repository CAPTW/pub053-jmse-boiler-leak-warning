"""IF97 saturation-property layer for the Phase A ``ab4`` physics core (§3.2).

Design contract (docs/phase_a_design.md §3.2, ADR-3/7):

* Range 0.5–120 bar (Phase C margin), saturation line.
* Provides Tsat, rho_w, rho_s, h_w, h_s, u_w, u_s, cp_w, cp_s **and** the
  saturation-line derivatives d(Tsat,rho_w,rho_s,h_w,h_s)/dp.
* Backend: ``iapws`` is a **hard dependency** — the table is generated once at
  import time by calling IAPWS97 over a pressure grid; afterwards every query is
  a cubic-spline evaluation. Derivatives come from the **spline derivative**, not
  central differences, so the RHS stays smooth in ``p`` (BDF FD-Jacobian needs a
  C1 path; the legacy ``media.py`` 1e-3 bar rounding lru_cache turns the RHS into
  a staircase and is banned here — review blocking #4).
* **No fallback.** If ``iapws`` is missing, importing this module raises
  ImportError. ``media.py``'s approximate fallback is legacy grey-box only and is
  deliberately kept out of this path.

The profiling in the WP A3 kickoff showed iapws ``IAPWS97`` construction costs
~213 us/call and dominated ~83% of the grey-box RHS wall time; a spline lookup
replaces that with a ~us evaluation, which is the empirical justification for
this layer (R3).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline

# Hard dependency: a missing iapws must fail the import (no fallback) — §3.2.
from iapws import IAPWS97

__all__ = [
    "P_MIN_BAR",
    "P_MAX_BAR",
    "PropsBundle",
    "saturation_state",
    "tsat_C",
    "in_range",
]

P_MIN_BAR: float = 0.5
P_MAX_BAR: float = 120.0

_BAR_TO_PA: float = 1.0e5
_KJ_TO_J: float = 1.0e3
# Geometric grid: denser at low pressure where Tsat(p) curvature is highest.
_N_KNOTS: int = 1000


def _sat_states(p_bar: float) -> tuple[IAPWS97, IAPWS97]:
    p_mpa = p_bar / 10.0
    return IAPWS97(P=p_mpa, x=0.0), IAPWS97(P=p_mpa, x=1.0)


def _build_tables() -> dict[str, CubicSpline]:
    """Tabulate saturation properties over [P_MIN_BAR, P_MAX_BAR] and fit C2 splines.

    Called exactly once at import. Cost: ~2*_N_KNOTS IAPWS97 constructions.
    """
    grid = np.geomspace(P_MIN_BAR, P_MAX_BAR, _N_KNOTS)
    tsat = np.empty_like(grid)
    rho_w = np.empty_like(grid)
    rho_s = np.empty_like(grid)
    h_w = np.empty_like(grid)
    h_s = np.empty_like(grid)
    cp_w = np.empty_like(grid)
    cp_s = np.empty_like(grid)

    for i, p_bar in enumerate(grid):
        sl, sv = _sat_states(float(p_bar))
        tsat[i] = sl.T - 273.15
        rho_w[i] = sl.rho
        rho_s[i] = sv.rho
        h_w[i] = sl.h * _KJ_TO_J
        h_s[i] = sv.h * _KJ_TO_J
        cp_w[i] = float(sl.cp) * _KJ_TO_J
        cp_s[i] = float(sv.cp) * _KJ_TO_J

    cols = {
        "Tsat_C": tsat,
        "rho_w": rho_w,
        "rho_s": rho_s,
        "h_w": h_w,
        "h_s": h_s,
        "cp_w": cp_w,
        "cp_s": cp_s,
    }
    return {name: CubicSpline(grid, values, extrapolate=False) for name, values in cols.items()}


_TABLES: dict[str, CubicSpline] = _build_tables()


@dataclass(frozen=True)
class PropsBundle:
    """Saturation properties + saturation-line pressure derivatives at ``p_bar``.

    Units: temperatures in degC, densities in kg/m^3, enthalpy/internal energy in
    J/kg, cp in J/(kg.K). Derivatives are **per Pascal** (SI), so the ab4 RHS can
    apply the chain rule directly with dP/dt in Pa/s.
    """

    p_bar: float
    Tsat_C: float
    rho_w: float
    rho_s: float
    h_w: float
    h_s: float
    h_fg: float
    u_w: float
    u_s: float
    cp_w: float
    cp_s: float
    # saturation-line derivatives w.r.t. pressure [per Pa]
    dTsat_dp: float
    drho_w_dp: float
    drho_s_dp: float
    dh_w_dp: float
    dh_s_dp: float


def in_range(p_bar: float) -> bool:
    """True iff ``p_bar`` is within the tabulated range (inclusive)."""
    return P_MIN_BAR <= float(p_bar) <= P_MAX_BAR


def _check_range(p_bar: float) -> float:
    p = float(p_bar)
    if not (P_MIN_BAR <= p <= P_MAX_BAR):
        raise ValueError(
            f"pressure {p} bar outside IF97 props range [{P_MIN_BAR}, {P_MAX_BAR}] "
            f"(clamping is banned in the ab4 path — §3.2)"
        )
    return p


def tsat_C(p_bar: float) -> float:
    """Saturation temperature [degC] at ``p_bar``. Raises ValueError out of range."""
    p = _check_range(p_bar)
    return float(_TABLES["Tsat_C"](p))


def saturation_state(p_bar: float) -> PropsBundle:
    """Full saturation :class:`PropsBundle` at ``p_bar`` (bar). Raises ValueError out of range."""
    p = _check_range(p_bar)

    rho_w = float(_TABLES["rho_w"](p))
    rho_s = float(_TABLES["rho_s"](p))
    h_w = float(_TABLES["h_w"](p))
    h_s = float(_TABLES["h_s"](p))
    p_pa = p * _BAR_TO_PA
    # u = h - P*v = h - P/rho (exact; matches iapws .u to ~1e-6).
    u_w = h_w - p_pa / max(rho_w, 1e-9)
    u_s = h_s - p_pa / max(rho_s, 1e-9)

    # Spline derivatives are per-bar; convert to per-Pa (/1e5).
    dTsat_dp = float(_TABLES["Tsat_C"](p, 1)) / _BAR_TO_PA
    drho_w_dp = float(_TABLES["rho_w"](p, 1)) / _BAR_TO_PA
    drho_s_dp = float(_TABLES["rho_s"](p, 1)) / _BAR_TO_PA
    dh_w_dp = float(_TABLES["h_w"](p, 1)) / _BAR_TO_PA
    dh_s_dp = float(_TABLES["h_s"](p, 1)) / _BAR_TO_PA

    return PropsBundle(
        p_bar=p,
        Tsat_C=float(_TABLES["Tsat_C"](p)),
        rho_w=rho_w,
        rho_s=rho_s,
        h_w=h_w,
        h_s=h_s,
        h_fg=max(0.0, h_s - h_w),
        u_w=u_w,
        u_s=u_s,
        cp_w=float(_TABLES["cp_w"](p)),
        cp_s=float(_TABLES["cp_s"](p)),
        dTsat_dp=dTsat_dp,
        drho_w_dp=drho_w_dp,
        drho_s_dp=drho_s_dp,
        dh_w_dp=dh_w_dp,
        dh_s_dp=dh_s_dp,
    )
