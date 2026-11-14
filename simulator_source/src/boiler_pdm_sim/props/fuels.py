"""Marine fuel objects for the Phase A combustion path (§3.3).

AFR is **derived from elemental composition**, not carried as an independent
field: the design review found documented AFR values (14.6/14.0) disagreed with
the stated composition by 1.6–2.9 %, which is the root of the lambda<->O2
self-contradiction. Here ``O2_stoich`` and ``AFR_stoich`` are computed from
C/H/S mass fractions so the gas-side mole balance (§3.3) stays self-consistent.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Fuel", "MGO", "HFO", "FUELS", "get_fuel"]

# Mass of O2 needed to fully oxidise 1 kg of each element (stoichiometric):
#   C  + O2  -> CO2 :  32/12.011  = 2.664 kg O2 / kg C
#   H2 + 1/2 O2 -> H2O : 16/2.016 = 7.937 kg O2 / kg H
#   S  + O2  -> SO2 :  32/32.06   = 0.998 kg O2 / kg S
_O2_PER_C = 2.664
_O2_PER_H = 7.937
_O2_PER_S = 0.998
# Mass fraction of O2 in dry air.
_O2_MASS_FRAC_AIR = 0.232


@dataclass(frozen=True)
class Fuel:
    name: str
    LHV_MJ_kg: float
    C_mass: float
    H_mass: float
    S_mass: float

    @property
    def O2_stoich_kg_per_kg(self) -> float:
        """Stoichiometric O2 demand [kg O2 / kg fuel] from elemental composition."""
        return _O2_PER_C * self.C_mass + _O2_PER_H * self.H_mass + _O2_PER_S * self.S_mass

    @property
    def AFR_stoich(self) -> float:
        """Stoichiometric air-fuel ratio [kg air / kg fuel]. MGO ~= 14.4, HFO ~= 13.6."""
        return self.O2_stoich_kg_per_kg / _O2_MASS_FRAC_AIR


# Representative compositions (docs/phase_a_design.md §3.3).
MGO = Fuel(name="MGO", LHV_MJ_kg=42.7, C_mass=0.866, H_mass=0.128, S_mass=0.001)
HFO = Fuel(name="HFO", LHV_MJ_kg=40.5, C_mass=0.860, H_mass=0.105, S_mass=0.025)

FUELS: dict[str, Fuel] = {MGO.name: MGO, HFO.name: HFO}


def get_fuel(name: str) -> Fuel:
    """Look up a fuel by name (case-insensitive). Raises KeyError on unknown fuel."""
    key = str(name).strip().upper()
    if key not in FUELS:
        raise KeyError(f"unknown fuel {name!r}; known: {sorted(FUELS)}")
    return FUELS[key]
