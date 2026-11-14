"""Enthalpy-based combustion / flue-gas furnace for the ab4 core (§3.3, WP A4).

Replaces the A3 combustion stub with a single-node, **enthalpy-based** gas-side
balance (cp*dT is banned — a temperature-dependent cp breaks energy closure and
the §7.1 gas-side gate catches it):

    q_fuel  = fuel_cmd * m_fuel_max
    Q_comb  = q_fuel * LHV * eta_comb                      # eta_comb = completeness
    products: CO2/H2O/SO2 scale with eta_comb; O2_flue = (lambda - eta_comb)*O2_stoich
    T_ad:    Q_comb = n_gas * [h_gas(T_ad) - h_gas(T_air)]  # adiabatic flame temp
    Q_water: Q_water = UA_eff * LMTD(T_ad->T_stack ; Tsat)  # single node
             = n_gas * [h_gas(T_ad) - h_gas(T_stack)]       # closes T_stack
    L_stack = n_gas * [h_gas(T_stack) - h_gas(T_air)]       # = Q_comb - Q_water
    L_wall  = f_wall * Q_comb
    Q_drum  = Q_water - L_wall                              # heat into evaporation
    eta_boiler = Q_drum / (q_fuel * LHV)                    # denominator = fuel input

burner_deg lowers eta_comb -> Q down and O2 up (dry-basis mole balance); fouling
lowers ua_scale -> T_stack up and eta down. Gas enthalpy comes from props.gas.

Hot-path split: T_ad and the product composition depend only on (fuel_cmd,
eta_comb), so ``prepare`` computes them once per step and ``evaluate`` solves only
the pressure-dependent T_stack per RHS evaluation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.optimize import brentq

from ...props import gas
from ...props.fuels import Fuel, MGO

__all__ = ["Furnace", "FurnaceOperatingPoint", "CombustionResult"]

_M_C, _M_H, _M_S = 0.012011, 0.001008, 0.032060   # molar masses [kg/mol]
_N2_PER_O2 = 3.76                                  # molar N2/O2 in dry air
_T0_K = 273.15
_T_MAX_GAS_K = 2500.0                              # props.gas valid ceiling


@dataclass(frozen=True)
class FurnaceOperatingPoint:
    m_fuel: float
    Q_comb: float
    n_gas: float
    fracs: dict[str, float]
    T_ad_K: float
    o2_dry_pct: float


@dataclass(frozen=True)
class CombustionResult:
    Q_drum_W: float          # heat delivered to evaporation
    T_stack_C: float         # flue-gas exit temperature
    T_ad_C: float            # adiabatic flame temperature
    eta_boiler: float        # direct-method efficiency
    o2_dry_pct: float        # dry-basis excess O2 [%]
    gas_residual_W: float    # Q_comb - (Q_water + L_stack), ~0 by construction


def _lmtd(dt1: float, dt2: float) -> float:
    dt1 = max(dt1, 1e-9)
    dt2 = max(dt2, 1e-9)
    if abs(dt1 - dt2) < 1e-6:
        return 0.5 * (dt1 + dt2)
    return (dt1 - dt2) / math.log(dt1 / dt2)


@dataclass(frozen=True)
class Furnace:
    fuel: Fuel
    m_fuel_max_kg_s: float
    UA_eff_W_K: float
    lambda_excess_air: float = 1.15
    f_wall: float = 0.015
    T_air_C: float = 25.0
    cp_fw_J_kgK: float = 4200.0

    def _o2_stoich_mol_per_kg(self) -> float:
        n_C = self.fuel.C_mass / _M_C
        n_H = self.fuel.H_mass / _M_H
        n_S = self.fuel.S_mass / _M_S
        return n_C + n_H / 4.0 + n_S

    def combustion_products(self, eta_comb: float) -> tuple[dict[str, float], float, float]:
        """Return (mole_fractions, total_wet_moles_per_kg_fuel, dry_O2_pct)."""
        eta = max(0.0, min(1.0, float(eta_comb)))
        lam = max(1.0, float(self.lambda_excess_air))
        n_C = self.fuel.C_mass / _M_C
        n_H = self.fuel.H_mass / _M_H
        n_S = self.fuel.S_mass / _M_S
        o2_stoich = n_C + n_H / 4.0 + n_S
        o2_supplied = lam * o2_stoich
        n2 = _N2_PER_O2 * o2_supplied
        co2, h2o, so2 = eta * n_C, eta * n_H / 2.0, eta * n_S
        o2_flue = max(0.0, o2_supplied - eta * o2_stoich)
        total = co2 + h2o + so2 + o2_flue + n2
        fracs = {
            "CO2": co2 / total, "H2O": h2o / total, "SO2": so2 / total,
            "O2": o2_flue / total, "N2": n2 / total,
        }
        o2_dry_pct = 100.0 * o2_flue / max(total - h2o, 1e-9)
        return fracs, total, o2_dry_pct

    def _h_mix(self, T_K: float, fracs: dict[str, float]) -> float:
        return gas.h_gas(min(max(T_K, 250.0), _T_MAX_GAS_K), fracs)

    def _adiabatic_flame_K(self, Q_per_mol: float, fracs: dict[str, float], T_air_K: float) -> float:
        target = Q_per_mol + self._h_mix(T_air_K, fracs)
        if self._h_mix(_T_MAX_GAS_K, fracs) <= target:
            return _T_MAX_GAS_K  # would exceed table ceiling; clamp (flagged via residual)
        return float(brentq(lambda T: self._h_mix(T, fracs) - target, T_air_K, _T_MAX_GAS_K,
                            xtol=1e-2, rtol=1e-8, maxiter=100))

    # ---- hot-path split ----
    def prepare(self, fuel_cmd: float, eta_comb: float) -> FurnaceOperatingPoint | None:
        """Per-step constant part (no pressure dependence). None if not firing."""
        m_fuel = max(0.0, min(1.0, float(fuel_cmd))) * self.m_fuel_max_kg_s
        if m_fuel <= 1e-9:
            return None
        eta = max(0.0, min(1.0, float(eta_comb)))
        lhv = self.fuel.LHV_MJ_kg * 1.0e6
        Q_comb = m_fuel * lhv * eta
        fracs, n_per_kg, o2_dry = self.combustion_products(eta)
        n_gas = m_fuel * n_per_kg
        T_ad_K = self._adiabatic_flame_K(Q_comb / max(n_gas, 1e-12), fracs, self.T_air_C + _T0_K)
        return FurnaceOperatingPoint(m_fuel, Q_comb, n_gas, fracs, T_ad_K, o2_dry)

    def evaluate(self, op: FurnaceOperatingPoint, Tsat_C: float, ua_scale: float = 1.0) -> CombustionResult:
        """Per-eval part: solve the pressure-dependent T_stack and the heat split."""
        Tsat_K = float(Tsat_C) + _T0_K
        T_air_K = self.T_air_C + _T0_K
        ua = max(0.0, self.UA_eff_W_K * float(ua_scale))
        h_ad = self._h_mix(op.T_ad_K, op.fracs)
        lo, hi = Tsat_K + 1e-3, op.T_ad_K - 1e-6

        if hi <= lo:
            T_stack_K = Tsat_K
        else:
            def f(Ts):
                q_water = op.n_gas * (h_ad - self._h_mix(Ts, op.fracs))
                return q_water - ua * _lmtd(op.T_ad_K - Tsat_K, Ts - Tsat_K)
            flo, fhi = f(lo), f(hi)
            if flo * fhi > 0.0:
                T_stack_K = lo if abs(flo) < abs(fhi) else hi
            else:
                T_stack_K = float(brentq(f, lo, hi, xtol=1e-2, rtol=1e-8, maxiter=100))

        Q_water = op.n_gas * (h_ad - self._h_mix(T_stack_K, op.fracs))
        L_stack = op.n_gas * (self._h_mix(T_stack_K, op.fracs) - self._h_mix(T_air_K, op.fracs))
        L_wall = self.f_wall * op.Q_comb
        Q_drum = max(0.0, Q_water - L_wall)
        lhv = self.fuel.LHV_MJ_kg * 1.0e6
        eta_boiler = Q_drum / max(op.m_fuel * lhv, 1e-9)
        return CombustionResult(
            Q_drum_W=Q_drum, T_stack_C=T_stack_K - _T0_K, T_ad_C=op.T_ad_K - _T0_K,
            eta_boiler=eta_boiler, o2_dry_pct=op.o2_dry_pct,
            gas_residual_W=op.Q_comb - (Q_water + L_stack),
        )

    def heat_to_drum(self, fuel_cmd: float, eta_comb: float, Tsat_C: float, ua_scale: float = 1.0) -> CombustionResult:
        op = self.prepare(fuel_cmd, eta_comb)
        if op is None:
            return CombustionResult(0.0, Tsat_C, Tsat_C, 0.0, 21.0, 0.0)
        return self.evaluate(op, Tsat_C, ua_scale)

    def feedwater_enthalpy_J_kg(self, T_fw_C: float) -> float:
        return float(self.cp_fw_J_kgK * max(0.0, float(T_fw_C)))

    @classmethod
    def from_rated(
        cls, *, q_evap_rated_W: float, Tsat_rated_C: float, rated_fuel_cmd: float = 0.7,
        target_eta: float = 0.90, fuel: Fuel = MGO, lambda_excess_air: float = 1.15,
        f_wall: float = 0.015, T_air_C: float = 25.0,
    ) -> "Furnace":
        """Size m_fuel_max and UA_eff so rated firing delivers q_evap_rated at
        ~target_eta, with T_stack set by the enthalpy balance (anchoring §7.3)."""
        lhv = fuel.LHV_MJ_kg * 1.0e6
        m_fuel_rated = q_evap_rated_W / (max(target_eta, 1e-3) * lhv)
        m_fuel_max = m_fuel_rated / max(rated_fuel_cmd, 1e-3)
        tmp = cls(fuel=fuel, m_fuel_max_kg_s=m_fuel_max, UA_eff_W_K=1.0,
                  lambda_excess_air=lambda_excess_air, f_wall=f_wall, T_air_C=T_air_C)
        Q_comb = m_fuel_rated * lhv
        fracs, n_per_kg, _ = tmp.combustion_products(1.0)
        n_gas = m_fuel_rated * n_per_kg
        Tsat_K = Tsat_rated_C + _T0_K
        T_ad_K = tmp._adiabatic_flame_K(Q_comb / n_gas, fracs, T_air_C + _T0_K)
        Q_water = q_evap_rated_W + f_wall * Q_comb     # so Q_drum = q_evap_rated
        h_ad = tmp._h_mix(T_ad_K, fracs)
        h_stack = h_ad - Q_water / max(n_gas, 1e-12)
        T_stack_K = float(brentq(lambda Ts: tmp._h_mix(Ts, fracs) - h_stack,
                                 Tsat_K + 1e-3, T_ad_K - 1e-6, xtol=1e-2, maxiter=100))
        UA_eff = Q_water / max(_lmtd(T_ad_K - Tsat_K, T_stack_K - Tsat_K), 1e-9)
        return cls(fuel=fuel, m_fuel_max_kg_s=m_fuel_max, UA_eff_W_K=UA_eff,
                   lambda_excess_air=lambda_excess_air, f_wall=f_wall, T_air_C=T_air_C)
