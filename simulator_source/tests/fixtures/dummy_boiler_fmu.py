from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from pythonfmu.fmi2slave import Fmi2Causality, Fmi2Slave, Real


SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from boiler_pdm_sim.core.boiler_system import BoilerSystem


class DummyBoilerFMU(Fmi2Slave):
    author = "Codex"
    description = "Synthetic BoilerSystem-backed FMU for adapter/parity tests"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.time = 0.0
        self.fuel_cmd = 0.4
        self.fw_cmd = 0.5
        self.steam_demand = 0.6

        self.P_d = 0.0
        self.M_l = 0.0
        self.T_w_d = 0.0
        self.m_circ = 0.0
        self.m_shrink = 0.0

        self.P_drum = 0.0
        self.L_drum = 0.0
        self.m_dot_steam = 0.0
        self.T_sh = 0.0
        self.m_dot_fw = 0.0
        self.T_flue_gas = 0.0
        self.O2_pct = 0.0
        self.h_fw = 0.0

        self.der_P_drum = 0.0
        self.der_L_drum = 0.0
        self.der_T_w_d = 0.0
        self.der_m_circ = 0.0
        self.der_m_shrink = 0.0

        self.mass_balance_residual = 0.0
        self.energy_balance_residual = 0.0
        self.volume_residual_m3 = 0.0

        boiler_cfg = {
            "boiler": {
                "geometry": {
                    "drum_radius_m": 0.8,
                    "drum_length_m": 6.0,
                },
                "nominal": {
                    "pressure_bar": 10.0,
                    "steam_flow_kg_s": 2.0,
                    "feedwater_mass_kg": 600.0,
                    "level_fraction": 0.55,
                },
                "parameters": {
                    "UA": {
                        "economizer": 1.2e5,
                        "evaporator": 2.5e5,
                        "superheater": 8.0e4,
                    },
                    "Cv": {
                        "steam_valve": 1.0,
                        "feedwater_valve": 1.0,
                    },
                    "combustion": {
                        "eta": 0.90,
                        "qmax_MW": 10.0,
                    },
                    "steam_discharge_pressure_bar": 1.0,
                    "losses": {
                        "wall_loss_W": 50000.0,
                    },
                    "dynamics": {
                        "pressure_gain": 0.002,
                        "pressure_mass_gain": 0.0006,
                        "circum_mass_gain": 0.6,
                        "circum_tau_s": 20.0,
                        "shrink_gain": 0.10,
                        "shrink_tau_s": 14.0,
                        "shrink_swell_gain": 0.035,
                        "wall_tau_K": 15.0,
                    },
                    "limits": {
                        "mdot_fw_max_kg_s": 6.0,
                        "mdot_s_nom_kg_s": 2.0,
                    },
                },
            }
        }
        self._params = boiler_cfg
        self._system = BoilerSystem(self._params)
        self._state_names = ("P_d", "M_l", "T_w_d", "m_circ", "m_shrink")
        self._sync_state_from_system()

        self.register_variable(Real("time", causality=Fmi2Causality.local))
        for name in self._state_names:
            self.register_variable(Real(name, causality=Fmi2Causality.local))
        for name in ("fuel_cmd", "fw_cmd", "steam_demand"):
            self.register_variable(Real(name, causality=Fmi2Causality.input))
        for name in (
            "P_drum",
            "L_drum",
            "m_dot_steam",
            "T_sh",
            "m_dot_fw",
            "T_flue_gas",
            "O2_pct",
            "h_fw",
            "der_P_drum",
            "der_L_drum",
            "der_T_w_d",
            "der_m_circ",
            "der_m_shrink",
            "mass_balance_residual",
            "energy_balance_residual",
            "volume_residual_m3",
        ):
            self.register_variable(
                Real(
                    name,
                    causality=Fmi2Causality.output,
                    getter=self._make_output_getter(name),
                )
            )

        self._sync_outputs()

    def _state_array(self) -> np.ndarray:
        return np.array([self.P_d, self.M_l, self.T_w_d, self.m_circ, self.m_shrink], dtype=float)

    def _control(self) -> dict[str, float]:
        return {
            "fuel_cmd": float(self.fuel_cmd),
            "fw_cmd": float(self.fw_cmd),
            "steam_demand": float(self.steam_demand),
        }

    def _sync_state_from_system(self) -> None:
        state = np.asarray(self._system.state, dtype=float)
        self.P_d = float(state[0])
        self.M_l = float(state[1])
        self.T_w_d = float(state[2])
        self.m_circ = float(state[3])
        self.m_shrink = float(state[4])

    def _make_output_getter(self, name: str):
        def _getter():
            self._sync_outputs()
            return getattr(self, name)

        return _getter

    def _sync_outputs(self) -> None:
        state = self._state_array()
        control = self._control()
        self._system.state = state.copy()
        outputs = self._system.outputs(state, control, self._params)
        deriv = self._system.derivatives(self.time, state, control, self._params)
        invariants = self._system.invariants(state, control, self._params)
        algebraics = self._system.algebraic_residual(state, control, self._params)

        self.P_drum = float(outputs["drum_pressure"])
        self.L_drum = float(outputs["drum_level"])
        self.m_dot_steam = float(outputs["steam_flow"])
        self.T_sh = float(outputs["drum_temp_sh"])
        self.m_dot_fw = float(outputs["feedwater_flow"])
        self.T_flue_gas = float(outputs["flue_gas_temp"])
        self.O2_pct = float(outputs["O2"])
        self.h_fw = float(outputs["h_fw"])

        self.der_P_drum = float(deriv[0])
        self.der_L_drum = float(deriv[1])
        self.der_T_w_d = float(deriv[2])
        self.der_m_circ = float(deriv[3])
        self.der_m_shrink = float(deriv[4])

        self.mass_balance_residual = float(invariants.get("mass_balance_residual", 0.0))
        self.energy_balance_residual = float(invariants.get("energy_balance_residual", 0.0))
        self.volume_residual_m3 = float(algebraics.get("volume_residual_m3", 0.0))

    def do_step(self, current_time: float, step_size: float) -> bool:
        self.time = float(current_time)
        state = self._state_array()
        control = self._control()
        self._system.state = state.copy()
        dx = self._system.derivatives(self.time, state, control, self._params)
        next_state = state + float(step_size) * np.asarray(dx, dtype=float)
        self._system.set_prev_steam_demand(float(self.steam_demand))
        next_state, _report = self._system.align_algebraic_state(next_state, self._params)
        self._system.state = next_state.copy()
        self.P_d = float(next_state[0])
        self.M_l = float(next_state[1])
        self.T_w_d = float(next_state[2])
        self.m_circ = float(next_state[3])
        self.m_shrink = float(next_state[4])
        self.time = float(current_time + step_size)
        self._sync_outputs()
        return True
