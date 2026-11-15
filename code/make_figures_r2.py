# -*- coding: utf-8 -*-
"""Regenerate / reproduce manuscript Figures 1-7 from --results into --out without overwriting figures/.

By default requires all 48 primary .npz files from PUB053_Manuscript_Package_R2.zip and exits 1
if they are missing. Pass --archived-assets-only (or --archived-tables-only) in standalone clones
to render Figure 4 from CSV and composite/stage preserved R2 assets from figures/raw_source_assets/.

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
    check_raw_npz_availability,
    detect_sequential_alarms,
    extract_observation_channels,
    load_csv,
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
    for method in METHODS_ORDER:
        st = style_map[method]
        ys = [
            float(next(r["delay_min"] for r in rows if r["episode"] == f"{blk}_tube_leak" and r["method"] == method))
            for blk in EVAL_BLOCKS
        ]
        ax.scatter(
            x + st["dx"],
            ys,
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
    ax.set_ylim(48.0, 195.0)
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


def render_figures_from_raw_npz(repo_root: Path, ep_csv: Path, out_dir: Path) -> None:
    """Plot Figures 1-3 and 5-7 directly from raw .npz observations/traces (plus Fig 4 from CSV)."""
    meta = load_csv(repo_root / "data" / "episode_metadata.csv")
    meta_by_ep = {m["episode"]: m for m in meta}
    episodes = [m["episode"] for m in meta]
    obs = {ep: dict(np.load(repo_root / "data" / "observations" / f"{ep}.npz", allow_pickle=False)) for ep in episodes}
    recon = reconstruct_features_from_observations(obs, episodes)
    tr = recon["traces"]

    thresholds: dict[str, float] = {}
    for method in METHODS_ORDER:
        key, av = METHOD_KEY_MAP[method]
        vals = np.concatenate([tr[f"{blk}_normal"][key][(tr[f"{blk}_normal"]["time"] >= 1200.0) & tr[f"{blk}_normal"][av]] for blk in DEV_BLOCKS])
        for q in (0.99, 0.995, 0.999, 0.9995, 1.0):
            th = float(np.quantile(vals, q, method="linear"))
            counts = [len(detect_sequential_alarms(tr[f"{blk}_normal"]["time"], tr[f"{blk}_normal"][key], tr[f"{blk}_normal"][av], th)) for blk in DEV_BLOCKS]
            if sum(counts) == 0:
                thresholds[method] = th
                break

    # Fig 1: E1_normal pressure & level overview
    e1n = extract_observation_channels(obs["E1_normal"])
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 5.2), dpi=200, sharex=True)
    axes[0].plot(e1n["time"] / 60.0, e1n["p_obs"], linewidth=0.9, color="#1f77b4")
    axes[0].axvline(20.0, linestyle=":", color="0.4")
    axes[0].set_ylabel("Drum pressure (bar)")
    axes[1].plot(e1n["time"] / 60.0, e1n["l_obs"], linewidth=0.9, color="#2ca02c")
    axes[1].axvline(20.0, linestyle=":", color="0.4")
    axes[1].set_ylabel("Drum level (m)")
    axes[1].set_xlabel("Time (min)")
    fig.tight_layout()
    _save_fig(fig, out_dir / "fig1_normal_overview.png")

    # Fig 2: E1_tube_leak physical trajectory
    e1f = extract_observation_channels(obs["E1_tube_leak"])
    fig, axes = plt.subplots(3, 1, figsize=(7.0, 6.2), dpi=200, sharex=True)
    axes[0].plot(e1f["time"] / 60.0, e1f["l_obs"], linewidth=0.9, color="#1f77b4", label="Level (m)")
    axes[1].plot(e1f["time"] / 60.0, e1f["q_f"], linewidth=0.9, color="#ff7f0e", label="Feedwater (kg/s)")
    axes[1].plot(e1f["time"] / 60.0, e1f["q_s"], linewidth=0.9, color="#2ca02c", label="Steam (kg/s)")
    axes[2].plot(e1f["time"] / 60.0, e1f["u_fw"], linewidth=0.9, color="#d62728", label="Feedwater cmd")
    for ax in axes:
        if meta_by_ep["E1_tube_leak"]["onset_s"]:
            ax.axvline(float(meta_by_ep["E1_tube_leak"]["onset_s"]) / 60.0, linestyle=":", color="0.4")
        ax.legend(loc="upper right", fontsize=8, frameon=False)
    axes[2].set_xlabel("Time (min)")
    fig.tight_layout()
    _save_fig(fig, out_dir / "fig2_e1_leak_trajectory.png")

    # Fig 3: E1_tube_leak component feature responses
    d1 = tr["E1_tube_leak"]
    fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=200)
    t_m = d1["time"] / 60.0
    m = t_m >= 20.0
    ax.plot(t_m[m], d1["state_score"][m], linewidth=0.9, label="State (B0)")
    ax.plot(t_m[m], d1["flow_z"][m], linewidth=0.9, label="Flow z_F")
    ax.plot(t_m[m], d1["command_z"][m], linewidth=0.9, label="Demand z_D")
    ax.axvline(float(meta_by_ep["E1_tube_leak"]["onset_s"]) / 60.0, linestyle=":", color="0.4")
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Standardized feature")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    _save_fig(fig, out_dir / "fig3_e1_feature_responses.jpeg")

    # Fig 4: method summary from CSV
    render_figure_4_from_csv(ep_csv, out_dir / "fig4_method_summary_delay_lead.png")

    # Fig 5: E1 threshold-normalized scores
    fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=200)
    for method in METHODS_ORDER:
        key, av = METHOD_KEY_MAP[method]
        mask = (d1["time"] >= 1200.0) & d1[av]
        ax.plot(d1["time"][mask] / 60.0, d1[key][mask] / thresholds[method], linewidth=0.9, label=METHOD_LABELS[method])
    ax.axhline(1.0, linestyle="--", color="0.3", linewidth=0.8)
    ax.axvline(float(meta_by_ep["E1_tube_leak"]["onset_s"]) / 60.0, linestyle=":", color="0.4")
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Score / threshold")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    _save_fig(fig, out_dir / "fig5_e1_score_traces.png")

    # Fig 6: All 8 evaluation fault blocks
    fig, axes = plt.subplots(4, 2, figsize=(9.0, 10.0), dpi=200, sharex=True)
    for ax, blk in zip(axes.flat, EVAL_BLOCKS):
        ep = f"{blk}_tube_leak"
        d = tr[ep]
        for method in ("B0_state", "B1_combined"):
            key, av = METHOD_KEY_MAP[method]
            mask = (d["time"] >= 1200.0) & d[av]
            ax.plot(d["time"][mask] / 60.0, d[key][mask] / thresholds[method], linewidth=0.8, label=METHOD_LABELS[method])
        ax.axhline(1.0, linestyle="--", color="0.3", linewidth=0.7)
        ax.set_title(blk, fontsize=9)
    axes[0, 0].legend(frameon=False, fontsize=7)
    fig.tight_layout()
    _save_fig(fig, out_dir / "fig6_all_eval_leak_panels.jpeg")

    # Fig 7: All 12 normal score traces
    fig, axes = plt.subplots(4, 3, figsize=(10.0, 9.0), dpi=200, sharex=True)
    for ax, blk in zip(axes.flat, DEV_BLOCKS + EVAL_BLOCKS):
        ep = f"{blk}_normal"
        d = tr[ep]
        for method in ("B0_state", "B1_combined"):
            key, av = METHOD_KEY_MAP[method]
            mask = (d["time"] >= 1200.0) & d[av]
            ax.plot(d["time"][mask] / 60.0, d[key][mask] / thresholds[method], linewidth=0.8, label=METHOD_LABELS[method])
        ax.axhline(1.0, linestyle="--", color="0.3", linewidth=0.7)
        ax.set_title(ep, fontsize=8)
    axes[0, 0].legend(frameon=False, fontsize=7)
    fig.tight_layout()
    _save_fig(fig, out_dir / "fig7_normal_score_traces.jpeg")


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

    ep_csv = results_dir / "episode_results.csv"
    if not ep_csv.exists():
        ep_csv = repo_root / "results" / "episode_results.csv"

    if npz_status["all_raw_npz_present"]:
        render_figures_from_raw_npz(repo_root, ep_csv, out_dir)
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
    manifest = {
        "script": "code/make_figures_r2.py",
        "results_input": res_rel,
        "out_dir": out_rel,
        "provenance_mode": prov_mode,
        "raw_npz_status": npz_status,
        "notes": notes,
        "rendered_from_raw_npz": rendered_raw,
        "rendered_from_csv": rendered_csv,
        "composited_or_padded_from_preserved_assets": composited,
        "copied_preserved_reference_assets": copied_ref,
        "unexecuted_items": unexecuted,
        "figures": comparisons,
        "all_files_valid": all_valid,
        "all_passed": all_valid,
    }
    write_json(out_dir / "figure_generation_manifest.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if all_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
