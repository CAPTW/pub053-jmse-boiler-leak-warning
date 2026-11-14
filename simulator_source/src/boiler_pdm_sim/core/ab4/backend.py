"""``Ab4Backend`` — CoreBackend wrapper for the Phase A ab4 physics core (A3-e).

Wires the 4-state drum model (§3.1) to the feedwater/steam/blowdown lines (§3.5)
and the combustion stub (§3.3 stub) and exposes the opaque-state
:class:`~boiler_pdm_sim.core.backend_protocol.CoreBackend` contract so
``backend_factory`` can select it via ``core_backend.type = "ab4"`` and the
existing step loop can drive it.

New backend => implements CoreBackend directly (its own ``advance``); it does NOT
inherit ``LegacyAdvanceMixin`` (that is hard-wired to the 5-state legacy layout).

The actuator commands (fuel/fw/steam) are held constant across a step, but the
feedwater and steam *flows* are recomputed from the live drum pressure inside the
RHS (they are pressure dependent), which is the physically correct coupling for
the BDF step.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Mapping

import numpy as np
from scipy.integrate import solve_ivp

from ..backend_protocol import BackendInputs, StepReport
from ...props import if97
from ...props.fuels import get_fuel
from .drum_model import Ab4DrumModel, Ab4Inputs, Ab4Params, STATE_NAMES
from .feedwater import FeedwaterLine
from .furnace import Furnace
from .steam_line import BlowdownSchedule, SteamLine

__all__ = ["Ab4Backend"]

_BAR_TO_PA = 1.0e5
# State atol vector [p (Pa), V_wt (m3), alpha_r (-), V_sd (m3)] (§6).
_ATOL = np.array([1.0e2, 1.0e-4, 1.0e-5, 1.0e-5], dtype=float)


class Ab4Backend:
    def __init__(
        self,
        params: Ab4Params,
        feedwater: FeedwaterLine,
        steam: SteamLine,
        combustion: Furnace,
        blowdown: BlowdownSchedule,
        *,
        x0: np.ndarray,
        base_eta_comb: float = 0.9,
        p_downstream_pa: float | None = None,
    ) -> None:
        self.model = Ab4DrumModel(params)
        self.fw = feedwater
        self.steam = steam
        self.comb = combustion
        self.blowdown = blowdown
        self.base_eta_comb = float(base_eta_comb)
        self.state = np.asarray(x0, dtype=float).copy()
        self._x0 = self.state.copy()

    # ---- construction from config (A3-f) ----
    @classmethod
    def from_config(cls, boiler_cfg: Mapping[str, Any], backend_cfg: Mapping[str, Any] | None = None) -> "Ab4Backend":
        """Build an ab4 backend from the boiler config + core_backend block.

        Geometry comes from ``boiler.geometry``; metal/riser/downcomer split and
        the empirical drum/riser parameters are marine-aux placeholders scaled to
        the configured geometry (R1/R9). Rated sizing uses ``boiler.nominal``.
        """
        bcfg = backend_cfg or {}
        geo = boiler_cfg.get("geometry", {})
        nominal = boiler_cfg.get("nominal", {})
        combu = boiler_cfg.get("parameters", {}).get("combustion", {})

        r = float(geo.get("drum_radius_m", 0.75))
        L = float(geo.get("drum_length_m", 5.0))
        p_bar = float(nominal.get("pressure_bar", 7.0))
        q_s_rated = float(nominal.get("steam_flow_kg_s", 1.4))
        level_frac = float(nominal.get("level_fraction", 0.55))
        base_eta = float(combu.get("eta", 0.9))

        # geometry-scaled parameters (placeholders, R9)
        from .geometry import DrumGeometry

        geom = DrumGeometry(radius_m=r, length_m=L)
        V_drum = geom.total_volume_m3
        # riser/downcomer placeholders (R9): kept modest vs the drum so the
        # void-driven swell on a small aux boiler stays physically bounded.
        V_r = float(bcfg.get("V_r", 0.35 * V_drum))
        V_dc = float(bcfg.get("V_dc", 0.15 * V_drum))
        V_t = V_drum + V_r + V_dc
        A_dc = float(bcfg.get("A_dc", 0.03))
        m_t_cp = float(bcfg.get("m_t_cp", 6000.0 * 490.0))
        V_sd0 = float(bcfg.get("V_sd0", 0.05 * V_drum))
        params = Ab4Params(
            geometry=geom, V_t=V_t, V_dc=V_dc, V_r=V_r, A_dc=A_dc, m_t_cp=m_t_cp,
            T_d=float(bcfg.get("T_d", 12.0)), beta=float(bcfg.get("beta", 0.3)),
            V_sd0=V_sd0, k_friction=float(bcfg.get("k_friction", 25.0)),
        )

        b = if97.saturation_state(p_bar)
        p_drum_pa = p_bar * _BAR_TO_PA
        T_fw = float(bcfg.get("T_fw_C", 60.0))
        h_f = 4200.0 * T_fw
        q_evap_rated = q_s_rated * max(b.h_s - h_f, 1.0)

        fw = FeedwaterLine.from_rated(
            q_rated_kg_s=q_s_rated, p_drum_rated_pa=p_drum_pa, rho_w=b.rho_w, t_fw_C=T_fw
        )
        p_down_pa = float(bcfg.get("p_downstream_bar", 0.6 * p_bar)) * _BAR_TO_PA
        steam = SteamLine.from_rated(
            q_rated_kg_s=q_s_rated, p_drum_rated_pa=p_drum_pa, rho_s_rated=b.rho_s,
            p_downstream_pa=p_down_pa,
        )
        comb = Furnace.from_rated(
            q_evap_rated_W=q_evap_rated,
            Tsat_rated_C=b.Tsat_C,
            rated_fuel_cmd=float(bcfg.get("rated_fuel_cmd", 0.7)),
            target_eta=base_eta,
            fuel=get_fuel(str(bcfg.get("fuel", "MGO"))),
            lambda_excess_air=float(bcfg.get("lambda_excess_air", 1.15)),
            f_wall=float(bcfg.get("f_wall", 0.015)),
            T_air_C=float(bcfg.get("T_air_C", 25.0)),
        )
        bd_cfg = bcfg.get("blowdown", {}) if isinstance(bcfg.get("blowdown"), Mapping) else {}
        blowdown = BlowdownSchedule(
            enabled=bool(bd_cfg.get("enabled", False)),
            period_s=float(bd_cfg.get("period_s", 3600.0)),
            duration_s=float(bd_cfg.get("duration_s", 60.0)),
            flow_kg_s=float(bd_cfg.get("flow_kg_s", 0.0)),
        )

        # Seed the initial state at the steady distribution for a nominal firing,
        # so a normal-operation run starts at equilibrium (no startup heatup swell
        # that would transiently overfill the drum). Apparent level is placed at
        # the nominal setpoint with the equilibrium void/sub-surface volume.
        from .drum_model import Ab4DrumModel, mean_void_fraction

        model = Ab4DrumModel(params)
        fuel0 = float(bcfg.get("rated_fuel_cmd", 0.7))
        Q0 = comb.heat_to_drum(fuel0, 1.0, b.Tsat_C).Q_drum_W
        q_boil0 = Q0 / max(b.h_fg, 1.0)

        def _equilibrium(mdl):
            """Fixed point: alpha_r = q_boil/q_dc(alpha_v(alpha_r)) -> (alpha_r, q_dc)."""
            a_r = float(bcfg.get("alpha_r0", 0.06))
            qd = 1.0
            for _ in range(40):
                av = mean_void_fraction(a_r, b.rho_w, b.rho_s)
                qd = max(mdl.circulation_flow(b.rho_w, b.rho_s, av), 1e-6)
                a_r = min(max(q_boil0 / qd, 1e-4), 0.5)
            return a_r, qd

        alpha_r, q_dc = _equilibrium(model)
        # Size friction so the circulation ratio q_dc/q_s lands in the design's
        # 10-30 band (R9 "circulation-ratio back-calculation"), unless k_friction
        # is given explicitly. q_dc ~ k_friction^(-1/2), so scale k by (q_dc/target)^2.
        if "k_friction" not in bcfg:
            cr_target = float(bcfg.get("circulation_ratio", 20.0))
            q_dc_target = max(cr_target * q_s_rated, 1e-6)
            k_fric = params.k_friction * (q_dc / q_dc_target) ** 2
            params = replace(params, k_friction=k_fric)
            model = Ab4DrumModel(params)
            alpha_r, q_dc = _equilibrium(model)
        av0 = mean_void_fraction(alpha_r, b.rho_w, b.rho_s)
        V_sd_eq = V_sd0 + params.beta * alpha_r * q_dc / max(b.rho_s, 1e-9) * params.T_d

        l0 = level_frac * 2.0 * r
        V_apparent = geom.volume_from_level(l0)          # V_wd + V_sd at the setpoint
        V_wd0 = max(V_apparent - V_sd_eq, 0.0)
        V_wt0 = V_wd0 + V_dc + (1.0 - av0) * V_r
        x0 = np.array([p_drum_pa, V_wt0, alpha_r, V_sd_eq], dtype=float)

        return cls(
            params, fw, steam, comb, blowdown, x0=x0, base_eta_comb=base_eta,
        )

    # ---- CoreBackend ----
    @property
    def state_names(self) -> list[str]:
        return list(STATE_NAMES)

    def reset(self, x0: Any = None, params: Mapping[str, Any] | None = None) -> np.ndarray:
        if x0 is not None:
            self.state = np.asarray(x0, dtype=float).copy()
        else:
            self.state = self._x0.copy()
        return self.state

    # ---- input mapping ----
    def _degradation(self, params: Mapping[str, Any] | None) -> dict[str, Any]:
        if isinstance(params, Mapping):
            deg = params.get("degradation", {})
            if isinstance(deg, Mapping):
                return dict(deg)
        return {}

    def _completeness(self, deg: Mapping[str, Any]) -> float:
        eta = float(deg.get("eta_comb", self.base_eta_comb))
        return max(0.0, min(1.0, eta / max(self.base_eta_comb, 1e-6)))

    def _make_inputs_fn(self, t0: float, inputs: BackendInputs, params: Mapping[str, Any] | None):
        deg = self._degradation(params)
        fuel_cmd = inputs.fuel_cmd
        fw_cmd = inputs.fw_cmd
        steam_demand = inputs.steam_demand
        completeness = self._completeness(deg)
        # fouling lowers heat-transfer UA (T_stack up, eta down); accept either key.
        ua_scale = float(deg.get("ua_scale", deg.get("qmax_scale", 1.0)))
        pump_wear = float(deg.get("pump_wear", 0.0))
        leak_coeff = float(deg.get("tube_leak_coeff", 0.0))
        boundary = inputs.boundary or {}
        T_fw = float(boundary.get("T_fw_C", 60.0))
        h_f = self.comb.feedwater_enthalpy_J_kg(T_fw)
        # T_ad / products depend only on (fuel_cmd, completeness) -> compute once per step.
        furnace_op = self.comb.prepare(fuel_cmd, completeness)

        def make(t: float, x: np.ndarray) -> Ab4Inputs:
            p_pa = float(x[0])
            p_bar = p_pa / _BAR_TO_PA
            b = if97.saturation_state(min(max(p_bar, if97.P_MIN_BAR), if97.P_MAX_BAR))
            Q = self.comb.evaluate(furnace_op, b.Tsat_C, ua_scale).Q_drum_W if furnace_op else 0.0
            q_f = self.fw.flow_kg_s(p_pa, fw_cmd, rho_w=b.rho_w, wear=pump_wear)
            q_s = self.steam.flow_kg_s(p_pa, steam_demand, rho_s=b.rho_s)
            q_leak = leak_coeff * math.sqrt(max(p_bar - 1.0, 0.0))
            q_bd = self.blowdown.flow_at(t)
            return Ab4Inputs(Q=Q, q_f=q_f, h_f=h_f, q_s=q_s, q_leak=q_leak, q_bd=q_bd)

        return make

    # ---- advance ----
    def advance(
        self,
        t: float,
        dt: float,
        inputs: BackendInputs,
        params: Mapping[str, Any],
        *,
        method: str = "BDF",
    ) -> StepReport:
        make_inputs = self._make_inputs_fn(t, inputs, params)

        def rhs(tt: float, x: np.ndarray) -> np.ndarray:
            return self.model.derivatives(x, make_inputs(tt, x))

        sol = solve_ivp(
            rhs, (t, t + dt), self.state, method=method, rtol=1e-6, atol=_ATOL, dense_output=False
        )
        if not sol.success:
            # fail-loud per §6 (no silent Euler fallback for ab4)
            raise RuntimeError(f"ab4 BDF integration failed at t={t}: {sol.message}")

        x_next = np.asarray(sol.y[:, -1], dtype=float)

        # physical guard (no clamp): flag, do not silently clip (§6)
        events: list[str] = []
        v_wt = x_next[1]
        v_frac = v_wt / max(self.model.p.V_t, 1e-9)
        feasible = 0.05 <= v_frac <= 0.95 and (if97.P_MIN_BAR * _BAR_TO_PA) < x_next[0] < (
            if97.P_MAX_BAR * _BAR_TO_PA
        )
        if not feasible:
            events.append(f"ab4_infeasible_t={t:.1f}")

        self.state = x_next
        u_end = make_inputs(t + dt, x_next)
        dx_end = self.model.derivatives(x_next, u_end)
        res = self.model.conservation_residuals(x_next, u_end, dx_end)

        return StepReport(
            x_after=x_next.copy(),
            solver={
                "requested_method": method,
                "solver_used": method,
                "retry_count": 0,
                "rejected_steps": 0,
                "fallback_used": False,
                "nfev": int(getattr(sol, "nfev", 0)),
            },
            alignment={
                "residual_before_m3": 0.0,
                "residual_after_m3": 0.0,
                "iterations": 0,
                "feasible": bool(feasible),
                "mass_balance_residual": res["mass_balance_residual"],
                "energy_balance_residual": res["energy_balance_residual"],
                "source": "ab4",
            },
            events=events,
            timings={"align_seconds": 0.0},
        )

    # ---- outputs / invariants ----
    def _resolve_state_inputs(self, x: Any, params: Any):
        """The loop calls outputs/invariants with a BackendInputs and params; use the
        internal state plus those inputs. An ndarray ``x`` overrides the state."""
        if isinstance(x, BackendInputs):
            state = self.state
            make = self._make_inputs_fn(0.0, x, params)
            return state, make(0.0, state)
        state = np.asarray(x, dtype=float)
        if isinstance(params, BackendInputs):
            make = self._make_inputs_fn(0.0, params, None)
            return state, make(0.0, state)
        # bare state, synthesize neutral inputs
        return state, Ab4Inputs(Q=0.0, q_f=0.0, h_f=0.0, q_s=0.0)

    def outputs(self, x: Any, u: Any = None, params: Any = None) -> dict[str, float]:
        state, ab4_u = self._resolve_state_inputs(x, u if u is not None else params)
        y = self.model.outputs(state, ab4_u)
        p_bar = y["drum_pressure"]
        b = if97.saturation_state(min(max(p_bar, if97.P_MIN_BAR), if97.P_MAX_BAR))
        deg = self._degradation(u if isinstance(u, Mapping) else params)
        completeness = self._completeness(deg)
        ua_scale = float(deg.get("ua_scale", deg.get("qmax_scale", 1.0)))
        fuel_cmd = x.fuel_cmd if isinstance(x, BackendInputs) else 0.0
        T_fw = 60.0
        if isinstance(x, BackendInputs) and x.boundary:
            T_fw = float(x.boundary.get("T_fw_C", 60.0))
        # required flue channels from the enthalpy-based furnace (§3.3, A4)
        op = self.comb.prepare(fuel_cmd, completeness)
        cr = self.comb.evaluate(op, b.Tsat_C, ua_scale) if op is not None else None
        y["flue_gas_temp"] = cr.T_stack_C if cr else b.Tsat_C
        y["O2"] = cr.o2_dry_pct if cr else 21.0
        y["boiler_efficiency"] = cr.eta_boiler if cr else 0.0   # additive PdM channel
        y["flame_temp"] = cr.T_ad_C if cr else b.Tsat_C          # additive PdM channel
        y["h_fw"] = self.comb.feedwater_enthalpy_J_kg(T_fw)
        y["m_leak"] = float(ab4_u.q_leak)
        y["m_boil"] = float(max(ab4_u.Q, 0.0) / max(b.h_fg, 1.0))
        y["wall_temp"] = b.Tsat_C       # ab4: metal follows Tsat (no fixed 280C)
        y["feedwater_temp"] = T_fw
        # legacy-schema parity channels (Phase A drum core has no superheater):
        y["drum_temp_sh"] = b.Tsat_C            # saturated steam temp (no SH section yet)
        y["steam_flow_true"] = float(ab4_u.q_s)  # ab4 q_s is the true model flow
        y["vapor_mass"] = float(b.rho_s * max(self.model.p.V_t - state[1], 0.0))
        return y

    def invariants(self, x: Any, u: Any = None, params: Any = None) -> dict[str, float]:
        state, ab4_u = self._resolve_state_inputs(x, u if u is not None else params)
        dx = self.model.derivatives(state, ab4_u)
        res = self.model.conservation_residuals(state, ab4_u, dx)
        v_frac = state[1] / max(self.model.p.V_t, 1e-9)
        p_bar = state[0] / _BAR_TO_PA
        return {
            "mass_balance_residual": res["mass_balance_residual"],
            "energy_balance_residual": res["energy_balance_residual"],
            "volume_algebraic_residual": 0.0,
            "state_feasible": float(0.05 <= v_frac <= 0.95),
            "pressure_in_range": float(if97.P_MIN_BAR < p_bar < if97.P_MAX_BAR),
        }
