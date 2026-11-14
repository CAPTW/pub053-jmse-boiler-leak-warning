from __future__ import annotations

from importlib.util import find_spec
from copy import deepcopy
from pathlib import Path

import pandas as pd
import yaml

from boiler_pdm_sim.core.backend_factory import build_core_backend
from boiler_pdm_sim.simulator import Simulator


class _FakeFMUSlave:
    def __init__(self) -> None:
        self.state = {
            "P_d": 11.0,
            "M_l": 3.2,
            "T_w_d": 420.0,
            "m_circ": 1.2,
            "m_shrink": 0.25,
        }
        self.inputs = {"fuel_cmd": 0.5, "fw_cmd": 0.5, "steam_demand": 0.5}

    def initialize(self) -> None:
        self.t = 0.0

    def set(self, name: str, value: float) -> None:
        if name in self.state:
            self.state[name] = float(value)
            return
        if name in self.inputs:
            self.inputs[name] = float(value)
            return

    def get(self, name: str) -> float:
        if name in self.state:
            return float(self.state[name])
        if name in self.inputs:
            return float(self.inputs[name])
        if name in {"mass_balance_residual", "energy_balance_residual"}:
            return 0.0
        if name == "volume_residual_m3":
            return 0.0
        if name == "der_P_drum":
            return float(self._derivative("P_d"))
        if name == "der_L_drum":
            return float(self._derivative("M_l"))
        if name == "der_T_w_d":
            return float(self._derivative("T_w_d"))
        if name == "der_m_circ":
            return float(self._derivative("m_circ"))
        if name == "der_m_shrink":
            return float(self._derivative("m_shrink"))

        if name == "P_drum":
            return float(self.state["P_d"])
        if name == "L_drum":
            return float(self.state["M_l"])
        if name == "m_dot_steam":
            return float(max(0.05, 0.12 + 0.25 * self.inputs["fuel_cmd"] + 0.02 * self.inputs["steam_demand"]))
        if name == "m_dot_fw":
            return float(max(0.05, 0.14 + 0.3 * self.inputs["fw_cmd"]))
        if name == "T_sh":
            return float(320.0 + 2.0 * self.state["T_w_d"] * 0.002 + 30.0 * self.inputs["fuel_cmd"])
        if name == "T_flue_gas":
            return float(500.0 + 250.0 * self.inputs["fuel_cmd"])
        if name == "O2_pct":
            return float(max(1.0, min(21.0, 18.0 + 1.2 * (0.6 - self.state["P_d"] / 15.0))))
        if name == "h_fw":
            return float(1200.0 + 300.0 * self.inputs["fw_cmd"])
        raise KeyError(name)

    def _derivative(self, state_name: str) -> float:
        p = self.state["P_d"]
        m = self.state["M_l"]
        t = self.state["T_w_d"]
        fuel = self.inputs["fuel_cmd"]
        fw = self.inputs["fw_cmd"]
        steam = self.inputs["steam_demand"]
        if state_name == "P_d":
            return 0.20 * fuel + 0.10 * fw - 0.02 * p + 0.04 * steam
        if state_name == "M_l":
            return 0.03 * fw - 0.05 * m + 0.02 * steam
        if state_name == "T_w_d":
            return 0.10 * fuel + 0.04 * p - 0.02 * t
        if state_name == "m_circ":
            return 0.08 * fw - 0.04 * self.state["m_circ"]
        if state_name == "m_shrink":
            return -0.01 * p + 0.10 * (1.0 - fuel)
        raise KeyError(state_name)

    def do_step(self, currentCommunicationPoint: float, communicationStepSize: float, *_args) -> None:
        dt = float(communicationStepSize)
        for k in ("P_d", "M_l", "T_w_d", "m_circ", "m_shrink"):
            self.state[k] = float(self.state[k] + dt * self._derivative(k))


def _fake_load_fmu(*_args, **_kwargs) -> _FakeFMUSlave:
    return _FakeFMUSlave()


def _discover_fmu_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    preferred = [
        Path("boiler_model.fmu"),
        Path("tests/boiler_model.fmu"),
        Path("tests/fixtures/boiler_model.fmu"),
        Path("configs/boiler_model.fmu"),
    ]
    for rel in preferred:
        candidate = root / rel
        if candidate.exists():
            return candidate

    for candidate in sorted(root.rglob("*.fmu")):
        return candidate

    return root / "unused_model.fmu"


def _base_cfg(fmu_path: Path):
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["dt"] = 0.5
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["seed"] = 31
    cfg["sim"]["horizon_s"] = 240
    cfg["fault_instances"] = []
    cfg["core_backend"] = {
        "type": "fmu",
        "path": str(fmu_path),
        "library": "auto",
        "time_var": "time",
        "variables": {
            "state_names": ["P_d", "M_l", "T_w_d", "m_circ", "m_shrink"],
            "input_names": ["fuel_cmd", "fw_cmd", "steam_demand"],
            "output_map": {
                "drum_pressure": "P_drum",
                "drum_level": "L_drum",
                "steam_flow": "m_dot_steam",
                "drum_temp_sh": "T_sh",
                "feedwater_flow": "m_dot_fw",
                "flue_gas_temp": "T_flue_gas",
                "O2": "O2_pct",
                "h_fw": "h_fw",
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
            "algebraic_state_names": ["M_v"],
            "algebraics": {
                "volume_residual_m3": "volume_residual_m3",
            },
        },
    }
    cfg["validation"] = {"mass_tol": 9999.0, "energy_tol": 1e12}
    return cfg


def test_fmu_backend_load_step_restart(monkeypatch):
    fmu_path = _discover_fmu_path()
    fmu_exists = fmu_path.exists()
    has_fmu_lib = find_spec("fmpy") is not None or find_spec("pyfmi") is not None

    if not fmu_exists or not has_fmu_lib:
        monkeypatch.setattr("boiler_pdm_sim.core.fmu_adapter._load_fmu", _fake_load_fmu)

    load_cfg = _base_cfg(fmu_path)
    backend = build_core_backend(load_cfg["boiler"], load_cfg["core_backend"])
    assert backend.algebraic_state_names == ["M_v"]
    assert backend.dae_partition()["algebraic"] == [5]
    load_cfg["scenario"] = {
        "type": "load_follow",
        "seed": 5,
        "load_follow": {"base": 0.6, "noise_std": 0.0, "ramp_limit_per_min": 0.05},
    }
    load_cfg["sim"]["horizon_s"] = 100
    rows_load = Simulator(seed=31).run(load_cfg)
    assert len(rows_load) > 10

    step_cfg = deepcopy(load_cfg)
    step_cfg["scenario"] = {
        "type": "step_tests",
        "seed": 9,
        "step_tests": {
            "base": 0.6,
            "steps": [{"start_s": 20.0, "duration_s": 300.0, "value": 0.9}],
        },
    }
    step_cfg["sim"]["horizon_s"] = 90
    rows_step = Simulator(seed=31).run(step_cfg)
    assert len(rows_step) > 10

    df = pd.DataFrame(rows_step)
    flat_events = [str(v) for v in df["label/event_log"].explode().dropna()]
    assert any(evt.startswith("steam_step_") for evt in flat_events)
    assert set(("truth/drum_pressure", "truth/drum_level", "meta/safety_state")).issubset(df.columns)
