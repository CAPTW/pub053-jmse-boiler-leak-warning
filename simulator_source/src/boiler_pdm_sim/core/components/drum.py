"""Drum geometry and geometric conversion helpers."""

from __future__ import annotations

import math
import numpy as np


class DrumGeometry:
    def __init__(self, radius_m: float, length_m: float) -> None:
        self.radius_m = float(radius_m)
        self.length_m = float(length_m)
        self._area_m2 = math.pi * self.radius_m ** 2
        self._volume_m3 = self._area_m2 * self.length_m

    @property
    def area_m2(self) -> float:
        return self._area_m2

    @property
    def volume_m3(self) -> float:
        return self._volume_m3

    def level_from_volume(self, V_l_m3: float) -> float:
        return float(max(0.0, min(self.length_m, float(V_l_m3) / self._area_m2)))

    def level_from_mass(self, M_l_kg: float, rho_l: float) -> float:
        return float(max(0.0, min(self.length_m, float(M_l_kg) / max(float(rho_l), 1e-6) / self._area_m2)))

    def level_from_state(
        self,
        M_l_kg: float,
        rho_l: float,
        shrink_state: float = 0.0,
        swell_gain: float = 0.03,
    ) -> float:
        """Liquid level with a small shrink/swell correction tied to dynamics.

        The model keeps the mass-balance-consistent base level from liquid
        mass, then applies a bounded correction from the swell state.
        """
        base_level = float(max(0.0, min(self.length_m, float(M_l_kg) / max(float(rho_l), 1e-6) / self._area_m2)))
        clipped_gain = max(-0.08, min(0.08, float(swell_gain)))
        swell = clipped_gain * self.length_m * math.tanh(float(shrink_state))
        return float(max(0.0, min(self.length_m, base_level + swell)))
