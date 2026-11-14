from __future__ import annotations

from pathlib import Path

import yaml

from boiler_pdm_sim.simulator import Simulator
from boiler_pdm_sim.validation.regression import (
    acceptance_thresholds,
    regression_gate,
    seed_sweep_battery,
    summarize_rows,
)


def _cfg():
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["dt"] = 0.5
    cfg["sim"]["horizon_s"] = 900
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["seed"] = 11
    cfg["fault_instances"] = []
    cfg["randomization"]["enable"] = False
    cfg["scenario"]["type"] = "load_follow"
    cfg["scenario"]["seed"] = 99
    return cfg


def test_acceptance_thresholds_utility():
    metrics = {
        "truth/mass_balance_residual_max_abs": 12.4,
        "truth/energy_balance_residual_max_abs": 4.3e6,
    }
    acc = acceptance_thresholds(
        metrics,
        {
            "truth/mass_balance_residual_max_abs": {"max": 20.0},
            "truth/energy_balance_residual_max_abs": {"max": 5e6, "min": 0.0},
        },
    )
    assert acc["passed"] is True
    assert acc["failures"] == []
    assert acc["details"]["truth/mass_balance_residual_max_abs"]["ok"] is True


def test_seed_sweep_battery_collects_multiple_runs():
    cfg = _cfg()
    cfg["sim"]["horizon_s"] = 360
    cfg["sim"]["seed"] = 11

    def run_case(case_cfg):
        return Simulator(seed=int(case_cfg["sim"]["seed"])).run(case_cfg)

    battery = seed_sweep_battery(
        run_case,
        cfg,
        seeds=[11, 12, 13],
        summary_channels=("truth/drum_pressure", "truth/drum_level", "label/fault_severity"),
    )
    assert battery["passed"] is True
    assert battery["n_runs"] == 3
    assert sorted(int(s) for s in battery["seeds"]) == [11, 12, 13]
    for seed in ["11", "12", "13"]:
        assert "truth/drum_pressure_mean" in battery["summaries"][seed]


def test_regression_gate_flags_same_seed_as_reference_and_catches_drift():
    cfg = _cfg()
    cfg["sim"]["horizon_s"] = 400
    cfg["sim"]["seed"] = 77

    channels = ("truth/drum_pressure", "truth/drum_level", "obs/drum_pressure")
    ref = summarize_rows(Simulator(seed=77).run(cfg), channels=channels)
    dup = summarize_rows(Simulator(seed=77).run(cfg), channels=channels)

    gate_same = regression_gate(
        ref,
        dup,
        {
            "truth/drum_pressure_mean": {"max_abs": 1e-9},
            "truth/drum_level_mean": {"max_abs": 1e-9},
        },
    )
    assert gate_same["passed"] is True

    drifted = dict(dup)
    drifted["truth/drum_pressure_mean"] = (drifted["truth/drum_pressure_mean"] + 0.25)
    gate_drift = regression_gate(
        ref,
        drifted,
        {"truth/drum_pressure_mean": {"max_abs": 1e-6}},
    )
    assert gate_drift["passed"] is False
