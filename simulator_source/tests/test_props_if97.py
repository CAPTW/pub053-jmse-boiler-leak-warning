"""§7.0 property gate (docs/phase_a_design.md) — DoD 2.

Validates the Phase A ``props.if97`` spline layer against iapws reference points:
value accuracy < 0.1 %, spline-derivative accuracy < 0.5 %, boundary behaviour,
out-of-range ValueError (no clamp), and ImportError when iapws is absent.
"""

from __future__ import annotations

import builtins
import importlib
import sys

import pytest

iapws = pytest.importorskip("iapws")
from iapws import IAPWS97  # noqa: E402

from boiler_pdm_sim.props import if97  # noqa: E402


REF_PRESSURES_BAR = [1.0, 7.0, 10.0, 50.0, 100.0]


def _iapws_ref(p_bar: float) -> dict[str, float]:
    sl = IAPWS97(P=p_bar / 10.0, x=0.0)
    sv = IAPWS97(P=p_bar / 10.0, x=1.0)
    return {
        "Tsat_C": sl.T - 273.15,
        "rho_w": sl.rho,
        "rho_s": sv.rho,
        "h_w": sl.h * 1000.0,
        "h_s": sv.h * 1000.0,
    }


@pytest.mark.parametrize("p_bar", REF_PRESSURES_BAR)
def test_value_accuracy_within_0p1pct(p_bar):
    """Tsat, rho_w, rho_s, h_w, h_s within 0.1 % of iapws at 1/7/10/50/100 bar."""
    ref = _iapws_ref(p_bar)
    b = if97.saturation_state(p_bar)
    got = {
        "Tsat_C": b.Tsat_C,
        "rho_w": b.rho_w,
        "rho_s": b.rho_s,
        "h_w": b.h_w,
        "h_s": b.h_s,
    }
    for key, ref_val in ref.items():
        rel = abs(got[key] - ref_val) / max(abs(ref_val), 1e-9)
        assert rel < 1e-3, f"{key} at {p_bar} bar: rel err {rel:.2e} >= 0.1% (got {got[key]}, ref {ref_val})"


@pytest.mark.parametrize("p_bar", REF_PRESSURES_BAR)
def test_derivative_accuracy_within_0p5pct(p_bar):
    """Spline d/dp vs iapws fine central difference (eps = 1e-2 bar) within 0.5 %."""
    eps_bar = 1e-2
    bar_to_pa = 1.0e5

    def fd(prop_fn):
        hi = prop_fn(p_bar + eps_bar)
        lo = prop_fn(p_bar - eps_bar)
        return (hi - lo) / (2.0 * eps_bar * bar_to_pa)  # per Pa

    def tsat(p):
        return IAPWS97(P=p / 10.0, x=0.0).T - 273.15

    def rho_w(p):
        return IAPWS97(P=p / 10.0, x=0.0).rho

    def rho_s(p):
        return IAPWS97(P=p / 10.0, x=1.0).rho

    def h_w(p):
        return IAPWS97(P=p / 10.0, x=0.0).h * 1000.0

    def h_s(p):
        return IAPWS97(P=p / 10.0, x=1.0).h * 1000.0

    b = if97.saturation_state(p_bar)
    checks = {
        "dTsat_dp": (b.dTsat_dp, fd(tsat)),
        "drho_w_dp": (b.drho_w_dp, fd(rho_w)),
        "drho_s_dp": (b.drho_s_dp, fd(rho_s)),
        "dh_w_dp": (b.dh_w_dp, fd(h_w)),
        "dh_s_dp": (b.dh_s_dp, fd(h_s)),
    }
    for name, (spline_d, fd_d) in checks.items():
        rel = abs(spline_d - fd_d) / max(abs(fd_d), 1e-30)
        assert rel < 5e-3, f"{name} at {p_bar} bar: rel err {rel:.2e} >= 0.5% (spline {spline_d:.3e}, fd {fd_d:.3e})"


def test_internal_energy_matches_h_minus_pv():
    """u = h - P/rho (exact) and matches iapws .u to ~1e-4 relative."""
    p_bar = 10.0
    b = if97.saturation_state(p_bar)
    sl = IAPWS97(P=p_bar / 10.0, x=0.0)
    assert abs(b.u_w - sl.u * 1000.0) / abs(sl.u * 1000.0) < 1e-4


def test_boundaries_defined():
    """0.5 and 120 bar return finite, physically-ordered values."""
    for p_bar in (if97.P_MIN_BAR, if97.P_MAX_BAR):
        b = if97.saturation_state(p_bar)
        assert b.Tsat_C > 0.0
        assert b.rho_w > b.rho_s > 0.0
        assert b.h_s > b.h_w > 0.0
        assert b.h_fg > 0.0


@pytest.mark.parametrize("p_bar", [0.49, 0.0, -1.0, 120.01, 200.0])
def test_out_of_range_raises_no_clamp(p_bar):
    """Out-of-range pressure raises ValueError (clamping is banned — §3.2)."""
    with pytest.raises(ValueError):
        if97.saturation_state(p_bar)
    with pytest.raises(ValueError):
        if97.tsat_C(p_bar)


def test_import_fails_without_iapws(monkeypatch):
    """With iapws unavailable, importing props.if97 raises ImportError (no fallback)."""
    # Drop cached props modules so a fresh import re-runs the top-level iapws import.
    for mod in list(sys.modules):
        if mod == "iapws" or mod.startswith("boiler_pdm_sim.props"):
            monkeypatch.delitem(sys.modules, mod, raising=False)

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "iapws" or name.startswith("iapws."):
            raise ImportError("iapws blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(ImportError):
        importlib.import_module("boiler_pdm_sim.props.if97")
