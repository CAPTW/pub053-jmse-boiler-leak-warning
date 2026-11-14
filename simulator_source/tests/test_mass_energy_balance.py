from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from boiler_pdm_sim.core.boiler_system import BoilerSystem
from boiler_pdm_sim.scenarios.randomization import apply_randomization
from boiler_pdm_sim.degradation.scheduler import DegradationScheduler
from boiler_pdm_sim.core.solver import integrate_step


def _load_cfg():
    return yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))


def test_mass_energy_balance_remains_bounded():
    cfg = _load_cfg()
    base = apply_randomization(cfg["boiler"], cfg.get("randomization", {}), np.random.default_rng(cfg["sim"]["seed"]))
    sys = BoilerSystem({"boiler": base})
    x = sys.state.copy()
    u = {"fuel_cmd": 0.5, "fw_cmd": 0.6, "steam_demand": 0.6}
    params = {"boiler": base, "degradation": {}}
    sched = DegradationScheduler([], None)
    params_faulted = sched.update(0.0, params)
    for _ in range(5):
        inv = sys.invariants(x, u, params_faulted)
        assert inv["mass_balance_residual"] < 50.0
        assert inv["energy_balance_residual"] < 3e7
        x = integrate_step(lambda t, xx: sys.derivatives(t, xx, u, params_faulted), 0.0, x, 0.2, method="euler")
