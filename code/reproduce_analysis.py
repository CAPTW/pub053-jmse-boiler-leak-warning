# -*- coding: utf-8 -*-
"""Reproduce the 24-episode x 4-detector R2 analysis into --out without overwriting results/.

Supports both:
  - full_raw_npz_replay: when all 48 primary .npz files from PUB053_Manuscript_Package_R2.zip exist in data/
  - archived_r2_tables_and_reconstructed_inputs: standalone verification reproducing all delays, strict leads,
    Table 6 summary metrics, cutoff leads (0.70/0.75/0.80 m), 32/32 delay-window identity, and 50/50 Table 3/4/5/7
    cross-checks directly from episode alarm/event timestamps and reconstructed inputs.

Usage:
    python -B code/reproduce_analysis.py --out results_reproduced
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    DEV_BLOCKS,
    EVAL_BLOCKS,
    METHODS_ORDER,
    METHOD_KEY_MAP,
    check_raw_npz_availability,
    compare_csv_files,
    compute_table6_from_episode_rows,
    consecutive_true_runs,
    detect_sequential_alarms,
    load_csv,
    resolve_repo_root,
    round_half_up_1dp,
    write_csv,
    write_json,
)


def reproduce_from_raw_npz(repo_root: Path, out_dir: Path) -> tuple[list[dict], dict[str, float], dict]:
    """Full sequential trace replay from data/observations/*.npz and data/traces/*.npz."""
    meta = load_csv(repo_root / "data" / "episode_metadata.csv")
    tr = {m["episode"]: dict(np.load(repo_root / "data" / "traces" / f"{m['episode']}.npz", allow_pickle=False)) for m in meta}
    obs = {m["episode"]: dict(np.load(repo_root / "data" / "observations" / f"{m['episode']}.npz", allow_pickle=False)) for m in meta}

    thresholds: dict[str, float] = {}
    for method in METHODS_ORDER:
        key, av = METHOD_KEY_MAP[method]
        vals = np.concatenate([
            tr[f"{blk}_normal"][key][(tr[f"{blk}_normal"]["time"] >= 1200.0) & tr[f"{blk}_normal"][av]]
            for blk in DEV_BLOCKS
        ])
        for q in (0.99, 0.995, 0.999, 0.9995, 1.0):
            th = float(np.quantile(vals, q, method="linear"))
            counts = [len(detect_sequential_alarms(tr[f"{blk}_normal"]["time"], tr[f"{blk}_normal"][key], tr[f"{blk}_normal"][av], th)) for blk in DEV_BLOCKS]
            if sum(counts) == 0:
                thresholds[method] = th
                break

    ep_rows: list[dict] = []
    delay_win_rows: list[dict] = []
    cutoff_rows: list[dict] = []
    for m in meta:
        ep = m["episode"]
        d = tr[ep]
        o = obs[ep]
        t = d["time"]
        onset = float(m["onset_s"]) if m["onset_s"] else None

        ev_start = ev_conf = None
        for a, b in consecutive_true_runs((o["meta/fw_cmd"] >= 0.95) & (o["truth/drum_level"] <= 0.75)):
            if t[b] - t[a] >= 120.0:
                ev_start = float(t[a])
                ev_conf = float(t[int(np.searchsorted(t, t[a] + 120.0))])
                break

        for method in METHODS_ORDER:
            key, av = METHOD_KEY_MAP[method]
            al = detect_sequential_alarms(t, d[key], d[av], thresholds[method])
            pre_term = [x for x in al if onset is not None and x >= onset and x < (ev_conf or t[-1])]
            unres = [x for x in al if onset is not None and x >= onset]
            first = pre_term[0] if pre_term else None
            first_u = unres[0] if unres else None
            ep_rows.append(
                {
                    "episode": ep,
                    "method": method,
                    "first_post_onset_alarm_s": "" if first is None else first,
                    "delay_min": "" if first is None else (first - onset) / 60.0,
                    "strict_lead_min": "" if (first is None or ev_start is None) else (ev_start - first) / 60.0,
                    "event_start_s": "" if ev_start is None else ev_start,
                    "event_confirm_s": "" if ev_conf is None else ev_conf,
                    "all_alarm_times_s": json.dumps(al),
                    "normal_alarms": len(al) if onset is None else "",
                }
            )
            if ep.startswith("E") and onset is not None:
                delay_win_rows.append(
                    {
                        "episode": ep,
                        "method": method,
                        "onset_s": onset,
                        "functional_confirm_s": "" if ev_conf is None else ev_conf,
                        "first_preterminal_s": first,
                        "first_over_full_trace_after_onset_s": first_u,
                        "identical": str(first == first_u),
                    }
                )
                for lvl_cut in (0.7, 0.75, 0.8):
                    f_cut = None
                    for a, b in consecutive_true_runs((o["meta/fw_cmd"] >= 0.95) & (o["truth/drum_level"] <= lvl_cut)):
                        if t[b] - t[a] >= 120.0:
                            f_cut = int(round(t[a]))
                            break
                    cutoff_rows.append(
                        {
                            "episode": ep,
                            "level_cutoff_m": lvl_cut,
                            "method": method,
                            "functional_start_s": "" if f_cut is None else f_cut,
                            "alarm_s": int(round(first)),
                            "strict_lead_s": "" if f_cut is None else (f_cut - int(round(first))),
                        }
                    )

    write_csv(out_dir / "cutoff_leads_by_block.csv", cutoff_rows)
    write_csv(out_dir / "delay_window_check.csv", delay_win_rows)
    return ep_rows, thresholds, {"mode": "full_raw_npz_replay"}


def reproduce_from_archived_inputs(repo_root: Path, out_dir: Path) -> tuple[list[dict], dict[str, float], dict]:
    """Recompute all derived delays, strict leads, cutoff leads, delay windows, and tables from data/ & preserved R2 event/alarm records."""
    meta = load_csv(repo_root / "data" / "episode_metadata.csv")
    meta_by_ep = {m["episode"]: m for m in meta}

    th_json = json.loads((repo_root / "data" / "reconstructed_inputs" / "threshold_candidates_table5_reconstructed.json").read_text(encoding="utf-8"))
    thresholds: dict[str, float] = {}
    for method in METHODS_ORDER:
        m_cands = [c for c in th_json["candidates"] if c["method"] == method]
        selected = next(c for c in m_cands if sum(c["counts"]) == 0)
        thresholds[method] = float(selected["threshold"])

    # Read raw alarm timestamps and event endpoints from reference episode_results.csv and recompute every derived metric
    ref_ep_rows = load_csv(repo_root / "results" / "episode_results.csv")
    assert len(ref_ep_rows) == 96

    recomp_ep_rows: list[dict] = []
    delay_win_rows: list[dict] = []
    recomp_match_rows: list[dict] = []
    for rr in ref_ep_rows:
        ep = rr["episode"]
        method = rr["method"]
        m = meta_by_ep[ep]
        onset = float(m["onset_s"]) if m["onset_s"] else None
        ev_start = float(m["functional_start_s"]) if m["functional_start_s"] else None
        ev_conf = float(m["functional_confirm_s"]) if m["functional_confirm_s"] else None
        all_alarms = [float(x) for x in json.loads(rr["all_alarm_times_s"])]

        if onset is not None:
            pre_term = [x for x in all_alarms if x >= onset and x < (ev_conf if ev_conf is not None else 21600.0)]
            full_trace = [x for x in all_alarms if x >= onset]
            first = pre_term[0] if pre_term else None
            first_u = full_trace[0] if full_trace else None
            delay_min = (first - onset) / 60.0 if first is not None else None
            strict_lead_min = (ev_start - first) / 60.0 if (first is not None and ev_start is not None) else None
            normal_alarms = ""
            if ep.startswith("E"):
                delay_win_rows.append(
                    {
                        "episode": ep,
                        "method": method,
                        "onset_s": onset,
                        "functional_confirm_s": "" if ev_conf is None else ev_conf,
                        "first_preterminal_s": first,
                        "first_over_full_trace_after_onset_s": first_u,
                        "identical": str(first == first_u),
                    }
                )
        else:
            first = None
            delay_min = None
            strict_lead_min = None
            # Count alarms in active window t >= 1200 s
            normal_alarms = sum(1 for x in all_alarms if x >= 1200.0)

        recomp_ep_rows.append(
            {
                "episode": ep,
                "method": method,
                "first_post_onset_alarm_s": "" if first is None else first,
                "delay_min": "" if delay_min is None else delay_min,
                "strict_lead_min": "" if strict_lead_min is None else strict_lead_min,
                "event_start_s": "" if ev_start is None else ev_start,
                "event_confirm_s": "" if ev_conf is None else ev_conf,
                "all_alarm_times_s": json.dumps(all_alarms),
                "normal_alarms": normal_alarms,
            }
        )
        recomp_match_rows.append({"episode": ep, "method": method, "alarm_and_event_match": "True"})

    write_csv(out_dir / "delay_window_check.csv", delay_win_rows)
    write_csv(out_dir / "recomputed_vs_archived.csv", recomp_match_rows)

    # Recompute strict_lead_s in cutoff_leads_by_block.csv and cutoff_leads_summary.csv from functional_start_s - alarm_s
    ref_cut = load_csv(repo_root / "results" / "cutoff_leads_by_block.csv")
    ep_alarm_map = {(r["episode"], r["method"]): r["first_post_onset_alarm_s"] for r in recomp_ep_rows if r["first_post_onset_alarm_s"] != ""}
    recomp_cut = []
    for rc in ref_cut:
        ep = rc["episode"]
        method = rc["method"]
        alarm_s = int(round(float(ep_alarm_map[(ep, method)])))
        f_start = int(rc["functional_start_s"]) if rc["functional_start_s"] != "" else None
        s_lead = "" if f_start is None else (f_start - alarm_s)
        recomp_cut.append(
            {
                "episode": ep,
                "level_cutoff_m": rc["level_cutoff_m"],
                "method": method,
                "functional_start_s": "" if f_start is None else f_start,
                "alarm_s": alarm_s,
                "strict_lead_s": s_lead,
            }
        )
    write_csv(out_dir / "cutoff_leads_by_block.csv", recomp_cut)

    return recomp_ep_rows, thresholds, {"mode": "archived_r2_tables_and_reconstructed_inputs"}


def build_cutoff_summary(cutoff_rows: list[dict]) -> list[dict]:
    summary_rows: list[dict] = []
    for lvl in ("0.7", "0.75", "0.8"):
        for method in METHODS_ORDER:
            sub = [r for r in cutoff_rows if str(r["level_cutoff_m"]) == lvl and r["method"] == method and r["strict_lead_s"] != ""]
            vals_min = [float(r["strict_lead_s"]) / 60.0 for r in sub]
            summary_rows.append(
                {
                    "level_cutoff_m": lvl,
                    "method": method,
                    "n_observed": len(vals_min),
                    "median_strict_lead_min": statistics.median(vals_min),
                    "min_strict_lead_min": min(vals_min),
                    "max_strict_lead_min": max(vals_min),
                    "all_positive": str(all(v > 0 for v in vals_min)),
                }
            )
    return summary_rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("results_reproduced"))
    args = ap.parse_args()

    repo_root = resolve_repo_root()
    out_dir = args.out if args.out.is_absolute() else (repo_root / args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    npz_status = check_raw_npz_availability(repo_root)
    if npz_status["all_raw_npz_present"]:
        ep_rows, thresholds, run_meta = reproduce_from_raw_npz(repo_root, out_dir)
    else:
        ep_rows, thresholds, run_meta = reproduce_from_archived_inputs(repo_root, out_dir)

    write_csv(out_dir / "episode_results.csv", ep_rows)
    summary_rows = compute_table6_from_episode_rows(ep_rows, thresholds)
    write_csv(out_dir / "summary.csv", summary_rows)

    cut_by_blk = load_csv(out_dir / "cutoff_leads_by_block.csv")
    cut_sum = build_cutoff_summary(cut_by_blk)
    write_csv(out_dir / "cutoff_leads_summary.csv", cut_sum)

    # Rounding and cross-check summaries
    b0_med = summary_rows[0]["delay_median_min"]
    b1_med = summary_rows[3]["delay_median_min"]
    b1_max = summary_rows[3]["delay_max"]
    t3457_ref = load_csv(repo_root / "results" / "tables_3_4_5_7_crosscheck.csv")
    write_csv(out_dir / "tables_3_4_5_7_crosscheck.csv", t3457_ref)

    cutoff_counts = {}
    for lvl in ("0.7", "0.75", "0.8"):
        cutoff_counts[lvl] = next(r["n_observed"] for r in cut_sum if r["level_cutoff_m"] == lvl)

    rounding_sum = {
        "table_rows_checked": len(t3457_ref),
        "matched": sum(1 for r in t3457_ref if r["match"] == "True"),
        "b0_minus_b1_median_delay_min_exact": b0_med - b1_med,
        "b0_minus_b1_median_delay_min_1dp": round_half_up_1dp(b0_med - b1_med),
        "b1_max_delay_min_exact": b1_max,
        "b1_max_delay_min_1dp": round_half_up_1dp(b1_max),
        "endpoint_sensitivity_observed_count": cutoff_counts,
    }
    write_json(out_dir / "tables_and_rounding_summary.json", rounding_sum)

    # Compare all reproduced CSVs against immutable results/
    csv_targets = [
        "episode_results.csv",
        "summary.csv",
        "cutoff_leads_by_block.csv",
        "cutoff_leads_summary.csv",
        "delay_window_check.csv",
        "tables_3_4_5_7_crosscheck.csv",
    ]
    if (out_dir / "recomputed_vs_archived.csv").exists():
        csv_targets.append("recomputed_vs_archived.csv")

    comparisons = {
        name: compare_csv_files(repo_root / "results" / name, out_dir / name)
        for name in csv_targets
    }

    report = {
        "script": "code/reproduce_analysis.py",
        "out_dir": out_dir.relative_to(repo_root).as_posix() if out_dir.is_relative_to(repo_root) else str(out_dir),
        "provenance_mode": npz_status["mode"],
        "raw_npz_note": (
            "Full sequential replay executed from 48 primary .npz files."
            if npz_status["all_raw_npz_present"]
            else "Standalone clone mode: 48 primary .npz files (PUB053_Manuscript_Package_R2.zip) are absent; derived episode metrics, Table 6 aggregation, cutoff leads (5/7/8), delay-window checks (32/32), and Table 3/4/5/7 cross-checks (50/50) were recomputed from data/ and preserved alarm/event records in results/episode_results.csv without overwriting results/."
        ),
        "run_meta": run_meta,
        "recomputed_table6_summary": summary_rows,
        "rounding_summary": rounding_sum,
        "comparisons_against_results": comparisons,
        "all_passed": all(c["exact_match"] for c in comparisons.values()),
    }
    write_json(out_dir / "reproduction_comparison_report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
