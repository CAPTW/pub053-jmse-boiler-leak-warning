from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from boiler_pdm_sim.core.boiler_system import BoilerSystem


def _load_system() -> tuple[BoilerSystem, dict]:
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    system = BoilerSystem({"boiler": cfg["boiler"]})
    return system, {"boiler": cfg["boiler"]}


def test_dae_partition_declares_algebraic_state() -> None:
    system, _ = _load_system()
    part = system.dae_partition()
    assert part["differential"] == [0, 1, 2, 3, 4]
    assert part["algebraic"] == [5]


def test_algebraic_alignment_reduces_volume_residual_to_tolerance() -> None:
    system, params = _load_system()
    raw = np.array([10.0, 1e9, 320.0, 3.0, 0.2], dtype=float)
    residual_before = system.algebraic_state_error(raw, params)
    aligned, report = system.align_algebraic_state(raw, params, max_iter=12, tol=1e-10)

    assert aligned.shape == raw.shape
    assert report["iterations"] >= 0
    assert bool(report["feasible"])
    assert abs(float(report["residual_after_m3"])) <= 1e-6
    assert abs(float(report["residual_after_m3"])) <= abs(residual_before)
    assert abs(system.algebraic_state_error(aligned, params)) <= 1e-6


def test_algebraic_alignment_supports_legacy_six_state_input() -> None:
    system, params = _load_system()
    raw = np.array([10.0, 1e9, 1000.0, 320.0, 3.0, 0.2], dtype=float)
    aligned, report = system.align_algebraic_state(raw, params, max_iter=12, tol=1e-10)
    assert aligned.shape == raw.shape
    assert aligned[0] == raw[0]
    assert aligned[2] > 0.0
    assert abs(float(report["residual_after_m3"])) <= 1e-6


def test_invariants_expose_feasibility_and_saturation_contract() -> None:
    system, params = _load_system()
    x = system.state.copy()
    u = {"fuel_cmd": 0.5, "fw_cmd": 0.5, "steam_demand": 0.5}
    inv = system.invariants(x, u, params)

    for key in (
        "mass_balance_residual",
        "energy_balance_residual",
        "volume_algebraic_residual",
        "liquid_mass_nonnegative",
        "vapor_mass_nonnegative",
        "negative_holdup_violation",
        "pressure_in_range",
        "sat_temperature_C",
        "superheat_C",
        "saturation_consistency_residual",
        "state_feasible",
    ):
        assert key in inv

    assert float(inv["liquid_mass_nonnegative"]) == 1.0
    assert float(inv["vapor_mass_nonnegative"]) == 1.0
    assert float(inv["negative_holdup_violation"]) == 0.0
    assert float(inv["pressure_in_range"]) == 1.0
    assert float(inv["state_feasible"]) == 1.0
