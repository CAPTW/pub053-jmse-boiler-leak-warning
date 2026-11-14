"""Core drum model: low-order 2-phase dynamics."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np

from .backend_protocol import BackendInputs, LegacyAdvanceMixin
from .components import drum as drum_geom
from .components.economizer import heat_to_fluid
from .components.economizer import outlet_temperature as econ_out_temp
from .components.combustion import heat_release_MW
from .components.pump import commanded_flow
from .components.valves import valve_flow_from_pressure
from .components.superheater import out_temp as superheater_out_temp
from .media import saturation_props, dhdP_approx
from .solver import integrate_step
from .state import ALGEBRAIC_STATE_NAMES, DIFFERENTIAL_STATE_NAMES, STATE_NAMES


class BoilerSystem(LegacyAdvanceMixin):
    """Simplified natural-circulation drum model.

    x = [P_d, M_l, T_w_d, m_circ, m_shrink]
    M_v is algebraically reconstructed from (P_d, M_l).
    """

    def __init__(self, params: dict[str, Any]) -> None:
        self._last_intermediate: dict[str, float] = {}
        self._prev_steam_demand: float | None = None
        self._props_cache_pressure: float | None = None
        self._props_cache: dict[str, float] = {}
        self.reset(None, params)

    def set_prev_steam_demand(self, steam_demand: float) -> None:
        self._prev_steam_demand = self._clamp(steam_demand, 0.0, 1.0)

    def reset(self, x0: dict[str, float] | None, params: dict[str, Any]) -> None:
        self.params = self._coerce_numeric_tree(deepcopy(params))
        self._props_cache_pressure = None
        self._props_cache = {}
        self.geometry = drum_geom.DrumGeometry(
            radius_m=self.params["boiler"]["geometry"]["drum_radius_m"],
            length_m=self.params["boiler"]["geometry"]["drum_length_m"],
        )
        self.state = self.consistent_init(x0)
        P0 = float(self.state[0])
        props = self._props(P0)
        M_v0 = self._algebraic_m_v(P0, float(self.state[1]), self.params["boiler"], props=props)
        self._last_intermediate = {
            "P_bar": P0,
            "M_l": float(self.state[1]),
            "T_w": float(self.state[2]),
            "m_circ_state": float(self.state[3]),
            "m_shrink_state": float(self.state[4]),
            "operating_key": None,
            "M_v": M_v0,
            "m_fw": 0.0,
            "m_s": 0.0,
            "m_boil": 0.0,
            "m_cond": 0.0,
            "m_leak": 0.0,
            "m_dc_in": 0.0,
            "q_evap": 0.0,
            "q_sh": 0.0,
            "dP": 0.0,
            "dM_l": 0.0,
            "dM_v": 0.0,
            "rho_l": props["rho_l"],
            "rho_v": props["rho_v"],
            "T_sh": props["Tsat_C"] + 5.0,
            "fuel_cmd": 0.0,
            "fw_cmd": 0.0,
            "steam_demand": 0.0,
            "params_id": id(self.params),
        }

    @property
    def state_names(self) -> list[str]:
        return list(DIFFERENTIAL_STATE_NAMES)

    @property
    def algebraic_state_names(self) -> list[str]:
        return [n for n in STATE_NAMES if n not in DIFFERENTIAL_STATE_NAMES]

    def dae_partition(self, params: dict[str, Any] | None = None) -> dict[str, list[int]]:
        del params
        differential = list(range(len(DIFFERENTIAL_STATE_NAMES)))
        # The public differential state vector has only differential coordinates;
        # algebraic coordinate bookkeeping is still preserved for the contract.
        algebraic = list(range(len(DIFFERENTIAL_STATE_NAMES), len(DIFFERENTIAL_STATE_NAMES) + len(ALGEBRAIC_STATE_NAMES)))
        if not ALGEBRAIC_STATE_NAMES:
            algebraic = []
        return {"differential": differential, "algebraic": algebraic}

    @staticmethod
    def _clip_pressure(P_bar: float) -> float:
        return float(max(0.2, min(30.0, float(P_bar))))

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return float(max(lower, min(upper, float(value))))

    @staticmethod
    def _coerce_numeric_tree(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: BoilerSystem._coerce_numeric_tree(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [BoilerSystem._coerce_numeric_tree(v) for v in obj]
        if isinstance(obj, tuple):
            return tuple(BoilerSystem._coerce_numeric_tree(v) for v in obj)
        if isinstance(obj, str):
            text = obj.strip()
            if not text:
                return obj
            try:
                return float(text)
            except ValueError:
                return obj
        return obj

    @staticmethod
    def _clip_state(x: np.ndarray) -> np.ndarray:
        return np.clip(np.asarray(x, dtype=float), 1e-9, np.inf)

    def _resolve_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None or params is self.params:
            return self.params
        return self._coerce_numeric_tree(params)

    def _props(self, P_bar: float) -> dict[str, float]:
        P_bar = self._clip_pressure(P_bar)
        if self._props_cache_pressure is None or abs(self._props_cache_pressure - P_bar) > 1e-12:
            self._props_cache_pressure = float(P_bar)
            self._props_cache = dict(saturation_props(P_bar))
        return self._props_cache

    @staticmethod
    def _operating_key(
        P_bar: float,
        M_l: float,
        T_w: float,
        m_circ: float,
        m_shrink: float,
        fuel_cmd: float,
        fw_cmd: float,
        steam_demand: float,
        params: dict[str, Any],
    ) -> tuple[float, ...]:
        return (
            float(id(params)),
            float(P_bar),
            float(M_l),
            float(T_w),
            float(m_circ),
            float(m_shrink),
            float(fuel_cmd),
            float(fw_cmd),
            float(steam_demand),
        )

    def _compute_operating_terms(
        self,
        P_bar: float,
        T_w: float,
        params: dict[str, Any],
        *,
        fuel_cmd: float,
        fw_cmd: float,
        steam_demand: float,
        props: dict[str, float] | None = None,
    ) -> tuple[float, float, float, float, float, float, float, float, float, float, float]:
        props = self._props(P_bar) if props is None else props
        boiler_params = params["boiler"]["parameters"]
        limits = boiler_params["limits"]
        combustion = boiler_params["combustion"]
        ua = boiler_params["UA"]
        d = params.get("degradation", {})
        ua_scale = float(d.get("ua_scale", 1.0))
        eta_comb = float(d.get("eta_comb", combustion["eta"]))
        qmax_scale = float(d.get("qmax_scale", 1.0))
        leak_coeff = float(d.get("tube_leak_coeff", 0.0))

        max_fw = limits["mdot_fw_max_kg_s"]
        max_s = limits["mdot_s_nom_kg_s"]
        m_fw = self._feedwater_flow(fw_cmd, max_fw, params, d)
        m_s, m_s_raw = self._steam_flow(P_bar, steam_demand, max_s, params, d)
        q_release_mw = heat_release_MW(
            eta_comb,
            combustion["qmax_MW"] * max(0.1, qmax_scale),
            fuel_cmd,
        )
        q_in = q_release_mw * 1e6
        Tsat = float(props["Tsat_C"])
        T_fw_in = max(10.0, Tsat - 120.0)
        m_fw_eff = max(m_fw, 1e-6)
        fw_heat_capacity = m_fw_eff * 4200.0
        econ_delta_t = max(Tsat + 240.0 - T_fw_in, 0.0)
        q_econ = min(q_in * 0.18, ua["economizer"] * econ_delta_t)
        T_fw_out = min(Tsat + 35.0, T_fw_in + q_econ / fw_heat_capacity)
        q_to_fluid = q_in * ua_scale * 0.75
        q_evap = 0.6 * q_to_fluid
        q_sh = 0.4 * q_to_fluid
        m_boil_nom = max(q_evap / max(float(props["h_fg"]), 1e-6), 0.0)
        m_cond = max(0.0, 0.004 * max(0.0, Tsat - T_w))
        m_leak = leak_coeff * np.sqrt(max(P_bar - 1.0, 0.0))
        return (
            float(m_fw),
            float(m_s),
            float(m_s_raw),
            float(q_release_mw),
            float(q_in),
            float(T_fw_out),
            float(q_evap),
            float(q_sh),
            float(m_boil_nom),
            float(m_cond),
            float(m_leak),
        )

    def _algebraic_m_v(
        self,
        P_bar: float,
        M_l: float,
        params: dict[str, Any],
        *,
        props: dict[str, float] | None = None,
    ) -> float:
        props = self._props(P_bar) if props is None else props
        V_total = self.geometry.volume_m3
        rho_l = max(props["rho_l"], 1e-6)
        rho_v = max(props["rho_v"], 1e-6)
        V_l = float(M_l) / rho_l
        return float(max(0.0, V_total - V_l) * rho_v)

    def _project_mass_from_volume(
        self,
        P_bar: float,
        M_l: float,
        params: dict[str, Any],
        *,
        props: dict[str, float] | None = None,
    ) -> float:
        props = self._props(P_bar) if props is None else props
        V_total = self.geometry.volume_m3
        rho_l = max(props["rho_l"], 1e-6)
        vapor_margin_m3 = max(1e-6, min(5e-3, 1e-3 * V_total))
        m_l_max = rho_l * max(1e-9, V_total - vapor_margin_m3)
        return self._clamp(float(M_l), 1e-9, m_l_max)

    def _volume_residual(
        self,
        P_bar: float,
        M_l: float,
        params: dict[str, Any],
        *,
        props: dict[str, float] | None = None,
    ) -> float:
        props = self._props(P_bar) if props is None else props
        rho_l = max(props["rho_l"], 1e-6)
        V_l = float(M_l) / rho_l
        _ = params
        return float(max(0.0, V_l - self.geometry.volume_m3))

    def algebraic_state_error(self, x: np.ndarray, params: dict[str, Any] | None = None) -> float:
        """Return the absolute algebraic volume residual for a differential-state vector."""
        p = self._resolve_params(params)
        arr = np.asarray(x, dtype=float)
        if arr.size == 6:
            arr = np.array([arr[0], arr[1], arr[3], arr[4], arr[5]], dtype=float)
        elif arr.size != 5:
            raise ValueError("state vector length must be 5 (or legacy 6 including vapor mass).")
        return abs(float(self._volume_residual(float(arr[0]), float(arr[1]), p["boiler"])))

    def algebraic_residual(self, x: np.ndarray, u: dict[str, float] | None, params: dict[str, Any] | None) -> dict[str, float]:
        p = self._resolve_params(params)
        P_d, M_l, T_w, m_circ, m_shrink = np.asarray(x, dtype=float)
        _ = u, T_w, m_circ, m_shrink
        P_bar = self._clip_pressure(P_d)
        props = self._props(P_bar)
        M_v = self._algebraic_m_v(P_bar, M_l, p["boiler"], props=props)
        return {
            "volume_residual_m3": float(self._volume_residual(P_bar, M_l, p["boiler"], props=props)),
            "pressure": P_bar,
            "liquid_mass": float(M_l),
            "vapor_mass": float(M_v),
        }

    def project_to_feasible(self, x: np.ndarray, params: dict[str, Any] | None = None) -> np.ndarray:
        p = self._resolve_params(params)
        arr = self._clip_state(np.asarray(x, dtype=float))
        if arr.size == 6:
            arr = np.array([arr[0], arr[1], arr[3], arr[4], arr[5]], dtype=float)
        elif arr.size != 5:
            raise ValueError("state vector must have length 5 (or legacy length 6 including vapor mass).")
        P_bar = self._clip_pressure(float(arr[0]))
        arr[0] = P_bar
        props = self._props(P_bar)
        m_l = self._project_mass_from_volume(P_bar, float(arr[1]), p["boiler"], props=props)
        arr[1] = m_l
        arr[2] = self._clamp(arr[2], 280.0, 350.0)
        arr[3] = max(1e-9, float(arr[3]))
        arr[4] = max(-5.0, min(5.0, float(arr[4])))
        return arr

    def align_algebraic_state(
        self,
        x: np.ndarray,
        params: dict[str, Any] | None = None,
        *,
        max_iter: int = 12,
        tol: float = 1e-10,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        p = self._resolve_params(params)
        arr = np.asarray(x, dtype=float)
        if arr.size == 6:
            arr_state = np.array([arr[0], arr[1], arr[3], arr[4], arr[5]], dtype=float)
        elif arr.size == 5:
            arr_state = arr.copy()
        else:
            raise ValueError("state vector length must be 5 (or legacy 6 with [P_d, M_l, M_v, T_w_d, m_circ, m_shrink]).")

        arr_state = self._clip_state(np.asarray(arr_state, dtype=float))
        P_bar = self._clip_pressure(float(arr_state[0]))
        arr_state[0] = P_bar

        props = self._props(P_bar)
        residual_before = float(self._volume_residual(P_bar, float(arr_state[1]), p["boiler"], props=props))
        arr_state[1] = self._project_mass_from_volume(P_bar, float(arr_state[1]), p["boiler"], props=props)
        arr_state[2] = self._clamp(arr_state[2], 280.0, 350.0)
        arr_state[3] = max(1e-9, float(arr_state[3]))
        arr_state[4] = max(-5.0, min(5.0, float(arr_state[4])))
        residual_after = float(self._volume_residual(P_bar, float(arr_state[1]), p["boiler"], props=props))
        feasible = bool(np.isfinite(residual_after) and abs(residual_after) <= tol)
        source = "exact_projection" if np.isfinite(residual_before) and abs(residual_before) <= tol else "projection"

        out = arr_state
        if x.size == 6:
            out = np.array([out[0], out[1], self._algebraic_m_v(P_bar, float(out[1]), p["boiler"], props=props), out[2], out[3], out[4]], dtype=float)

        return out, {
            "iterations": 0,
            "residual_before_m3": float(residual_before),
            "residual_after_m3": float(residual_after),
            "feasible": bool(feasible),
            "source": source,
        }

    def consistent_init(self, x0: dict[str, float] | np.ndarray | None = None, *, params: dict[str, Any] | None = None) -> np.ndarray:
        p = self._resolve_params(params)
        if isinstance(x0, np.ndarray):
            raw = np.asarray(x0, dtype=float).reshape(-1)
            if raw.size == 6:
                base = np.array([raw[0], raw[1], raw[3], raw[4], raw[5]], dtype=float)
            elif raw.size == 5:
                base = raw.copy()
            else:
                raise ValueError("x0 ndarray must have length 5 (or legacy 6 with [P_d, M_l, M_v, T_w, m_circ, m_shrink]).")
        else:
            base = self._build_initial_state(None if x0 is None else dict(x0))
        state = self.project_to_feasible(base, p)
        for _ in range(4):
            residual = abs(self._volume_residual(float(state[0]), float(state[1]), p["boiler"]))
            if residual < 1e-10:
                break
            state = self.project_to_feasible(state, p)
        return state

    @staticmethod
    def _apply_stiction(opening: float, stiction: float, deadband: float) -> float:
        opening = BoilerSystem._clamp(opening, 0.0, 1.0)
        worn = opening * max(0.0, 1.0 - stiction)
        if deadband <= 0.0:
            return worn
        correction = np.sign(opening - 0.5) * min(abs(opening - 0.5), deadband)
        return max(0.0, worn * (1.0 - abs(correction)))

    def _steam_flow(self, P_bar: float, steam_cmd: float, max_s: float, params: dict[str, Any], d: dict[str, Any]) -> tuple[float, float]:
        stiction = float(d.get("valve_stiction", 0.0))
        stiction_deadband = float(d.get("valve_stiction_deadband", 0.0))
        cv = float(params["boiler"]["parameters"].get("Cv", {}).get("steam_valve", 1.0))
        p_down = float(params["boiler"]["parameters"].get("steam_discharge_pressure_bar", 1.0))
        steam_cmd_eff = self._apply_stiction(steam_cmd, stiction, stiction_deadband)
        raw = valve_flow_from_pressure(cv, steam_cmd_eff, P_bar, p_down)
        return float(min(max(raw, 0.0), max_s)), float(raw)

    def _feedwater_flow(self, fw_cmd: float, max_fw: float, params: dict[str, Any], d: dict[str, Any]) -> float:
        stiction = float(d.get("valve_stiction", 0.0))
        stiction_deadband = float(d.get("valve_stiction_deadband", 0.0))
        fw_open = self._apply_stiction(fw_cmd, stiction, stiction_deadband)
        return float(
            commanded_flow(
                fw_open,
                max_fw,
                wear_factor=max(0.0, float(d.get("pump_wear", 0.0))),
            ),
        )

    def _build_initial_state(self, x0: dict[str, float] | None) -> np.ndarray:
        P0 = self.params["boiler"]["nominal"]["pressure_bar"]
        props = self._props(P0)
        rho_l = props["rho_l"]
        A = self.geometry.area_m2
        level0 = self.params["boiler"]["nominal"]["level_fraction"] * self.geometry.length_m
        M_l0 = x0.get("M_l", rho_l * A * level0) if x0 else rho_l * A * level0
        V_l = M_l0 / max(rho_l, 1e-6)
        return np.array(
            [
                float(x0.get("P_d", P0) if x0 else P0),
                float(M_l0 if x0 is None or "M_l" not in x0 else x0["M_l"]),
                float(x0.get("T_w_d", props["Tsat_C"] + 6.0) if x0 else props["Tsat_C"] + 6.0),
                float(x0.get("m_circ", 2.5) if x0 else 2.5),
                float(x0.get("m_shrink", 0.0) if x0 else 0.0),
            ],
            dtype=float,
        )

    def _superheater_temperature(
        self,
        *,
        Tsat: float,
        T_w: float,
        q_sh: float,
        m_s: float,
        m_boil: float,
        ua_scale: float,
        fouling_severity: float = 0.0,
    ) -> float:
        base = superheater_out_temp(
            T_wall=float(T_w),
            T_in=float(Tsat),
            split=float(q_sh) / 1_000.0,
            m_s_kg_s=max(float(m_s), 1e-6),
            ua_super=max(0.15, 0.9 * float(ua_scale)),
        )
        margin = max(0.0, float(base - Tsat))
        fouling_scale = max(0.1, float(ua_scale) ** 1.6)
        boil_bonus = 0.025 * float(m_boil) * max(0.2, float(ua_scale))
        fouling_penalty = (
            60.0 * (1.0 - float(ua_scale))
            + 0.18 * (1.0 - float(ua_scale)) * max(0.0, float(m_boil))
            + 55.0 * max(0.0, float(fouling_severity))
        )
        return float(max(120.0, Tsat + margin * fouling_scale + boil_bonus - fouling_penalty))

    def _integrate_raw(
        self,
        t: float,
        x: np.ndarray,
        control: dict[str, Any],
        dt: float,
        method: str,
        params: dict[str, Any],
    ) -> tuple[np.ndarray, dict[str, Any]]:
        fun = lambda ti, xx: self.derivatives(ti, xx, control, params)
        x_next, diag = integrate_step(fun, t, x, dt, method=method, return_diagnostics=True)
        return np.asarray(x_next, dtype=float), dict(diag)

    def derivatives(self, t: float, x: np.ndarray, u: dict[str, float], params: dict[str, Any]) -> np.ndarray:
        p = self._resolve_params(params)
        boiler = p["boiler"]
        boiler_params = boiler["parameters"]
        dynamics = boiler_params["dynamics"]
        limits = boiler_params["limits"]
        ua = boiler_params["UA"]
        losses = boiler_params["losses"]
        P_d, M_l, T_w, m_circ, m_shrink = np.asarray(x, dtype=float)

        P_bar = self._clip_pressure(P_d)
        props = self._props(P_bar)
        rho_l = props["rho_l"]
        rho_v = props["rho_v"]
        h_l = props["h_l"]
        h_v = props["h_v"]
        h_fg = props["h_fg"]
        Tsat = props["Tsat_C"]

        fuel_cmd = self._clamp(float(u.get("fuel_cmd", 0.4)), 0.0, 1.0)
        fw_cmd = self._clamp(float(u.get("fw_cmd", 0.5)), 0.0, 1.0)
        steam_demand = self._clamp(float(u.get("steam_demand", 0.5)), 0.0, 1.0)
        operating_key = self._operating_key(P_bar, M_l, T_w, m_circ, m_shrink, fuel_cmd, fw_cmd, steam_demand, p)

        d = p.get("degradation", {})
        ua_scale = float(d.get("ua_scale", 1.0))
        eta_comb = float(d.get("eta_comb", boiler_params["combustion"]["eta"]))
        shrink_gain = float(dynamics.get("shrink_gain", 0.08))
        shrink_tau = float(dynamics.get("shrink_tau_s", 15.0))

        max_s = limits["mdot_s_nom_kg_s"]
        wall_loss = losses.get("wall_loss_W", 40_000.0)
        ua_evap = ua["evaporator"] * max(0.05, ua_scale)
        m_fw, m_s, m_s_raw, q_release_mw, q_in, T_fw_out, q_evap, q_sh, m_boil_nom, m_cond, m_leak = self._compute_operating_terms(
            P_bar,
            float(T_w),
            p,
            fuel_cmd=fuel_cmd,
            fw_cmd=fw_cmd,
            steam_demand=steam_demand,
            props=props,
        )

        if self._prev_steam_demand is None:
            demand_delta = 0.0
        else:
            demand_delta = steam_demand - self._prev_steam_demand

        shrink_step_scale = float(dynamics.get("shrink_step_scale", 8000.0))

        # shrink/swell state captures transient response to demand ramp rates
        # and decays to zero while command is constant.
        steam_demand_pulse = demand_delta * shrink_step_scale
        dm_shrink = (
            -shrink_gain * steam_demand_pulse - m_shrink
        ) / max(1e-6, shrink_tau)
        m_boil = max(m_boil_nom - m_shrink, 0.0)

        m_circ_target = max(0.2, 0.04 * m_boil + 0.015 * M_l)
        circ_tau = dynamics.get("circ_tau_s", dynamics.get("circum_tau_s", 20.0))
        dm_circ = (m_circ_target - m_circ) / max(1e-6, circ_tau)
        alpha_l = 0.65
        m_r_out_l = alpha_l * m_circ
        m_r_out_v = max(0.0, m_circ - m_r_out_l)
        m_dc_in = m_circ

        M_v = self._algebraic_m_v(P_bar, M_l, p["boiler"], props=props)
        dM_l = m_fw + m_dc_in - m_r_out_l - m_boil + m_cond - m_leak
        dM_v = m_r_out_v + m_boil - m_s - m_cond

        V_l = M_l / max(rho_l, 1e-6)
        V_v = M_v / max(rho_v, 1e-6)
        V_err = (V_l + V_v - self.geometry.volume_m3) / max(self.geometry.volume_m3, 1e-6)
        k_p = float(dynamics["pressure_gain"])
        k_m = float(dynamics["pressure_mass_gain"])
        dP = k_p * V_err + k_m * (m_boil + m_fw - m_s - m_leak)

        Cw = float(dynamics.get("wall_tau_K", 15.0)) * 3500.0
        UAtot = max(1.0, ua["superheater"] + ua_evap)
        dT_w = (q_in - UAtot * max(T_w - Tsat, 0.0) - wall_loss) / Cw

        qmax_mw = float(boiler_params["combustion"]["qmax_MW"])
        T_sh = self._superheater_temperature(
            Tsat=float(Tsat),
            T_w=float(T_w),
            q_sh=float(q_sh),
            m_s=float(m_s),
            m_boil=float(m_boil),
            ua_scale=float(ua_scale),
            fouling_severity=float(d.get("fouling_severity", 0.0)),
        )
        q_ratio = self._clamp(float(q_release_mw) / max(1e-6, qmax_mw), 0.0, 1.5)
        q_ratio_capped = min(1.0, q_ratio)
        flue_gas_temp = float(Tsat + 90.0 + 280.0 * q_ratio_capped + 45.0 * max(0.0, q_ratio - 1.0))
        o2_pct = self._clamp(21.0 - 14.0 * self._clamp(q_ratio, 0.0, 1.0) - 4.0 * (1.0 - eta_comb), 1.0, 21.0)
        h_fw = float(4200.0 * max(0.0, T_fw_out))
        mass_rhs = float((m_fw + m_dc_in) - (m_s + m_leak))
        energy_rhs = float((m_fw + m_dc_in - m_boil - m_leak) * h_l + (m_cond - m_s) * h_v + q_evap + q_sh)
        dP_clamped = float(self._clamp(dP, -0.5, 0.5))
        dM_l_clamped = float(self._clamp(dM_l, -2.0, 2.0))
        dhl = dhdP_approx(P_bar, "h_l") * dP_clamped
        dhv = dhdP_approx(P_bar, "h_v") * dP_clamped
        dM_total = float(dM_l_clamped + dM_v)
        mass_resid = float(abs(dM_total - mass_rhs))
        dE_l = h_l * dM_l_clamped + M_l * dhl
        dE_v = h_v * dM_v + M_v * dhv
        energy_resid = float(abs((dE_l + dE_v) - energy_rhs))
        output_payload = (
            float(M_v),
            float(m_fw),
            float(m_s),
            float(T_fw_out),
            float(m_boil),
            float(m_leak),
            float(T_sh),
            float(flue_gas_temp),
            float(o2_pct),
            float(h_fw),
        )
        invariant_payload = {
            "vapor_mass": float(M_v),
            "dM_total": float(dM_total),
            "mass_balance_residual": float(mass_resid),
            "energy_balance_residual": float(energy_resid),
            "volume_algebraic_residual": abs(float(V_l + V_v - self.geometry.volume_m3)),
            "liquid_mass_nonnegative": float(M_l >= 0.0),
            "vapor_mass_nonnegative": float(M_v >= 0.0),
            "negative_holdup_violation": float(M_l < 0.0 or M_v < 0.0),
            "pressure_in_range": float(0.2 <= P_bar <= 30.0),
            "sat_temperature_C": float(Tsat),
            "superheat_C": float(max(0.0, float(T_w) - float(Tsat))),
            "saturation_consistency_residual": float(abs(self._clip_pressure(P_bar) - P_bar)),
            "state_feasible": float(
                M_l >= 0.0
                and M_v >= 0.0
                and abs(float(V_l + V_v - self.geometry.volume_m3)) <= 1e-6
                and 0.2 <= P_bar <= 30.0
            ),
        }

        self._last_intermediate = {
            "operating_key": operating_key,
            "output_payload": output_payload,
            "invariant_payload": invariant_payload,
        }

        return np.array(
            [
                dP_clamped,
                dM_l_clamped,
                self._clamp(dT_w, -6.0, 6.0),
                self._clamp(dm_circ, -1.5, 1.5),
                self._clamp(dm_shrink, -1.5, 1.5),
            ],
            dtype=float,
        )

    def outputs(self, x: np.ndarray | BackendInputs, u: Any = None, params: Any = None) -> dict[str, float]:
        if isinstance(x, BackendInputs):
            # CoreBackend signature: outputs(inputs, params) on the current
            # internal state. params may arrive positionally (in u's slot) or
            # as a keyword — accept both, reject ambiguity.
            if u is not None and params is not None:
                raise TypeError("outputs(inputs, params): pass params positionally or as keyword, not both")
            x, u, params = np.asarray(self.state, dtype=float), x.as_control(), (u if u is not None else params)
        params = self._resolve_params(params)
        P_d, M_l, T_w, m_circ, m_shrink = np.asarray(x, dtype=float)
        P_bar = self._clip_pressure(float(P_d))
        props = self._props(P_bar)
        boiler = params["boiler"]
        boiler_params = boiler["parameters"]
        dynamics = boiler_params["dynamics"]
        limits = boiler_params["limits"]
        combustion = boiler_params["combustion"]
        d = params.get("degradation", {})
        eta = float(d.get("eta_comb", combustion["eta"]))
        qmax_scale = float(d.get("qmax_scale", 1.0))
        fuel_cmd = self._clamp(float(u.get("fuel_cmd", 0.4)), 0.0, 1.0)
        steam_demand = self._clamp(float(u.get("steam_demand", 0.5)), 0.0, 1.0)
        fw_cmd = self._clamp(float(u.get("fw_cmd", 0.5)), 0.0, 1.0)
        operating_key = self._operating_key(P_bar, M_l, T_w, m_circ, m_shrink, fuel_cmd, fw_cmd, steam_demand, params)
        rho_l = float(props["rho_l"])
        Tsat = float(props["Tsat_C"])
        M_v = self._algebraic_m_v(P_bar, M_l, boiler, props=props)
        cache = self._last_intermediate
        cache_valid = cache.get("operating_key") == operating_key
        if cache_valid:
            M_v, m_fw, m_s, t_fw_out, m_boil, m_leak, t_sh, flue_gas_temp, o2_pct, h_fw = cache["output_payload"]
        else:
            m_fw, m_s, _m_s_raw, q_release_mw, _q_in, t_fw_out, _q_evap, q_sh, m_boil_nom, _m_cond, m_leak = self._compute_operating_terms(
                P_bar,
                float(T_w),
                params,
                fuel_cmd=fuel_cmd,
                fw_cmd=fw_cmd,
                steam_demand=steam_demand,
                props=props,
            )
            m_boil = max(m_boil_nom - float(m_shrink), 0.0)
            ua_scale = float(d.get("ua_scale", 1.0))
            t_sh = self._superheater_temperature(
                Tsat=float(Tsat),
                T_w=float(T_w),
                q_sh=float(q_sh),
                m_s=float(m_s),
                m_boil=float(m_boil),
                ua_scale=float(ua_scale),
                fouling_severity=float(d.get("fouling_severity", 0.0)),
            )
            q_ratio = self._clamp(float(q_release_mw) / max(1e-6, float(combustion["qmax_MW"])), 0.0, 1.5)
            q_ratio_capped = min(1.0, q_ratio)
            flue_gas_temp = float(Tsat + 90.0 + 280.0 * q_ratio_capped + 45.0 * max(0.0, q_ratio - 1.0))
            o2_pct = self._clamp(21.0 - 14.0 * self._clamp(q_ratio, 0.0, 1.0) - 4.0 * (1.0 - eta), 1.0, 21.0)
            h_fw = float(4200.0 * max(0.0, t_fw_out))
        swell_gain = float(dynamics.get("shrink_swell_gain", 0.03))
        level = self.geometry.level_from_state(M_l, rho_l, m_shrink, swell_gain)
        pulse_gain = float(dynamics.get("shrink_swell_pulse_gain", 0.08))
        if self._prev_steam_demand is None:
            demand_delta = 0.0
        else:
            demand_delta = steam_demand - self._prev_steam_demand
        level = self._clamp(level - pulse_gain * self.geometry.length_m * float(demand_delta), 0.0, self.geometry.length_m)

        return {
            "drum_pressure": float(P_bar),
            "drum_level": float(level),
            "steam_flow": float(m_s),
            "steam_flow_true": float(m_s),
            "drum_temp_sh": float(t_sh),
            "feedwater_flow": float(m_fw),
            "feedwater_temp": float(t_fw_out),
            "m_boil": m_boil,
            "m_leak": m_leak,
            "wall_temp": float(T_w),
            "vapor_mass": float(M_v),
            "drum_temp": float(T_w),
            "flue_gas_temp": flue_gas_temp,
            "O2": o2_pct,
            "h_fw": h_fw,
        }

    def invariants(self, x: np.ndarray | BackendInputs, u: Any = None, params: Any = None) -> dict[str, float]:
        if isinstance(x, BackendInputs):
            if u is not None and params is not None:
                raise TypeError("invariants(inputs, params): pass params positionally or as keyword, not both")
            x, u, params = np.asarray(self.state, dtype=float), x.as_control(), (u if u is not None else params)
        params = self._resolve_params(params)
        P_d, M_l, T_w, m_circ, m_shrink = np.asarray(x, dtype=float)
        P_bar = self._clip_pressure(float(P_d))
        fuel_cmd = self._clamp(float(u.get("fuel_cmd", 0.4)), 0.0, 1.0)
        fw_cmd = self._clamp(float(u.get("fw_cmd", 0.5)), 0.0, 1.0)
        steam_demand = self._clamp(float(u.get("steam_demand", 0.5)), 0.0, 1.0)
        cache = self._last_intermediate
        operating_key = self._operating_key(P_bar, M_l, T_w, m_circ, m_shrink, fuel_cmd, fw_cmd, steam_demand, params)
        cache_hit = cache.get("operating_key") == operating_key
        if not cache_hit:
            self.derivatives(0.0, x, u, params)
            cache = self._last_intermediate

        payload = cache["invariant_payload"]
        if isinstance(payload, tuple):
            M_v, dM_total, mass_resid, energy_resid, volume_residual = payload
            payload = {
                "vapor_mass": float(M_v),
                "dM_total": float(dM_total),
                "mass_balance_residual": float(mass_resid),
                "energy_balance_residual": float(energy_resid),
                "volume_algebraic_residual": float(volume_residual),
            }

        M_v = float(payload.get("vapor_mass", self._algebraic_m_v(P_bar, M_l, params["boiler"])))
        mass_resid = float(payload.get("mass_balance_residual", 0.0))
        energy_resid = float(payload.get("energy_balance_residual", 0.0))
        volume_residual = float(payload.get("volume_algebraic_residual", 0.0))
        return {
            "mass_balance_residual": mass_resid,
            "energy_balance_residual": energy_resid,
            "volume_algebraic_residual": volume_residual,
            "m_total": float(M_l + M_v),
            "dM_total": float(payload.get("dM_total", 0.0)),
            "liquid_mass_nonnegative": float(payload.get("liquid_mass_nonnegative", 1.0 if M_l >= 0.0 else 0.0)),
            "vapor_mass_nonnegative": float(payload.get("vapor_mass_nonnegative", 1.0 if M_v >= 0.0 else 0.0)),
            "negative_holdup_violation": float(payload.get("negative_holdup_violation", 1.0 if (M_l < 0.0 or M_v < 0.0) else 0.0)),
            "pressure_in_range": float(payload.get("pressure_in_range", 1.0 if 0.2 <= P_bar <= 30.0 else 0.0)),
            "sat_temperature_C": float(payload.get("sat_temperature_C", self._props(P_bar)["Tsat_C"])),
            "superheat_C": float(payload.get("superheat_C", max(0.0, T_w - self._props(P_bar)["Tsat_C"]))),
            "saturation_consistency_residual": float(payload.get("saturation_consistency_residual", 0.0)),
            "state_feasible": float(payload.get("state_feasible", 1.0 if abs(volume_residual) <= 1e-6 and M_l >= 0.0 and M_v >= 0.0 else 0.0)),
        }
