"""Steam line + blowdown for the Phase A ab4 core (§3.5).

Steam valve: ``steam_demand`` (0..1) sets the valve opening against a downstream
pressure. The critical pressure ratio for **saturated** steam (k ~= 1.135) is
0.577 (the legacy 0.55 was a superheated-steam value -- review fix):

    subcritical (p_down/p > 0.577):  q = Cv_SI * opening * sqrt(dp * rho_s)
    critical    (p_down/p <= 0.577): q = C_choked * Cv_SI * opening * p

Blowdown: a config schedule (period / duration / flow fraction) yields q_bd, which
leaves with saturated-water enthalpy in the (E1)/(E2) balances.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SteamLine", "BlowdownSchedule", "CRITICAL_PRESSURE_RATIO"]

# Saturated steam, isentropic exponent k ~= 1.135:  (2/(k+1))^(k/(k-1)) ~= 0.577
CRITICAL_PRESSURE_RATIO: float = 0.577


@dataclass(frozen=True)
class SteamLine:
    cv_si: float                 # valve flow coefficient [SI]
    p_downstream_pa: float       # header / downstream pressure [Pa]
    c_choked: float = 0.30       # choked-flow coefficient (sized at the critical point)

    @classmethod
    def from_rated(
        cls,
        *,
        q_rated_kg_s: float,
        p_drum_rated_pa: float,
        rho_s_rated: float,
        p_downstream_pa: float,
        opening_rated: float = 0.6,
    ) -> "SteamLine":
        """Size the valve cv from a rated subcritical operating point."""
        dp = max(p_drum_rated_pa - p_downstream_pa, 1.0)
        cv_si = q_rated_kg_s / (opening_rated * (dp * rho_s_rated) ** 0.5)
        # Match the choked-flow coefficient to the subcritical law at the critical ratio
        # so flow is continuous across the transition.
        p_crit = p_drum_rated_pa
        c_choked = (max(p_crit - p_crit * CRITICAL_PRESSURE_RATIO, 0.0) * rho_s_rated) ** 0.5 / p_crit
        return cls(cv_si=cv_si, p_downstream_pa=p_downstream_pa, c_choked=c_choked)

    def flow_kg_s(self, p_drum_pa: float, steam_demand: float, *, rho_s: float) -> float:
        """Steam mass flow [kg/s] for drum pressure ``p_drum_pa`` and demand (= opening).

        Subcritical when ``p_downstream/p_drum > 0.577``; choked otherwise. No
        backflow: ``p_drum <= p_downstream`` gives a zero subcritical pressure drop.
        """
        op = max(0.0, min(1.0, float(steam_demand)))
        p = float(p_drum_pa)
        if op <= 1e-6 or p <= 0.0:
            return 0.0
        ratio = self.p_downstream_pa / p
        if ratio > CRITICAL_PRESSURE_RATIO:
            dp = max(p - self.p_downstream_pa, 0.0)
            return float(self.cv_si * op * (dp * max(rho_s, 0.0)) ** 0.5)
        # choked: q ~ p, independent of downstream pressure
        return float(self.c_choked * self.cv_si * op * p)


@dataclass(frozen=True)
class BlowdownSchedule:
    """Periodic blowdown: every ``period_s`` open for ``duration_s`` at ``flow_kg_s``."""

    enabled: bool = False
    period_s: float = 3600.0
    duration_s: float = 60.0
    flow_kg_s: float = 0.0

    def flow_at(self, t_s: float) -> float:
        """Blowdown mass flow [kg/s] at simulation time ``t_s``."""
        if not self.enabled or self.flow_kg_s <= 0.0 or self.period_s <= 0.0:
            return 0.0
        phase = float(t_s) % self.period_s
        return float(self.flow_kg_s) if phase < self.duration_s else 0.0
