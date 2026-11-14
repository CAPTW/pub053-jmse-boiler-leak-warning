"""Tests for the ab4 CoreBackend wiring (A3-e/f) and the §7.1 conservation gate.

Covers: factory construction via core_backend.type='ab4', CoreBackend protocol
conformance, advance/outputs/invariants contract incl. the schema-required flue
channels, and a long closed-loop run that must stay physical and conserve
mass/energy within the §7.1 bounds (mass < 1% rated steam, energy < 1% Q_op).
"""

from __future__ import annotations

import numpy as np
import pytest

iapws = pytest.importorskip("iapws")

from boiler_pdm_sim.core.backend_factory import build_core_backend
from boiler_pdm_sim.core.backend_protocol import BackendInputs, CoreBackend, StepReport
from boiler_pdm_sim.core.ab4.backend import Ab4Backend
from boiler_pdm_sim.core.ab4.drum_model import mean_void_fraction
from boiler_pdm_sim.props import if97

_BOILER_CFG = {
    "geometry": {"drum_radius_m": 0.75, "drum_length_m": 5.0},
    "nominal": {"pressure_bar": 7.0, "steam_flow_kg_s": 1.4, "level_fraction": 0.55},
    "parameters": {"combustion": {"eta": 0.9, "qmax_MW": 4.0}},
}
_Q_S_RATED = 1.4


def _backend() -> Ab4Backend:
    return build_core_backend(_BOILER_CFG, {"type": "ab4"})


def test_factory_builds_ab4_and_conforms_to_corebackend():
    be = _backend()
    assert isinstance(be, Ab4Backend)
    assert isinstance(be, CoreBackend)  # runtime_checkable structural conformance
    assert be.state_names == ["p", "V_wt", "alpha_r", "V_sd"]
    assert be.state.shape == (4,)


def test_circulation_ratio_in_design_band():
    """Friction is back-calculated so the circulation ratio lands in 10-30 (R9)."""
    be = _backend()
    b = if97.saturation_state(7.0)
    _p, _V_wt, alpha_r, _V_sd = be.state
    av = mean_void_fraction(alpha_r, b.rho_w, b.rho_s)
    q_dc = be.model.circulation_flow(b.rho_w, b.rho_s, av)
    cr = q_dc / _Q_S_RATED
    assert 10.0 <= cr <= 30.0          # design circulation-ratio band
    assert 0.01 < alpha_r < 0.2        # realistic riser-exit quality


def test_outputs_have_required_flue_channels():
    be = _backend()
    inp = BackendInputs.from_control({"fuel_cmd": 0.5, "fw_cmd": 0.5, "steam_demand": 0.6})
    y = be.outputs(inp, {})
    for k in ("drum_pressure", "drum_level", "drum_temp", "flue_gas_temp", "O2", "h_fw"):
        assert k in y
    assert y["drum_pressure"] == pytest.approx(7.0, rel=1e-6)
    assert y["wall_temp"] == pytest.approx(y["drum_temp"])  # metal follows Tsat (no fixed 280C)


def test_advance_returns_stepreport_and_conserves():
    be = _backend()
    inp = BackendInputs.from_control({"fuel_cmd": 0.5, "fw_cmd": 0.5, "steam_demand": 0.5})
    rep = be.advance(0.0, 1.0, inp, {}, method="BDF")
    assert isinstance(rep, StepReport)
    assert rep.x_after.shape == (4,)
    assert rep.solver["fallback_used"] is False
    assert abs(rep.alignment["mass_balance_residual"]) < 1e-6
    assert abs(rep.alignment["energy_balance_residual"]) < 1e-1


def test_reset_restores_initial_state():
    be = _backend()
    x0 = be.state.copy()
    be.advance(0.0, 1.0, BackendInputs.from_control({"fuel_cmd": 0.6, "fw_cmd": 0.4, "steam_demand": 0.7}), {})
    assert not np.allclose(be.state, x0)
    be.reset()
    assert np.allclose(be.state, x0)


def _run_closed_loop(horizon_s: float, dt: float, steam_demand_fn):
    """Drive ab4 with a simple PI loop; return per-step residuals and trajectory."""
    be = _backend()
    p_sp_bar, level_sp_m = 7.0, 0.85
    fuel_i = fw_i = 0.0
    fuel_cmd, fw_cmd = 0.5, 0.5

    mass_res, energy_res = [], []
    p_hist, level_hist, feasible_all = [], [], True

    t = 0.0
    n = int(horizon_s / dt)
    for i in range(n + 1):
        inp = BackendInputs.from_control(
            {"fuel_cmd": fuel_cmd, "fw_cmd": fw_cmd, "steam_demand": steam_demand_fn(t)}
        )
        y = be.outputs(inp, {})
        p_bar, level = y["drum_pressure"], y["drum_level"]
        p_hist.append(p_bar)
        level_hist.append(level)

        # simple PI control (clamped)
        e_p = p_sp_bar - p_bar
        fuel_i = float(np.clip(fuel_i + 0.02 * e_p * dt, -0.5, 0.5))
        fuel_cmd = float(np.clip(0.5 + 0.08 * e_p + fuel_i, 0.0, 1.0))
        e_l = level_sp_m - level
        fw_i = float(np.clip(fw_i + 0.05 * e_l * dt, -0.5, 0.5))
        fw_cmd = float(np.clip(0.5 + 1.5 * e_l + fw_i, 0.0, 1.0))

        if i < n:
            rep = be.advance(t, dt, inp, {}, method="BDF")
            mass_res.append(abs(rep.alignment["mass_balance_residual"]))
            energy_res.append(abs(rep.alignment["energy_balance_residual"]))
            feasible_all = feasible_all and bool(rep.alignment["feasible"])
        t += dt
    return {
        "mass_res": np.array(mass_res),
        "energy_res": np.array(energy_res),
        "p": np.array(p_hist),
        "level": np.array(level_hist),
        "feasible_all": feasible_all,
    }


def test_conservation_gate_long_run():
    """§7.1: a long closed-loop run conserves mass/energy and stays physical."""
    # 1 hour at dt=2 s (1800 steps) with a steam-demand step at 1800 s.
    res = _run_closed_loop(3600.0, 2.0, lambda t: 0.6 if t < 1800.0 else 0.75)

    # §7.1 mass residual < 1% of rated steam flow; energy < 1% of Q_op (~3.5 MW)
    mass_bound = 0.01 * _Q_S_RATED          # 0.014 kg/s
    energy_bound = 0.01 * 3.5e6             # 35000 W
    assert res["mass_res"].max() < mass_bound
    assert res["energy_res"].max() < energy_bound

    # solver never fell back, states stayed feasible, pressure/level bounded
    assert res["feasible_all"]
    assert np.all(np.isfinite(res["p"])) and np.all(np.isfinite(res["level"]))
    assert res["p"].min() > 1.0 and res["p"].max() < 20.0
    assert res["level"].min() > 0.0 and res["level"].max() < 1.5


def test_shrink_swell_sign_on_steam_step():
    """A steam-demand increase causes an initial drum-level swell (non-minimum phase)."""
    res = _run_closed_loop(2400.0, 2.0, lambda t: 0.55 if t < 1200.0 else 0.8)
    # find the step index and check the level rises in the seconds just after it
    step_idx = int(1200.0 / 2.0)
    pre = res["level"][step_idx - 1]
    just_after = res["level"][step_idx + 1 : step_idx + 8].max()
    assert just_after > pre  # swell: level transiently rises despite more steam out
