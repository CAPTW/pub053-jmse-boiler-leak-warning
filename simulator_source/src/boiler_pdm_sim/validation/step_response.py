"""Step response checks."""

from __future__ import annotations

import re
import numpy as np

_STEAM_STEP_EVENT = re.compile(r"^steam_step_(?P<direction>up|down)_t=(?P<time>-?\d+(?:\.\d+)?)$")


def _as_finite_array(v: list[float]) -> np.ndarray:
    arr = np.asarray([float(x) for x in v], dtype=float)
    return arr


def _as_event_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, tuple):
        return [str(v) for v in value]
    return []


def _iter_event_values(value: object) -> list[str]:
    events: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, (list, tuple)):
                events.extend(str(v) for v in item)
            else:
                events.append(str(item))
    return events


def _extract_step_events_from_log(event_log: object, dt: float) -> list[tuple[int, str, float]]:
    if dt <= 0.0:
        dt = 0.5
    events: list[tuple[int, str, float]] = []
    for event in _iter_event_values(event_log):
        m = _STEAM_STEP_EVENT.fullmatch(str(event).strip())
        if m is None:
            continue
        try:
            direction = m.group("direction")
            t = float(m.group("time"))
            idx = max(0, int(round(t / dt)))
            events.append((idx, direction, t))
        except Exception:
            continue
    return events


def _detect_step_events_from_signal(
    cmd: np.ndarray,
    dt: float,
    *,
    window_s: float = 240.0,
    min_delta: float = 0.05,
) -> list[tuple[int, str, float]]:
    if cmd.size < 3 or dt <= 0.0:
        return []
    window = max(1, int(round(window_s / dt)))
    events: list[tuple[int, str, float]] = []
    last_idx = -10_000

    for i in range(window, cmd.size):
        delta = cmd[i] - cmd[i - window]
        if abs(delta) < min_delta:
            continue
        if i - last_idx < window:
            continue
        direction = "up" if delta > 0 else "down"
        t = i * dt
        events.append((i, direction, t))
        last_idx = i
    return events


def _check_single_event(
    arr: np.ndarray,
    idx: int,
    *,
    direction: str,
    dt: float,
    window_s: float,
    min_excursion: float,
    min_recover: float,
    recovery_ratio: float,
) -> tuple[bool, float, float]:
    if arr.size < 12:
        return False, 0.0, 0.0
    idx = max(0, int(idx))
    if idx >= arr.size - 2:
        return False, 0.0, 0.0

    base_start = max(0, idx - max(1, int(20.0 / max(dt, 1e-6))))
    base = arr[base_start:idx + 1]
    if base.size == 0 or not np.isfinite(base).any():
        return False, 0.0, 0.0
    baseline = float(np.nanmedian(base))

    segment_end = min(arr.size, idx + max(3, int(window_s / max(dt, 1e-6))))
    segment = arr[idx:segment_end]
    if segment.size < 3:
        return False, 0.0, 0.0
    finite_mask = np.isfinite(segment)
    if not finite_mask.any():
        return False, 0.0, 0.0
    seg = np.asarray(segment, dtype=float)
    if direction == "up":
        local = int(np.nanargmin(seg))
        excursion = baseline - float(seg[local])
        if excursion < min_excursion:
            return False, excursion, 0.0
        recover = float(np.nanmax(seg[local:]) - seg[local])
        ok = recover >= max(min_recover, recovery_ratio * excursion)
        return bool(ok), excursion, recover

    local = int(np.nanargmax(seg))
    excursion = float(seg[local] - baseline)
    if excursion < min_excursion:
        return False, excursion, 0.0
    recover = float(seg[local] - np.nanmin(seg[local:]))
    ok = recover >= max(min_recover, recovery_ratio * excursion)
    return bool(ok), excursion, recover


