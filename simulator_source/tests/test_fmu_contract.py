from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml

from boiler_pdm_sim.core.backend_factory import build_core_backend
from boiler_pdm_sim.interface.fmu import build_fmu_contract
from boiler_pdm_sim.simulator import Simulator


def test_fmu_contract_supports_model_exchange_mode() -> None:
    contract = build_fmu_contract({"type": "fmu", "fmi_mode": "model-exchange"})
    assert contract["mode"] == "model-exchange"


def test_model_exchange_mode_is_recorded_in_provenance(tmp_path: Path) -> None:
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["horizon_s"] = 30.0
    cfg["fault_instances"] = []
    cfg["core_backend"] = {"type": "python", "fmi_mode": "model-exchange"}
    out = tmp_path / "model_exchange.parquet"

    Simulator(seed=9).run_to_file(cfg, out)
    manifest = json.loads(out.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert manifest["provenance"]["pipeline"]["fmu_contract"]["mode"] == "model-exchange"


class _FakeModelExchangeFMU:
    def __init__(self) -> None:
        self.state = {
            "P_d": 10.0,
            "M_l": 3.3,
            "T_w_d": 320.0,
            "m_circ": 2.0,
            "m_shrink": 0.0,
        }
        self.inputs = {"fuel_cmd": 0.5, "fw_cmd": 0.5, "steam_demand": 0.5}

    def initialize(self) -> None:
        return None

    def set(self, name: str, value: float) -> None:
        if name in self.state:
            self.state[name] = float(value)
        elif name in self.inputs:
            self.inputs[name] = float(value)

    def get(self, name: str) -> float:
        if name in self.state:
            return float(self.state[name])
        if name in self.inputs:
            return float(self.inputs[name])
        deriv = {
            "der_P_drum": 0.08 * self.inputs["fuel_cmd"] - 0.01 * self.state["P_d"],
            "der_L_drum": 0.03 * self.inputs["fw_cmd"] - 0.02 * self.state["M_l"],
            "der_T_w_d": 0.15 * self.inputs["fuel_cmd"] - 0.01 * self.state["T_w_d"],
            "der_m_circ": 0.05 * self.inputs["fw_cmd"] - 0.03 * self.state["m_circ"],
            "der_m_shrink": 0.04 * (1.0 - self.inputs["steam_demand"]) - 0.1 * self.state["m_shrink"],
        }
        outputs = {
            "P_drum": self.state["P_d"],
            "L_drum": self.state["M_l"],
            "m_dot_steam": max(0.05, 0.3 * self.inputs["steam_demand"]),
            "m_dot_fw": max(0.05, 0.4 * self.inputs["fw_cmd"]),
            "T_sh": self.state["T_w_d"] + 10.0,
            "mass_balance_residual": 0.0,
            "energy_balance_residual": 0.0,
            "volume_residual_m3": 0.0,
        }
        if name in deriv:
            return float(deriv[name])
        if name in outputs:
            return float(outputs[name])
        raise KeyError(name)


def test_model_exchange_backend_steps_via_derivative_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "boiler_pdm_sim.core.fmu_adapter._load_fmu",
        lambda *_args, **_kwargs: _FakeModelExchangeFMU(),
    )
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    backend = build_core_backend(
        cfg["boiler"],
        {
            "type": "fmu",
            "path": "unused.fmu",
            "library": "auto",
            "fmi_mode": "model-exchange",
            "variables": {
                "state_names": ["P_d", "M_l", "T_w_d", "m_circ", "m_shrink"],
                "input_names": ["fuel_cmd", "fw_cmd", "steam_demand"],
                "output_map": {
                    "drum_pressure": "P_drum",
                    "drum_level": "L_drum",
                    "steam_flow": "m_dot_steam",
                    "feedwater_flow": "m_dot_fw",
                    "drum_temp_sh": "T_sh",
                },
                "derivative_names": [
                    "der_P_drum",
                    "der_L_drum",
                    "der_T_w_d",
                    "der_m_circ",
                    "der_m_shrink",
                ],
                "invariants": {
                    "mass_balance_residual": "mass_balance_residual",
                    "energy_balance_residual": "energy_balance_residual",
                },
                "algebraics": {
                    "volume_residual_m3": "volume_residual_m3",
                },
            },
        },
    )
    x0 = backend.state.copy()
    x1 = backend.step(0.0, x0, {"fuel_cmd": 0.6, "fw_cmd": 0.5, "steam_demand": 0.4}, 0.5, {})
    assert not np.allclose(x0, x1)
