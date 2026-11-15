# -*- coding: utf-8 -*-
"""Shared mathematical definitions, provenance checks, and CSV/JSON helpers for PUB-053 R2 analysis."""

from __future__ import annotations

import csv
import functools
import hashlib
import json
import math
import statistics
from collections.abc import Mapping, Sequence
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import numpy as np
from scipy.interpolate import CubicSpline

METHODS_ORDER = ["B0_state", "Flow_only", "Command_only", "B1_combined"]
METHOD_KEY_MAP = {
    "B0_state": ("state_score", "available_state"),
    "Flow_only": ("flow_z", "available_flow_command"),
    "Command_only": ("command_z", "available_flow_command"),
    "B1_combined": ("combined_score", "available_flow_command"),
}
METHOD_LABELS = {
    "B0_state": "State (B0)",
    "Flow_only": "Flow only",
    "Command_only": "Demand only",
    "B1_combined": "Combined (B1)",
}
EVAL_BLOCKS = [f"E{i}" for i in range(1, 9)]
DEV_BLOCKS = [f"D{i}" for i in range(1, 5)]


def resolve_repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    if here.is_file():
        here = here.parent
    for cand in [here, *here.parents]:
        if (cand / "data" / "episode_metadata.csv").exists() and (cand / "results").exists():
            return cand
    raise FileNotFoundError("Could not locate repository root containing data/episode_metadata.csv and results/")


