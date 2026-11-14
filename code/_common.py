# -*- coding: utf-8 -*-
"""Shared mathematical definitions, provenance checks, and CSV/JSON helpers for PUB-053 R2 analysis."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import numpy as np

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
    missing_examples: list[str] = []
    for row in meta:
        ep = row["episode"]
        obs_p = repo_root / "data" / "observations" / f"{ep}.npz"
        tr_p = repo_root / "data" / "traces" / f"{ep}.npz"
        if obs_p.exists():
            obs_present += 1
        elif len(missing_examples) < 4:
            missing_examples.append(obs_p.relative_to(repo_root).as_posix())
        if tr_p.exists():
            tr_present += 1
        elif len(missing_examples) < 6:
            missing_examples.append(tr_p.relative_to(repo_root).as_posix())

    expected_per_dir = len(meta)
    all_present = obs_present == expected_per_dir and tr_present == expected_per_dir
    return {
        "mode": "full_raw_npz_replay" if all_present else "archived_r2_tables_and_reconstructed_inputs",
        "all_raw_npz_present": all_present,
        "observations_npz_found": obs_present,
        "traces_npz_found": tr_present,
        "expected_per_kind": expected_per_dir,
        "total_expected_npz": expected_per_dir * 2,
        "total_found_npz": obs_present + tr_present,
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
    q_f: np.ndarray,
    u_f: np.ndarray,
    fit_params: dict[str, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate OLS mass-balance/demand references and standardized flow/demand residuals."""
    r_ref = fit_params["a0"] + fit_params["a1"] * q_s + fit_params["a2"] * l_dev
    u_ref = fit_params["b0"] + fit_params["b1"] * q_s
    z_f = np.abs((q_f - r_ref) / fit_params["sigma_F"])
    z_d = np.abs((u_f - u_ref) / fit_params["sigma_D"])
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


def compare_csv_files(ref_path: Path, gen_path: Path, tol: float = 1e-12) -> dict[str, Any]:
    """Compare two CSV tables row-by-row and report max numeric difference and exact mismatches."""
    ref_rows = load_csv(ref_path)
    gen_rows = load_csv(gen_path)
    if len(ref_rows) != len(gen_rows):
        return {
            "ref": ref_path.as_posix(),
            "gen": gen_path.as_posix(),
            "row_count_match": False,
            "ref_rows": len(ref_rows),
            "gen_rows": len(gen_rows),
            "exact_match": False,
            "max_abs_diff": None,
        }
    max_diff = 0.0
    mismatches: list[dict[str, Any]] = []
    for idx, (rr, gr) in enumerate(zip(ref_rows, gen_rows)):
        for k in rr.keys():
            rv = rr[k]
            gv = gr.get(k, "")
            if rv == gv:
                continue
            try:
                rf = float(rv)
                gf = float(gv)
                diff = abs(rf - gf)
                max_diff = max(max_diff, diff)
                if diff > tol:
                    mismatches.append({"row": idx, "col": k, "ref": rv, "gen": gv, "diff": diff})
            except ValueError:
                mismatches.append({"row": idx, "col": k, "ref": rv, "gen": gv, "diff": "string_mismatch"})
    return {
        "row_count_match": True,
        "rows_checked": len(ref_rows),
        "exact_match": len(mismatches) == 0,
        "max_abs_diff": max_diff,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:5],
    }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
