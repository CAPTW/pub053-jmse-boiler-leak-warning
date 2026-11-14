"""Water/steam thermophysical helper functions.

This module defaults to IAPWS-IF97 saturation properties and falls back to a
lightweight correlation when :mod:`iapws` is unavailable. The fallback is
loud: importing without ``iapws`` emits a ``RuntimeWarning``, and setting the
environment variable ``BOILER_STRICT_PROPS=1`` turns it into a hard failure so
deployments cannot silently run on approximate properties.
"""

from __future__ import annotations

import os
import warnings
from functools import lru_cache
import numpy as np
from typing import Any

try:
    from iapws import IAPWS97  # type: ignore
    _IAPWS_IMPORT_ERROR: Exception | None = None
except Exception as _exc:  # pragma: no cover - optional dependency
    IAPWS97 = None  # type: ignore
    _IAPWS_IMPORT_ERROR = _exc

if IAPWS97 is None:  # pragma: no cover - depends on environment
    _strict = os.environ.get("BOILER_STRICT_PROPS", "").strip().lower()
    if _strict in {"1", "true", "yes", "on"}:
        raise ImportError(
            "iapws is unavailable and BOILER_STRICT_PROPS is set: refusing "
            "to run with approximate water/steam properties. Install iapws "
            "(pip install iapws) or unset BOILER_STRICT_PROPS. "
            f"Underlying import error: {_IAPWS_IMPORT_ERROR!r}"
        )
    warnings.warn(
        "iapws is unavailable; boiler_pdm_sim is falling back to a 9-point "
        "table + ideal-gas approximation for water/steam properties. Results "
        "are NOT IAPWS-IF97 accurate. Install iapws, or set "
        "BOILER_STRICT_PROPS=1 to make this a hard error. "
        f"Underlying import error: {_IAPWS_IMPORT_ERROR!r}",
        RuntimeWarning,
        stacklevel=2,
    )


_TSAT_BAR = np.array([0.2, 1.0, 3.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0], dtype=float)
_TSAT_C = np.array([60.1, 99.6, 133.5, 151.8, 179.9, 198.3, 213.0, 224.0, 233.9], dtype=float)

_MIN_P_BAR = 1e-3
_MAX_P_BAR = float(_TSAT_BAR[-1])
_PRESSURE_CACHE_DECIMALS = 3
_TSAT_SLOPES = np.diff(_TSAT_C) / np.diff(_TSAT_BAR)


def _clamp_pressure(P_bar: float) -> float:
    return float(max(_MIN_P_BAR, min(_MAX_P_BAR, float(P_bar))))


def _pressure_cache_key(P_bar: float) -> float:
    return round(_clamp_pressure(P_bar), _PRESSURE_CACHE_DECIMALS)


def _to_mpa(P_bar: float) -> float:
    return _clamp_pressure(P_bar) / 10.0


def _tsat_value_and_slope(P_bar: float) -> tuple[float, float]:
    p = _clamp_pressure(P_bar)
    idx = int(np.searchsorted(_TSAT_BAR, p, side="right") - 1)
    idx = max(0, min(idx, len(_TSAT_SLOPES) - 1))
    p0 = float(_TSAT_BAR[idx])
    t0 = float(_TSAT_C[idx])
    slope = float(_TSAT_SLOPES[idx])
    return float(t0 + (p - p0) * slope), slope


@lru_cache(maxsize=2048)
def _fallback_saturation_cached(P_bar_key: float) -> tuple[float, float, float, float, float, float]:
    p = float(P_bar_key)
    Tsat, _ = _tsat_value_and_slope(p)
    rho_l = float(max(100.0, 960.0 - 0.2 * max(Tsat - 100.0, 0.0)))
    P_pa = p * 1e5
    rho_v = float(P_pa * 0.018015 / (8.314462618 * (Tsat + 273.15)))
    rho_v = float(max(rho_v, 0.02))

    h_l = float(419_000.0 + max(0.0, Tsat - 100.0) * 4_200.0)
    h_fg = float(max(500_000.0, 2_500_000.0 - 4_300.0 * Tsat))
    h_v = h_l + h_fg

    return Tsat, rho_l, rho_v, h_l, h_v, h_fg


def _fallback_saturation(P_bar: float) -> dict[str, float]:
    Tsat, rho_l, rho_v, h_l, h_v, h_fg = _fallback_saturation_cached(_pressure_cache_key(P_bar))
    return {
        "Tsat_C": Tsat,
        "rho_l": rho_l,
        "rho_v": rho_v,
        "h_l": h_l,
        "h_v": h_v,
        "h_fg": h_fg,
    }


def saturation_temperature_C(P_bar: float) -> float:
    p = _clamp_pressure(P_bar)
    if IAPWS97 is None:
        Tsat, _ = _tsat_value_and_slope(p)
        return Tsat
    return float(IAPWS97(P=_to_mpa(p), x=1).T - 273.15)


def sat_liquid_enthalpy_J_kg(P_bar: float) -> float:
    p = _clamp_pressure(P_bar)
    if IAPWS97 is None:
        return _fallback_saturation(p)["h_l"]
    return float(IAPWS97(P=_to_mpa(p), x=0).hL * 1000.0)


def sat_enthalpy_J_kg(P_bar: float, phase: str = "h_l") -> float:
    props = saturation_props(P_bar)
    if phase == "h_v":
        return float(props["h_v"])
    return float(props["h_l"])


def saturation_props(P_bar: float) -> dict[str, float]:
    p = _clamp_pressure(P_bar)
    if IAPWS97 is None:
        return _fallback_saturation(p)

    state_l = IAPWS97(P=_to_mpa(p), x=0)
    state_v = IAPWS97(P=_to_mpa(p), x=1)
    h_l = float(state_l.h * 1000.0)
    h_v = float(state_v.h * 1000.0)
    h_fg = max(0.0, h_v - h_l)

    return {
        "Tsat_C": float(state_l.T - 273.15),
        "rho_l": float(state_l.rho),
        "rho_v": float(state_v.rho),
        "h_l": h_l,
        "h_v": h_v,
        "h_fg": h_fg,
    }


def dhdP_approx(P_bar: float, phase: str = "h_l", *, eps: float = 1e-4) -> float:
    p = max(_clamp_pressure(P_bar), eps)
    if IAPWS97 is None:
        Tsat, dTsat_dP = _tsat_value_and_slope(p)
        dh_l = 4200.0 * dTsat_dP if Tsat > 100.0 else 0.0
        if phase == "h_l":
            return float(dh_l)
        dh_fg = -4300.0 * dTsat_dP if (2_500_000.0 - 4_300.0 * Tsat) > 500_000.0 else 0.0
        return float(dh_l + dh_fg)
    h = sat_enthalpy_J_kg(p, phase=phase)
    hp = sat_enthalpy_J_kg(p + eps, phase=phase)
    return float((hp - h) / eps)


def steam_properties(P_bar: float, quality: float = 1.0) -> dict[str, Any]:
    """Return a compact saturation state for a given pressure and quality."""
    p = _clamp_pressure(P_bar)
    q = float(np.clip(quality, 0.0, 1.0))
    if IAPWS97 is None:
        props = _fallback_saturation(p)
        return {
            "T_C": props["Tsat_C"],
            "h_J_kg": props["h_l"] + q * props["h_fg"],
            "rho": props["rho_l"] * (1.0 - q) + props["rho_v"] * q,
        }
    sat_state = IAPWS97(P=_to_mpa(p), x=q)
    return {
        "T_C": float(sat_state.T - 273.15),
        "h_J_kg": float(sat_state.h * 1000.0),
        "rho": float(sat_state.rho),
    }
