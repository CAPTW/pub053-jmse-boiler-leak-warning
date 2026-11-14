"""Phase A property layer (§3.2/§3.3).

IF97 saturation properties + derivatives (spline-tabulated, no fallback), marine
fuel objects, and a flue-gas enthalpy primitive. ``iapws`` is a hard dependency:
importing this package fails with ImportError if iapws is unavailable, by design
(the approximate fallback lives only in legacy ``core/media.py`` for the grey-box).
"""

from __future__ import annotations

from .if97 import P_MAX_BAR, P_MIN_BAR, PropsBundle, in_range, saturation_state, tsat_C
from .fuels import FUELS, HFO, MGO, Fuel, get_fuel
from .gas import SPECIES, T_REF_K, h_gas, molar_cp, molar_enthalpy

__all__ = [
    # if97
    "P_MIN_BAR",
    "P_MAX_BAR",
    "PropsBundle",
    "saturation_state",
    "tsat_C",
    "in_range",
    # fuels
    "Fuel",
    "MGO",
    "HFO",
    "FUELS",
    "get_fuel",
    # gas
    "SPECIES",
    "T_REF_K",
    "molar_cp",
    "molar_enthalpy",
    "h_gas",
]