def check_raw_npz_availability(repo_root: Path) -> dict[str, Any]:
    """Check whether all 48 primary .npz trajectory/trace files from PUB053_Manuscript_Package_R2.zip exist."""
    meta = load_csv(repo_root / "data" / "episode_metadata.csv")
    obs_present = 0
    tr_present = 0
    missing_obs: list[str] = []
    missing_traces: list[str] = []
    missing_examples: list[str] = []
    for row in meta:
        ep = row["episode"]
        obs_p = repo_root / "data" / "observations" / f"{ep}.npz"
        tr_p = repo_root / "data" / "traces" / f"{ep}.npz"
        if obs_p.exists():
            obs_present += 1
        else:
            rel = obs_p.relative_to(repo_root).as_posix()
            missing_obs.append(rel)
            if len(missing_examples) < 4:
                missing_examples.append(rel)
        if tr_p.exists():
            tr_present += 1
        else:
            rel = tr_p.relative_to(repo_root).as_posix()
            missing_traces.append(rel)
            if len(missing_examples) < 6:
                missing_examples.append(rel)

    expected_per_dir = len(meta)
    all_present = obs_present == expected_per_dir and tr_present == expected_per_dir
    return {
        "mode": "full_raw_npz_replay" if all_present else "missing_primary_raw_npz",
        "all_raw_npz_present": all_present,
        "observations_npz_found": obs_present,
        "traces_npz_found": tr_present,
        "expected_per_kind": expected_per_dir,
        "total_expected_npz": expected_per_dir * 2,
        "total_found_npz": obs_present + tr_present,
        "missing_observations_count": len(missing_obs),
        "missing_traces_count": len(missing_traces),
        "missing_examples": missing_examples,
        "primary_archive_origin": "PUB053_Manuscript_Package_R2.zip (not bundled on public release)",
    }


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def round_half_up_1dp(val: float) -> float:
    return float(Decimal(str(val)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def consecutive_true_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return inclusive (start_idx, end_idx) pairs for contiguous True segments."""
    b = np.asarray(mask, dtype=bool)
    if b.size == 0:
        return []
    edges = np.flatnonzero(np.diff(np.r_[False, b, False].astype(np.int8)))
    return [(int(edges[i]), int(edges[i + 1] - 1)) for i in range(0, len(edges), 2)]


def detect_sequential_alarms(
    time_s: np.ndarray,
    scores: np.ndarray,
    available: np.ndarray,
    threshold: float,
    start_s: float = 1200.0,
    persist_s: float = 600.0,
    cooldown_s: float = 1800.0,
) -> list[float]:
    """Sequential persistence detector: triggers when score > threshold continuously for elapsed >= persist_s."""
    t = np.asarray(time_s, dtype=float)
    s = np.asarray(scores, dtype=float)
    av = np.asarray(available, dtype=bool)
    active = (t >= start_s) & av & np.isfinite(s) & (s > threshold)
    alarms: list[float] = []
    for a, b in consecutive_true_runs(active):
        due = t[a] + persist_s
        if alarms:
            due = max(due, alarms[-1] + cooldown_s)
        while due <= t[b] + 1e-9:
            k = int(np.searchsorted(t, due - 1e-9))
            if k >= len(t):
                break
            alarms.append(float(t[k]))
            due = t[k] + cooldown_s
    return alarms


def max_exceedance_span_s(
    time_s: np.ndarray,
    scores: np.ndarray,
    available: np.ndarray,
    threshold: float,
    start_s: float = 1200.0,
) -> float:
    """Maximum contiguous elapsed exceedance span (t[b] - t[a]) in seconds."""
    t = np.asarray(time_s, dtype=float)
    s = np.asarray(scores, dtype=float)
    av = np.asarray(available, dtype=bool)
    active = (t >= start_s) & av & np.isfinite(s) & (s > threshold)
    spans = [float(t[b] - t[a]) for a, b in consecutive_true_runs(active)]
    return max(spans, default=0.0)


def compute_ewls_residuals(
    q_s: np.ndarray,
    l_dev: np.ndarray,
    r_m: np.ndarray | None = None,
    u_f: np.ndarray | None = None,
    fit_params: dict[str, float] | None = None,
    *,
    q_f: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate OLS mass-balance/demand references and signed standardized flow/demand residuals."""
    if r_m is None:
        if q_f is None:
            raise ValueError("Either r_m or q_f must be provided.")
        r_m_arr = np.asarray(q_f, dtype=float)
    elif q_f is not None:
        raise ValueError("Specify only one of r_m or q_f, not both.")
    else:
        r_m_arr = np.asarray(r_m, dtype=float)
    if u_f is None or fit_params is None:
        raise ValueError("u_f and fit_params must be provided.")
    q_s_arr = np.asarray(q_s, dtype=float)
    l_dev_arr = np.asarray(l_dev, dtype=float)
    u_f_arr = np.asarray(u_f, dtype=float)
    r_ref = fit_params["a0"] + fit_params["a1"] * q_s_arr + fit_params["a2"] * l_dev_arr
    u_ref = fit_params["b0"] + fit_params["b1"] * q_s_arr
    z_f = (r_m_arr - r_ref) / fit_params["sigma_F"]
    z_d = (u_f_arr - u_ref) / fit_params["sigma_D"]
    return r_ref, u_ref, z_f, z_d


def compute_table6_from_episode_rows(
    ep_rows: list[dict[str, Any]],
    thresholds_by_method: dict[str, float],
) -> list[dict[str, Any]]:
    """Aggregate evaluation-split Table 6 summary directly from the 96 episode-method rows."""
    summary_rows: list[dict[str, Any]] = []
    for method in METHODS_ORDER:
        eval_norm = [
            r for r in ep_rows
            if r["method"] == method and r["episode"].startswith("E") and r["episode"].endswith("_normal")
        ]
        eval_fault = [
            r for r in ep_rows
            if r["method"] == method and r["episode"].startswith("E") and r["episode"].endswith("_tube_leak")
        ]
        delays = [float(r["delay_min"]) for r in eval_fault]
        leads = [float(r["strict_lead_min"]) for r in eval_fault if str(r["strict_lead_min"]) not in ("", "None")]
        norm_alarms = sum(int(r["normal_alarms"]) for r in eval_norm)
        summary_rows.append(
            {
                "method": method,
                "threshold": thresholds_by_method[method],
                "normal_alarm_count": norm_alarms,
                "fault_n": len(eval_fault),
                "event_n": len(leads),
                "delay_median_min": float(statistics.median(delays)),
                "delay_min": float(min(delays)),
                "delay_max": float(max(delays)),
                "lead_median_min": float(statistics.median(leads)),
                "lead_min": float(min(leads)),
                "lead_max": float(max(leads)),
            }
        )
    return summary_rows


def horizontal_cylinder_volume_m3(
    level_m: np.ndarray,
    radius_m: float = 0.75,
    length_m: float = 5.0,
) -> np.ndarray:
    """Compute liquid volume V(h) in a horizontal cylindrical drum (Supplement S3)."""
    h = np.clip(np.asarray(level_m, dtype=float), 0.0, 2.0 * radius_m)
    d = radius_m - h
    rad_term = np.sqrt(np.maximum(radius_m**2 - d**2, 0.0))
    area = (radius_m**2) * np.arccos(np.clip(d / radius_m, -1.0, 1.0)) - d * rad_term
    return length_m * area


def _if97_region4_tsat_k(pressure_bar: np.ndarray) -> np.ndarray:
    """Compute IAPWS-IF97 Region 4 saturation temperature T_s(p) in Kelvin from pressure in bar."""
    p_mpa = np.asarray(pressure_bar, dtype=float) / 10.0
    n1 = 0.11670521452767e4
    n2 = -0.72421316703206e6
    n3 = -0.17073846940092e2
    n4 = 0.12020824702470e5
    n5 = -0.32325550322333e7
    n6 = 0.14915108613530e2
    n7 = -0.48232657361591e4
    n8 = 0.40511340542057e6
    n9 = -0.23855557567849
    n10 = 0.65017534844798e3
    beta = np.power(p_mpa, 0.25)
    e = beta**2 + n3 * beta + n6
    f = n1 * (beta**2) + n4 * beta + n7
    g = n2 * (beta**2) + n5 * beta + n8
    d = (2.0 * g) / (-f - np.sqrt(np.maximum(f**2 - 4.0 * e * g, 0.0)))
    return (n10 + d - np.sqrt(np.maximum((n10 + d) ** 2 - 4.0 * (n9 + n10 * d), 0.0))) / 2.0


def _iapws95_sat_liquid_density_kg_m3(temp_k: np.ndarray) -> np.ndarray:
    """Compute saturated liquid water density from the IAPWS-95 auxiliary equation."""
    theta = np.maximum(1.0 - np.asarray(temp_k, dtype=float) / 647.096, 0.0)
    b1 = 1.99274064
    b2 = 1.09965342
    b3 = -0.510839303
    b4 = -1.75493479
    b5 = -45.5170352
    b6 = -6.74694450e5
    ratio = (
        1.0
        + b1 * np.power(theta, 1.0 / 3.0)
        + b2 * np.power(theta, 2.0 / 3.0)
        + b3 * np.power(theta, 5.0 / 3.0)
        + b4 * np.power(theta, 16.0 / 3.0)
        + b5 * np.power(theta, 43.0 / 3.0)
        + b6 * np.power(theta, 110.0 / 3.0)
    )
    return 322.0 * ratio


@functools.lru_cache(maxsize=1)
def _sat_liquid_density_spline() -> CubicSpline:
    """Build cached 1,000-knot geometric cubic spline over 0.5-120 bar (Supplement S3)."""
    p_grid_bar = np.geomspace(0.5, 120.0, 1000)
    try:
        from iapws import IAPWS97  # type: ignore

        rho_grid = np.array([float(IAPWS97(P=float(p) / 10.0, x=0).rho) for p in p_grid_bar], dtype=float)
    except Exception:
        t_sat = _if97_region4_tsat_k(p_grid_bar)
        rho_grid = _iapws95_sat_liquid_density_kg_m3(t_sat)
    return CubicSpline(p_grid_bar, rho_grid, bc_type="not-a-knot")


def saturated_liquid_density_kg_m3(pressure_bar: np.ndarray) -> np.ndarray:
    """Evaluate saturated liquid density with [0.5, 30.0] bar detector clipping (Supplement S3)."""
    p = np.asarray(pressure_bar, dtype=float)
    finite_mask = np.isfinite(p)
    p_safe = np.where(finite_mask, np.clip(p, 0.5, 30.0), 7.0)
    rho = _sat_liquid_density_spline()(p_safe)
    return np.where(finite_mask, rho, np.nan)


def _pick_npz_array(
    npz_data: Mapping[str, np.ndarray],
    candidates: Sequence[str],
    *,
    required: bool = True,
    dtype: Any = float,
) -> np.ndarray | None:
    """Select the first matching key from an NPZ dictionary."""
    for key in candidates:
        if key in npz_data:
            return np.asarray(npz_data[key], dtype=dtype)
    if required:
        raise KeyError(f"Missing required NPZ array; tried candidates={list(candidates)}")
    return None


def extract_observation_channels(obs_npz: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Extract canonical time, conditioned sensor, command, blowdown, and availability arrays."""
    t = _pick_npz_array(obs_npz, ("time", "t", "time_s"))
    p_obs = _pick_npz_array(obs_npz, ("meta/obs_held_drum_pressure", "obs/drum_pressure", "drum_pressure_obs"))
    l_obs = _pick_npz_array(obs_npz, ("meta/obs_held_drum_level", "obs/drum_level", "drum_level_obs"))
    q_f = _pick_npz_array(obs_npz, ("meta/obs_held_feedwater_flow", "obs/feedwater_flow", "feedwater_flow_obs"))
    q_s = _pick_npz_array(obs_npz, ("meta/obs_held_steam_flow", "obs/steam_flow", "steam_flow_obs"))
    u_fw = _pick_npz_array(obs_npz, ("meta/fw_cmd", "meta/final_control_fw_cmd", "ctrl/fw_cmd", "u_fw"))
    q_bd = _pick_npz_array(obs_npz, ("meta/q_bd", "truth/blowdown_flow", "blowdown_flow"), required=False)
    if q_bd is None:
        q_bd = np.where(np.mod(t, 1800.0) < (60.0 - 1e-9), 0.05, 0.0)

    av_p = _pick_npz_array(obs_npz, ("meta/obs_available_drum_pressure", "obs/available_drum_pressure"), required=False, dtype=bool)
    av_l = _pick_npz_array(obs_npz, ("meta/obs_available_drum_level", "obs/available_drum_level"), required=False, dtype=bool)
    av_qf = _pick_npz_array(obs_npz, ("meta/obs_available_feedwater_flow", "obs/available_feedwater_flow"), required=False, dtype=bool)
    av_qs = _pick_npz_array(obs_npz, ("meta/obs_available_steam_flow", "obs/available_steam_flow"), required=False, dtype=bool)

    state_finite = np.isfinite(p_obs) & np.isfinite(l_obs)
    if av_p is not None:
        state_finite &= av_p
    if av_l is not None:
        state_finite &= av_l

    explicit_av_state = _pick_npz_array(obs_npz, ("meta/available_state", "available_state"), required=False, dtype=bool)
    available_state = state_finite if explicit_av_state is None else (state_finite & explicit_av_state)

    fc_point = state_finite & np.isfinite(q_f) & np.isfinite(q_s) & np.isfinite(u_fw) & np.isfinite(q_bd)
    if av_qf is not None:
        fc_point &= av_qf
    if av_qs is not None:
        fc_point &= av_qs
    explicit_av_fc = _pick_npz_array(obs_npz, ("meta/available_flow_command", "available_flow_command"), required=False, dtype=bool)

    return {
        "time": t,
        "p_obs": p_obs,
        "l_obs": l_obs,
        "q_f": q_f,
        "q_s": q_s,
        "u_fw": u_fw,
        "q_bd": q_bd,
        "available_state": available_state,
        "fc_point_valid": fc_point,
        "explicit_av_fc": explicit_av_fc,
    }


def _compute_causal_b0_ewma(
    time_s: np.ndarray,
    p_obs: np.ndarray,
    l_obs: np.ndarray,
    available_state: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute causal EWMA deviations e_l, e_p starting from the first available observation."""
    n = len(time_s)
    e_l = np.full(n, np.nan, dtype=float)
    e_p = np.full(n, np.nan, dtype=float)
    initialized = False
    prev_l = 0.0
    prev_p = 0.0
    for i in range(n):
        if not available_state[i]:
            initialized = False
            continue
        d_l = float(l_obs[i]) - 0.85
        d_p = float(p_obs[i]) - 7.0
        if not initialized:
            prev_l = d_l
            prev_p = d_p
            initialized = True
        else:
            dt_step = float(time_s[i] - time_s[i - 1])
            alpha = 1.0 - math.exp(-dt_step / 120.0)
            prev_l = prev_l + alpha * (d_l - prev_l)
            prev_p = prev_p + alpha * (d_p - prev_p)
        e_l[i] = prev_l
        e_p[i] = prev_p
    return e_l, e_p


def _compute_episode_flow_features(
    ch: dict[str, np.ndarray],
    window_s: float = 600.0,
) -> dict[str, np.ndarray]:
    """Compute causal 600 s trailing mass-balance r_M and OLS covariates from raw channels."""
    t = ch["time"]
    n = len(t)
    m_hat = saturated_liquid_density_kg_m3(ch["p_obs"]) * horizontal_cylinder_volume_m3(ch["l_obs"])
    q_net = ch["q_f"] - ch["q_s"] - ch["q_bd"]
    l_dev = ch["l_obs"] - 0.85

    r_m = np.full(n, np.nan, dtype=float)
    q_s_bar = np.full(n, np.nan, dtype=float)
    l_d_bar = np.full(n, np.nan, dtype=float)
    u_fw_bar = np.full(n, np.nan, dtype=float)
    av_fc = np.zeros(n, dtype=bool)

    dt_diffs = np.diff(t)
    uniform_dt = float(dt_diffs[0]) if len(dt_diffs) > 0 and np.allclose(dt_diffs, dt_diffs[0], atol=1e-9) else None
    if uniform_dt is not None and abs(window_s / uniform_dt - round(window_s / uniform_dt)) < 1e-9:
        w_steps = int(round(window_s / uniform_dt))
        if n > w_steps:
            fc_win = np.lib.stride_tricks.sliding_window_view(ch["fc_point_valid"], w_steps + 1)
            valid = np.all(fc_win, axis=1)
            q_s_win = np.lib.stride_tricks.sliding_window_view(ch["q_s"], w_steps + 1)
            l_d_win = np.lib.stride_tricks.sliding_window_view(l_dev, w_steps + 1)
            u_win = np.lib.stride_tricks.sliding_window_view(ch["u_fw"], w_steps + 1)
            qn_win = np.lib.stride_tricks.sliding_window_view(q_net, w_steps + 1)

            q_s_m = np.mean(q_s_win, axis=1)
            l_d_m = np.mean(l_d_win, axis=1)
            u_m = np.mean(u_win, axis=1)
            trapz_mean = (np.sum(qn_win[:, 1:-1], axis=1) + 0.5 * (qn_win[:, 0] + qn_win[:, -1])) * (uniform_dt / window_s)
            dm_dt = (m_hat[w_steps:] - m_hat[:-w_steps]) / window_s
            r_vals = trapz_mean - dm_dt

            av_fc[w_steps:] = valid
            q_s_bar[w_steps:] = np.where(valid, q_s_m, np.nan)
            l_d_bar[w_steps:] = np.where(valid, l_d_m, np.nan)
            u_fw_bar[w_steps:] = np.where(valid, u_m, np.nan)
            r_m[w_steps:] = np.where(valid, r_vals, np.nan)
    else:
        for i in range(n):
            t_start = t[i] - window_s
            if t_start < t[0] - 1e-9:
                continue
            j = int(np.searchsorted(t, t_start - 1e-9))
            if abs((t[i] - t[j]) - window_s) > 1e-6:
                continue
            if not np.all(ch["fc_point_valid"][j : i + 1]):
                continue
            av_fc[i] = True
            q_s_bar[i] = float(np.mean(ch["q_s"][j : i + 1]))
            l_d_bar[i] = float(np.mean(l_dev[j : i + 1]))
            u_fw_bar[i] = float(np.mean(ch["u_fw"][j : i + 1]))
            int_qn = float(np.trapz(q_net[j : i + 1], t[j : i + 1]))
            r_m[i] = (int_qn - (float(m_hat[i]) - float(m_hat[j]))) / (float(t[i]) - float(t[j]))

    if ch["explicit_av_fc"] is not None:
        av_fc &= ch["explicit_av_fc"]
        r_m = np.where(av_fc, r_m, np.nan)
        q_s_bar = np.where(av_fc, q_s_bar, np.nan)
        l_d_bar = np.where(av_fc, l_d_bar, np.nan)
        u_fw_bar = np.where(av_fc, u_fw_bar, np.nan)

    return {
        "r_m": r_m,
        "q_s_bar": q_s_bar,
        "l_d_bar": l_d_bar,
        "u_fw_bar": u_fw_bar,
        "available_flow_command": av_fc,
    }


def reconstruct_features_from_observations(
    obs_by_ep: Mapping[str, Mapping[str, np.ndarray]],
    episodes: Sequence[str],
    dev_blocks: Sequence[str] = DEV_BLOCKS,
    window_s: float = 600.0,
    start_s: float = 1200.0,
) -> dict[str, Any]:
    """Reconstruct B0 EWMA and 600 s EWLS/OLS detector scores directly from raw observation NPZs."""
    raw_ep: dict[str, dict[str, np.ndarray]] = {}
    for ep in episodes:
        ch = extract_observation_channels(obs_by_ep[ep])
        e_l, e_p = _compute_causal_b0_ewma(ch["time"], ch["p_obs"], ch["l_obs"], ch["available_state"])
        fc = _compute_episode_flow_features(ch, window_s=window_s)
        raw_ep[ep] = {
            "time": ch["time"],
            "e_l": e_l,
            "e_p": e_p,
            "available_state": ch["available_state"],
            **fc,
        }

    dev_eps = [f"{blk}_normal" for blk in dev_blocks]
    el_pool = np.concatenate([raw_ep[ep]["e_l"][(raw_ep[ep]["time"] >= start_s) & raw_ep[ep]["available_state"]] for ep in dev_eps])
    ep_pool = np.concatenate([raw_ep[ep]["e_p"][(raw_ep[ep]["time"] >= start_s) & raw_ep[ep]["available_state"]] for ep in dev_eps])
    sigma_l = float(np.std(el_pool, ddof=0))
    sigma_p = float(np.std(ep_pool, ddof=0))

    fc_masks = [(raw_ep[ep]["time"] >= start_s) & raw_ep[ep]["available_flow_command"] for ep in dev_eps]
    qs_pool = np.concatenate([raw_ep[ep]["q_s_bar"][m] for ep, m in zip(dev_eps, fc_masks)])
    ld_pool = np.concatenate([raw_ep[ep]["l_d_bar"][m] for ep, m in zip(dev_eps, fc_masks)])
    rm_pool = np.concatenate([raw_ep[ep]["r_m"][m] for ep, m in zip(dev_eps, fc_masks)])
    uf_pool = np.concatenate([raw_ep[ep]["u_fw_bar"][m] for ep, m in zip(dev_eps, fc_masks)])

    x_flow = np.column_stack([np.ones_like(qs_pool), qs_pool, ld_pool])
    a_coef = np.linalg.lstsq(x_flow, rm_pool, rcond=None)[0]
    sigma_f = float(np.std(rm_pool - x_flow @ a_coef, ddof=0))

    x_cmd = np.column_stack([np.ones_like(qs_pool), qs_pool])
    b_coef = np.linalg.lstsq(x_cmd, uf_pool, rcond=None)[0]
    sigma_d = float(np.std(uf_pool - x_cmd @ b_coef, ddof=0))

    fit_params = {
        "a0": float(a_coef[0]),
        "a1": float(a_coef[1]),
        "a2": float(a_coef[2]),
        "b0": float(b_coef[0]),
        "b1": float(b_coef[1]),
        "sigma_F": sigma_f,
        "sigma_D": sigma_d,
        "sigma_l": sigma_l,
        "sigma_p": sigma_p,
    }

    traces: dict[str, dict[str, np.ndarray]] = {}
    for ep in episodes:
        r = raw_ep[ep]
        av_st = r["available_state"]
        av_fc = r["available_flow_command"]
        state_score = np.where(av_st, np.maximum(np.abs(r["e_l"]) / sigma_l, np.abs(r["e_p"]) / sigma_p), np.nan)
        r_ref, u_ref, z_f_raw, z_d_raw = compute_ewls_residuals(
            r["q_s_bar"], r["l_d_bar"], r["r_m"], r["u_fw_bar"], fit_params
        )
        flow_z = np.where(av_fc, z_f_raw, np.nan)
        command_z = np.where(av_fc, z_d_raw, np.nan)
        combined_score = np.where(av_fc, np.maximum(flow_z, command_z), np.nan)
        traces[ep] = {
            "time": r["time"],
            "state_score": state_score,
            "flow_z": flow_z,
            "command_z": command_z,
            "combined_score": combined_score,
            "available_state": av_st,
            "available_flow_command": av_fc,
            "r_m": r["r_m"],
            "q_s_bar": r["q_s_bar"],
            "l_d_bar": r["l_d_bar"],
            "u_fw_bar": r["u_fw_bar"],
            "r_ref": r_ref,
            "u_ref": u_ref,
            "e_l": r["e_l"],
            "e_p": r["e_p"],
        }

    return {
        "fit_params": fit_params,
        "fit_sample_n": int(len(rm_pool)),
        "state_fit_sample_n": int(len(el_pool)),
        "traces": traces,
    }


def _load_csv_with_header(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, list(reader)


def _canonical_key_part(val: str) -> str:
    s = str(val).strip()
    if s == "":
        return ""
    try:
        f = float(s)
        if math.isfinite(f):
            if abs(f - round(f)) <= 1e-12:
                return str(int(round(f)))
            return f"{f:.12g}"
    except ValueError:
        pass
    return s


def _compare_row_cells(
    idx_or_key: Any,
    rr: dict[str, str],
    gr: dict[str, str],
    cols: Sequence[str],
    tol: float,
    max_diff: float,
    mismatches: list[dict[str, Any]],
) -> float:
    for k in cols:
        rv = rr.get(k, "")
        gv = gr.get(k, "")
        if rv == gv:
            continue
        if rv == "" or gv == "":
            mismatches.append({"row": idx_or_key, "col": k, "ref": rv, "gen": gv, "diff": "empty_mismatch"})
            continue
        try:
            rf = float(rv)
            gf = float(gv)
        except ValueError:
            mismatches.append({"row": idx_or_key, "col": k, "ref": rv, "gen": gv, "diff": "string_mismatch"})
            continue
        if math.isnan(rf) and math.isnan(gf):
            continue
        if math.isnan(rf) or math.isnan(gf):
            mismatches.append({"row": idx_or_key, "col": k, "ref": rv, "gen": gv, "diff": "nan_mismatch"})
            continue
        if math.isinf(rf) or math.isinf(gf):
            if rf != gf:
                mismatches.append({"row": idx_or_key, "col": k, "ref": rv, "gen": gv, "diff": "inf_mismatch"})
            continue
        diff = abs(rf - gf)
        max_diff = max(max_diff, diff)
        if diff > tol:
            mismatches.append({"row": idx_or_key, "col": k, "ref": rv, "gen": gv, "diff": diff})
    return max_diff


def compare_csv_files(
    ref_path: Path,
    gen_path: Path,
    tol: float = 1e-12,
    key_cols: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compare two CSV tables row-by-row or aligned by key_cols and report exact differences."""
    ref_cols, ref_rows = _load_csv_with_header(ref_path)
    gen_cols, gen_rows = _load_csv_with_header(gen_path)
    header_match = ref_cols == gen_cols
    row_count_match = len(ref_rows) == len(gen_rows)

    if key_cols is None:
        if not header_match or not row_count_match:
            return {
                "ref": ref_path.as_posix(),
                "gen": gen_path.as_posix(),
                "header_match": header_match,
                "row_count_match": row_count_match,
                "ref_rows": len(ref_rows),
                "gen_rows": len(gen_rows),
                "key_cols": None,
                "exact_match": False,
                "max_abs_diff": None,
            }
        max_diff = 0.0
        mismatches: list[dict[str, Any]] = []
        for idx, (rr, gr) in enumerate(zip(ref_rows, gen_rows)):
            max_diff = _compare_row_cells(idx, rr, gr, ref_cols, tol, max_diff, mismatches)
        return {
            "header_match": True,
            "row_count_match": True,
            "rows_checked": len(ref_rows),
            "key_cols": None,
            "exact_match": len(mismatches) == 0,
            "max_abs_diff": max_diff,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches[:5],
        }

    key_list = list(key_cols)
    missing_key_cols = [k for k in key_list if k not in ref_cols or k not in gen_cols]
    if missing_key_cols or not header_match:
        return {
            "ref": ref_path.as_posix(),
            "gen": gen_path.as_posix(),
            "header_match": header_match,
            "row_count_match": row_count_match,
            "ref_rows": len(ref_rows),
            "gen_rows": len(gen_rows),
            "key_cols": key_list,
            "missing_key_columns": missing_key_cols,
            "exact_match": False,
            "max_abs_diff": None,
        }

    ref_map: dict[tuple[str, ...], dict[str, str]] = {}
    dup_ref: list[tuple[str, ...]] = []
    for rr in ref_rows:
        kt = tuple(_canonical_key_part(rr[k]) for k in key_list)
        if kt in ref_map:
            dup_ref.append(kt)
        else:
            ref_map[kt] = rr

    gen_map: dict[tuple[str, ...], dict[str, str]] = {}
    dup_gen: list[tuple[str, ...]] = []
    for gr in gen_rows:
        kt = tuple(_canonical_key_part(gr[k]) for k in key_list)
        if kt in gen_map:
            dup_gen.append(kt)
        else:
            gen_map[kt] = gr

    missing_keys = [k for k in ref_map if k not in gen_map]
    extra_keys = [k for k in gen_map if k not in ref_map]
    max_diff = 0.0
    mismatches = []
    shared_keys = [k for k in ref_map if k in gen_map]
    for kt in shared_keys:
        max_diff = _compare_row_cells(list(kt), ref_map[kt], gen_map[kt], ref_cols, tol, max_diff, mismatches)

    exact = (
        header_match
        and row_count_match
        and not dup_ref
        and not dup_gen
        and not missing_keys
        and not extra_keys
        and len(mismatches) == 0
    )
    return {
        "header_match": header_match,
        "row_count_match": row_count_match,
        "rows_checked": len(shared_keys),
        "ref_rows": len(ref_rows),
        "gen_rows": len(gen_rows),
        "key_cols": key_list,
        "duplicate_ref_keys": [list(k) for k in dup_ref[:5]],
        "duplicate_gen_keys": [list(k) for k in dup_gen[:5]],
        "missing_keys": [list(k) for k in missing_keys[:5]],
        "extra_keys": [list(k) for k in extra_keys[:5]],
        "exact_match": exact,
        "max_abs_diff": max_diff,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:5],
    }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