def check_shrink_swell_event_consistency(
    level: list[float],
    steam_cmd: list[float],
    *,
    dt: float,
    event_log: object | None = None,
    event_window_s: float = 420.0,
    min_excursion: float = 0.003,
    min_recover: float = 0.0025,
    recovery_ratio: float = 0.35,
    implicit_window_s: float = 240.0,
    implicit_delta: float = 0.06,
) -> dict[str, float | int | bool | list[dict[str, object]]]:
    level_arr = _as_finite_array(level)
    if level_arr.size != len(steam_cmd):
        return {
            "passed": False,
            "events_total": 0,
            "events_matched": 0,
            "coverage": 0.0,
            "details": [],
        }
    if dt <= 0.0 or not np.isfinite(dt):
        return {
            "passed": False,
            "events_total": 0,
            "events_matched": 0,
            "coverage": 0.0,
            "details": [],
        }

    steam_arr = np.asarray([float(v) for v in steam_cmd], dtype=float)
    step_events = _extract_step_events_from_log(event_log, dt)
    if not step_events:
        step_events = _detect_step_events_from_signal(
            steam_arr,
            dt,
            window_s=implicit_window_s,
            min_delta=implicit_delta,
        )

    if not step_events:
        return {
            "passed": False,
            "events_total": 0,
            "events_matched": 0,
            "coverage": 0.0,
            "details": [],
        }

    details: list[dict[str, object]] = []
    matched = 0
    for idx, direction, t in step_events:
        ok, excursion, recovery = _check_single_event(
            level_arr,
            idx=idx,
            direction=direction,
            dt=dt,
            window_s=event_window_s,
            min_excursion=min_excursion,
            min_recover=min_recover,
            recovery_ratio=recovery_ratio,
        )
        if ok:
            matched += 1
        details.append(
            {
                "index": int(idx),
                "time_s": float(t),
                "direction": direction,
                "matched": bool(ok),
                "excursion": float(excursion),
                "recovery": float(recovery),
            }
        )

    coverage = float(matched / len(step_events))
    return {
        "passed": bool(coverage >= 0.7 and matched >= 1),
        "events_total": int(len(step_events)),
        "events_matched": int(matched),
        "coverage": coverage,
        "details": details,
    }


def has_shrink_swell(
    level: list[float],
    *,
    smooth_window: int = 7,
    min_pre_drop: float = 0.004,
    min_recover: float = 0.0075,
    trough_early_frac: float = 0.65,
) -> bool:
    arr = np.asarray([float(v) for v in level], dtype=float)
    if arr.size < 30:
        return False

    valid = np.isfinite(arr)
    if valid.sum() < 0.8 * arr.size:
        return False
    if not np.all(valid):
        arr = np.interp(np.arange(arr.size), np.arange(arr.size)[valid], arr[valid])

    # light smoothing to remove sensor noise
    wlen = max(3, int(smooth_window))
    if wlen % 2 == 0:
        wlen += 1
    if arr.size >= wlen:
        w = np.ones(wlen, dtype=float) / float(wlen)
        arr = np.convolve(arr, w, mode="valid")
    if arr.size < 24:
        return False

    baseline_idx = max(5, int(0.12 * arr.size))
    base = float(np.nanpercentile(arr[:baseline_idx], 20.0))
    if not np.isfinite(base):
        return False
    arr = arr - base
    if np.nanmax(np.abs(arr)) <= 1e-9:
        return False

    trough_window = max(6, int(trough_early_frac * arr.size))
    if trough_window <= 10:
        return False

    search_start = max(6, int(0.08 * arr.size))
    if search_start >= trough_window:
        return False

    if trough_window >= arr.size - 5:
        return False

    candidates: list[tuple[int, float, float, float]] = []
    for i in range(search_start, trough_window):
        if arr[i - 1] >= arr[i] and arr[i] <= arr[i + 1]:
            pre_slice = arr[max(search_start, i - 12) : i + 1]
            peak_slice = arr[i + 1 : i + 241]
            if peak_slice.size == 0:
                continue

            pre_drop = float(np.max(pre_slice) - arr[i])
            post_recover = float(np.max(peak_slice) - arr[i])
            if pre_drop < min_pre_drop or post_recover < min_recover:
                continue
            candidates.append((i, pre_drop, post_recover, float(np.max(peak_slice))))

    if not candidates:
        return False

    trough_rel, pre_drop, post_recover, peak = max(candidates, key=lambda v: v[1])
    if post_recover < 0.45 * pre_drop:
        return False

    return True
