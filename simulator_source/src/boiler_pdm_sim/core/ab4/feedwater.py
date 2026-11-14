"""Feedwater line for the Phase A ab4 core (§3.5).

``fw_cmd`` is the **valve opening**; pump speed N is fixed at 1.0 in Phase A.
Pump curve  dP_pump(q) = a0 - a1*q^2  (rated point + shutoff head).
``pump_wear`` maps to a0*(1-wear) so the controller opens the valve further to
compensate -- the PdM signature arises physically rather than by injection.

Feedwater flow is the algebraic solution of the series pressure balance
    P_feedtank + dP_pump(q) = P_drum + dP_valve(q, opening)
    dP_valve = (q / (Cv_SI * opening))^2 / rho_w          (SI consistent)
which is closed-form because both dP terms are quadratic in q:
    q^2 = max(0, P_feedtank + a0 - P_drum) / (a1 + 1/(rho_w*(Cv_SI*opening)^2))
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FeedwaterLine"]

_BAR_TO_PA = 1.0e5


@dataclass(frozen=True)
class FeedwaterLine:
    cv_si: float          # valve flow coefficient [SI: kg/s per sqrt(Pa*kg/m3)]
    pump_a0_pa: float     # shutoff head [Pa]
    pump_a1: float        # quadratic droop [Pa/(kg/s)^2]
    p_feedtank_pa: float = 1.2 * _BAR_TO_PA
    t_fw_C: float = 60.0

    @classmethod
    def from_rated(
        cls,
        *,
        q_rated_kg_s: float,
        p_drum_rated_pa: float,
        rho_w: float,
        opening_rated: float = 0.5,
        shutoff_factor: float = 1.6,
        p_feedtank_pa: float = 1.2 * _BAR_TO_PA,
        t_fw_C: float = 60.0,
    ) -> "FeedwaterLine":
        """Size pump/valve from a rated operating point.

        The pump shutoff head is ``shutoff_factor`` times the rated developed head
        (drum pressure minus feedtank, plus the rated valve drop); ``a1`` is set so
        the curve passes through the rated (q, head) point. The valve ``cv_si`` is
        sized so ``opening_rated`` gives the rated flow at the rated pressures.
        """
        # Valve drop required at rated flow & opening to reach drum from pump outlet.
        # Choose the pump to develop head_rated = (P_drum - P_feedtank) + dP_valve_rated.
        # Pick dP_valve_rated as a modest fraction of the static rise for controllability.
        static_rise = max(p_drum_rated_pa - p_feedtank_pa, 1.0)
        dp_valve_rated = 0.25 * static_rise
        # cv from dP_valve = (q/(cv*opening))^2 / rho_w  ->  cv = q / (opening*sqrt(dP*rho_w))
        cv_si = q_rated_kg_s / (opening_rated * (dp_valve_rated * rho_w) ** 0.5)
        head_rated = static_rise + dp_valve_rated
        a0 = shutoff_factor * head_rated
        a1 = (a0 - head_rated) / max(q_rated_kg_s**2, 1e-9)
        return cls(cv_si=cv_si, pump_a0_pa=a0, pump_a1=a1, p_feedtank_pa=p_feedtank_pa, t_fw_C=t_fw_C)

    def pump_head_pa(self, q_kg_s: float, wear: float = 0.0) -> float:
        a0 = self.pump_a0_pa * max(0.0, 1.0 - float(wear))
        return a0 - self.pump_a1 * float(q_kg_s) ** 2

    def flow_kg_s(self, p_drum_pa: float, opening: float, *, rho_w: float, wear: float = 0.0) -> float:
        """Algebraic feedwater mass flow [kg/s] for a given drum pressure and valve opening."""
        op = max(0.0, min(1.0, float(opening)))
        if op <= 1e-6:
            return 0.0
        a0 = self.pump_a0_pa * max(0.0, 1.0 - float(wear))
        driving = self.p_feedtank_pa + a0 - float(p_drum_pa)
        if driving <= 0.0:
            return 0.0
        valve_coeff = 1.0 / (rho_w * (self.cv_si * op) ** 2)
        denom = self.pump_a1 + valve_coeff
        q2 = driving / denom
        return float(max(0.0, q2) ** 0.5)
