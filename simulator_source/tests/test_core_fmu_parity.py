from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pandas as pd
import yaml

from boiler_pdm_sim.core.boiler_system import BoilerSystem
from boiler_pdm_sim.pipeline.runtime import _coerce_scalars
from boiler_pdm_sim.simulator import Simulator


class _ParityFMUSlave:
    def __init__(self, boiler_cfg: dict) -> None:
        self._params = {"boiler": _coerce_scalars(deepcopy(boiler_cfg))}
        self._system = BoilerSystem(self._params)
        self._state_names = ["P_d", "M_l", "T_w_d", "m_circ", "m_shrink"]
        self._inputs = {"fuel_cmd": 0.4, "fw_cmd": 0.5, "steam_demand": 0.6}
        self._state = self._system.state.copy()
        self._time = 0.0

    def initialize(self) -> None:
        self._time = 0.0
        self._state = self._system.state.copy()
        self._system.state = self._state.copy()

    def set(self, name: str, value: float) -> None:
        if name in self._state_names:
            idx = self._state_names.index(name)
            self._state[idx] = float(value)
            return
        if name in self._inputs:
            self._inputs[name] = float(value)
            return
        if name == "time":
            self._time = float(value)

    def get(self, name: str) -> float:
        if name in self._state_names:
            idx = self._state_names.index(name)
            return float(self._state[idx])
        outputs = self._system.outputs(self._state, self._inputs, self._params)
        invariants = self._system.invariants(self._state, self._inputs, self._params)
        algebraics = self._system.algebraic_residual(self._state, self._inputs, self._params)
        if name in outputs:
            return float(outputs[name])
        if name in invariants:
            return float(invariants[name])
        if name in algebraics:
            return float(algebraics[name])
        raise KeyError(name)

    def do_step(self, currentCommunicationPoint: float, communicationStepSize: float, *_args) -> None:
        self._time = float(currentCommunicationPoint)
        dt = float(communicationStepSize)
        dx = self._system.derivatives(self._time, self._state, self._inputs, self._params)
        self._state = self._state + dt * dx
        self._system.set_prev_steam_demand(float(self._inputs.get("steam_demand", 0.5)))
        self._state, _ = self._system.align_algebraic_state(self._state, self._params)
        self._system.state = self._state.copy()
        self._time += dt


def test_python_and_fmu_backends_keep_parity_for_core_truth(monkeypatch) -> None:
    monkeypatch.setattr(
        "boiler_pdm_sim.core.fmu_adapter._load_fmu",
        lambda *_args, **_kwargs: _ParityFMUSlave(
            yaml.safe_load(Path("configs/local_pipeline_step_tests.yaml").read_text(encoding="utf-8"))["boiler"]
        ),
    )

    cfg = yaml.safe_load(Path("configs/local_pipeline_step_tests.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["horizon_s"] = 180
    cfg["fault_instances"] = []
    cfg["randomization"]["enable"] = False
    cfg["calibration"]["enabled"] = False
    for sensor_cfg in cfg["sensors"].values():
        sensor_cfg["noise_std"] = 0.0
        sensor_cfg["drift_per_hour"] = 0.0
        sensor_cfg["dropout_p"] = 0.0
        sensor_cfg["spike_p"] = 0.0
        sensor_cfg["spike_std"] = 0.0

    python_rows = Simulator(seed=42).run(cfg)

    fmu_cfg = deepcopy(cfg)
    fmu_cfg["core_backend"] = {
        "type": "fmu",
        "path": "unused_model.fmu",
        "library": "auto",
        "time_var": "time",
        "variables": {
            "state_names": ["P_d", "M_l", "T_w_d", "m_circ", "m_shrink"],
            "input_names": ["fuel_cmd", "fw_cmd", "steam_demand"],
            "output_map": {
                "drum_pressure": "drum_pressure",
                "drum_level": "drum_level",
                "steam_flow": "steam_flow",
                "drum_temp_sh": "drum_temp_sh",
                "feedwater_flow": "feedwater_flow",
                "flue_gas_temp": "flue_gas_temp",
                "O2": "O2",
                "h_fw": "h_fw",
            },
            "invariants": {
                "mass_balance_residual": "mass_balance_residual",
                "energy_balance_residual": "energy_balance_residual",
            },
            "algebraic_state_names": ["M_v"],
            "algebraics": {
                "volume_residual_m3": "volume_residual_m3",
            },
        },
    }
    fmu_rows = Simulator(seed=42).run(fmu_cfg)

    left = pd.DataFrame(python_rows)
    right = pd.DataFrame(fmu_rows)
    columns = [
        "truth/drum_pressure",
        "truth/drum_level",
        "truth/steam_flow",
        "truth/flue_gas_temp",
        "truth/O2",
        "truth/h_fw",
        "meta/final_control_fuel_cmd",
        "meta/final_control_fw_cmd",
        "meta/final_control_steam_demand",
    ]
    pd.testing.assert_frame_equal(
        left[columns].reset_index(drop=True),
        right[columns].reset_index(drop=True),
        check_exact=False,
        atol=1e-6,
        rtol=1e-6,
    )
