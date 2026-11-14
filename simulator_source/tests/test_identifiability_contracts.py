from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from boiler_pdm_sim.scenarios.randomization import apply_randomization
from boiler_pdm_sim.simulator import Simulator


def _load_boiler_cfg() -> dict:
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    return cfg["boiler"]


def test_identifiability_constraints_lock_and_group_randomization() -> None:
    boiler_cfg = _load_boiler_cfg()
    randomized = apply_randomization(
        boiler_cfg,
        {
            "enable": True,
            "drift_std_pct": {
                "UA_evap": 0.05,
                "combustion_eta": 0.05,
                "feedwater_max": 0.05,
            },
            "identifiability_constraints": {
                "lock_keys": ["feedwater_max"],
                "groups": {
                    "thermal_efficiency": ["UA_evap", "combustion_eta"],
                },
            },
        },
        np.random.default_rng(7),
    )

    diagnostics = randomized["diagnostics"]["randomization"]
    assert diagnostics["locked_keys"] == ["feedwater_max"]
    assert diagnostics["applied_scales"]["UA_evap"] == diagnostics["applied_scales"]["combustion_eta"]
    assert "feedwater_max" not in diagnostics["applied_scales"]
    assert randomized["parameters"]["limits"]["mdot_fw_max_kg_s"] == boiler_cfg["parameters"]["limits"]["mdot_fw_max_kg_s"]


def test_identifiability_freezes_sensor_fault_channels() -> None:
    sim = Simulator(seed=3)
    _boiler, report = sim._apply_identifiability(  # pyright: ignore[reportPrivateUsage]
        _load_boiler_cfg(),
        {
            "enabled": True,
            "freeze_level_chain": True,
            "freeze_sensor_channels": ["drum_level"],
        },
    )

    frozen = sim._freeze_sensor_config(  # pyright: ignore[reportPrivateUsage]
        {
            "drum_level": {
                "bias": 0.12,
                "drift_per_hour": 0.5,
                "dropout_p": 0.2,
                "spike_p": 0.1,
            },
            "drum_pressure": {
                "bias": 0.03,
                "drift_per_hour": 0.02,
            },
        },
        tuple(report["fixed_sensor_channels"]),
    )

    assert frozen["drum_level"]["bias"] == 0.0
    assert frozen["drum_level"]["drift_per_hour"] == 0.0
    assert frozen["drum_level"]["dropout_p"] == 0.0
    assert frozen["drum_level"]["spike_p"] == 0.0
    assert frozen["drum_pressure"]["bias"] == 0.03
