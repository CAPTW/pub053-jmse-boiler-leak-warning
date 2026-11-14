"""Horizontal-cylinder drum geometry for the Phase A ab4 core (§3.4).

Nonlinear level<->volume for a horizontal cylindrical drum:

    V(l) = L * [ r^2 * acos((r - l)/r) - (r - l) * sqrt(2 r l - l^2) ]

with l the liquid height in [0, 2r]. The inverse l = V^{-1}(V_target) is found by
Newton with a [l_min, l_max] bracket and a bisection fallback, because
dV/dl -> 0 at l -> 0 and l -> 2r (the design's explicit guard).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["DrumGeometry"]


@dataclass(frozen=True)
class DrumGeometry:
    radius_m: float
    length_m: float

    @property
    def diameter_m(self) -> float:
        return 2.0 * self.radius_m

    @property
    def total_volume_m3(self) -> float:
        return math.pi * self.radius_m**2 * self.length_m

    def volume_from_level(self, level_m: float) -> float:
        """Liquid volume [m^3] for liquid height ``level_m`` in [0, 2r] (clamped at ends)."""
        r = self.radius_m
        l = min(max(float(level_m), 0.0), 2.0 * r)
        rl = r - l
        # numerical floor for the chord term near the extremes
        chord_arg = max(0.0, 2.0 * r * l - l * l)
        area = r * r * math.acos(max(-1.0, min(1.0, rl / r))) - rl * math.sqrt(chord_arg)
        return self.length_m * area

    def dvolume_dlevel(self, level_m: float) -> float:
        """dV/dl [m^2] = L * chord-width at level l = L * 2*sqrt(2 r l - l^2)."""
        r = self.radius_m
        l = min(max(float(level_m), 0.0), 2.0 * r)
        chord_arg = max(0.0, 2.0 * r * l - l * l)
        return self.length_m * 2.0 * math.sqrt(chord_arg)

    def level_from_volume(
        self,
        volume_m3: float,
        level_guess_m: float | None = None,
        *,
        tol_m3: float = 1e-9,
        max_iter: int = 50,
    ) -> float:
        """Invert V(l) for liquid height [m] via Newton + bisection fallback.

        ``volume_m3`` is clamped to [0, total_volume]; the result is in [0, 2r].
        """
        r = self.radius_m
        v_total = self.total_volume_m3
        v_target = min(max(float(volume_m3), 0.0), v_total)

        lo, hi = 0.0, 2.0 * r
        # Bracket endpoints are exact (V(0)=0, V(2r)=v_total).
        if v_target <= 0.0:
            return 0.0
        if v_target >= v_total:
            return 2.0 * r

        l = level_guess_m if level_guess_m is not None else r
        l = min(max(float(l), lo), hi)

        for _ in range(max_iter):
            f = self.volume_from_level(l) - v_target
            if f > 0.0:
                hi = l
            else:
                lo = l
            if abs(f) <= tol_m3:
                return l
            dfdl = self.dvolume_dlevel(l)
            if dfdl > 1e-12:
                step = f / dfdl
                l_newton = l - step
                # Accept Newton only if it stays inside the bracket; else bisect.
                if lo < l_newton < hi:
                    l = l_newton
                    continue
            l = 0.5 * (lo + hi)
        return l
