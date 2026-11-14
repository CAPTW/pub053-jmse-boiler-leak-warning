from __future__ import annotations

import pandas as pd

from boiler_pdm_sim.calibration.baseline import build_baseline_profile
from boiler_pdm_sim.calibration.identify import compute_identifiability
from boiler_pdm_sim.calibration.sensitivity import compute_local_signal_sensitivity
from boiler_pdm_sim.core.thermo.if97 import saturation_props
from boiler_pdm_sim.core.thermo.steam_props import get_saturation_props
from boiler_pdm_sim.dataset.splits import split_indices
from boiler_pdm_sim.interface.fmu import build_fmu_contract
from boiler_pdm_sim.validation.level_instrumentation import validate_level_instrumentation
from boiler_pdm_sim.validation.steady_state_map import validate_steady_state_map


def test_compatibility_modules_expose_expected_contracts() -> None:
    props = saturation_props(10.0)
    props_alias = get_saturation_props(10.0)
    assert props_alias["rho_l"] == props["rho_l"]

    rows = [
        {
            "time": float(i),
            "scenario_id": f"s{i // 2}",
            "meta/parameter_draw": f"p{i // 2}",
            "meta/fault_instance_id": f"f{i // 2}",
            "meta/load_cmd": 0.5 + 0.1 * (i // 2),
            "truth/drum_pressure": 9.5 + 0.2 * i,
            "truth/drum_level": 3.0 + 0.01 * i,
            "truth/level_true": 3.0 + 0.01 * i,
            "obs/drum_level": 3.0 + 0.008 * i,
            "obs/drum_level_dp_raw": 2.95 + 0.02 * i,
            "obs/drum_level_compensated": 3.0 + 0.008 * i,
            "label/fault_type": "none",
        }
        for i in range(6)
    ]
    df = pd.DataFrame(rows)
    splits, meta = split_indices(df, {"enabled": True, "train": 0.5, "val": 0.25, "test": 0.25}, 42)
    assert meta["unit"] == "group"
    assert {"train", "test"} <= set(splits)

    steady = validate_steady_state_map(rows, bins=3)
    assert steady["passed"] is True
    level_report = validate_level_instrumentation(rows)
    assert level_report["passed"] is True

    baseline = build_baseline_profile(rows)
    ident = compute_identifiability(rows, channels=("obs/drum_level", "truth/drum_pressure"))
    sensitivity = compute_local_signal_sensitivity([1.0, 1.1, 1.2, 1.3], epsilon=1e-3, window=2)
    contract = build_fmu_contract({"type": "fmu", "fmi_mode": "model-exchange"})
    assert baseline["status"] == "ok"
    assert ident["status"] in {"ok", "single_class"}
    assert sensitivity["status"] == "ok"
    assert sensitivity["mean_sensitivity"] > 0.0
    assert contract["mode"] == "model-exchange"
