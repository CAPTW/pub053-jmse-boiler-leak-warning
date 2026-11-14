"""Drum-level DP instrumentation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..core.media import saturation_props


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _water_density_from_temp(temp_c: float) -> float:
    """Crude liquid-water density curve suitable for reference-leg compensation."""
    t = float(temp_c)
    density = 999.84 - 0.32 * max(0.0, t - 4.0) - 0.0015 * max(0.0, t - 4.0) ** 2
    return float(min(1000.0, max(860.0, density)))


def _clip(value: float, lower: float, upper: float) -> float:
    return float(max(lower, min(upper, float(value))))


@dataclass
class DrumLevelDPResult:
    level_dp_raw: float
    level_compensated: float
    level_radar: float | None
    quality: str
    diagnostics: dict[str, float | bool | str]


class DrumLevelDPInstrument:
    """Reference-leg DP drum-level indication with simple field faults."""

    def __init__(self, cfg: dict[str, Any] | None, rng: np.random.Generator) -> None:
        self.cfg = dict(cfg) if isinstance(cfg, dict) else {}
        self.rng = rng
        self._last_raw: float | None = None
        self._last_comp: float | None = None
        self._last_radar: float | None = None
        self._last_head: float | None = None
        self._radar_state: float | None = None

    def _coerce_cfg(self, override_cfg: dict[str, Any] | None) -> dict[str, Any]:
        out = dict(self.cfg)
        if isinstance(override_cfg, dict):
            out.update({str(k): v for k, v in override_cfg.items() if k is not None})
        return out

    def _radar_value(self, t: float, level_true: float, cfg: dict[str, Any]) -> float | None:
        radar_cfg = cfg.get("radar")
        if radar_cfg is None and not _as_bool(cfg.get("radar_enabled"), False):
            return None
        if not isinstance(radar_cfg, dict):
            radar_cfg = {}
        bias = _as_float(radar_cfg.get("bias", 0.0), 0.0)
        drift = _as_float(radar_cfg.get("drift_per_hour", 0.0), 0.0) * (float(t) / 3600.0)
        noise_std = max(0.0, _as_float(radar_cfg.get("noise_std", 0.002), 0.002))
        tau_s = max(0.0, _as_float(radar_cfg.get("tau_s", 0.0), 0.0))
        value = float(level_true + bias + drift)
        if noise_std > 0.0:
            value += float(self.rng.normal(0.0, noise_std))
        if tau_s > 1e-6:
            prev = value if self._radar_state is None else float(self._radar_state)
            alpha = 1.0 - float(np.exp(-1.0 / tau_s))
            value = prev + alpha * (value - prev)
            self._radar_state = float(value)
        else:
            self._radar_state = float(value)
        return float(value)

    def observe(
        self,
        t: float,
        *,
        truth: dict[str, float],
        base_level_obs: float,
        sampled: bool,
        override_cfg: dict[str, Any] | None = None,
    ) -> DrumLevelDPResult:
        cfg = self._coerce_cfg(override_cfg)
        if not sampled and self._last_raw is not None and self._last_comp is not None:
            return DrumLevelDPResult(
                level_dp_raw=float(self._last_raw),
                level_compensated=float(self._last_comp),
                level_radar=None if self._last_radar is None else float(self._last_radar),
                quality="stale",
                diagnostics={"sampled": False, "plugging": 0.0, "reverse_action": False},
            )

        level_true = float(truth.get("drum_level", base_level_obs))
        pressure_bar = float(truth.get("drum_pressure", cfg.get("nominal_pressure_bar", 10.0)))
        props = saturation_props(pressure_bar)
        process_density = float(props.get("rho_l", 950.0))
        nominal_pressure_bar = _as_float(cfg.get("nominal_pressure_bar", pressure_bar), pressure_bar)
        nominal_density = float(saturation_props(nominal_pressure_bar).get("rho_l", process_density))
        span = max(
            1.0,
            _as_float(cfg.get("reference_leg_height_m", 0.0), 0.0),
            _as_float(cfg.get("range_max", 0.0), 0.0),
            float(level_true) + 0.5,
        )
        ref_temp = _as_float(cfg.get("reference_leg_temp_C", 60.0), 60.0)
        ref_temp_shift = _as_float(cfg.get("reference_leg_temp_shift_C", 0.0), 0.0)
        ref_density_scale = _as_float(cfg.get("wet_leg_density_scale", 1.0), 1.0)
        nominal_ref_density = _water_density_from_temp(ref_temp)
        ref_density = _water_density_from_temp(ref_temp + ref_temp_shift) * ref_density_scale
        process_ratio = process_density / max(nominal_density, 1e-6)
        ref_ratio = ref_density / max(nominal_ref_density, 1e-6)
        indicated_bias = span * (ref_ratio - process_ratio)
        plugging = _clip(_as_float(cfg.get("impulse_line_plugging", 0.0), 0.0), 0.0, 1.0)
        if self._last_head is None:
            effective_head = indicated_bias
        else:
            effective_head = (1.0 - plugging) * indicated_bias + plugging * float(self._last_head)
        self._last_head = float(effective_head)

        raw_level = float(base_level_obs) + effective_head
        compensated_level = float(base_level_obs) + span * (ref_ratio - 1.0)
        calibration_bias = _as_float(cfg.get("bad_calibration_bias_m", 0.0), 0.0)
        raw_level += calibration_bias
        compensated_level += 0.5 * calibration_bias

        reverse_action = _as_bool(cfg.get("reverse_action"), False)
        if reverse_action:
            raw_level = span - raw_level
            compensated_level = span - compensated_level

        range_min = _as_float(cfg.get("range_min", 0.0), 0.0)
        range_max = max(range_min + 1.0, _as_float(cfg.get("range_max", span), span))
        raw_level = _clip(raw_level, range_min, range_max)
        compensated_level = _clip(compensated_level, range_min, range_max)

        freeze_after_s = cfg.get("freeze_after_s")
        quality = "good"
        if freeze_after_s is not None and float(t) >= _as_float(freeze_after_s, float("inf")) and self._last_raw is not None:
            raw_level = float(self._last_raw)
            compensated_level = float(self._last_comp if self._last_comp is not None else compensated_level)
            quality = "stale"
        elif plugging >= 0.85:
            quality = "bad"
        elif plugging >= 0.35 or abs(ref_temp_shift) >= 5.0 or abs(ref_density_scale - 1.0) >= 0.03:
            quality = "degraded"

        radar_level = self._radar_value(t, level_true, cfg)
        self._last_raw = float(raw_level)
        self._last_comp = float(compensated_level)
        self._last_radar = None if radar_level is None else float(radar_level)

        return DrumLevelDPResult(
            level_dp_raw=float(raw_level),
            level_compensated=float(compensated_level),
            level_radar=None if radar_level is None else float(radar_level),
            quality=str(quality),
            diagnostics={
                "sampled": True,
                "plugging": float(plugging),
                "reverse_action": bool(reverse_action),
                "reference_leg_temp_shift_C": float(ref_temp_shift),
                "wet_leg_density_scale": float(ref_density_scale),
                "reference_leg_density_kg_m3": float(ref_density),
                "process_density_kg_m3": float(process_density),
            },
        )
