"""Validation for the Phase A fuels + flue-gas enthalpy primitives (§3.3).

Fuels: AFR derived from composition (the self-consistency the review required).
Gas: the cubic cp(T) fit must reproduce its tabulated reference points and produce
a monotonically increasing sensible enthalpy. Precise gas-side closure is gated
in WP A4 (§7.1); this only pins the primitive.
"""

from __future__ import annotations

import pytest

from boiler_pdm_sim.props import fuels, gas


def test_mgo_afr_from_composition():
    mgo = fuels.get_fuel("mgo")
    # O2_stoich = 2.664*0.866 + 7.937*0.128 + 0.998*0.001 ~= 3.323 kg/kg
    assert mgo.O2_stoich_kg_per_kg == pytest.approx(3.323, abs=0.02)
    # AFR = O2_stoich / 0.232 ~= 14.3..14.5 (design target ~14.4)
    assert 14.0 < mgo.AFR_stoich < 14.8


def test_hfo_afr_lower_than_mgo():
    assert fuels.HFO.AFR_stoich < fuels.MGO.AFR_stoich  # ~13.6 < ~14.4
    assert 13.0 < fuels.HFO.AFR_stoich < 14.0


def test_unknown_fuel_raises():
    with pytest.raises(KeyError):
        fuels.get_fuel("LNG")


@pytest.mark.parametrize("species", gas.SPECIES)
def test_cp_fit_reproduces_reference_points(species):
    """The cubic fit reproduces the embedded reference cp points within 1 %."""
    ref_T = gas._CP_T_K
    ref_cp = gas._CP_REF[species]
    for T, cp_ref in zip(ref_T, ref_cp):
        cp_fit = gas.molar_cp(species, float(T))
        assert abs(cp_fit - cp_ref) / cp_ref < 1e-2, f"{species} cp at {T}K off: {cp_fit} vs {cp_ref}"


def test_molar_enthalpy_zero_at_reference_and_monotonic():
    for sp in gas.SPECIES:
        assert gas.molar_enthalpy(sp, gas.T_REF_K) == pytest.approx(0.0, abs=1e-6)
        h500 = gas.molar_enthalpy(sp, 500.0)
        h1500 = gas.molar_enthalpy(sp, 1500.0)
        assert 0.0 < h500 < h1500  # sensible enthalpy increases with T


def test_h_gas_mixture_and_unknown_species():
    # Roughly stoichiometric-lean flue gas mole fractions (illustrative).
    mix = {"N2": 0.74, "H2O": 0.10, "CO2": 0.10, "O2": 0.06}
    h = gas.h_gas(1200.0, mix)
    # Mixture enthalpy is a positive mole-weighted blend of the components.
    comps = [gas.molar_enthalpy(sp, 1200.0) for sp in mix]
    assert min(comps) * 0.9 < h < max(comps) * 1.1
    assert h > 0.0
    with pytest.raises(KeyError):
        gas.h_gas(1200.0, {"CH4": 1.0})


def test_gas_out_of_range_raises():
    with pytest.raises(ValueError):
        gas.molar_cp("N2", 100.0)
    with pytest.raises(ValueError):
        gas.molar_enthalpy("N2", 3000.0)
