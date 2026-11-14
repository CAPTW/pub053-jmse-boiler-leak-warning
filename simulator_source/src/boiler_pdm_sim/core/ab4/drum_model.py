"""Phase A ab4 drum-boiler 4-state core (§3.1) — conservation-first variant.

State x = [p, V_wt, alpha_r, V_sd]:
    p        drum pressure                         [Pa]
    V_wt     total water (liquid) volume in system [m^3]
    alpha_r  riser-exit steam mass fraction        [-]
    V_sd     steam volume below the drum surface   [m^3]

Design note (path 2, conservation-first): the global mass (E1) and energy (E2)
balances are written **exactly** from first principles using the IF97 property
derivatives supplied by ``props.if97`` (chain rule on rho(p), h(p)); they form a
2x2 linear system in (dp/dt, dV_wt/dt) so global mass/energy are conserved by
construction (the §7.1 win over the grey-box, whose residuals were diagnostic
only). The riser (E3) and drum-surface (E4) states are spatial-distribution
relaxations that set the drum level without adding or removing global inventory.

The mean riser void fraction is the homogeneous-flow, linear-quality average

    alpha_v(a) = rw/(rw-rs) * [1 - rs/((rw-rs)a) * ln(1 + (rw-rs)a/rs)]

which is **derived here from first principles** (integral of the homogeneous
local void over a linear quality profile 0->alpha_r) and happens to coincide with
Astrom-Bell Eq.(19); the §7.2 utility-scale benchmark transcription is deferred.

Empirical riser/drum parameters (T_d, beta, V_sd0, k_friction) and the
geometry/metal split (V_t, V_dc, V_r, A_dc, m_t) are marine placeholders with
sensitivity ranges (R1/R9) — see :class:`Ab4Params`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..ab4.geometry import DrumGeometry
from ...props import if97

__all__ = ["Ab4Params", "Ab4Inputs", "Ab4DrumModel", "STATE_NAMES", "mean_void_fraction"]

STATE_NAMES: tuple[str, ...] = ("p", "V_wt", "alpha_r", "V_sd")
_G = 9.80665


def mean_void_fraction(alpha_r: float, rho_w: float, rho_s: float) -> float:
    """Homogeneous, linear-quality mean riser void fraction (derivation in module docstring).

    Bounded to [0, 1); uses a small-alpha series to stay numerically clean as
    alpha_r -> 0 (where the closed form is 0/0).
    """
    a = max(0.0, float(alpha_r))
    drho = rho_w - rho_s
    if a < 1e-9 or drho <= 0.0 or rho_s <= 0.0:
        return 0.0
    z = drho * a / rho_s
    if z < 1e-4:
        # series: 1 - (1/z) ln(1+z) = z/2 - z^2/3 + ...
        bracket = z / 2.0 - z * z / 3.0
    else:
        bracket = 1.0 - math.log1p(z) / z
    av = (rho_w / drho) * bracket
    return float(min(max(av, 0.0), 0.999))


@dataclass(frozen=True)
class Ab4Params:
    """Geometry / metal / empirical parameters.

    Marine-aux placeholders (R1/R9): refine from vendor GA, heat-transfer area and
    circulation ratio (10-30). ``research/sensitivity.py`` screens T_d/beta/V_sd0.
    """

    geometry: DrumGeometry
    V_t: float                 # total system volume (drum+riser+downcomer) [m^3]
    V_dc: float                # downcomer volume (water-filled) [m^3]
    V_r: float                 # riser volume [m^3]
    A_dc: float                # downcomer flow area [m^2]
    m_t_cp: float              # total metal heat capacity m_t*C_p [J/K]
    # empirical drum/riser
    T_d: float = 12.0          # drum steam residence time [s]
    beta: float = 0.3          # fraction of riser steam carried below surface [-]
    V_sd0: float = 0.0         # nominal sub-surface steam volume [m^3]
    k_friction: float = 25.0   # circulation friction coefficient [-]

    @classmethod
    def marine_aux_default(cls) -> "Ab4Params":
        """Documented marine-aux placeholder (7 bar, ~1.4 kg/s). Geometry r=0.75,L=5.0."""
        geom = DrumGeometry(radius_m=0.75, length_m=5.0)
        V_drum = geom.total_volume_m3            # ~8.84 m^3
        V_r = 0.6 * V_drum                       # riser bundle (sizing assumption)
        V_dc = 0.25 * V_drum                     # downcomers
        V_t = V_drum + V_r + V_dc
        A_dc = 0.03                              # m^2 (downcomer cross-section)
        m_t_cp = 6000.0 * 490.0                  # ~6 t steel * 490 J/kgK
        return cls(
            geometry=geom, V_t=V_t, V_dc=V_dc, V_r=V_r, A_dc=A_dc, m_t_cp=m_t_cp,
            T_d=12.0, beta=0.3, V_sd0=0.05 * V_drum, k_friction=25.0,
        )


@dataclass
class Ab4Inputs:
    """Per-step boundary inputs to the core (supplied by lines/furnace)."""

    Q: float            # evaporator heat input [W]
    q_f: float          # feedwater mass flow [kg/s]
    h_f: float          # feedwater enthalpy [J/kg]
    q_s: float          # steam mass flow [kg/s]
    q_leak: float = 0.0  # tube-leak outflow [kg/s]
    q_bd: float = 0.0    # blowdown outflow [kg/s]


class Ab4DrumModel:
    def __init__(self, params: Ab4Params) -> None:
        self.p = params

    # ---- algebraic helpers ----
    def circulation_flow(self, rho_w: float, rho_s: float, alpha_v: float) -> float:
        """Static downcomer circulation flow [kg/s] (§3.1 static balance)."""
        drho = max(rho_w - rho_s, 0.0)
        driving = 2.0 * rho_w * self.p.A_dc * drho * _G * max(alpha_v, 0.0) * self.p.V_r
        return float(math.sqrt(max(driving, 0.0) / max(self.p.k_friction, 1e-9)))

    def drum_level_m(self, V_wt: float, V_sd: float, alpha_v: float) -> float:
        """Apparent drum water level [m]; swell enters via V_sd and riser void."""
        V_wd = V_wt - self.p.V_dc - (1.0 - alpha_v) * self.p.V_r
        return self.p.geometry.level_from_volume(max(V_wd + V_sd, 0.0))

    # ---- RHS ----
    def derivatives(self, x: np.ndarray, u: Ab4Inputs) -> np.ndarray:
        p_pa, V_wt, alpha_r, V_sd = (float(v) for v in x)
        p_bar = p_pa / 1.0e5
        b = if97.saturation_state(p_bar)
        rho_w, rho_s = b.rho_w, b.rho_s
        h_w, h_s, h_fg = b.h_w, b.h_s, max(b.h_fg, 1.0)
        # property derivatives w.r.t. pressure [per Pa]
        drw, drs = b.drho_w_dp, b.drho_s_dp
        dhw, dhs = b.dh_w_dp, b.dh_s_dp
        dTsat_dp = b.dTsat_dp

        V_st = self.p.V_t - V_wt

        # --- E1/E2 exact 2x2 in (dp, dV_wt) ---
        # d/dt[rho_s V_st + rho_w V_wt] = q_f - q_s - q_leak - q_bd
        e11 = V_st * drs + V_wt * drw
        e12 = rho_w - rho_s
        # d/dt[rho_s h_s V_st + rho_w h_w V_wt - p V_t + m_t Cp Tsat] = Q + q_f h_f - q_s h_s - (q_leak+q_bd) h_w
        d_rhsh_s = h_s * drs + rho_s * dhs   # d(rho_s h_s)/dp
        d_rhwh_w = h_w * drw + rho_w * dhw   # d(rho_w h_w)/dp
        e21 = V_st * d_rhsh_s + V_wt * d_rhwh_w - self.p.V_t + self.p.m_t_cp * dTsat_dp
        e22 = rho_w * h_w - rho_s * h_s

        out = u.q_leak + u.q_bd
        b1 = u.q_f - u.q_s - out
        b2 = u.Q + u.q_f * u.h_f - u.q_s * h_s - out * h_w

        det = e11 * e22 - e12 * e21
        if abs(det) < 1e-12:
            dp = 0.0
            dV_wt = (b1 - e11 * dp) / e12 if abs(e12) > 1e-12 else 0.0
        else:
            dp = (b1 * e22 - e12 * b2) / det
            dV_wt = (e11 * b2 - b1 * e21) / det

        # --- E3 riser steam fraction: relaxation to steady quality q_boil/q_dc ---
        alpha_v = mean_void_fraction(alpha_r, rho_w, rho_s)
        q_dc = self.circulation_flow(rho_w, rho_s, alpha_v)
        q_boil = max(u.Q, 0.0) / h_fg
        riser_water = rho_w * self.p.V_r
        dalpha_r = (q_boil - alpha_r * q_dc) / max(riser_water, 1e-6)

        # --- E4 drum sub-surface steam volume: carry-under minus surface escape ---
        carry_under = self.p.beta * alpha_r * q_dc / max(rho_s, 1e-9)  # [m^3/s]
        dV_sd = carry_under - (V_sd - self.p.V_sd0) / max(self.p.T_d, 1e-6)

        return np.array([dp, dV_wt, dalpha_r, dV_sd], dtype=float)

    def conservation_residuals(self, x: np.ndarray, u: Ab4Inputs, dx: np.ndarray) -> dict[str, float]:
        """Mass/energy balance residuals [kg/s], [W]. ~0 by construction (E1/E2 exact)."""
        p_pa, V_wt, alpha_r, V_sd = (float(v) for v in x)
        b = if97.saturation_state(p_pa / 1.0e5)
        rho_w, rho_s = b.rho_w, b.rho_s
        h_w, h_s = b.h_w, b.h_s
        drw, drs, dhw, dhs, dTsat_dp = b.drho_w_dp, b.drho_s_dp, b.dh_w_dp, b.dh_s_dp, b.dTsat_dp
        dp, dV_wt = float(dx[0]), float(dx[1])
        V_st = self.p.V_t - V_wt
        out = u.q_leak + u.q_bd

        dM = (V_st * drs + V_wt * drw) * dp + (rho_w - rho_s) * dV_wt
        mass_resid = dM - (u.q_f - u.q_s - out)

        dU = (
            V_st * (h_s * drs + rho_s * dhs) + V_wt * (h_w * drw + rho_w * dhw)
            - self.p.V_t + self.p.m_t_cp * dTsat_dp
        ) * dp + (rho_w * h_w - rho_s * h_s) * dV_wt
        energy_resid = dU - (u.Q + u.q_f * u.h_f - u.q_s * h_s - out * h_w)
        return {"mass_balance_residual": float(mass_resid), "energy_balance_residual": float(energy_resid)}

    def outputs(self, x: np.ndarray, u: Ab4Inputs) -> dict[str, float]:
        p_pa, V_wt, alpha_r, V_sd = (float(v) for v in x)
        b = if97.saturation_state(p_pa / 1.0e5)
        alpha_v = mean_void_fraction(alpha_r, b.rho_w, b.rho_s)
        return {
            "drum_pressure": p_pa / 1.0e5,
            "drum_level": self.drum_level_m(V_wt, V_sd, alpha_v),
            "drum_temp": b.Tsat_C,
            "steam_flow": u.q_s,
            "feedwater_flow": u.q_f,
            "alpha_r": alpha_r,
            "alpha_v_mean": alpha_v,
            "circulation_flow": self.circulation_flow(b.rho_w, b.rho_s, alpha_v),
            "V_sd": V_sd,
        }
