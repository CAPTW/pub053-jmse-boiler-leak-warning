"""Tests for the Phase A feedwater / steam / blowdown line closures (§3.5)."""

from __future__ import annotations

import pytest

from boiler_pdm_sim.core.ab4.feedwater import FeedwaterLine
from boiler_pdm_sim.core.ab4.steam_line import (
    CRITICAL_PRESSURE_RATIO,
    BlowdownSchedule,
    SteamLine,
)

iapws = pytest.importorskip("iapws")
from boiler_pdm_sim.props import if97  # noqa: E402

_P_RATED_PA = 7.0e5
_B = if97.saturation_state(7.0)
_RHO_W = _B.rho_w   # ~902.6
_RHO_S = _B.rho_s   # ~3.67


# ---------------- feedwater ----------------

def _fw() -> FeedwaterLine:
    return FeedwaterLine.from_rated(
        q_rated_kg_s=1.4, p_drum_rated_pa=_P_RATED_PA, rho_w=_RHO_W, opening_rated=0.5
    )


def test_feedwater_rated_point_recovers_rated_flow():
    fw = _fw()
    q = fw.flow_kg_s(_P_RATED_PA, opening=0.5, rho_w=_RHO_W)
    assert q == pytest.approx(1.4, rel=0.05)


def test_feedwater_monotonic_in_opening():
    fw = _fw()
    qs = [fw.flow_kg_s(_P_RATED_PA, opening=o, rho_w=_RHO_W) for o in (0.1, 0.3, 0.5, 0.8, 1.0)]
    assert all(b > a for a, b in zip(qs, qs[1:]))


def test_feedwater_decreases_with_drum_pressure():
    fw = _fw()
    q_lo = fw.flow_kg_s(6.0e5, opening=0.5, rho_w=_RHO_W)
    q_hi = fw.flow_kg_s(8.0e5, opening=0.5, rho_w=_RHO_W)
    assert q_lo > q_hi


def test_feedwater_pump_wear_reduces_flow_and_zero_opening():
    fw = _fw()
    q_ok = fw.flow_kg_s(_P_RATED_PA, opening=0.5, rho_w=_RHO_W, wear=0.0)
    q_worn = fw.flow_kg_s(_P_RATED_PA, opening=0.5, rho_w=_RHO_W, wear=0.3)
    assert q_worn < q_ok
    assert fw.flow_kg_s(_P_RATED_PA, opening=0.0, rho_w=_RHO_W) == 0.0


def test_feedwater_zero_when_drum_exceeds_shutoff():
    fw = _fw()
    # Drum pressure above feedtank + shutoff head -> no flow possible.
    huge = fw.p_feedtank_pa + fw.pump_a0_pa + 1.0
    assert fw.flow_kg_s(huge, opening=1.0, rho_w=_RHO_W) == 0.0


# ---------------- steam ----------------

def _sl(p_down_pa: float) -> SteamLine:
    return SteamLine.from_rated(
        q_rated_kg_s=1.4,
        p_drum_rated_pa=_P_RATED_PA,
        rho_s_rated=_RHO_S,
        p_downstream_pa=p_down_pa,
        opening_rated=0.6,
    )


def test_steam_rated_point_recovers_rated_flow_subcritical():
    sl = _sl(5.0e5)  # ratio 0.71 > 0.577 -> subcritical at rated
    q = sl.flow_kg_s(_P_RATED_PA, steam_demand=0.6, rho_s=_RHO_S)
    assert q == pytest.approx(1.4, rel=0.05)


def test_steam_monotonic_in_demand():
    sl = _sl(5.0e5)
    qs = [sl.flow_kg_s(_P_RATED_PA, steam_demand=d, rho_s=_RHO_S) for d in (0.1, 0.3, 0.6, 1.0)]
    assert all(b > a for a, b in zip(qs, qs[1:]))


def test_steam_choked_flow_is_linear_in_drum_pressure():
    # For a FIXED valve in the choked regime, q = c_choked*cv*op*p is linear in p
    # and independent of the (fixed) downstream pressure.
    sl = _sl(0.10 * _P_RATED_PA)  # ratio 0.10 < 0.577 -> choked at/above rated drum p
    p1, p2 = _P_RATED_PA, 1.5 * _P_RATED_PA
    assert sl.p_downstream_pa / p1 < CRITICAL_PRESSURE_RATIO
    assert sl.p_downstream_pa / p2 < CRITICAL_PRESSURE_RATIO
    q1 = sl.flow_kg_s(p1, steam_demand=0.6, rho_s=_RHO_S)
    q2 = sl.flow_kg_s(p2, steam_demand=0.6, rho_s=_RHO_S)
    assert q2 / q1 == pytest.approx(p2 / p1, rel=1e-9)


def test_steam_continuous_across_critical_transition():
    # Valve whose downstream equals the critical ratio at the rated drum pressure:
    # flow is continuous when crossing the subcritical<->choked boundary.
    p_down = CRITICAL_PRESSURE_RATIO * _P_RATED_PA
    sl = _sl(p_down)
    q_sub = sl.flow_kg_s(_P_RATED_PA * 0.999, steam_demand=0.6, rho_s=_RHO_S)  # subcritical side
    q_chk = sl.flow_kg_s(_P_RATED_PA * 1.001, steam_demand=0.6, rho_s=_RHO_S)  # choked side
    assert q_sub == pytest.approx(q_chk, rel=1e-2)


def test_steam_zero_demand():
    sl = _sl(5.0e5)
    assert sl.flow_kg_s(_P_RATED_PA, steam_demand=0.0, rho_s=_RHO_S) == 0.0


def test_critical_ratio_constant():
    assert CRITICAL_PRESSURE_RATIO == pytest.approx(0.577, abs=1e-3)


# ---------------- blowdown ----------------

def test_blowdown_disabled_is_zero():
    bd = BlowdownSchedule(enabled=False, flow_kg_s=0.1)
    assert all(bd.flow_at(t) == 0.0 for t in (0.0, 100.0, 5000.0))


def test_blowdown_periodic_on_off():
    bd = BlowdownSchedule(enabled=True, period_s=1000.0, duration_s=60.0, flow_kg_s=0.05)
    assert bd.flow_at(0.0) == 0.05      # within first window
    assert bd.flow_at(59.0) == 0.05
    assert bd.flow_at(61.0) == 0.0      # after window
    assert bd.flow_at(1000.0) == 0.05   # next period
    assert bd.flow_at(1061.0) == 0.0
