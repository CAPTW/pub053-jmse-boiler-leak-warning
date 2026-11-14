"""Tests for the Phase A ab4 4-state drum core (§3.1, conservation-first).

Key checks:
* mean void fraction: limits, monotonicity, bound, closed-form spot value.
* circulation flow positive.
* **Conservation** two ways: (a) analytic residuals ~0 (E1/E2 self-consistency),
  (b) finite-difference of the actual stored mass/energy vs net flux (proves the
  analytic e_ij are the true derivatives of stored inventory).
* short BDF integration stays finite and physical (no clamps).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

iapws = pytest.importorskip("iapws")
from scipy.integrate import solve_ivp  # noqa: E402

from boiler_pdm_sim.props import if97  # noqa: E402
from boiler_pdm_sim.core.ab4.drum_model import (  # noqa: E402
    Ab4DrumModel,
    Ab4Inputs,
    Ab4Params,
    mean_void_fraction,
)

P = Ab4Params.marine_aux_default()
MODEL = Ab4DrumModel(P)


def _ref_operating_state():
    """A physically reasonable 7-bar marine-aux operating point."""
    p_pa = 7.0e5
    V_wt = 0.66 * P.V_t          # mostly water-filled system
    alpha_r = 0.08
    V_sd = P.V_sd0
    return np.array([p_pa, V_wt, alpha_r, V_sd], dtype=float)


def _ref_inputs():
    b = if97.saturation_state(7.0)
    h_f = 4200.0 * 60.0          # feedwater at 60 C
    Q = 3.5e6                    # ~3.5 MW
    q_boil = Q / b.h_fg
    # near steady: feed = steam, steam carries h_s - h_f against Q
    q_s = Q / (b.h_s - h_f)
    return Ab4Inputs(Q=Q, q_f=q_s, h_f=h_f, q_s=q_s), q_boil


# ---------------- void fraction ----------------

def test_void_fraction_limits_and_bounds():
    b = if97.saturation_state(7.0)
    assert mean_void_fraction(0.0, b.rho_w, b.rho_s) == 0.0
    for a in [0.01, 0.05, 0.1, 0.3, 0.6, 1.0]:
        av = mean_void_fraction(a, b.rho_w, b.rho_s)
        assert 0.0 <= av < 1.0


def test_void_fraction_monotonic():
    b = if97.saturation_state(7.0)
    avs = [mean_void_fraction(a, b.rho_w, b.rho_s) for a in [0.02, 0.05, 0.1, 0.2, 0.4, 0.8]]
    assert all(y > x for x, y in zip(avs, avs[1:]))


def test_void_fraction_matches_closed_form():
    rw, rs = 902.6, 3.666
    a = 0.1
    z = (rw - rs) * a / rs
    expected = (rw / (rw - rs)) * (1.0 - math.log1p(z) / z)
    assert mean_void_fraction(a, rw, rs) == pytest.approx(expected, rel=1e-9)


def test_circulation_positive():
    b = if97.saturation_state(7.0)
    av = mean_void_fraction(0.08, b.rho_w, b.rho_s)
    assert MODEL.circulation_flow(b.rho_w, b.rho_s, av) > 0.0


# ---------------- conservation ----------------

def test_analytic_residuals_near_zero():
    """E1/E2 are solved exactly -> analytic residuals are ~machine epsilon."""
    x = _ref_operating_state()
    u, _ = _ref_inputs()
    dx = MODEL.derivatives(x, u)
    res = MODEL.conservation_residuals(x, u, dx)
    assert abs(res["mass_balance_residual"]) < 1e-9          # kg/s
    assert abs(res["energy_balance_residual"]) < 1e-3        # W (scaled by large e_ij)


def _stored_mass(x):
    p_pa, V_wt = float(x[0]), float(x[1])
    b = if97.saturation_state(p_pa / 1.0e5)
    V_st = P.V_t - V_wt
    return b.rho_s * V_st + b.rho_w * V_wt


def _stored_energy(x):
    p_pa, V_wt = float(x[0]), float(x[1])
    b = if97.saturation_state(p_pa / 1.0e5)
    V_st = P.V_t - V_wt
    return b.rho_s * b.h_s * V_st + b.rho_w * b.h_w * V_wt - p_pa * P.V_t + P.m_t_cp * b.Tsat_C


def test_finite_difference_conservation():
    """d/dt of the ACTUAL stored mass/energy (finite diff) matches the net flux.

    This is the real conservation proof: it checks the analytic e_ij are the true
    derivatives of stored inventory, not just internally self-consistent.
    """
    x = _ref_operating_state()
    u, _ = _ref_inputs()
    dx = MODEL.derivatives(x, u)

    dt = 1e-2
    x2 = x + dx * dt
    out = u.q_leak + u.q_bd

    dM_fd = (_stored_mass(x2) - _stored_mass(x)) / dt
    net_mass = u.q_f - u.q_s - out
    assert dM_fd == pytest.approx(net_mass, abs=1e-4)

    b = if97.saturation_state(float(x[0]) / 1.0e5)
    dU_fd = (_stored_energy(x2) - _stored_energy(x)) / dt
    net_energy = u.Q + u.q_f * u.h_f - u.q_s * b.h_s - out * b.h_w
    # relative tolerance: FD truncation on a ~1e8-scale storage term
    assert dU_fd == pytest.approx(net_energy, rel=2e-3)


# ---------------- integration ----------------

def test_short_bdf_integration_stays_physical():
    x0 = _ref_operating_state()
    u, _ = _ref_inputs()

    def f(_t, x):
        return MODEL.derivatives(x, u)

    sol = solve_ivp(f, (0.0, 30.0), x0, method="BDF", rtol=1e-5, atol=[1e2, 1e-4, 1e-5, 1e-5])
    assert sol.success
    p_bar = sol.y[0] / 1.0e5
    assert np.all(np.isfinite(sol.y))
    assert np.all((p_bar > if97.P_MIN_BAR) & (p_bar < if97.P_MAX_BAR))
    # near-steady inputs -> pressure should not run away (stays within a few bar)
    assert abs(p_bar[-1] - 7.0) < 2.0


def test_outputs_keys_and_level_in_drum():
    x = _ref_operating_state()
    u, _ = _ref_inputs()
    y = MODEL.outputs(x, u)
    for k in ("drum_pressure", "drum_level", "drum_temp", "steam_flow", "alpha_v_mean"):
        assert k in y
    assert 0.0 <= y["drum_level"] <= 2.0 * P.geometry.radius_m
    assert y["drum_pressure"] == pytest.approx(7.0, rel=1e-6)
