"""24-hour full-horizon §7.1 conservation gate (slow / nightly, R7).

Drives the ab4 backend in a closed loop for a full 24 h marine-aux mission and
asserts mass/energy conservation holds within the §7.1 bounds for the entire run,
the solver never falls back, and the state stays physical and trip-free. Marked
``slow`` so the default/PR suite skips it; run with ``pytest -m slow``.
"""

from __future__ import annotations

import numpy as np
import pytest

iapws = pytest.importorskip("iapws")

from boiler_pdm_sim.core.backend_factory import build_core_backend
from boiler_pdm_sim.core.backend_protocol import BackendInputs

_BOILER = {
    "geometry": {"drum_radius_m": 0.75, "drum_length_m": 5.0},
    "nominal": {"pressure_bar": 7.0, "steam_flow_kg_s": 1.4, "level_fraction": 0.55},
    "parameters": {"combustion": {"eta": 0.9, "qmax_MW": 4.0}},
}
_Q_S_RATED = 1.4
_BACKEND = {"type": "ab4", "blowdown": {"enabled": True, "period_s": 3600.0, "duration_s": 60.0, "flow_kg_s": 0.05}}


@pytest.mark.slow
def test_ab4_24h_conservation_gate():
    be = build_core_backend(_BOILER, _BACKEND)
    dt, horizon_s = 2.0, 86400.0           # 24 h at dt=2 s -> 43200 steps
    p_sp, level_sp = 7.0, 0.85
    fuel_i = fw_i = 0.0
    fuel_cmd = fw_cmd = 0.5

    max_mass = max_energy = 0.0
    feasible_all = True
    p_min, p_max = 1e9, -1e9
    l_min, l_max = 1e9, -1e9
    fallback_any = False

    t = 0.0
    n = int(horizon_s / dt)
    for i in range(n + 1):
        # a slow diurnal load swing so the loop actually works over 24 h
        load = 0.6 + 0.15 * np.sin(2.0 * np.pi * t / 43200.0)
        inp = BackendInputs.from_control(
            {"fuel_cmd": fuel_cmd, "fw_cmd": fw_cmd, "steam_demand": float(np.clip(load, 0.2, 0.95))}
        )
        y = be.outputs(inp, {})
        p, level = y["drum_pressure"], y["drum_level"]
        p_min, p_max = min(p_min, p), max(p_max, p)
        l_min, l_max = min(l_min, level), max(l_max, level)

        e_p = p_sp - p
        fuel_i = float(np.clip(fuel_i + 0.02 * e_p * dt, -0.5, 0.5))
        fuel_cmd = float(np.clip(0.5 + 0.08 * e_p + fuel_i, 0.0, 1.0))
        e_l = level_sp - level
        fw_i = float(np.clip(fw_i + 0.05 * e_l * dt, -0.5, 0.5))
        fw_cmd = float(np.clip(0.5 + 1.5 * e_l + fw_i, 0.0, 1.0))

        if i < n:
            rep = be.advance(t, dt, inp, {}, method="BDF")
            max_mass = max(max_mass, abs(rep.alignment["mass_balance_residual"]))
            max_energy = max(max_energy, abs(rep.alignment["energy_balance_residual"]))
            feasible_all = feasible_all and bool(rep.alignment["feasible"])
            fallback_any = fallback_any or bool(rep.solver["fallback_used"])
        t += dt

    # §7.1: mass residual < 1% rated steam, energy < 1% of ~3.5 MW operating heat
    assert max_mass < 0.01 * _Q_S_RATED
    assert max_energy < 0.01 * 3.5e6
    assert not fallback_any          # no silent Euler fallback over 24 h
    assert feasible_all              # state stayed feasible the whole run
    assert 4.0 < p_min and p_max < 10.0
    assert 0.0 < l_min and l_max < 1.5
