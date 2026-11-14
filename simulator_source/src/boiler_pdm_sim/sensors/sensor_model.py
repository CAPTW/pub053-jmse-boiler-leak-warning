"""Observation model with multirate sampling, lag, noise, and quality flags."""

from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np

from .drum_level_dp import DrumLevelDPInstrument
from .noise import apply_gaussian


def _coerce_cfg(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if k is not None}


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


class SensorModel:
    def __init__(self, sensor_cfg: dict[str, dict[str, float]], rng: np.random.Generator) -> None:
        self.cfg = {str(k): _coerce_cfg(v) for k, v in sensor_cfg.items()}
        self.rng = rng
        self._drum_level_dp = DrumLevelDPInstrument(self.cfg.get("drum_level"), rng)
        self._base_terms: dict[str, dict[str, Any]] = {}
        self._block_remaining: dict[str, int] = {}
        self._held_values: dict[str, float] = {}
        self._last_sample_time: dict[str, float] = {}
        self._filter_state: dict[str, float] = {}
        self._dead_time_queue: dict[str, deque[tuple[float, float]]] = {}
        self._last_quality: dict[str, str] = {}

        for key, raw in self.cfg.items():
            self._base_terms[key] = {
                "bias": _as_float(raw.get("bias", 0.0), 0.0),
                "drift_per_hour": _as_float(raw.get("drift_per_hour", 0.0), 0.0),
                "noise_std": _as_float(raw.get("noise_std", 0.0), 0.0),
                "dropout_p": _as_float(raw.get("dropout_p", 0.0), 0.0),
                "spike_p": _as_float(raw.get("spike_p", 0.0), 0.0),
                "spike_std": _as_float(raw.get("spike_std", 0.0), 0.0),
                "block_dropout_p": _as_float(raw.get("block_dropout_p", 0.0), 0.0),
                "block_dropout_len_min": int(raw.get("block_dropout_len_min", 3)),
                "block_dropout_len_max": int(raw.get("block_dropout_len_max", 12)),
                "sample_period_s": max(0.0, _as_float(raw.get("sample_period_s", 0.0), 0.0)),
                "tau_s": max(0.0, _as_float(raw.get("tau_s", 0.0), 0.0)),
                "dead_time_s": max(0.0, _as_float(raw.get("dead_time_s", 0.0), 0.0)),
                "range_min": raw.get("range_min"),
                "range_max": raw.get("range_max"),
                "quality_flag_logic": str(raw.get("quality_flag_logic", "good")).strip().lower() or "good",
            }
            self._dead_time_queue[key] = deque()

    def last_quality_flags(self) -> dict[str, str]:
        return dict(self._last_quality)

    @staticmethod
    def _block_len(rng: np.random.Generator, cfg: dict[str, Any]) -> int:
        min_len = max(1, int(cfg.get("block_dropout_len_min", 3)))
        max_len = max(min_len, int(cfg.get("block_dropout_len_max", 12)))
        if max_len <= min_len:
            return min_len
        return int(rng.integers(min_len, max_len + 1))

    def _merge_terms(self, channel: str, override_cfg: dict[str, Any] | None) -> dict[str, Any]:
        base = dict(self._base_terms.get(channel, {}))
        if override_cfg:
            base.update(_coerce_cfg(override_cfg))
        return base

    def _filter_and_delay(self, channel: str, t: float, raw_value: float, terms: dict[str, Any]) -> float:
        tau = max(0.0, _as_float(terms.get("tau_s", 0.0), 0.0))
        filtered = float(raw_value)
        if tau > 1e-6:
            prev = self._filter_state.get(channel, filtered)
            sample_dt = max(1e-6, _as_float(terms.get("sample_period_s", 0.0), 0.0) or 1e-6)
            alpha = 1.0 - float(np.exp(-sample_dt / tau))
            filtered = float(prev + alpha * (filtered - prev))
            self._filter_state[channel] = filtered
        else:
            self._filter_state[channel] = filtered

        dead_time = max(0.0, _as_float(terms.get("dead_time_s", 0.0), 0.0))
        if dead_time <= 1e-9:
            return filtered

        queue = self._dead_time_queue.setdefault(channel, deque())
        queue.append((float(t) + dead_time, filtered))
        delivered = self._held_values.get(channel, filtered)
        while queue and queue[0][0] <= float(t) + 1e-9:
            _, delivered = queue.popleft()
        return float(delivered)

    def observe(self, t: float, y_truth: dict[str, float], params: dict[str, Any] | None = None) -> dict[str, float]:
        sensor_fault_cfg: dict[str, Any] | None = None
        if isinstance(params, dict):
            candidate = params.get("sensors")
            if isinstance(candidate, dict):
                sensor_fault_cfg = candidate

        obs: dict[str, float] = {}
        sample_flags: dict[str, bool] = {}
        t_h = t / 3600.0
        for ch, v in y_truth.items():
            override_cfg: dict[str, Any] | None = None
            if sensor_fault_cfg is not None and isinstance(sensor_fault_cfg.get(ch), dict):
                override_cfg = sensor_fault_cfg.get(ch)
            terms = self._merge_terms(ch, override_cfg)

            sample_period = max(0.0, _as_float(terms.get("sample_period_s", 0.0), 0.0))
            last_sample_time = self._last_sample_time.get(ch)
            if sample_period > 0.0 and last_sample_time is not None and (t - last_sample_time) < sample_period - 1e-9:
                held = self._held_values.get(ch, float(v))
                obs[ch] = float(held)
                self._last_quality[ch] = self._last_quality.get(ch, "stale")
                sample_flags[ch] = False
                continue

            self._last_sample_time[ch] = float(t)
            sample_flags[ch] = True

            remaining = self._block_remaining.get(ch, 0)
            if remaining > 0:
                self._block_remaining[ch] = remaining - 1
                obs[ch] = float("nan")
                self._last_quality[ch] = "bad"
                continue

            if _as_float(terms.get("block_dropout_p", 0.0), 0.0) > 0.0 and self.rng.random() < _as_float(terms.get("block_dropout_p", 0.0), 0.0):
                block_len = self._block_len(self.rng, terms)
                self._block_remaining[ch] = max(0, block_len - 1)
                obs[ch] = float("nan")
                self._last_quality[ch] = "bad"
                continue

            if _as_float(terms.get("dropout_p", 0.0), 0.0) > 0.0 and self.rng.random() < _as_float(terms.get("dropout_p", 0.0), 0.0):
                obs[ch] = float("nan")
                self._last_quality[ch] = "bad"
                continue

            val = float(v)
            val += _as_float(terms.get("bias", 0.0), 0.0)
            val += _as_float(terms.get("drift_per_hour", 0.0), 0.0) * t_h
            noise_std = max(0.0, _as_float(terms.get("noise_std", 0.0), 0.0))
            if noise_std > 0.0:
                val = apply_gaussian(val, noise_std, self.rng)
            if _as_float(terms.get("spike_p", 0.0), 0.0) > 0.0 and self.rng.random() < _as_float(terms.get("spike_p", 0.0), 0.0):
                val += float(self.rng.normal(0.0, _as_float(terms.get("spike_std", 0.0), 0.0)))

            delivered = self._filter_and_delay(ch, t, val, terms)
            q_logic = str(terms.get("quality_flag_logic", "good")).strip().lower()
            q_state = "good"
            range_min = terms.get("range_min")
            range_max = terms.get("range_max")
            if range_min is not None and delivered < float(range_min):
                q_state = "bad" if q_logic != "ignore_range" else q_state
                delivered = max(float(range_min), delivered)
            if range_max is not None and delivered > float(range_max):
                q_state = "bad" if q_logic != "ignore_range" else q_state
                delivered = min(float(range_max), delivered)

            obs[ch] = float(delivered)
            self._held_values[ch] = float(delivered)
            self._last_quality[ch] = q_state

        if "drum_level" in y_truth:
            level_override = None
            if sensor_fault_cfg is not None and isinstance(sensor_fault_cfg.get("drum_level"), dict):
                level_override = sensor_fault_cfg.get("drum_level")
            dp_enabled = isinstance(self.cfg.get("drum_level"), dict) and any(
                key in self.cfg.get("drum_level", {})
                for key in ("reference_leg_height_m", "nominal_pressure_bar", "radar", "radar_enabled")
            )
            dp_enabled = dp_enabled or (isinstance(level_override, dict) and any(
                key in level_override
                for key in ("reference_leg_temp_shift_C", "wet_leg_density_scale", "impulse_line_plugging", "reverse_action", "freeze_after_s")
            ))
            if dp_enabled:
                dp = self._drum_level_dp.observe(
                    t,
                    truth=y_truth,
                    base_level_obs=float(obs.get("drum_level", y_truth["drum_level"])),
                    sampled=bool(sample_flags.get("drum_level", True)),
                    override_cfg=level_override,
                )
                obs["drum_level_dp_raw"] = float(dp.level_dp_raw)
                obs["drum_level_compensated"] = float(dp.level_compensated)
                obs["drum_level"] = float(dp.level_compensated)
                self._held_values["drum_level_dp_raw"] = float(dp.level_dp_raw)
                self._held_values["drum_level_compensated"] = float(dp.level_compensated)
                self._held_values["drum_level"] = float(dp.level_compensated)
                self._last_quality["drum_level"] = str(dp.quality)
                self._last_quality["drum_level_dp_raw"] = str(dp.quality)
                self._last_quality["drum_level_compensated"] = str(dp.quality)
                if dp.level_radar is not None:
                    obs["drum_level_radar"] = float(dp.level_radar)
                    self._held_values["drum_level_radar"] = float(dp.level_radar)
                    self._last_quality["drum_level_radar"] = "good" if str(dp.quality) == "good" else str(dp.quality)

        return obs
