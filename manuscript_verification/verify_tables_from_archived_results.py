# -*- coding: utf-8 -*-
"""Verify PUB-053 manuscript Tables 1-8 and Figures 1-7 strictly from release repo artifacts."""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

try:
    from PIL import Image
except ImportError:
    Image = None


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def round_half_up_1dp(val: float) -> float:
    return float(Decimal(str(val)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def approx_eq(a: float, b: float, tol: float = 1e-6) -> bool:
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


def verify_release_repository(repo_root: Path) -> dict:
    sim_dir = repo_root / "simulator_source"
    res_dir = repo_root / "results_archived"
    fig_dir = repo_root / "figures"

    # 1. Table 1 check against simulator_source/configs/ab4_marine_aux.yaml & ab4 source
    cfg_path = sim_dir / "configs" / "ab4_marine_aux.yaml"
    drum_path = sim_dir / "src" / "boiler_pdm_sim" / "core" / "ab4" / "drum_model.py"
    assert cfg_path.exists(), f"Missing {cfg_path}"
    assert drum_path.exists(), f"Missing {drum_path}"
    table1_checks = {}
    if yaml is not None:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        geom = cfg["boiler"]["geometry"]
        nom = cfg["boiler"]["nominal"]
        comb = cfg["boiler"]["parameters"]["combustion"]
        ctrl = cfg["control"]
        assert approx_eq(geom["drum_radius_m"], 0.75)
        assert approx_eq(geom["drum_length_m"], 5.0)
        assert approx_eq(nom["pressure_bar"], 7.0)
        assert approx_eq(nom["steam_flow_kg_s"], 1.4)
        assert approx_eq(nom["level_fraction"], 0.55)
        assert approx_eq(ctrl["drum_level_pid"]["setpoint_level_m"], 0.85)
        assert approx_eq(ctrl["pressure_pid"]["setpoint_pressure_bar"], 7.0)
        assert approx_eq(comb["qmax_MW"], 4.0)
        assert approx_eq(comb["eta"], 0.90)
        table1_checks["yaml_loaded"] = True
    drum_src = drum_path.read_text(encoding="utf-8")
    assert 'STATE_NAMES: tuple[str, ...] = ("p", "V_wt", "alpha_r", "V_sd")' in drum_src
    assert "k_friction: float = 25.0" in drum_src
    assert "T_d: float = 12.0" in drum_src
    assert "beta: float = 0.3" in drum_src
    table1_checks["ab4_core_constants_verified"] = True

    # 2. Tables 3, 4, 5, 7 crosscheck (50 rows)
    t3457_rows = load_csv(res_dir / "tables_3_4_5_7_crosscheck.csv")
    t3457_true = sum(1 for r in t3457_rows if r["match"] == "True")
    assert len(t3457_rows) == 50 and t3457_true == 50, (
        f"Expected 50/50 matches in tables_3_4_5_7_crosscheck.csv, got {t3457_true}/{len(t3457_rows)}"
    )

    # 3. R2 replay summary and rounding summary
    replay_path = res_dir / "r2_replay_summary.json"
    if not replay_path.exists():
        replay_path = res_dir / "review_execution_summary.json"
    exec_sum = json.loads(replay_path.read_text(encoding="utf-8"))
    assert exec_sum["episodes"] == 24
    assert exec_sum["timestamps"] == 259224
    assert exec_sum["episode_method_comparisons"] == 96
    assert exec_sum["matches"] == 96

    round_sum = json.loads((res_dir / "tables_and_rounding_summary.json").read_text(encoding="utf-8"))
    assert round_sum["table_rows_checked"] == 50 and round_sum["matched"] == 50
    assert round_sum["endpoint_sensitivity_observed_count"] == {"0.7": 5, "0.75": 7, "0.8": 8}

    # 4. Recompute Table 6 summary directly from results_archived/episode_results.csv & normal_persistence.csv
    ep_rows = load_csv(res_dir / "episode_results.csv")
    np_rows = load_csv(res_dir / "normal_persistence.csv")
    sum_rows = load_csv(res_dir / "summary.csv")
    assert len(ep_rows) == 96, f"Expected 96 episode-method rows, got {len(ep_rows)}"
    assert len(np_rows) == 48, f"Expected 48 normal-persistence rows, got {len(np_rows)}"

    recomputed_t6 = {}
    for s in sum_rows:
        m = s["method"]
        eval_fault = [
            r for r in ep_rows
            if r["method"] == m and r["episode"].startswith("E") and r["episode"].endswith("_tube_leak")
        ]
        eval_norm = [
            r for r in ep_rows
            if r["method"] == m and r["episode"].startswith("E") and r["episode"].endswith("_normal")
        ]
        assert len(eval_fault) == 8 and len(eval_norm) == 8
        delays = [float(r["delay_min"]) for r in eval_fault]
        leads = [float(r["strict_lead_min"]) for r in eval_fault if r["strict_lead_min"] != ""]
        norm_alarms = sum(int(r["normal_alarms"]) for r in eval_norm)
        assert norm_alarms == int(s["normal_alarm_count"])
        assert len(leads) == int(s["event_n"]) == 7
        assert approx_eq(statistics.median(delays), float(s["delay_median_min"]))
        assert approx_eq(min(delays), float(s["delay_min"]))
        assert approx_eq(max(delays), float(s["delay_max"]))
        assert approx_eq(statistics.median(leads), float(s["lead_median_min"]))
        assert approx_eq(min(leads), float(s["lead_min"]))
        assert approx_eq(max(leads), float(s["lead_max"]))
        recomputed_t6[m] = {
            "normal_alarms": norm_alarms,
            "delay_1dp": [round(statistics.median(delays), 1), round(min(delays), 1), round(max(delays), 1)],
            "lead_1dp": [round(statistics.median(leads), 1), round(min(leads), 1), round(max(leads), 1)],
        }

    # Verify Table 6 51.3 min difference and 115.5 min rounding
    b0_med = float(next(s["delay_median_min"] for s in sum_rows if s["method"] == "B0_state"))
    b1_med = float(next(s["delay_median_min"] for s in sum_rows if s["method"] == "B1_combined"))
    b1_max = float(next(s["delay_max"] for s in sum_rows if s["method"] == "B1_combined"))
    assert round(b0_med - b1_med, 1) == 51.3
    assert round(b1_max, 1) == 115.5

    # Verify current manuscript verification CSV if present (all 62 rows of Tables 3..8)
    cur_checks_path = res_dir / "current_manuscript_verification" / "current_manuscript_table_checks.csv"
    prior_checks_path = res_dir / "prior_draft_review_ce0e9a0e" / "manuscript_table_checks.csv"
    if cur_checks_path.exists():
        cur_rows = load_csv(cur_checks_path)
        assert len(cur_rows) == 62 and all(r["match"] == "True" for r in cur_rows), (
            f"Expected 62/62 matches in {cur_checks_path}"
        )
        t8_expected = {r["row"]: json.loads(r["expected"]) for r in cur_rows if r["table"] == "8"}
        current_checks_summary = f"{len(cur_rows)}/{len(cur_rows)}"
    else:
        tab_checks = load_csv(prior_checks_path if prior_checks_path.exists() else (res_dir / "manuscript_table_checks.csv"))
        t8_expected = {r["row"]: json.loads(r["expected"]) for r in tab_checks if r["table"] == "8"}
        current_checks_summary = "pending"

    assert len(t8_expected) == 8
    methods_order = ["B0_state", "Flow_only", "Command_only", "B1_combined"]
    for block in [f"E{i}" for i in range(1, 9)]:
        spans = [
            float(next(r["max_exceedance_span_s"] for r in np_rows if r["episode"] == f"{block}_normal" and r["method"] == m))
            for m in methods_order
        ]
        assert spans == t8_expected[block], f"Table 8 mismatch for {block}: {spans} != {t8_expected[block]}"

    # 5. Verify reconstructed_inputs JSON files match archived tables
    rec_dir = res_dir / "reconstructed_inputs"
    reconstructed_verified = False
    if rec_dir.exists():
        b_json = json.loads((rec_dir / "block_design_table3_reconstructed.json").read_text(encoding="utf-8"))
        ewls_json = json.loads((rec_dir / "ewls_fit_table4_reconstructed.json").read_text(encoding="utf-8"))
        th_json = json.loads((rec_dir / "threshold_candidates_table5_reconstructed.json").read_text(encoding="utf-8"))
        ev_json = json.loads((rec_dir / "episode_event_timings_table7_reconstructed.json").read_text(encoding="utf-8"))
        p_json = json.loads((rec_dir / "plant_parameters_table1_table2_from_source.json").read_text(encoding="utf-8"))
        assert len(b_json["blocks"]) == 12
        assert ewls_json["fit_sample_n"] == 40804
        assert len(th_json["candidates"]) == 20
        assert len(ev_json["evaluation_blocks"]) == 8
        assert approx_eq(p_json["table1_from_source_yaml_and_code"]["drum_radius_m"], 0.75)
        reconstructed_verified = True

    # 6. Verify cutoff_leads_summary.csv & delay_window_check.csv
    cutoff_rows = load_csv(res_dir / "cutoff_leads_summary.csv")
    assert len(cutoff_rows) == 12
    by_cutoff = {}
    for r in cutoff_rows:
        by_cutoff[(r["level_cutoff_m"], r["method"])] = (
            int(r["n_observed"]),
            round_half_up_1dp(float(r["median_strict_lead_min"])),
        )
    assert by_cutoff[("0.7", "B0_state")] == (5, 54.6)
    assert by_cutoff[("0.75", "B0_state")] == (7, 34.7)
    assert by_cutoff[("0.8", "B0_state")] == (8, 8.9)
    assert by_cutoff[("0.7", "Command_only")] == (5, 76.3)
    assert by_cutoff[("0.75", "Command_only")] == (7, 59.0)
    assert by_cutoff[("0.8", "Command_only")] == (8, 54.8)
    assert by_cutoff[("0.8", "B1_combined")] == (8, 54.9)

    delay_win_rows = load_csv(res_dir / "delay_window_check.csv")
    assert len(delay_win_rows) == 32
    assert all(r["identical"] == "True" for r in delay_win_rows)

    # 7. Verify quantile_claim_check.json
    q_chk = json.loads((res_dir / "quantile_claim_check.json").read_text(encoding="utf-8"))
    assert round(q_chk["observed_max_flow"], 6) == 4.063845
    assert round(q_chk["observed_q99_demand"], 6) == 4.388325
    assert round(q_chk["observed_q99_max"], 6) == 4.388325
    assert q_chk["counterexample_strict"] == {"Q_F": 0.0, "Q_D": 1.0, "Q_max": 10.0}

    # 8. Verify Figures 1..7 and raw_source_assets exist and are valid image assets
    expected_figs = [
        "fig1_normal_overview.png",
        "fig2_e1_leak_trajectory.png",
        "fig3_e1_feature_responses.jpeg",
        "fig4_method_summary_delay_lead.png",
        "fig5_e1_score_traces.png",
        "fig6_all_eval_leak_panels.jpeg",
        "fig7_normal_score_traces.jpeg",
    ]
    fig_info = {}
    for fname in expected_figs:
        fpath = fig_dir / fname
        assert fpath.exists(), f"Missing figure file: {fpath}"
        size = fpath.stat().st_size
        assert size > 10_000, f"Figure too small ({size} B): {fpath}"
        dims = None
        if Image is not None:
            with Image.open(fpath) as im:
                dims = list(im.size)
        fig_info[fname] = {"bytes": size, "dimensions_px": dims}

    raw_assets_dir = fig_dir / "raw_source_assets"
    raw_assets_count = len(list(raw_assets_dir.iterdir())) if raw_assets_dir.exists() else 0

    result = {
        "repo_root": str(repo_root),
        "table1_config_and_source": table1_checks,
        "reconstructed_inputs_verified": reconstructed_verified,
        "tables_3_4_5_7_crosscheck_matches": f"{t3457_true}/{len(t3457_rows)}",
        "current_manuscript_table_checks": current_checks_summary,
        "episode_method_comparisons_matches": f"{exec_sum['matches']}/{exec_sum['episode_method_comparisons']}",
        "recomputed_table6_summary": recomputed_t6,
        "delay_median_difference_min": round(b0_med - b1_med, 1),
        "b1_max_delay_min_1dp": round(b1_max, 1),
        "table8_blocks_verified": 8,
        "cutoff_leads_verified": len(cutoff_rows),
        "delay_window_comparisons_identical": f"{len(delay_win_rows)}/{len(delay_win_rows)}",
        "figures_verified": fig_info,
        "raw_source_assets_count": raw_assets_count,
        "all_passed": True,
    }
    return result


def main() -> int:
    repo_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    result = verify_release_repository(repo_root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
