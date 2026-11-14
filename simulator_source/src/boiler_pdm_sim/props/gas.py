"""Flue-gas sensible-enthalpy primitive for the Phase A combustion path (§3.3).

The furnace balance in §3.3 is **enthalpy based** (``cp*dT`` is banned because a
temperature-dependent cp breaks energy closure and the §7.1 gate catches it).
This module supplies ``h_gas(T)`` for a CO2/H2O/N2/O2/SO2 mixture as a
mole-weighted **sensible enthalpy relative to 298.15 K** [J/mol]. The range guard
accepts 250–2500 K (≈ −23 … 2227 degC); the per-species cp(T) fits are anchored on
tabulated points spanning 300–2300 K, which covers the furnace adiabatic-flame band
(~2220 K for MGO at λ=1.15) so the quartic does not turn over inside the operating range.

Grounding: rather than embed memorised high-temperature NASA polynomial
coefficients (hard to sanity-check), per-species molar cp is built from tabulated
reference points (standard thermodynamic tables, J/mol.K) fitted with a quartic and
integrated analytically. ``tests/test_props_fuels_gas.py`` re-checks that the fit
reproduces those reference points, so the constants are validated rather than
asserted. Absolute accuracy is "primitive grade" — the precise gas-side energy
closure is formalised and gated in WP A4 (§7.1 gas-side residual).
"""

from __future__ import annotations

import numpy as np

__all__ = ["SPECIES", "molar_cp", "molar_enthalpy", "h_gas", "T_REF_K"]

T_REF_K: float = 298.15
_T_MIN_K: float = 250.0
_T_MAX_K: float = 2500.0

# Reference molar cp [J/mol.K] at [300, 500, 1000, 1500, 2000, 2300] K from
# standard thermodynamic tables (primitive grade; A4 owns precise validation).
# The 2300 K knot keeps the quartic fit rising through the furnace flame band
# (~2220 K) instead of turning over above the previous 2000 K top knot.
_CP_T_K = np.array([300.0, 500.0, 1000.0, 1500.0, 2000.0, 2300.0])
_CP_REF: dict[str, np.ndarray] = {
    "N2": np.array([29.1, 29.6, 32.7, 34.8, 35.9, 36.4]),
    "O2": np.array([29.4, 31.1, 34.9, 36.6, 37.8, 38.5]),
    "CO2": np.array([37.2, 44.6, 54.3, 58.4, 60.4, 61.8]),
    "H2O": np.array([33.6, 35.2, 41.2, 46.0, 51.1, 53.5]),
    "SO2": np.array([39.9, 46.6, 54.3, 56.7, 57.8, 58.8]),
}
SPECIES: tuple[str, ...] = tuple(_CP_REF)

# Fit each species cp(T) with a quartic in T (6 reference points) so the fit
# reproduces every knot tightly and stays monotone through the flame band.
_CP_FIT: dict[str, np.ndarray] = {
    sp: np.polyfit(_CP_T_K, cp, 4) for sp, cp in _CP_REF.items()
}


def _check_T(T_K: float) -> float:
    T = float(T_K)
    if not (_T_MIN_K <= T <= _T_MAX_K):
        raise ValueError(f"temperature {T} K outside gas-enthalpy range [{_T_MIN_K}, {_T_MAX_K}]")
    return T


def molar_cp(species: str, T_K: float) -> float:
    """Molar heat capacity cp [J/mol.K] for one species at ``T_K``."""
    T = _check_T(T_K)
    if species not in _CP_FIT:
        raise KeyError(f"unknown species {species!r}; known: {SPECIES}")
    return float(np.polyval(_CP_FIT[species], T))


def molar_enthalpy(species: str, T_K: float) -> float:
    """Sensible molar enthalpy h(T) - h(298.15K) [J/mol] for one species.

    Analytic integral of the quartic cp(T) fit from T_REF_K to T_K.
    """
    T = _check_T(T_K)
    coeffs = _CP_FIT[species]  # cp = c3 T^3 + c2 T^2 + c1 T + c0
    # Antiderivative of cp: c3/4 T^4 + c2/3 T^3 + c1/2 T^2 + c0 T
    antideriv = np.polyint(coeffs)
    return float(np.polyval(antideriv, T) - np.polyval(antideriv, T_REF_K))


def h_gas(T_K: float, mole_fracs: dict[str, float]) -> float:
    """Mole-weighted sensible enthalpy [J/mol] of a flue-gas mixture at ``T_K``.

    ``mole_fracs`` maps species name -> mole fraction (need not sum to exactly 1;
    it is used as supplied). Unknown species raise KeyError.
    """
    total = 0.0
    for sp, x in mole_fracs.items():
        if sp not in _CP_FIT:
            raise KeyError(f"unknown species {sp!r}; known: {SPECIES}")
        total += float(x) * molar_enthalpy(sp, T_K)
    return total
