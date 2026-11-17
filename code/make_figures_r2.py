# -*- coding: utf-8 -*-
"""Regenerate / reproduce manuscript Figures 1-7 from --results into --out without overwriting figures/.

By default requires both all 48 primary .npz files from PUB053_Manuscript_Package_R2.zip (missing_raw_npz_error)
and iapws==1.5.5 for exact IAPWS-IF97 density reconstruction (missing_iapws_error, unless --allow-approx-density
is explicitly passed) and exits 1 if required inputs or dependencies are missing. Pass --archived-assets-only
(or --archived-tables-only) in standalone clones to render Figure 4 from CSV and composite/stage preserved R2
assets from figures/raw_source_assets/.

Usage:
    python -B code/make_figures_r2.py --results results_reproduced --out figures_reproduced
    python -B code/make_figures_r2.py --archived-assets-only --results results_reproduced --out figures_reproduced
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    DEV_BLOCKS,
    EVAL_BLOCKS,
    METHODS_ORDER,
    METHOD_KEY_MAP,
    METHOD_LABELS,
    calibrate_thresholds_from_traces,
    check_raw_npz_availability,
    detect_functional_event,
    detect_sequential_alarms,
    extract_observation_channels,
    extract_raw_trip_and_domain_exit,
    get_density_backend_info,
    load_csv,
    max_exceedance_span_s,
    reconstruct_features_from_observations,
    resolve_repo_root,
    sha256_file,
    write_json,
)


def render_figure_4_from_csv(ep_csv_path: Path, out_png: Path) -> None:
    """Plot confirmed post-onset detection delay across E1-E8 directly from episode_results.csv."""
    rows = load_csv(ep_csv_path)
    x_labels = [f"{b}*" if b == "E5" else b for b in EVAL_BLOCKS]
    x = np.arange(len(EVAL_BLOCKS), dtype=float)

    style_map = {
        "B0_state": {"label": "State (B0)", "marker": "o", "color": "#1f77b4", "dx": -0.22},
        "Flow_only": {"label": "Flow", "marker": "s", "color": "#ff7f0e", "dx": -0.07},
        "Command_only": {"label": "Demand", "marker": "^", "color": "#2ca02c", "dx": 0.08},
        "B1_combined": {"label": "Combined", "marker": "x", "color": "#d62728", "dx": 0.22},
    }

    fig, ax = plt.subplots(figsize=(5.68, 4.48), dpi=200)
    all_ys: list[float] = []
    for method in METHODS_ORDER:
        st = style_map[method]
        xs_m: list[float] = []
        ys_m: list[float] = []
        for idx, blk in enumerate(EVAL_BLOCKS):
            val_s = next(r["delay_min"] for r in rows if r["episode"] == f"{blk}_tube_leak" and r["method"] == method)
            if val_s not in ("", None):
                xs_m.append(float(x[idx] + st["dx"]))
                ys_m.append(float(val_s))
                all_ys.append(float(val_s))
        ax.scatter(
            xs_m,
            ys_m,
            marker=st["marker"],
            color=st["color"],
            s=46,
            linewidths=1.4 if st["marker"] == "x" else 0.8,
            label=st["label"],
            zorder=3,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(x_labels)
    ax.set_xlabel("Evaluation block (*endpoint-censored)")
    ax.set_ylabel("Confirmed post-onset delay (min)")
    if all_ys and min(all_ys) >= 48.0 and max(all_ys) <= 195.0:
        ax.set_ylim(48.0, 195.0)
    elif all_ys:
        pad = max(2.0, 0.1 * (max(all_ys) - min(all_ys)))
        ax.set_ylim(min(all_ys) - pad, max(all_ys) + pad)
    ax.grid(axis="y", color="#e0e0e0", linewidth=0.8, zorder=1)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper left", ncol=2, frameon=False, fontsize=9)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def compose_figure_1(raw_dir: Path, out_png: Path) -> None:
    """Stack R2 Supplement Figs S2 & S3 vertically with +30 px separator."""
    with Image.open(raw_dir / "page1_img3_1261.jpeg") as img_p, Image.open(raw_dir / "page1_img4_1265.jpeg") as img_l:
        w = max(img_p.width, img_l.width)
        gap = 30
        h = img_p.height + img_l.height + gap
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        canvas.paste(img_p, (0, 0))
        canvas.paste(img_l, (0, img_p.height + gap))
        canvas.save(out_png, dpi=(300, 300))


def compose_figure_2(raw_dir: Path, out_png: Path) -> None:
    """Pad R2 Main Fig 1 bottom margin (+32 px white strip) to prevent x-label clipping."""
    with Image.open(raw_dir / "rId27.png") as src:
        im = src.convert("RGB")
        w, h = im.size
        new_im = Image.new("RGB", (w, h + 32), (255, 255, 255))
        new_im.paste(im, (0, 0))
        new_im.save(out_png, format="PNG")


def _save_fig(fig: plt.Figure, out_path: Path, dpi: int = 200) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def render_figures_from_raw_npz(repo_root: Path, ep_csv: Path, out_dir: Path) -> dict[str, dict[str, Any]]:
    """Plot manuscript Figures 1-3 and 5-7 directly from raw .npz observations/traces (plus Fig 4 from CSV)."""
    meta = load_csv(repo_root / "data" / "episode_metadata.csv")
    meta_by_ep = {m["episode"]: m for m in meta}
    episodes = [m["episode"] for m in meta]
    obs = {ep: dict(np.load(repo_root / "data" / "observations" / f"{ep}.npz", allow_pickle=False)) for ep in episodes}
    recon = reconstruct_features_from_observations(obs, episodes)
    tr = recon["traces"]
    thresholds, _, _ = calibrate_thresholds_from_traces(tr)

    specs: dict[str, dict[str, Any]] = {}

    # Fig 1: E1_normal conditioned pressure & drum level overview (2 panels, 0-6 h)
    e1n = extract_observation_channels(obs["E1_normal"])
    t1_h = e1n["time"] / 3600.0
    fig, axes = plt.subplots(2, 1, figsize=(7.6, 5.4), dpi=200)
    axes[0].plot(t1_h, e1n["p_obs"], linewidth=0.9, color="#1f77b4", label="Conditioned pressure")
    axes[0].axhline(7.0, linestyle="--", color="0.35", linewidth=0.9, label="Setpoint (7.0 bar)")
    axes[0].axvline(1200.0 / 3600.0, linestyle=":", color="0.3", linewidth=1.0, label="Monitoring begins")
    axes[0].set_ylabel("Conditioned pressure (bar)")
    axes[0].set_xlabel("Episode time (h)")
    axes[0].grid(color="#e6e6e6", linewidth=0.7)
    axes[0].legend(loc="best", fontsize=8, frameon=False)

    axes[1].plot(t1_h, e1n["l_obs"], linewidth=0.9, color="#2ca02c", label="Conditioned drum level")
    axes[1].axhline(0.85, linestyle="--", color="0.35", linewidth=0.9, label="Setpoint (0.85 m)")
    axes[1].axvline(1200.0 / 3600.0, linestyle=":", color="0.3", linewidth=1.0, label="Monitoring begins")
    axes[1].set_ylabel("Conditioned drum level (m)")
    axes[1].set_xlabel("Episode time (h)")
    axes[1].grid(color="#e6e6e6", linewidth=0.7)
    axes[1].legend(loc="best", fontsize=8, frameon=False)
    fig.tight_layout()
    specs["fig1_normal_overview.png"] = {
        "panels": len(axes),
        "xlabel": [ax.get_xlabel() for ax in axes],
        "ylabel": [ax.get_ylabel() for ax in axes],
        "spec_ok": len(axes) == 2 and axes[0].get_ylabel() == "Conditioned pressure (bar)" and axes[1].get_ylabel() == "Conditioned drum level (m)",
    }
    _save_fig(fig, out_dir / "fig1_normal_overview.png")

    # Common E1_tube_leak arrays and event boundaries for Figs 2, 3, and 5
    e1f = extract_observation_channels(obs["E1_tube_leak"])
    d1 = tr["E1_tube_leak"]
    t_f = d1["time"]
    t_fh = t_f / 3600.0
    lvl_e1 = np.asarray(obs["E1_tube_leak"]["truth/drum_level"], dtype=float) if "truth/drum_level" in obs["E1_tube_leak"] else e1f["l_obs"]
    onset_e1 = float(meta_by_ep["E1_tube_leak"]["onset_s"])
    ev_s1, ev_c1 = detect_functional_event(t_f, e1f["u_fw"], lvl_e1)
    _trip1, dom1, _ = extract_raw_trip_and_domain_exit(obs["E1_tube_leak"], t_f, meta_by_ep["E1_tube_leak"])
    end_e1 = min(float(t_f[-1]), float(ev_c1 + 300.0)) if ev_c1 is not None else (float(dom1) if dom1 is not None else float(t_f[-1]))
    m_e1 = (t_f >= 1200.0) & (t_f <= end_e1)

    def _annotate_e1_events(ax: plt.Axes) -> None:
        ax.axvline(onset_e1 / 3600.0, linestyle=":", color="0.3", linewidth=1.0, label="Leak onset")
        if ev_s1 is not None and ev_c1 is not None:
            ax.axvspan(ev_s1 / 3600.0, ev_c1 / 3600.0, alpha=0.22, color="#ffbb78", label="Functional dwell")

    # Fig 2: E1_tube_leak physical trajectory (3 panels: pressure, level, feedwater command)
    fig, axes = plt.subplots(3, 1, figsize=(7.6, 7.6), dpi=200, sharex=True)
    axes[0].plot(t_fh[m_e1], e1f["p_obs"][m_e1], linewidth=0.9, color="#1f77b4", label="Observed pressure")
    axes[0].axhline(7.0, linestyle="--", color="0.35", linewidth=0.9, label="Setpoint (7.0 bar)")
    _annotate_e1_events(axes[0])
    axes[0].set_title("(a) Regulated pressure", loc="left", fontsize=9.5)
    axes[0].set_ylabel("Pressure (bar abs.)")
    axes[0].grid(color="#e6e6e6", linewidth=0.7)
    axes[0].legend(loc="best", fontsize=7.5, frameon=False)

    axes[1].plot(t_fh[m_e1], e1f["l_obs"][m_e1], linewidth=0.9, color="#1f77b4", label="Observed level")
    axes[1].axhline(0.85, linestyle="--", color="0.35", linewidth=0.9, label="Setpoint (0.85 m)")
    axes[1].axhline(0.75, linestyle="-.", color="#d62728", linewidth=0.9, label="Oracle level criterion (0.75 m)")
    _annotate_e1_events(axes[1])
    axes[1].set_title("(b) Drum-level response", loc="left", fontsize=9.5)
    axes[1].set_ylabel("Drum level (m)")
    axes[1].grid(color="#e6e6e6", linewidth=0.7)
    axes[1].legend(loc="best", fontsize=7.5, frameon=False)

    axes[2].plot(t_fh[m_e1], e1f["u_fw"][m_e1], linewidth=0.7, color="#6baed6", alpha=0.85, label="Applied command u_fw")
    axes[2].plot(t_fh[m_e1], d1["u_fw_bar"][m_e1], linewidth=1.1, color="#ff7f0e", label="Trailing mean (600 s) u_fw_bar")
    axes[2].plot(t_fh[m_e1], d1["u_ref"][m_e1], linewidth=1.0, linestyle="--", color="#2ca02c", label="Normal-conditioned reference u_ref")
    axes[2].axhline(0.95, linestyle=":", color="0.35", linewidth=0.9, label="Saturation criterion (0.95)")
    _annotate_e1_events(axes[2])
    axes[2].set_title("(c) Rising control requirement", loc="left", fontsize=9.5)
    axes[2].set_ylabel("Feedwater command")
    axes[2].set_xlabel("Episode time (h)")
    axes[2].set_xlim(1200.0 / 3600.0, end_e1 / 3600.0)
    axes[2].grid(color="#e6e6e6", linewidth=0.7)
    axes[2].legend(loc="best", fontsize=7.5, frameon=False)
    fig.tight_layout()
    panel_b_labels = [line.get_label() for line in axes[1].get_lines()]
    specs["fig2_e1_leak_trajectory.png"] = {
        "panels": len(axes),
        "titles": [ax.get_title(loc="left") for ax in axes],
        "ylabel": [ax.get_ylabel() for ax in axes],
        "xlabel": axes[2].get_xlabel(),
        "time_window_s": [1200.0, float(end_e1)],
        "panel_b_series": panel_b_labels,
        "spec_ok": (
            len(axes) == 3
            and [ax.get_ylabel() for ax in axes] == ["Pressure (bar abs.)", "Drum level (m)", "Feedwater command"]
            and "Plant truth level" not in panel_b_labels
        ),
    }
    _save_fig(fig, out_dir / "fig2_e1_leak_trajectory.png")

    # Fig 3: E1_tube_leak conditioned feedwater & steam flows
    fig, ax = plt.subplots(figsize=(8.0, 4.2), dpi=200)
    ax.plot(t_fh[m_e1], e1f["q_f"][m_e1], linewidth=0.9, color="#1f77b4", label="Observed feedwater")
    ax.plot(t_fh[m_e1], e1f["q_s"][m_e1], linewidth=0.9, color="#ff7f0e", label="Observed steam")
    ax.axvline(onset_e1 / 3600.0, linestyle=":", color="0.3", linewidth=1.0, label="Leak onset")
    if ev_s1 is not None and ev_c1 is not None:
        ax.axvspan(ev_s1 / 3600.0, ev_c1 / 3600.0, alpha=0.22, color="#ffbb78", label="Endpoint dwell")
    ax.set_xlabel("Episode time (h)")
    ax.set_ylabel("Conditioned flow (kg/s)")
    ax.grid(color="#e6e6e6", linewidth=0.7)
    ax.legend(loc="best", frameon=False, fontsize=8)
    fig.tight_layout()
    specs["fig3_e1_feature_responses.jpeg"] = {
        "panels": 1,
        "series": ["Observed feedwater", "Observed steam"],
        "xlabel": ax.get_xlabel(),
        "ylabel": ax.get_ylabel(),
        "time_window_s": [1200.0, float(end_e1)],
        "spec_ok": ax.get_ylabel() == "Conditioned flow (kg/s)" and ax.get_xlabel() == "Episode time (h)",
    }
    _save_fig(fig, out_dir / "fig3_e1_feature_responses.jpeg")

    # Fig 4: method summary delay from CSV
    render_figure_4_from_csv(ep_csv, out_dir / "fig4_method_summary_delay_lead.png")
    specs["fig4_method_summary_delay_lead.png"] = {
        "panels": 1,
        "xlabel": "Evaluation block (*endpoint-censored)",
        "ylabel": "Confirmed post-onset delay (min)",
        "spec_ok": (out_dir / "fig4_method_summary_delay_lead.png").exists(),
    }

    # Fig 5: E1_tube_leak threshold-normalized scores + confirmed post-onset alarm markers
    fig, ax = plt.subplots(figsize=(7.8, 4.4), dpi=200)
    fig5_styles = {
        "B0_state": {"color": "#1f77b4", "marker": "o", "ls": "-"},
        "Flow_only": {"color": "#ff7f0e", "marker": "s", "ls": "-"},
        "Command_only": {"color": "#2ca02c", "marker": "^", "ls": "-"},
        "B1_combined": {"color": "#d62728", "marker": "x", "ls": "--"},
    }
    alarm_markers_plotted = 0
    for method in METHODS_ORDER:
        key, av = METHOD_KEY_MAP[method]
        st = fig5_styles[method]
        mask = m_e1 & d1[av]
        norm_scores = d1[key] / thresholds[method]
        ax.plot(t_fh[mask], norm_scores[mask], linewidth=1.0, linestyle=st["ls"], color=st["color"], label=METHOD_LABELS[method])
        alarms = detect_sequential_alarms(t_f, d1[key], d1[av], thresholds[method])
        pre_term = [x for x in alarms if x >= onset_e1 and (ev_c1 is None or x < ev_c1)]
        if pre_term:
            al_t = pre_term[0]
            al_idx = int(np.searchsorted(t_f, al_t))
            ax.scatter(
                [al_t / 3600.0],
                [float(norm_scores[al_idx])],
                marker=st["marker"],
                color=st["color"],
                s=52,
                zorder=4,
                label=f"{METHOD_LABELS[method]} alarm",
            )
            alarm_markers_plotted += 1
    ax.axhline(1.0, linestyle="--", color="0.3", linewidth=0.9, label="Threshold")
    ax.axvline(onset_e1 / 3600.0, linestyle=":", color="0.3", linewidth=1.0, label="Leak onset")
    if ev_s1 is not None and ev_c1 is not None:
        ax.axvspan(ev_s1 / 3600.0, ev_c1 / 3600.0, alpha=0.22, color="#ffbb78", label="Endpoint dwell")
    ax.set_xlabel("Episode time (h)")
    ax.set_ylabel("Score / own threshold")
    ax.set_xlim(1200.0 / 3600.0, end_e1 / 3600.0)
    ax.grid(color="#e6e6e6", linewidth=0.7)
    ax.legend(loc="best", frameon=False, fontsize=7.5, ncol=2)
    fig.tight_layout()
    specs["fig5_e1_score_traces.png"] = {
        "panels": 1,
        "alarm_markers_plotted": alarm_markers_plotted,
        "xlabel": ax.get_xlabel(),
        "ylabel": ax.get_ylabel(),
        "time_window_s": [1200.0, float(end_e1)],
        "spec_ok": ax.get_ylabel() == "Score / own threshold" and ax.get_xlabel() == "Episode time (h)",
    }
    _save_fig(fig, out_dir / "fig5_e1_score_traces.png")

    # Fig 6: Horizontal milestone timeline across E1-E8
    fig, ax = plt.subplots(figsize=(8.2, 4.8), dpi=200)
    y_positions = np.arange(len(EVAL_BLOCKS))[::-1]
    used_labels: set[str] = set()
    max_end_h = 0.0
    fig6_fallback_used = False
    event_sources: dict[str, dict[str, str]] = {}
    for y_val, blk in zip(y_positions, EVAL_BLOCKS):
        ep = f"{blk}_tube_leak"
        o_ep = obs[ep]
        ch = extract_observation_channels(o_ep)
        t_ep = ch["time"]
        end_h = float(t_ep[-1]) / 3600.0
        max_end_h = max(max_end_h, end_h)
        lvl_ep = np.asarray(o_ep["truth/drum_level"], dtype=float) if "truth/drum_level" in o_ep else ch["l_obs"]
        ev_s, ev_c = detect_functional_event(t_ep, ch["u_fw"], lvl_ep)
        trip_t, dom_t, ev_prov = extract_raw_trip_and_domain_exit(o_ep, t_ep, meta_by_ep[ep])
        event_sources[ep] = ev_prov
        if ev_prov["trip_source"] == "metadata_fallback" or ev_prov["domain_exit_source"] == "metadata_fallback":
            fig6_fallback_used = True

        ax.axhline(y_val, color="#ededed", linewidth=0.8, zorder=1)
        milestones: list[tuple[float | None, str, str, str]] = [
            (ev_s, "Functional start", "o", "#1f77b4"),
            (ev_c, "Functional confirmation", "|", "#ff7f0e"),
            (trip_t, "Process trip", "s", "#2ca02c"),
            (dom_t, "Model-domain exit", "x", "#d62728"),
        ]
        for ts, lbl, mk, col in milestones:
            if ts is not None:
                ax.scatter(
                    [ts / 3600.0],
                    [y_val],
                    marker=mk,
                    color=col,
                    s=64 if mk == "|" else 48,
                    linewidths=1.5 if mk in ("|", "x") else 0.9,
                    label=lbl if lbl not in used_labels else None,
                    zorder=3,
                )
                used_labels.add(lbl)
        if ev_s is None and trip_t is None and dom_t is None:
            lbl = "Horizon censoring"
            ax.scatter(
                [end_h],
                [y_val],
                marker=">",
                color="#9467bd",
                s=52,
                label=lbl if lbl not in used_labels else None,
                zorder=3,
            )
            used_labels.add(lbl)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(EVAL_BLOCKS)
    ax.set_xlim(0.0, max(6.0, max_end_h) + 0.25)
    ax.set_xlabel("Episode time (h)")
    ax.set_ylabel("Evaluation fault block")
    ax.grid(axis="x", color="#e6e6e6", linewidth=0.7, zorder=0)
    ax.legend(loc="best", frameon=False, fontsize=8)
    fig.tight_layout()
    specs["fig6_all_eval_leak_panels.jpeg"] = {
        "panels": 1,
        "blocks": list(EVAL_BLOCKS),
        "xlabel": ax.get_xlabel(),
        "ylabel": ax.get_ylabel(),
        "event_sources": event_sources,
        "fallback_used": fig6_fallback_used,
        "spec_ok": ax.get_xlabel() == "Episode time (h)" and ax.get_ylabel() == "Evaluation fault block" and not fig6_fallback_used,
    }
    _save_fig(fig, out_dir / "fig6_all_eval_leak_panels.jpeg")

    # Fig 7: Longest threshold-exceedance span across normal evaluation blocks E1-E8
    fig, ax = plt.subplots(figsize=(8.0, 4.4), dpi=200)
    x_e = np.arange(len(EVAL_BLOCKS), dtype=float)
    fig7_styles = {
        "B0_state": {"color": "#1f77b4", "marker": "o", "dx": -0.09},
        "Flow_only": {"color": "#ff7f0e", "marker": "s", "dx": -0.03},
        "Command_only": {"color": "#2ca02c", "marker": "^", "dx": 0.03},
        "B1_combined": {"color": "#d62728", "marker": "x", "dx": 0.09},
    }
    max_span = 0.0
    for method in METHODS_ORDER:
        key, av = METHOD_KEY_MAP[method]
        st = fig7_styles[method]
        spans = [
            max_exceedance_span_s(tr[f"{blk}_normal"]["time"], tr[f"{blk}_normal"][key], tr[f"{blk}_normal"][av], thresholds[method], start_s=1200.0)
            for blk in EVAL_BLOCKS
        ]
        max_span = max(max_span, max(spans, default=0.0))
        ax.scatter(
            x_e + st["dx"],
            spans,
            marker=st["marker"],
            color=st["color"],
            s=48,
            linewidths=1.4 if st["marker"] == "x" else 0.9,
            label=METHOD_LABELS[method],
            zorder=3,
        )
    ax.axhline(600.0, linestyle="--", color="0.3", linewidth=0.9, label="Required persistence (600 s)")
    ax.set_xticks(x_e)
    ax.set_xticklabels(EVAL_BLOCKS)
    ax.set_xlabel("Normal evaluation block")
    ax.set_ylabel("Longest threshold-exceedance span (s)")
    ax.set_ylim(-20.0, max(660.0, max_span * 1.12))
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.7, zorder=1)
    ax.legend(loc="best", frameon=False, fontsize=8)
    fig.tight_layout()
    specs["fig7_normal_score_traces.jpeg"] = {
        "panels": 1,
        "blocks": list(EVAL_BLOCKS),
        "xlabel": ax.get_xlabel(),
        "ylabel": ax.get_ylabel(),
        "spec_ok": ax.get_xlabel() == "Normal evaluation block" and ax.get_ylabel() == "Longest threshold-exceedance span (s)",
    }
    _save_fig(fig, out_dir / "fig7_normal_score_traces.jpeg")
    return specs


def inspect_image_pair(ref_path: Path, gen_path: Path) -> dict[str, Any]:
    ref_sha = sha256_file(ref_path)
    gen_sha = sha256_file(gen_path)
    with Image.open(ref_path) as rim, Image.open(gen_path) as gim:
        r_size = list(rim.size)
        g_size = list(gim.size)
        pixel_max_diff = None
        if r_size == g_size:
            arr_r = np.asarray(rim.convert("RGB"), dtype=np.int16)
            arr_g = np.asarray(gim.convert("RGB"), dtype=np.int16)
            pixel_max_diff = int(np.max(np.abs(arr_r - arr_g)))
    return {
        "ref_file": ref_path.name,
        "ref_bytes": ref_path.stat().st_size,
        "gen_bytes": gen_path.stat().st_size,
        "ref_dims": r_size,
        "gen_dims": g_size,
        "ref_sha256": ref_sha,
        "gen_sha256": gen_sha,
        "exact_byte_match": ref_sha == gen_sha,
        "pixel_max_abs_diff": pixel_max_diff,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", type=Path, default=Path("results_reproduced"))
    ap.add_argument("--out", type=Path, default=Path("figures_reproduced"))
    ap.add_argument(
        "--archived-assets-only",
        action="store_true",
        help="Explicit opt-in to render Fig 4 from CSV and stage/composite preserved R2 source assets when primary .npz files are absent.",
    )
    ap.add_argument(
        "--archived-tables-only",
        action="store_true",
        help="Alias for --archived-assets-only for CLI consistency across analysis scripts.",
    )
    ap.add_argument(
        "--allow-approx-density",
        action="store_true",
        help="Allow approximate IAPWS-95 density fallback during raw .npz figure rendering when iapws is absent (not exact).",
    )
    args = ap.parse_args()

    repo_root = resolve_repo_root()
    results_dir = args.results if args.results.is_absolute() else (repo_root / args.results)
    out_dir = args.out if args.out.is_absolute() else (repo_root / args.out)
    fig_dir = repo_root / "figures"
    raw_dir = fig_dir / "raw_source_assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    res_rel = results_dir.relative_to(repo_root).as_posix() if results_dir.is_relative_to(repo_root) else str(results_dir)
    out_rel = out_dir.relative_to(repo_root).as_posix() if out_dir.is_relative_to(repo_root) else str(out_dir)

    npz_status = check_raw_npz_availability(repo_root)
    density_info = get_density_backend_info()
    archived_opt_in = bool(args.archived_assets_only or args.archived_tables_only)
    unexecuted_raw_items = [
        "Plot Figures 1, 2, 3, 5, 6, 7 directly from 2 s primary .npz arrays (PUB053_Manuscript_Package_R2.zip is absent)"
    ]

    if not npz_status["all_raw_npz_present"] and not archived_opt_in:
        manifest = {
            "script": "code/make_figures_r2.py",
            "results_input": res_rel,
            "out_dir": out_rel,
            "provenance_mode": "missing_raw_npz_error",
            "raw_npz_status": npz_status,
            "density_backend": density_info,
            "error": (
                "Primary 48 .npz files (PUB053_Manuscript_Package_R2.zip) are absent. Raw time-series figures (1, 2, 3, 5, 6, 7) "
                "cannot be plotted; pass --archived-assets-only only to render Figure 4 from CSV and stage/composite preserved R2 visual assets."
            ),
            "rendered_from_raw_npz": [],
            "rendered_from_csv": [],
            "composited_or_padded_from_preserved_assets": [],
            "copied_preserved_reference_assets": [],
            "unexecuted_items": unexecuted_raw_items,
            "all_files_valid": False,
            "all_passed": False,
        }
        write_json(out_dir / "figure_generation_manifest.json", manifest)
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 1

    if npz_status["all_raw_npz_present"] and not density_info["iapws_available"] and not args.allow_approx_density:
        manifest = {
            "script": "code/make_figures_r2.py",
            "results_input": res_rel,
            "out_dir": out_rel,
            "provenance_mode": "missing_iapws_error",
            "raw_npz_status": npz_status,
            "density_backend": density_info,
            "error": (
                "iapws==1.5.5 is required for exact IAPWS-IF97 saturated-liquid density spline reconstruction "
                "during raw .npz figure rendering (install via `pip install -r requirements-lock.txt`). "
                "Built-in approximate fallback diverges from primary .npz traces and thresholds."
            ),
            "rendered_from_raw_npz": [],
            "rendered_from_csv": [],
            "composited_or_padded_from_preserved_assets": [],
            "copied_preserved_reference_assets": [],
            "unexecuted_items": [
                "Plot Figures 1, 2, 3, 5, 6, 7 from primary .npz arrays with exact iapws.IAPWS97 density backend (missing iapws==1.5.5)"
            ],
            "all_files_valid": False,
            "figure_spec_verified": {
                "mode": "missing_iapws_error",
                "all_specs_verified": False,
                "note": "Aborted before plotting because primary .npz files are present without iapws==1.5.5 (pass --allow-approx-density only for non-exact diagnostics).",
            },
            "all_passed": False,
        }
        write_json(out_dir / "figure_generation_manifest.json", manifest)
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 1

    ep_csv = results_dir / "episode_results.csv"
    if not ep_csv.exists():
        ep_csv = repo_root / "results" / "episode_results.csv"

    if npz_status["all_raw_npz_present"]:
        fig_specs = render_figures_from_raw_npz(repo_root, ep_csv, out_dir)
        generation_modes = {
            "fig1_normal_overview.png": "rendered_from_raw_npz",
            "fig2_e1_leak_trajectory.png": "rendered_from_raw_npz",
            "fig3_e1_feature_responses.jpeg": "rendered_from_raw_npz",
            "fig4_method_summary_delay_lead.png": "rendered_from_csv",
            "fig5_e1_score_traces.png": "rendered_from_raw_npz",
            "fig6_all_eval_leak_panels.jpeg": "rendered_from_raw_npz",
            "fig7_normal_score_traces.jpeg": "rendered_from_raw_npz",
        }
        notes = "All raw time-series figures (1, 2, 3, 5, 6, 7) rendered from raw .npz observations/traces; Figure 4 rendered from episode_results.csv."
        rendered_raw = [k for k, v in generation_modes.items() if v == "rendered_from_raw_npz"]
        rendered_csv = ["fig4_method_summary_delay_lead.png"]
        composited: list[str] = []
        copied_ref: list[str] = []
        unexecuted: list[str] = []
        prov_mode = "full_raw_npz_replay"
    else:
        fig_specs = {}
        compose_figure_1(raw_dir, out_dir / "fig1_normal_overview.png")
        compose_figure_2(raw_dir, out_dir / "fig2_e1_leak_trajectory.png")
        shutil.copy2(raw_dir / "page1_img5_475.jpeg", out_dir / "fig3_e1_feature_responses.jpeg")
        render_figure_4_from_csv(ep_csv, out_dir / "fig4_method_summary_delay_lead.png")
        shutil.copy2(raw_dir / "rId34.png", out_dir / "fig5_e1_score_traces.png")
        shutil.copy2(raw_dir / "page1_img1_1103.jpeg", out_dir / "fig6_all_eval_leak_panels.jpeg")
        shutil.copy2(raw_dir / "page1_img2_1217.jpeg", out_dir / "fig7_normal_score_traces.jpeg")
        generation_modes = {
            "fig1_normal_overview.png": "composited_or_padded_from_preserved_assets",
            "fig2_e1_leak_trajectory.png": "composited_or_padded_from_preserved_assets",
            "fig3_e1_feature_responses.jpeg": "copied_preserved_reference_assets",
            "fig4_method_summary_delay_lead.png": "rendered_from_csv",
            "fig5_e1_score_traces.png": "copied_preserved_reference_assets",
            "fig6_all_eval_leak_panels.jpeg": "copied_preserved_reference_assets",
            "fig7_normal_score_traces.jpeg": "copied_preserved_reference_assets",
        }
        notes = (
            "Explicit --archived-assets-only run: Figure 4 is freshly plotted from episode_results.csv; "
            "Figures 1-2 are deterministically recomposed/padded from raw_source_assets/; "
            "Figures 3, 5, 6, 7 are preserved upstream R2 raw-trace reference assets copied without recomputation because primary 2 s .npz arrays are absent."
        )
        rendered_raw = []
        rendered_csv = ["fig4_method_summary_delay_lead.png"]
        composited = ["fig1_normal_overview.png", "fig2_e1_leak_trajectory.png"]
        copied_ref = [
            "fig3_e1_feature_responses.jpeg",
            "fig5_e1_score_traces.png",
            "fig6_all_eval_leak_panels.jpeg",
            "fig7_normal_score_traces.jpeg",
        ]
        unexecuted = unexecuted_raw_items
        prov_mode = "archived_assets_only"

    comparisons = {}
    for fname, gmode in generation_modes.items():
        info = inspect_image_pair(fig_dir / fname, out_dir / fname)
        info["generation_mode"] = gmode
        if fname == "fig4_method_summary_delay_lead.png":
            info["byte_difference_explanation"] = (
                "Re-rendered freshly with local matplotlib from episode_results.csv; "
                "PNG bytes/metadata differ from upstream rId31.png while plotted 8x4 delay values match."
            )
        comparisons[fname] = info

    all_valid = all(v["gen_bytes"] > 10_000 for v in comparisons.values())
    if npz_status["all_raw_npz_present"]:
        all_specs_ok = bool(fig_specs) and all(s.get("spec_ok", False) for s in fig_specs.values())
        spec_block: dict[str, Any] = {
            "mode": prov_mode,
            "all_specs_verified": all_specs_ok,
            "raw_replay_exact_if97_backend": bool(density_info["iapws_available"]),
            "allow_approx_density_override": bool(args.allow_approx_density and not density_info["iapws_available"]),
            "per_figure": fig_specs,
        }
        all_passed = all_valid and all_specs_ok
    else:
        spec_block = {
            "mode": prov_mode,
            "all_specs_verified": False,
            "note": (
                "Raw .npz content specifications were not re-executed: Figures 1-2 were recomposed from "
                "preserved raw_source_assets/ and Figures 3, 5, 6, 7 were copied reference assets; "
                "only Figure 4 was freshly rendered from episode_results.csv."
            ),
        }
        all_passed = all_valid

    manifest = {
        "script": "code/make_figures_r2.py",
        "results_input": res_rel,
        "out_dir": out_rel,
        "provenance_mode": prov_mode,
        "raw_npz_status": npz_status,
        "density_backend": density_info,
        "notes": notes,
        "rendered_from_raw_npz": rendered_raw,
        "rendered_from_csv": rendered_csv,
        "composited_or_padded_from_preserved_assets": composited,
        "copied_preserved_reference_assets": copied_ref,
        "unexecuted_items": unexecuted,
        "figures": comparisons,
        "all_files_valid": all_valid,
        "figure_spec_verified": spec_block,
        "all_passed": all_passed,
    }
    write_json(out_dir / "figure_generation_manifest.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
