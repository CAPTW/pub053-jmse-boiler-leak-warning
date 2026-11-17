# -*- coding: utf-8 -*-
"""Verify EWLS feature parameters, threshold candidates, normal persistence, and crossing order.

By default this script requires all 48 primary .npz files from PUB053_Manuscript_Package_R2.zip
under data/observations/ and data/traces/ and exits 1 if they are missing.
Pass --archived-tables-only to explicitly run algebraic and internal consistency checks on
archived results/ tables and data/reconstructed_inputs/ in standalone public clones.

Usage:
    python -B code/verify_features.py --out results_reproduced
    python -B code/verify_features.py --archived-tables-only --out results_reproduced
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    DEV_BLOCKS,
    EVAL_BLOCKS,
    METHODS_ORDER,
    METHOD_KEY_MAP,
    check_raw_npz_availability,
    compare_csv_files,
    compute_ewls_residuals,
    detect_sequential_alarms,
    get_density_backend_info,
    load_csv,
    max_exceedance_span_s,
    reconstruct_features_from_observations,
    resolve_repo_root,
    write_csv,
    write_json,
)


def _compare_trace_arrays(
    episodes: list[str],
    recon_traces: dict[str, dict[str, np.ndarray]],
    ref_traces: dict[str, dict[str, np.ndarray]],
    trace_atol: float = 1e-4,
) -> dict[str, Any]:
    """Compare all 24 x 6 reconstructed detector score/availability arrays against archived trace NPZs."""
    float_keys = ("state_score", "flow_z", "command_z", "combined_score")
    bool_keys = ("available_state", "available_flow_command")
    checks: list[dict[str, Any]] = []
    max_abs_diff = 0.0

    for ep in episodes:
        rec = recon_traces[ep]
        ref = ref_traces[ep]
        for key in float_keys + bool_keys:
            if key not in ref:
                checks.append({"episode": ep, "array": key, "passed": False, "reason": "missing_in_ref_npz", "max_abs_diff": None, "mismatch_count": 1})
                continue
            r_arr = np.asarray(rec[key])
            f_arr = np.asarray(ref[key])
            if r_arr.shape != f_arr.shape:
                checks.append({"episode": ep, "array": key, "passed": False, "reason": f"shape_mismatch:{r_arr.shape}!={f_arr.shape}", "max_abs_diff": None, "mismatch_count": 1})
                continue
            if key in bool_keys:
                mism = int(np.sum(r_arr.astype(bool) != f_arr.astype(bool)))
                checks.append({"episode": ep, "array": key, "passed": mism == 0, "max_abs_diff": float(mism > 0), "mismatch_count": mism})
            else:
                r_f = r_arr.astype(float)
                f_f = f_arr.astype(float)
                fin_r = np.isfinite(r_f)
                fin_f = np.isfinite(f_f)
                fin_mism = int(np.sum(fin_r != fin_f))
                both = fin_r & fin_f
                diffs = np.abs(r_f[both] - f_f[both]) if np.any(both) else np.array([0.0])
                ep_max = float(np.max(diffs))
                max_abs_diff = max(max_abs_diff, ep_max)
                val_mism = int(np.sum(diffs > trace_atol))
                total_mism = fin_mism + val_mism
                checks.append({"episode": ep, "array": key, "passed": total_mism == 0, "max_abs_diff": ep_max, "mismatch_count": total_mism})

    passed_count = sum(1 for c in checks if c["passed"])
    failed = [c for c in checks if not c["passed"]]
    return {
        "total": len(checks),
        "passed": passed_count,
        "all_matched": passed_count == len(checks) and len(checks) == len(episodes) * 6,
        "max_abs_diff": max_abs_diff,
        "tolerance": trace_atol,
        "failed_examples": failed[:10],
    }


def verify_from_raw_npz(repo_root: Path, out_dir: Path, *, trace_atol: float = 1e-4) -> dict[str, Any]:
    """Reconstruct features/scores from data/observations/*.npz and verify against data/traces/*.npz."""
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = load_csv(repo_root / "data" / "episode_metadata.csv")
    meta_by_ep = {m["episode"]: m for m in meta}
    episodes = [m["episode"] for m in meta]
    obs = {ep: dict(np.load(repo_root / "data" / "observations" / f"{ep}.npz", allow_pickle=False)) for ep in episodes}
    tr = {ep: dict(np.load(repo_root / "data" / "traces" / f"{ep}.npz", allow_pickle=False)) for ep in episodes}

    # 1. Reconstruct B0 EWMA, 600 s mass-balance residual r_M, OLS/B0 fit parameters, and 24 x 6 trace arrays
    recon = reconstruct_features_from_observations(obs, episodes)
    recon_traces = recon["traces"]
    fit = recon["fit_params"]
    trace_cmp = _compare_trace_arrays(episodes, recon_traces, tr, trace_atol=trace_atol)

    # Zero-residual algebraic check on refitted parameters
    q_s_probe = np.array([0.85, 1.40])
    l_dev_probe = np.array([0.0, -0.01])
    r_probe = fit["a0"] + fit["a1"] * q_s_probe + fit["a2"] * l_dev_probe
    u_probe = fit["b0"] + fit["b1"] * q_s_probe
    _, _, zf_probe, zd_probe = compute_ewls_residuals(q_s_probe, l_dev_probe, r_probe, u_probe, fit)
    assert float(np.max(np.abs(zf_probe))) < 1e-12 and float(np.max(np.abs(zd_probe))) < 1e-12

    # Compare refitted parameters with data/reconstructed_inputs/ewls_fit_table4_reconstructed.json when present
    fit_ref_path = repo_root / "data" / "reconstructed_inputs" / "ewls_fit_table4_reconstructed.json"
    fit_comparisons: dict[str, Any] = {}
    fit_params_match = True
    if fit_ref_path.exists():
        ewls_ref = json.loads(fit_ref_path.read_text(encoding="utf-8"))
        ref_map = {item["parameter"]: float(item["full_precision_value"]) for item in ewls_ref["parameters"]}
        key_pairs = [("a0", "a0"), ("a1", "a1"), ("a2", "a2"), ("b0", "b0"), ("b1", "b1"), ("sigma_F", "σF"), ("sigma_D", "σD"), ("sigma_l", "σl"), ("sigma_p", "σp")]
        for k_fit, k_ref in key_pairs:
            if k_ref in ref_map:
                diff = abs(fit[k_fit] - ref_map[k_ref])
                matched = diff <= 1e-3
                fit_comparisons[k_ref] = {"recomputed": fit[k_fit], "reference": ref_map[k_ref], "abs_diff": diff, "matched": matched}
                if not matched:
                    fit_params_match = False

    write_json(out_dir / "recomputed_fit_params.json", {"fit_sample_n": recon["fit_sample_n"], "fit_params": fit, "reference_comparison": fit_comparisons})

    # 2. Threshold candidate sweep on development normal episodes D1..D4 (t >= 1200 s) using reconstructed traces
    cands = []
    settings: dict[str, float] = {}
    for method in METHODS_ORDER:
        key, av = METHOD_KEY_MAP[method]
        vals = np.concatenate([
            recon_traces[f"{blk}_normal"][key][(recon_traces[f"{blk}_normal"]["time"] >= 1200.0) & recon_traces[f"{blk}_normal"][av]]
            for blk in DEV_BLOCKS
        ])
        for q in (0.99, 0.995, 0.999, 0.9995, 1.0):
            v = float(np.quantile(vals, q, method="linear"))
            counts = [
                len(detect_sequential_alarms(recon_traces[f"{blk}_normal"]["time"], recon_traces[f"{blk}_normal"][key], recon_traces[f"{blk}_normal"][av], v))
                for blk in DEV_BLOCKS
            ]
            cands.append({"method": method, "quantile": q, "threshold": v, "counts": counts})
            if method not in settings and sum(counts) == 0:
                settings[method] = v

    # 3. Normal persistence spans across all 12 normal episodes
    np_rows = []
    for blk in DEV_BLOCKS + EVAL_BLOCKS:
        ep = f"{blk}_normal"
        d = recon_traces[ep]
        t = d["time"]
        for method in METHODS_ORDER:
            key, av = METHOD_KEY_MAP[method]
            av_mask = (t >= 1200.0) & d[av]
            span = max_exceedance_span_s(t, d[key], d[av], settings[method])
            np_rows.append(
                {
                    "episode": ep,
                    "method": method,
                    "max_exceedance_span_s": span,
                    "score_max": float(np.max(d[key][av_mask])) if np.any(av_mask) else 0.0,
                }
            )
    write_csv(out_dir / "normal_persistence.csv", np_rows)

    # 4. Component crossing timing across evaluation fault episodes E1..E8
    theta_shared = settings["B1_combined"]
    cc_rows = []
    for idx, blk in enumerate(EVAL_BLOCKS, start=1):
        ep = f"{blk}_tube_leak"
        onset = float(meta_by_ep[ep]["onset_s"])
        d = recon_traces[ep]
        t = d["time"]
        av_fc = d["available_flow_command"]
        post = (t >= onset) & av_fc
        f_idx = np.flatnonzero(post & (d["flow_z"] > theta_shared))
        d_idx = np.flatnonzero(post & (d["command_z"] > theta_shared))
        f_cross = float(t[f_idx[0]]) if len(f_idx) > 0 else ""
        d_cross = float(t[d_idx[0]]) if len(d_idx) > 0 else ""
        f_conf_all = [x for x in detect_sequential_alarms(t, d["flow_z"], av_fc, theta_shared) if x >= onset]
        d_conf_all = [x for x in detect_sequential_alarms(t, d["command_z"], av_fc, theta_shared) if x >= onset]
        c_conf_all = [x for x in detect_sequential_alarms(t, d["combined_score"], av_fc, theta_shared) if x >= onset]
        c_conf = c_conf_all[0] if c_conf_all else ""
        flow_pts = ""
        onlyflow_pts = ""
        if c_conf != "":
            win_m = (t >= float(c_conf) - 600.0 - 1e-9) & (t <= float(c_conf) + 1e-9) & av_fc
            flow_pts = int(np.sum(d["flow_z"][win_m] > theta_shared))
            onlyflow_pts = int(np.sum((d["flow_z"][win_m] > theta_shared) & ~(d["command_z"][win_m] > theta_shared)))
        cc_rows.append(
            {
                "block": idx,
                "onset": int(round(onset)),
                "theta": theta_shared,
                "flow_first_cross": f_cross,
                "demand_first_cross": d_cross,
                "flow_first_standalone_sharedtheta_confirm": f_conf_all[0] if f_conf_all else "",
                "demand_first_standalone_sharedtheta_confirm": d_conf_all[0] if d_conf_all else "",
                "combined_confirm": c_conf,
                "flow_crossing_points_in_first_combined_run": flow_pts,
                "onlyflow_crossing_points_in_first_combined_run": onlyflow_pts,
            }
        )
    write_csv(out_dir / "component_crossing_timing.csv", cc_rows)

    # 5. Quantile empirical check
    f_vals = np.concatenate([recon_traces[f"{blk}_normal"]["flow_z"][(recon_traces[f"{blk}_normal"]["time"] >= 1200.0) & recon_traces[f"{blk}_normal"]["available_flow_command"]] for blk in DEV_BLOCKS])
    c_vals = np.concatenate([recon_traces[f"{blk}_normal"]["command_z"][(recon_traces[f"{blk}_normal"]["time"] >= 1200.0) & recon_traces[f"{blk}_normal"]["available_flow_command"]] for blk in DEV_BLOCKS])
    a = np.zeros(1000)
    b = np.ones(1000)
    a[:9] = 10.0
    b[9:18] = 11.0
    q_chk = {
        "observed_max_flow": float(np.max(f_vals)),
        "observed_q99_flow": float(np.quantile(f_vals, 0.99)),
        "observed_q99_demand": float(np.quantile(c_vals, 0.99)),
        "observed_q99_max": float(np.quantile(np.maximum(f_vals, c_vals), 0.99)),
        "counterexample_strict": {
            "Q_F": float(np.quantile(a, 0.99)),
            "Q_D": float(np.quantile(b, 0.99)),
            "Q_max": float(np.quantile(np.maximum(a, b), 0.99)),
        },
    }
    write_json(out_dir / "quantile_claim_check.json", q_chk)
    write_json(out_dir / "threshold_candidates.json", {"source": "full_raw_npz_replay", "selected_thresholds": settings, "candidates": cands})

    flow_first_all_8 = len(cc_rows) == 8 and all(
        r["flow_first_cross"] != "" and r["demand_first_cross"] != "" and float(r["flow_first_cross"]) < float(r["demand_first_cross"])
        for r in cc_rows
    )
    all_passed = bool(trace_cmp["all_matched"] and len(np_rows) == 48 and len(cc_rows) == 8)
    return {
        "density_backend": get_density_backend_info(),
        "trace_array_checks_total": trace_cmp["total"],
        "trace_array_checks_passed": trace_cmp["passed"],
        "all_trace_arrays_matched": trace_cmp["all_matched"],
        "max_trace_array_abs_diff": trace_cmp["max_abs_diff"],
        "failed_trace_arrays": trace_cmp["failed_examples"],
        "fit_sample_n": recon["fit_sample_n"],
        "fit_params_recomputed": fit,
        "fit_parameter_comparisons": fit_comparisons,
        "fit_parameters_match": fit_params_match,
        "threshold_candidates_count": len(cands),
        "selected_thresholds": settings,
        "normal_persistence_rows": len(np_rows),
        "component_crossing_blocks": len(cc_rows),
        "flow_crossed_first_all_8": flow_first_all_8,
        "quantile_dominance_verified": q_chk["observed_max_flow"] < q_chk["observed_q99_demand"],
        "obs_loaded": len(obs),
        "all_passed": all_passed,
    }


def verify_from_archived_inputs(repo_root: Path, out_dir: Path) -> dict:
    """Verify feature/threshold/persistence invariants from reconstructed inputs and preserved R2 tables."""
    rec_dir = repo_root / "data" / "reconstructed_inputs"
    ewls = json.loads((rec_dir / "ewls_fit_table4_reconstructed.json").read_text(encoding="utf-8"))
    th = json.loads((rec_dir / "threshold_candidates_table5_reconstructed.json").read_text(encoding="utf-8"))

    # Verify Table 4 OLS parameters (N = 40,804 = 4 dev blocks * 10,201 post-warm-start samples)
    assert ewls["fit_sample_n"] == 40804
    param_map = {item["parameter"]: float(item["full_precision_value"]) for item in ewls["parameters"]}
    fit = {
        "a0": param_map["a0"],
        "a1": param_map["a1"],
        "a2": param_map["a2"],
        "b0": param_map["b0"],
        "b1": param_map["b1"],
        "sigma_F": param_map["σF"],
        "sigma_D": param_map["σD"],
    }
    q_s_probe = np.array([0.85, 1.40])
    l_dev_probe = np.array([0.0, -0.01])
    q_f_probe = fit["a0"] + fit["a1"] * q_s_probe + fit["a2"] * l_dev_probe
    u_f_probe = fit["b0"] + fit["b1"] * q_s_probe
    _, _, z_f_zero, z_d_zero = compute_ewls_residuals(q_s_probe, l_dev_probe, q_f_probe, u_f_probe, fit)
    assert float(np.max(np.abs(z_f_zero))) < 1e-12 and float(np.max(np.abs(z_d_zero))) < 1e-12

    # Verify Table 5 monotonicity & selected zero-false-alarm development thresholds
    cands = th["candidates"]
    assert len(cands) == 20
    selected: dict[str, float] = {}
    for method in METHODS_ORDER:
        m_cands = [c for c in cands if c["method"] == method]
        qs = [float(c["quantile"]) for c in m_cands]
        ths = [float(c["threshold"]) for c in m_cands]
        assert qs == [0.99, 0.995, 0.999, 0.9995, 1]
        assert all(ths[i] <= ths[i + 1] for i in range(len(ths) - 1)), f"Non-monotone thresholds for {method}"
        first_zero = next(c for c in m_cands if sum(c["counts"]) == 0)
        selected[method] = float(first_zero["threshold"])

    assert abs(selected["Command_only"] - selected["B1_combined"]) < 1e-12
    write_json(
        out_dir / "threshold_candidates.json",
        {
            "source": "data/reconstructed_inputs/threshold_candidates_table5_reconstructed.json",
            "selected_thresholds": selected,
            "candidates": cands,
        },
    )

    # Verify and write normal_persistence.csv, component_crossing_timing.csv, quantile_claim_check.json
    np_rows = load_csv(repo_root / "results" / "normal_persistence.csv")
    assert len(np_rows) == 48
    for r in np_rows:
        span = float(r["max_exceedance_span_s"])
        smax = float(r["score_max"])
        th_val = selected[r["method"]]
        if span > 0.0:
            assert smax > th_val, f"Positive exceedance span requires score_max > threshold in {r}"
    write_csv(out_dir / "normal_persistence.csv", np_rows, list(np_rows[0].keys()))

    cc_rows = load_csv(repo_root / "results" / "component_crossing_timing.csv")
    assert len(cc_rows) == 8
    for r in cc_rows:
        assert float(r["flow_first_cross"]) < float(r["demand_first_cross"]), (
            f"Expected flow component crossing before demand in block {r['block']}"
        )
        assert float(r["demand_first_standalone_sharedtheta_confirm"]) == float(r["demand_first_cross"]) + 600.0
    write_csv(out_dir / "component_crossing_timing.csv", cc_rows, list(cc_rows[0].keys()))

    q_chk = json.loads((repo_root / "results" / "quantile_claim_check.json").read_text(encoding="utf-8"))
    assert q_chk["observed_max_flow"] < q_chk["observed_q99_demand"]
    assert q_chk["counterexample_strict"]["Q_max"] > q_chk["counterexample_strict"]["Q_D"] > q_chk["counterexample_strict"]["Q_F"]
    write_json(out_dir / "quantile_claim_check.json", q_chk)

    return {
        "threshold_candidates_count": len(cands),
        "selected_thresholds": selected,
        "normal_persistence_rows": len(np_rows),
        "component_crossing_blocks": len(cc_rows),
        "flow_crossed_first_all_8": True,
        "quantile_dominance_verified": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("results_reproduced"))
    ap.add_argument(
        "--archived-tables-only",
        action="store_true",
        help="Explicit opt-in to run algebraic/internal checks on archived tables when primary .npz files are absent.",
    )
    ap.add_argument(
        "--allow-approx-density",
        action="store_true",
        help="Allow approximate IAPWS-95 density fallback during raw .npz replay when iapws is absent (not exact).",
    )
    args = ap.parse_args()

    repo_root = resolve_repo_root()
    out_dir = args.out if args.out.is_absolute() else (repo_root / args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_rel = out_dir.relative_to(repo_root).as_posix() if out_dir.is_relative_to(repo_root) else str(out_dir)

    npz_status = check_raw_npz_availability(repo_root)
    density_info = get_density_backend_info()
    unexecuted_raw_items = [
        "Reconstruct B0 EWMA and 600 s mass-balance residual r_M from 24 data/observations/*.npz files",
        "Refit Table 4 OLS and B0 scale parameters on pooled D1_normal..D4_normal monitoring rows",
        "Compare all 144 (24 x 6) reconstructed score/availability arrays against data/traces/*.npz",
        "Recompute Table 5 threshold candidates, normal_persistence.csv, component_crossing_timing.csv, and quantile_claim_check.json from raw traces",
    ]

    if npz_status["all_raw_npz_present"]:
        if not density_info["iapws_available"] and not args.allow_approx_density:
            report = {
                "script": "code/verify_features.py",
                "out_dir": out_rel,
                "provenance_mode": "missing_iapws_error",
                "raw_npz_status": npz_status,
                "density_backend": density_info,
                "error": (
                    "iapws==1.5.5 is required for exact IAPWS-IF97 saturated-liquid density spline reconstruction "
                    "during full_raw_npz_replay (install via `pip install -r requirements-lock.txt`). "
                    "Built-in approximate fallback diverges from primary .npz traces."
                ),
                "recomputed_from_raw_inputs": [],
                "compared_against_reference_results": {},
                "archived_table_internal_checks": {},
                "preserved_or_copied_artifacts": [],
                "unexecuted_items": unexecuted_raw_items,
                "all_passed": False,
            }
            write_json(out_dir / "feature_verification_report.json", report)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 1
        details = verify_from_raw_npz(repo_root, out_dir)
        comparisons = {
            "normal_persistence.csv": compare_csv_files(repo_root / "results" / "normal_persistence.csv", out_dir / "normal_persistence.csv"),
            "component_crossing_timing.csv": compare_csv_files(
                repo_root / "results" / "component_crossing_timing.csv",
                out_dir / "component_crossing_timing.csv",
                key_cols=("block",),
            ),
        }
        all_passed = bool(
            details["all_passed"]
            and details.get("fit_parameters_match", True)
            and all(c["exact_match"] for c in comparisons.values())
        )
        report = {
            "script": "code/verify_features.py",
            "out_dir": out_rel,
            "provenance_mode": "full_raw_npz_replay",
            "raw_npz_status": npz_status,
            "density_backend": density_info,
            "raw_npz_note": "Executed full raw observation reconstruction (EWMA, r_M, OLS refit, 144/144 trace array comparison), threshold sweep, normal persistence, and component crossing checks from all 48 .npz files.",
            "recomputed_from_raw_inputs": [
                "recomputed_fit_params.json",
                "threshold_candidates.json",
                "normal_persistence.csv",
                "component_crossing_timing.csv",
                "quantile_claim_check.json",
            ],
            "compared_against_reference_results": {
                **comparisons,
                "trace_arrays_144": {
                    "total": details["trace_array_checks_total"],
                    "passed": details["trace_array_checks_passed"],
                    "exact_match": details["all_trace_arrays_matched"],
                    "max_abs_diff": details["max_trace_array_abs_diff"],
                },
                "fit_parameters": details["fit_parameter_comparisons"],
            },
            "archived_table_internal_checks": {},
            "preserved_or_copied_artifacts": [],
            "unexecuted_items": [],
            "details": details,
            "comparisons_against_results": comparisons,
            "all_passed": all_passed,
        }
        write_json(out_dir / "feature_verification_report.json", report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["all_passed"] else 1

    if not args.archived_tables_only:
        report = {
            "script": "code/verify_features.py",
            "out_dir": out_rel,
            "provenance_mode": "missing_raw_npz_error",
            "raw_npz_status": npz_status,
            "error": (
                "Primary 48 .npz files (24 data/observations/*.npz and 24 data/traces/*.npz from PUB053_Manuscript_Package_R2.zip) "
                "are absent. Raw feature reconstruction cannot run; pass --archived-tables-only only to run algebraic and internal checks on archived tables."
            ),
            "recomputed_from_raw_inputs": [],
            "compared_against_reference_results": {},
            "archived_table_internal_checks": {},
            "preserved_or_copied_artifacts": [],
            "unexecuted_items": unexecuted_raw_items,
            "all_passed": False,
        }
        write_json(out_dir / "feature_verification_report.json", report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1

    details = verify_from_archived_inputs(repo_root, out_dir)
    archived_checks = {
        "normal_persistence.csv_schema_roundtrip": compare_csv_files(
            repo_root / "results" / "normal_persistence.csv", out_dir / "normal_persistence.csv"
        ),
        "component_crossing_timing.csv_schema_roundtrip": compare_csv_files(
            repo_root / "results" / "component_crossing_timing.csv", out_dir / "component_crossing_timing.csv", key_cols=("block",)
        ),
        "internal_invariants": {
            "ewls_zero_residual_identity": True,
            "threshold_monotonicity_and_zero_dev_selection": True,
            "normal_persistence_span_vs_threshold": details["normal_persistence_rows"] == 48,
            "component_crossing_flow_precedes_demand_8_of_8": details["flow_crossed_first_all_8"],
            "quantile_dominance_and_counterexample": details["quantile_dominance_verified"],
        },
    }
    all_passed = bool(
        archived_checks["normal_persistence.csv_schema_roundtrip"]["exact_match"]
        and archived_checks["component_crossing_timing.csv_schema_roundtrip"]["exact_match"]
        and all(archived_checks["internal_invariants"].values())
    )
    report = {
        "script": "code/verify_features.py",
        "out_dir": out_rel,
        "provenance_mode": "archived_tables_only",
        "raw_npz_status": npz_status,
        "density_backend": density_info,
        "raw_npz_note": (
            "Explicit --archived-tables-only run: primary 48 .npz files (PUB053_Manuscript_Package_R2.zip) are absent, "
            "so raw observation reconstruction and 144-array trace comparisons were NOT executed; only algebraic/tabular invariants "
            "across archived results/ and data/reconstructed_inputs/ were checked."
        ),
        "recomputed_from_raw_inputs": [],
        "compared_against_reference_results": {},
        "archived_table_internal_checks": archived_checks,
        "preserved_or_copied_artifacts": [
            "normal_persistence.csv (staged from results/normal_persistence.csv)",
            "component_crossing_timing.csv (staged from results/component_crossing_timing.csv)",
            "quantile_claim_check.json (staged from results/quantile_claim_check.json)",
            "threshold_candidates.json (converted from data/reconstructed_inputs/threshold_candidates_table5_reconstructed.json)",
        ],
        "unexecuted_items": unexecuted_raw_items,
        "details": details,
        "all_passed": all_passed,
    }
    write_json(out_dir / "feature_verification_report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
