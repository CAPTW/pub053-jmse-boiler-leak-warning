"""Integrated steady-state anchoring (§7.3) and low-pressure transient (§7.4).

The tight §7.3 furnace anchoring (eta/O2/T_stack at the exact rated point) is
asserted at component level in test_ab4_furnace; here we confirm the *integrated*
ab4 backend (drum + lines + furnace under a closed loop) settles to a sane
operating point, and that the low-pressure transient (§7.4) shows the correct
non-minimum-phase swell sign and stays physical.
"""

from __future__ import annotations

import numpy as np
import pytest

iapws = pytest.importorskip("iapws")

from boiler_pdm_sim.core.backend_factory import build_core_backend
from boiler_pdm_sim.core.backend_protocol import BackendInputs


def _drive(boiler_cfg, *, horizon_s, dt, steam_demand, p_sp_bar, level_sp=0.85, seed_state=None):
    """Simple PI closed loop on the ab4 backend; returns the trajectory + final outputs."""
    be = build_core_backend(boiler_cfg, {"type": "ab4"})
    fuel_i = fw_i = 0.0
    fuel_cmd = fw_cmd = 0.5
    levels, pressures, last_y = [], [], None
    t = 0.0
    n = int(horizon_s / dt)
    for i in range(n + 1):
        sd = steam_demand(t) if callable(steam_demand) else steam_demand
        inp = BackendInputs.from_control({"fuel_cmd": fuel_cmd, "fw_cmd": fw_cmd, "steam_demand": sd})
        y = be.outputs(inp, {})
        last_y = y
        levels.append(y["drum_level"])
        pressures.append(y["drum_pressure"])
        e_p = p_sp_bar - y["drum_pressure"]
        fuel_i = float(np.clip(fuel_i + 0.02 * e_p * dt, -0.5, 0.5))
        fuel_cmd = float(np.clip(0.5 + 0.08 * e_p + fuel_i, 0.0, 1.0))
        e_l = level_sp - y["drum_level"]
        fw_i = float(np.clip(fw_i + 0.05 * e_l * dt, -0.5, 0.5))
        fw_cmd = float(np.clip(0.5 + 1.5 * e_l + fw_i, 0.0, 1.0))
        if i < n:
            be.advance(t, dt, inp, {}, method="BDF")
        t += dt
    return np.array(levels), np.array(pressures), last_y


_BOILER_7BAR = {
    "geometry": {"drum_radius_m": 0.75, "drum_length_m": 5.0},
    "nominal": {"pressure_bar": 7.0, "steam_flow_kg_s": 1.4, "level_fraction": 0.55},
    "parameters": {"combustion": {"eta": 0.9, "qmax_MW": 4.0}},
}
_BOILER_3BAR = {
    "geometry": {"drum_radius_m": 0.75, "drum_length_m": 5.0},
    "nominal": {"pressure_bar": 3.0, "steam_flow_kg_s": 1.0, "level_fraction": 0.55},
    "parameters": {"combustion": {"eta": 0.9, "qmax_MW": 4.0}},
}


def test_steady_state_operating_point_sane():
    """§7.3 (integrated): a near-rated steady run lands in a sane eta/O2/T_stack band."""
    levels, pressures, y = _drive(
        _BOILER_7BAR, horizon_s=2400.0, dt=2.0, steam_demand=0.7, p_sp_bar=7.0
    )
    # settled near setpoints, trip-free physical band
    assert abs(pressures[-1] - 7.0) < 1.0
    assert 0.4 < levels[-1] < 1.3
    # furnace operating point at the settled state (component §7.3 is tighter)
    assert 0.86 <= y["boiler_efficiency"] <= 0.93
    assert 2.0 <= y["O2"] <= 4.5
    assert 150.0 <= y["flue_gas_temp"] <= 260.0
    assert y["drum_temp"] == pytest.approx(y["wall_temp"])  # metal follows Tsat


def test_low_pressure_transient_swell_and_stability():
    """§7.4: at low pressure a steam-demand step gives an initial level swell and
    the integration stays physical (no clamp, no blowup)."""
    step_t = 1200.0
    dt = 2.0
    levels, pressures, _ = _drive(
        _BOILER_3BAR, horizon_s=2400.0, dt=dt,
        steam_demand=lambda t: 0.5 if t < step_t else 0.75, p_sp_bar=3.0,
    )
    k = int(step_t / dt)
    pre = levels[k - 1]
    swell_peak = levels[k + 1 : k + 8].max()
    assert swell_peak > pre                       # non-minimum-phase swell
    assert np.all(np.isfinite(levels)) and np.all(np.isfinite(pressures))
    assert pressures.min() > 0.5 and pressures.max() < 6.0
    assert levels.min() > 0.0 and levels.max() < 1.5
