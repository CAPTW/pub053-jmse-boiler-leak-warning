"""Tests for the Phase A enthalpy-based furnace (§3.3, WP A4).

Covers the §7.1 gas-side closure (Q_comb = Q_water + L_stack), §7.3 steady-state
anchoring at the marine rated point (eta/O2/T_stack ranges), load monotonicity,
the burner_deg signature (eta_comb down -> O2 up, eta down), the fouling signature
(ua_scale down -> T_stack up, eta down), and prepare/evaluate consistency.
"""

from __future__ import annotations

import pytest

iapws = pytest.importorskip("iapws")

from boiler_pdm_sim.core.ab4.furnace import Furnace
from boiler_pdm_sim.props import if97

_B = if97.saturation_state(7.0)
_TSAT = _B.Tsat_C
_H_F = 4200.0 * 60.0
_Q_EVAP_RATED = 1.4 * (_B.h_s - _H_F)   # ~3.5 MW


def _furnace() -> Furnace:
    return Furnace.from_rated(
        q_evap_rated_W=_Q_EVAP_RATED, Tsat_rated_C=_TSAT, rated_fuel_cmd=0.7, target_eta=0.90
    )


def test_section_7_3_anchoring_at_rated():
    fur = _furnace()
    r = fur.heat_to_drum(0.7, 1.0, _TSAT)
    assert r.Q_drum_W == pytest.approx(_Q_EVAP_RATED, rel=1e-3)
    assert 0.88 <= r.eta_boiler <= 0.92          # direct-method efficiency
    assert 2.5 <= r.o2_dry_pct <= 4.0            # dry-basis excess O2
    assert 180.0 <= r.T_stack_C <= 250.0         # stack temperature
    assert 1700.0 < r.T_ad_C < 2100.0            # adiabatic flame temp (MGO, lambda 1.15)


def test_section_7_1_gas_side_closure():
    """Q_comb = Q_water + L_stack to ~root-find precision (enthalpy bookkeeping)."""
    fur = _furnace()
    for fc in (0.3, 0.5, 0.7, 1.0):
        for ec in (1.0, 0.9):
            r = fur.heat_to_drum(fc, ec, _TSAT)
            # residual relative to the combustion heat is negligible
            q_comb = fc * fur.m_fuel_max_kg_s * fur.fuel.LHV_MJ_kg * 1e6 * ec
            assert abs(r.gas_residual_W) < max(1e-3 * q_comb, 1e-2)


def test_load_monotonicity():
    fur = _furnace()
    res = [fur.heat_to_drum(fc, 1.0, _TSAT) for fc in (0.3, 0.5, 0.7, 1.0)]
    q = [r.Q_drum_W for r in res]
    ts = [r.T_stack_C for r in res]
    assert all(b > a for a, b in zip(q, q[1:]))     # more fuel -> more heat to drum
    assert all(b >= a for a, b in zip(ts, ts[1:]))  # ... and a hotter stack


def test_burner_deg_signature_o2_up_eta_down():
    fur = _furnace()
    base = fur.heat_to_drum(0.7, 1.0, _TSAT)
    deg = fur.heat_to_drum(0.7, 0.85, _TSAT)
    assert deg.o2_dry_pct > base.o2_dry_pct      # incomplete combustion -> excess O2
    assert deg.eta_boiler < base.eta_boiler      # ... and lower efficiency
    assert deg.Q_drum_W < base.Q_drum_W


def test_fouling_signature_stack_up_eta_down():
    fur = _furnace()
    clean = fur.heat_to_drum(0.7, 1.0, _TSAT, ua_scale=1.0)
    fouled = fur.heat_to_drum(0.7, 1.0, _TSAT, ua_scale=0.6)
    assert fouled.T_stack_C > clean.T_stack_C    # worse heat transfer -> hotter stack
    assert fouled.eta_boiler < clean.eta_boiler  # ... and lower efficiency


def test_prepare_evaluate_matches_heat_to_drum():
    fur = _furnace()
    op = fur.prepare(0.7, 1.0)
    assert op is not None
    r_split = fur.evaluate(op, _TSAT)
    r_full = fur.heat_to_drum(0.7, 1.0, _TSAT)
    assert r_split.Q_drum_W == pytest.approx(r_full.Q_drum_W, rel=1e-9)
    assert r_split.T_stack_C == pytest.approx(r_full.T_stack_C, rel=1e-9)


def test_no_fire_returns_zero():
    fur = _furnace()
    assert fur.prepare(0.0, 1.0) is None
    r = fur.heat_to_drum(0.0, 1.0, _TSAT)
    assert r.Q_drum_W == 0.0
