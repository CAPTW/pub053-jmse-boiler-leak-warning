# -*- coding: utf-8 -*-
"""Unit and structural integrity tests for the PUB-053 R2 detector and statistical claims.

Usage:
    python -B code/test_analysis.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import statistics
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    METHODS_ORDER,
    check_raw_npz_availability,
    compare_csv_files,
    compute_ewls_residuals,
    compute_table6_from_episode_rows,
    detect_sequential_alarms,
    extract_raw_trip_and_domain_exit,
    get_density_backend_info,
    load_csv,
    max_exceedance_span_s,
    reconstruct_features_from_observations,
    resolve_repo_root,
    round_half_up_1dp,
    saturated_liquid_density_kg_m3,
    write_csv,
)
from make_figures_r2 import render_figures_from_raw_npz
from reproduce_analysis import _format_table5_quantile, reproduce_from_raw_npz
from verify_features import verify_from_raw_npz

REPO_ROOT = resolve_repo_root()


class TestPub053R2Analysis(unittest.TestCase):
    def test_sequential_detector_persistence_and_cooldown(self) -> None:
        """Verify strict > threshold, elapsed >= 600 s persistence, and 1800 s cooldown."""
        t = np.arange(0.0, 6002.0, 2.0)
        av = np.ones_like(t, dtype=bool)
        s = np.zeros_like(t, dtype=float)
        theta = 4.0

        # Warm-start excursion before t = 1200 s must be ignored
        s[(t >= 200.0) & (t <= 900.0)] = 5.0
        # Equality (score == theta) must NOT trigger strict > threshold
        s[(t >= 1300.0) & (t <= 2100.0)] = 4.0
        # 598 s contiguous exceedance (1500..1798 -> 300 samples? Wait: 2200..2798 has span 598 s) must NOT alarm
        s[(t >= 2200.0) & (t <= 2798.0)] = 4.5
        # Sustained exceedance starting at 3000 s through 5600 s must fire at 3600 s and 5400 s
        s[(t >= 3000.0) & (t <= 5600.0)] = 4.5

        alarms = detect_sequential_alarms(t, s, av, theta, start_s=1200.0, persist_s=600.0, cooldown_s=1800.0)
        self.assertEqual(alarms, [3600.0, 5400.0])

        # Exact 600 s span [3000..3600] must trigger once at 3600.0 s
        s2 = np.zeros_like(t, dtype=float)
        s2[(t >= 3000.0) & (t <= 3600.0)] = 4.5
        self.assertEqual(detect_sequential_alarms(t, s2, av, theta), [3600.0])
        self.assertAlmostEqual(max_exceedance_span_s(t, s2, av, theta), 600.0)

    def test_ewls_residuals_and_fit_parameters(self) -> None:
        """Verify Table 4 OLS fit structure, zero-residual identity, and signed positive/negative residuals."""
        ewls = json.loads((REPO_ROOT / "data" / "reconstructed_inputs" / "ewls_fit_table4_reconstructed.json").read_text(encoding="utf-8"))
        self.assertEqual(ewls["fit_sample_n"], 40804)
        self.assertEqual(40804, 4 * 10201)  # 4 development blocks * (21600 - 1200) / 2 + 1 samples
        p = {item["parameter"]: float(item["full_precision_value"]) for item in ewls["parameters"]}
        fit = {
            "a0": p["a0"],
            "a1": p["a1"],
            "a2": p["a2"],
            "b0": p["b0"],
            "b1": p["b1"],
            "sigma_F": p["σF"],
            "sigma_D": p["σD"],
        }
        q_s = np.array([0.8, 1.4, 1.1])
        l_dev = np.array([0.0, -0.02, 0.01])
        r_ref_expected = fit["a0"] + fit["a1"] * q_s + fit["a2"] * l_dev
        u_ref_expected = fit["b0"] + fit["b1"] * q_s

        # Zero-residual check
        _, _, z_f0, z_d0 = compute_ewls_residuals(q_s, l_dev, r_ref_expected, u_ref_expected, fit)
        np.testing.assert_allclose(z_f0, 0.0, atol=1e-12)
        np.testing.assert_allclose(z_d0, 0.0, atol=1e-12)

        # Signed residual preservation (positive, zero, negative)
        delta_r = np.array([2.5 * fit["sigma_F"], 0.0, -1.75 * fit["sigma_F"]])
        delta_u = np.array([-3.0 * fit["sigma_D"], 1.5 * fit["sigma_D"], -0.5 * fit["sigma_D"]])
        _, _, z_f, z_d = compute_ewls_residuals(q_s, l_dev, r_ref_expected + delta_r, u_ref_expected + delta_u, fit)
        np.testing.assert_allclose(z_f, np.array([2.5, 0.0, -1.75]), atol=1e-12)
        np.testing.assert_allclose(z_d, np.array([-3.0, 1.5, -0.5]), atol=1e-12)

        # Keyword backward-compatibility & duplicate-argument guard
        _, _, z_f_kw, _ = compute_ewls_residuals(q_s, l_dev, q_f=r_ref_expected + delta_r, u_f=u_ref_expected, fit_params=fit)
        np.testing.assert_allclose(z_f_kw, z_f, atol=1e-12)
        with self.assertRaises(ValueError):
            compute_ewls_residuals(q_s, l_dev, r_ref_expected, u_ref_expected, fit, q_f=r_ref_expected)

    def test_quantile_counterexample_and_empirical_dominance(self) -> None:
        """Prove max-score quantile != max of marginal quantiles in general, while checking observed upper-tail condition."""
        q_chk = json.loads((REPO_ROOT / "results" / "quantile_claim_check.json").read_text(encoding="utf-8"))
        self.assertLess(q_chk["observed_max_flow"], q_chk["observed_q99_demand"])
        self.assertAlmostEqual(q_chk["observed_q99_demand"], q_chk["observed_q99_max"], places=12)

        # Construct strict counterexample where Q_0.99(D) > Q_0.99(F) yet Q_0.99(max(F, D)) > Q_0.99(D)
        a = np.zeros(1000)
        b = np.ones(1000)
        a[:9] = 10.0
        b[9:18] = 11.0
        q_f = float(np.quantile(a, 0.99, method="linear"))
        q_d = float(np.quantile(b, 0.99, method="linear"))
        q_m = float(np.quantile(np.maximum(a, b), 0.99, method="linear"))
        self.assertGreater(q_m, max(q_f, q_d))
        self.assertAlmostEqual(q_f, q_chk["counterexample_strict"]["Q_F"], places=9)
        self.assertAlmostEqual(q_d, q_chk["counterexample_strict"]["Q_D"], places=9)
        self.assertAlmostEqual(q_m, q_chk["counterexample_strict"]["Q_max"], places=9)

    def test_archived_24_episode_consistency_and_rounding(self) -> None:
        """Verify 96 episode-method records, Table 6 rounding (51.3 min / 115.5 min), and 5/7/8 cutoffs."""
        ep_rows = load_csv(REPO_ROOT / "results" / "episode_results.csv")
        self.assertEqual(len(ep_rows), 96)

        replay = json.loads((REPO_ROOT / "results" / "r2_replay_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(replay["episodes"], 24)
        self.assertEqual(replay["timestamps"], 259224)
        self.assertEqual(replay["episode_method_comparisons"], 96)
        self.assertEqual(replay["matches"], 96)

        sum_rows = load_csv(REPO_ROOT / "results" / "summary.csv")
        th_by_method = {r["method"]: float(r["threshold"]) for r in sum_rows}
        recomp = compute_table6_from_episode_rows(ep_rows, th_by_method)
        for ref_r, new_r in zip(sum_rows, recomp):
            self.assertEqual(ref_r["method"], new_r["method"])
            self.assertEqual(int(ref_r["normal_alarm_count"]), new_r["normal_alarm_count"])
            self.assertAlmostEqual(float(ref_r["delay_median_min"]), new_r["delay_median_min"], places=9)
            self.assertAlmostEqual(float(ref_r["lead_median_min"]), new_r["lead_median_min"], places=9)

        # Raw difference before rounding: (7636 - 4556)/60 = 51.333... -> 51.3 min
        b0_med = recomp[0]["delay_median_min"]
        b1_med = recomp[3]["delay_median_min"]
        self.assertEqual(round_half_up_1dp(b0_med - b1_med), 51.3)
        self.assertEqual(round_half_up_1dp(recomp[3]["delay_max"]), 115.5)

        # Normal exceedance span criterion (< 600 s => 0 alarms; >= 600 s => alarm)
        np_rows = load_csv(REPO_ROOT / "results" / "normal_persistence.csv")
        self.assertEqual(len(np_rows), 48)
        e8_b0 = next(r for r in np_rows if r["episode"] == "E8_normal" and r["method"] == "B0_state")
        self.assertEqual(float(e8_b0["max_exceedance_span_s"]), 850.0)
        for r in np_rows:
            if r["episode"].startswith("E") and not (r["episode"] == "E8_normal" and r["method"] == "B0_state"):
                self.assertLess(float(r["max_exceedance_span_s"]), 600.0)

    def _build_synthetic_raw_repo(self, tmp_root: Path) -> tuple[np.ndarray, list[dict[str, str]], dict[str, dict[str, np.ndarray]]]:
        import shutil

        (tmp_root / "data" / "observations").mkdir(parents=True)
        (tmp_root / "data" / "traces").mkdir(parents=True)
        shutil.copytree(REPO_ROOT / "data" / "reconstructed_inputs", tmp_root / "data" / "reconstructed_inputs")
        shutil.copytree(REPO_ROOT / "results", tmp_root / "results")
        base_meta = load_csv(REPO_ROOT / "data" / "episode_metadata.csv")
        t = np.arange(0.0, 2602.0, 2.0)
        q_bd = np.where(np.mod(t, 1800.0) < (60.0 - 1e-9), 0.05, 0.0)

        obs_map: dict[str, dict[str, np.ndarray]] = {}
        synth_meta: list[dict[str, str]] = []
        for idx, m in enumerate(base_meta):
            ep = m["episode"]
            row = dict(m)
            rng = np.random.default_rng(1000 + idx)
            base_qs = float(m["base_regime"]) * 2.0 + 0.04 * np.sin(t / 180.0 + idx) + rng.normal(0.0, 0.005, size=t.size)
            p_obs = 7.0 + 0.02 * np.cos(t / 240.0 + idx) + rng.normal(0.0, 0.002, size=t.size)
            l_obs = 0.85 + 0.005 * np.sin(t / 300.0 + idx) + rng.normal(0.0, 0.001, size=t.size)
            q_f = base_qs + q_bd + 0.02 + 0.02 * (base_qs - 1.0) + rng.normal(0.0, 0.015, size=t.size)
            u_fw = 0.40 + 0.30 * base_qs + rng.normal(0.0, 0.012, size=t.size)
            safety_state = np.full(t.shape, "safe", dtype="<U8")
            state_feasible = np.ones(t.shape, dtype=float)

            if m["condition"] == "tube_leak":
                onset = 1300.0
                row["onset_s"] = str(onset)
                after = t >= onset
                # Flow leak anomaly starts at onset, well before feedwater command saturation
                q_f = np.where(after, q_f + 0.90, q_f)
                u_fw = 0.40 + 0.30 * base_qs + np.where(t >= onset + 320.0, 0.40, 0.0)
                l_obs = np.where(t >= onset + 320.0, l_obs - 0.08, l_obs)
                if m["block"] != "E5":
                    u_fw = np.where(t >= 2300.0, 0.98, u_fw)
                    l_obs = np.where(t >= 2300.0, 0.71, l_obs)
                    if m["block"].startswith("E"):
                        safety_state = np.where(t >= 2460.0, "trip", "safe")
                    if m["block"] in ("E1", "E2", "E3"):
                        state_feasible = np.where(t >= 2500.0, 0.0, 1.0)
            synth_meta.append(row)

            obs_ep = {
                "time": t,
                "meta/obs_held_drum_pressure": p_obs,
                "meta/obs_held_drum_level": l_obs,
                "meta/obs_held_feedwater_flow": q_f,
                "meta/obs_held_steam_flow": base_qs,
                "meta/fw_cmd": u_fw,
                "meta/q_bd": q_bd,
                "meta/safety_state": safety_state,
                "truth/drum_level": l_obs,
                "truth/state_feasible": state_feasible,
            }
            obs_map[ep] = obs_ep
            np.savez(tmp_root / "data" / "observations" / f"{ep}.npz", **obs_ep)

        write_csv(tmp_root / "data" / "episode_metadata.csv", synth_meta, list(base_meta[0].keys()))
        episodes = [r["episode"] for r in synth_meta]
        recon = reconstruct_features_from_observations(obs_map, episodes)
        for ep, tr_ep in recon["traces"].items():
            np.savez(
                tmp_root / "data" / "traces" / f"{ep}.npz",
                time=tr_ep["time"],
                state_score=tr_ep["state_score"],
                flow_z=tr_ep["flow_z"],
                command_z=tr_ep["command_z"],
                combined_score=tr_ep["combined_score"],
                available_state=tr_ep["available_state"],
                available_flow_command=tr_ep["available_flow_command"],
            )
        return t, synth_meta, obs_map

    def test_raw_feature_reconstruction_and_negative_mutation(self) -> None:
        """Exercise end-to-end 24-episode raw NPZ reconstruction (144/144 arrays) and fail on perturbation."""
        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            t, _synth_meta, obs_map = self._build_synthetic_raw_repo(tmp_root)

            ok = verify_from_raw_npz(tmp_root, tmp_root / "out_ok")
            self.assertEqual(ok["trace_array_checks_total"], 144)
            self.assertEqual(ok["trace_array_checks_passed"], 144)
            self.assertTrue(ok["all_trace_arrays_matched"])
            self.assertTrue(ok["flow_crossed_first_all_8"])
            self.assertTrue(ok["all_passed"])

            # Mutate raw feedwater observation in D1_normal and verify raw-replay check detects mismatch
            d1_mut = dict(obs_map["D1_normal"])
            d1_mut["meta/obs_held_feedwater_flow"] = d1_mut["meta/obs_held_feedwater_flow"] + np.where(t >= 1200.0, 0.30, 0.0)
            np.savez(tmp_root / "data" / "observations" / "D1_normal.npz", **d1_mut)

            bad = verify_from_raw_npz(tmp_root, tmp_root / "out_bad")
            self.assertEqual(bad["trace_array_checks_total"], 144)
            self.assertLess(bad["trace_array_checks_passed"], 144)
            self.assertFalse(bad["all_trace_arrays_matched"])
            self.assertFalse(bad["all_passed"])

    def test_raw_reproduce_crosscheck_and_figures(self) -> None:
        """Verify 50-row crosscheck, quantile labels, provenance/rounding compare, event extraction, and Fig 1-7 specs."""
        self.assertEqual(
            [_format_table5_quantile(q) for q in (0.99, 0.995, 0.999, 0.9995, 1.0)],
            ["0.990", "0.995", "0.999", "0.9995", "1.000"],
        )

        t_arr = np.arange(0.0, 20.0, 2.0)
        trip_none, dom_none, prov_raw = extract_raw_trip_and_domain_exit(
            {"meta/safety_state": np.full(t_arr.shape, "safe"), "truth/state_feasible": np.ones(t_arr.shape)},
            t_arr,
            {"process_trip_s": "10.0", "domain_exit_s": "12.0"},
        )
        self.assertIsNone(trip_none)
        self.assertIsNone(dom_none)
        self.assertEqual(prov_raw, {"trip_source": "raw_npz:meta/safety_state", "domain_exit_source": "raw_npz:truth/state_feasible"})

        trip_fb, dom_fb, prov_fb = extract_raw_trip_and_domain_exit({}, t_arr, {"process_trip_s": "10.0", "domain_exit_s": "12.0"})
        self.assertEqual((trip_fb, dom_fb), (10.0, 12.0))
        self.assertEqual(prov_fb, {"trip_source": "metadata_fallback", "domain_exit_source": "metadata_fallback"})

        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            self._build_synthetic_raw_repo(tmp_root)
            out_rep = tmp_root / "rep_out"
            ep_rows, thresholds, run_meta = reproduce_from_raw_npz(tmp_root, out_rep)
            self.assertEqual(len(thresholds), 4)
            self.assertFalse(run_meta["raw_event_fallback_used"])
            self.assertEqual(
                run_meta["event_timing_provenance"]["E1_tube_leak"],
                {"trip_source": "raw_npz:meta/safety_state", "domain_exit_source": "raw_npz:truth/state_feasible"},
            )

            t_rows = load_csv(out_rep / "tables_3_4_5_7_crosscheck.csv")
            self.assertEqual(len(t_rows), 50)
            self.assertEqual(len({(r["table"], r["row"]) for r in t_rows}), 50)
            t5_rows = [r["row"] for r in t_rows if r["table"] == "5"]
            self.assertTrue(any(r.endswith(":0.990") for r in t5_rows))
            self.assertTrue(any(r.endswith(":1.000") for r in t5_rows))
            t7_map = {r["row"]: json.loads(r["actual"]) for r in t_rows if r["table"] == "7"}
            self.assertEqual(t7_map["E1"][-2:], [2460.0, 2500.0])
            self.assertEqual(t7_map["E5"][-4:], [None, None, None, None])

            ep_csv = out_rep / "episode_results.csv"
            write_csv(ep_csv, ep_rows, list(ep_rows[0].keys()))
            fig_out = tmp_root / "figs_out"
            specs = render_figures_from_raw_npz(tmp_root, ep_csv, fig_out)
            self.assertEqual(len(specs), 7)
            self.assertTrue(all(s["spec_ok"] for s in specs.values()))
            self.assertFalse(specs["fig6_all_eval_leak_panels.jpeg"]["fallback_used"])
            self.assertEqual(specs["fig1_normal_overview.png"]["panels"], 2)
            self.assertEqual(specs["fig2_e1_leak_trajectory.png"]["panels"], 3)
            self.assertNotIn("Plant truth level", specs["fig2_e1_leak_trajectory.png"]["panel_b_series"])
            self.assertIn("Observed level", specs["fig2_e1_leak_trajectory.png"]["panel_b_series"])
            expected_win = [1200.0, 2600.0]
            self.assertEqual(specs["fig2_e1_leak_trajectory.png"]["time_window_s"], expected_win)
            self.assertEqual(specs["fig3_e1_feature_responses.jpeg"]["time_window_s"], expected_win)
            self.assertEqual(specs["fig5_e1_score_traces.png"]["time_window_s"], expected_win)
            self.assertEqual(specs["fig3_e1_feature_responses.jpeg"]["ylabel"], "Conditioned flow (kg/s)")
            self.assertEqual(specs["fig7_normal_score_traces.jpeg"]["ylabel"], "Longest threshold-exceedance span (s)")
            for fname in specs:
                fpath = fig_out / fname
                self.assertTrue(fpath.exists() and fpath.stat().st_size > 10_000, f"Invalid figure {fname}")

            # Verify Figs 2, 3, 5 stop at ev_confirm + 300 s when confirm + 300 < domain_exit < t_end
            e1_obs_path = tmp_root / "data" / "observations" / "E1_tube_leak.npz"
            with np.load(e1_obs_path) as e1_z:
                e1_d = {k: e1_z[k] for k in e1_z.files}
            t_e1 = e1_d["time"]
            e1_d["meta/fw_cmd"] = np.where(t_e1 >= 1900.0, 0.98, e1_d["meta/fw_cmd"])
            e1_d["truth/drum_level"] = np.where(t_e1 >= 1900.0, 0.71, e1_d["truth/drum_level"])
            np.savez(e1_obs_path, **e1_d)
            fig_out_early = tmp_root / "figs_out_early"
            specs_early = render_figures_from_raw_npz(tmp_root, ep_csv, fig_out_early)
            # 1900 + 120 dwell = 2020 confirm; + 300 = 2320 (< dom1 = 2500 < t_end = 2600)
            for fig_key in ("fig2_e1_leak_trajectory.png", "fig3_e1_feature_responses.jpeg", "fig5_e1_score_traces.png"):
                self.assertEqual(specs_early[fig_key]["time_window_s"], [1200.0, 2320.0])

            ref_csv = REPO_ROOT / "results" / "tables_3_4_5_7_crosscheck.csv"
            ref_rows = load_csv(ref_csv)
            gen_full = [dict(r) for r in ref_rows]
            for r in gen_full:
                if r["table"] == "4":
                    r["kind"] = "raw OLS/EWMA fit check"
                    if r["row"] != "Fit sample N":
                        r["actual"] = r["expected"]
                elif r["table"] == "5":
                    r["kind"] = "independently recomputed thresholds and alarms"
                elif r["table"] == "7":
                    r["kind"] = "independently recomputed alarms and raw events"
                    # Simulate reproduce_analysis.py json.dumps ("null") vs reference Python repr ("None")
                    r["actual"] = r["actual"].replace("None", "null")
                    r["expected"] = r["expected"].replace("None", "null")
            p_full = tmp_root / "t3457_full.csv"
            write_csv(p_full, gen_full, list(ref_rows[0].keys()))
            cmp_ok = compare_csv_files(
                ref_csv,
                p_full,
                key_cols=("table", "row"),
                provenance_cols=("kind",),
                display_rounded_cols=("actual",),
            )
            self.assertTrue(cmp_ok["exact_match"])
            self.assertEqual(cmp_ok["mismatch_count"], 0)
            self.assertGreater(cmp_ok["provenance_difference_count"], 0)
            self.assertEqual(cmp_ok["display_rounded_match_count"], 1)

            # Negative check: Table 7 None vs numeric value must fail comparison
            gen_t7_bad = [dict(r) for r in gen_full]
            for r in gen_t7_bad:
                if r["table"] == "7" and r["row"] == "E5":
                    r["actual"] = r["actual"].replace("null", "21000.0", 1)
                    break
            p_t7_bad = tmp_root / "t3457_t7_bad.csv"
            write_csv(p_t7_bad, gen_t7_bad, list(ref_rows[0].keys()))
            cmp_t7_bad = compare_csv_files(
                ref_csv,
                p_t7_bad,
                key_cols=("table", "row"),
                provenance_cols=("kind",),
                display_rounded_cols=("actual",),
            )
            self.assertFalse(cmp_t7_bad["exact_match"])
            self.assertEqual(cmp_t7_bad["mismatch_count"], 1)
            self.assertEqual(cmp_t7_bad["mismatches"][0]["diff"], "list_none_mismatch")

            gen_bad = [dict(r) for r in gen_full]
            for r in gen_bad:
                if r["table"] == "4" and r["row"] == "a2":
                    r["actual"] = str(float(r["actual"]) + 1e-6)
                    break
            p_bad = tmp_root / "t3457_bad.csv"
            write_csv(p_bad, gen_bad, list(ref_rows[0].keys()))
            cmp_bad = compare_csv_files(
                ref_csv,
                p_bad,
                key_cols=("table", "row"),
                provenance_cols=("kind",),
                display_rounded_cols=("actual",),
            )
            self.assertFalse(cmp_bad["exact_match"])
            self.assertEqual(cmp_bad["mismatch_count"], 1)

    def test_cutoff_leads_key_alignment(self) -> None:
        """Verify key-aligned CSV comparison handles permuted rows and canonical numeric keys while rejecting corruptions."""
        ref_rows = load_csv(REPO_ROOT / "results" / "cutoff_leads_by_block.csv")
        cols = list(ref_rows[0].keys())
        # Permute from (episode, level_cutoff_m, method) to (episode, method, level_cutoff_m) and format 0.7 -> 0.70
        permuted = sorted(
            [dict(r) for r in ref_rows],
            key=lambda r: (r["episode"], METHODS_ORDER.index(r["method"]), float(r["level_cutoff_m"])),
        )
        permuted[0]["level_cutoff_m"] = "0.70" if permuted[0]["level_cutoff_m"] == "0.7" else permuted[0]["level_cutoff_m"]

        with tempfile.TemporaryDirectory() as td:
            p_ref = Path(td) / "ref.csv"
            p_perm = Path(td) / "perm.csv"
            p_bad = Path(td) / "bad.csv"
            p_dup = Path(td) / "dup.csv"
            write_csv(p_ref, ref_rows, cols)
            write_csv(p_perm, permuted, cols)

            # Positional comparison fails on row permutation; keyed comparison passes
            pos_cmp = compare_csv_files(p_ref, p_perm)
            key_cmp = compare_csv_files(p_ref, p_perm, key_cols=("episode", "level_cutoff_m", "method"))
            self.assertFalse(pos_cmp["exact_match"])
            self.assertTrue(key_cmp["exact_match"])
            self.assertEqual(key_cmp["rows_checked"], len(ref_rows))

            # Value perturbation fails
            bad_rows = [dict(r) for r in permuted]
            for r in bad_rows:
                if r["strict_lead_s"] != "":
                    r["strict_lead_s"] = str(int(r["strict_lead_s"]) + 2)
                    break
            write_csv(p_bad, bad_rows, cols)
            bad_cmp = compare_csv_files(p_ref, p_bad, key_cols=("episode", "level_cutoff_m", "method"))
            self.assertFalse(bad_cmp["exact_match"])
            self.assertEqual(bad_cmp["mismatch_count"], 1)

            # Duplicate/missing key fails
            dup_rows = [dict(r) for r in permuted[:-1]] + [dict(permuted[0])]
            write_csv(p_dup, dup_rows, cols)
            dup_cmp = compare_csv_files(p_ref, p_dup, key_cols=("episode", "level_cutoff_m", "method"))
            self.assertFalse(dup_cmp["exact_match"])
            self.assertTrue(len(dup_cmp["duplicate_gen_keys"]) > 0 or len(dup_cmp["missing_keys"]) > 0)

    def test_iapws_density_backend_and_missing_iapws_guard(self) -> None:
        """Verify IAPWS97 (iapws==1.5.5) vs fallback divergence and missing_iapws_error CLI guards across all 3 scripts."""
        import _common
        import make_figures_r2
        import reproduce_analysis
        import verify_features

        try:
            with tempfile.TemporaryDirectory() as td:
                tmp_root = Path(td)
                self._build_synthetic_raw_repo(tmp_root)
                _common._sat_liquid_density_spline.cache_clear()

                if importlib.util.find_spec("iapws") is not None:
                    info = get_density_backend_info()
                    self.assertTrue(info["iapws_available"])
                    self.assertEqual(info["density_backend"], "iapws.IAPWS97")
                    rho_if97 = float(saturated_liquid_density_kg_m3(np.array([7.0]))[0])

                    with mock.patch.dict(sys.modules, {"iapws": None}):
                        _common._sat_liquid_density_spline.cache_clear()
                        with warnings.catch_warnings(record=True) as wrec:
                            warnings.simplefilter("always")
                            rho_fb = float(saturated_liquid_density_kg_m3(np.array([7.0]))[0])
                            self.assertGreater(abs(rho_if97 - rho_fb), 1e-4)
                            self.assertTrue(any("iapws" in str(w.message) for w in wrec))
                            mismatch_res = verify_features.verify_from_raw_npz(tmp_root, tmp_root / "out_no_iapws")
                            self.assertFalse(mismatch_res["density_backend"]["iapws_available"])
                            self.assertEqual(mismatch_res["trace_array_checks_total"], 144)
                            self.assertEqual(mismatch_res["trace_array_checks_passed"], 132)
                            self.assertFalse(mismatch_res["all_trace_arrays_matched"])
                            self.assertGreater(mismatch_res["max_trace_array_abs_diff"], 1e-4)
                            self.assertFalse(mismatch_res["all_passed"])

                    _common._sat_liquid_density_spline.cache_clear()

                fake_density = {
                    "iapws_available": False,
                    "iapws_version": None,
                    "density_backend": "approx_if97_reg4_iapws95_fallback",
                    "sat_liquid_rho_7bar_kg_m3": 750.56,
                }
                # Verify CLI guards refuse full_raw_npz_replay without iapws across verify_features, reproduce_analysis, and make_figures_r2
                with (
                    mock.patch.object(_common, "get_density_backend_info", return_value=fake_density),
                    mock.patch.object(verify_features, "get_density_backend_info", return_value=fake_density),
                    mock.patch.object(reproduce_analysis, "get_density_backend_info", return_value=fake_density),
                    mock.patch.object(make_figures_r2, "get_density_backend_info", return_value=fake_density),
                    mock.patch.object(verify_features, "resolve_repo_root", return_value=tmp_root),
                    mock.patch.object(reproduce_analysis, "resolve_repo_root", return_value=tmp_root),
                    mock.patch.object(make_figures_r2, "resolve_repo_root", return_value=tmp_root),
                    mock.patch.object(sys, "argv", ["verify_features.py", "--out", str(tmp_root / "cli_vf")]),
                ):
                    with contextlib.redirect_stdout(io.StringIO()):
                        rc_vf = verify_features.main()
                    self.assertEqual(rc_vf, 1)
                    rep_vf = json.loads((tmp_root / "cli_vf" / "feature_verification_report.json").read_text(encoding="utf-8"))
                    self.assertEqual(rep_vf["provenance_mode"], "missing_iapws_error")
                    self.assertFalse(rep_vf["density_backend"]["iapws_available"])

                    with mock.patch.object(sys, "argv", ["reproduce_analysis.py", "--out", str(tmp_root / "cli_ra")]):
                        with contextlib.redirect_stdout(io.StringIO()):
                            rc_ra = reproduce_analysis.main()
                        self.assertEqual(rc_ra, 1)
                        rep_ra = json.loads((tmp_root / "cli_ra" / "reproduction_comparison_report.json").read_text(encoding="utf-8"))
                        self.assertEqual(rep_ra["provenance_mode"], "missing_iapws_error")
                        self.assertFalse(rep_ra["density_backend"]["iapws_available"])

                    with mock.patch.object(sys, "argv", ["make_figures_r2.py", "--results", str(tmp_root / "results"), "--out", str(tmp_root / "cli_mf")]):
                        with contextlib.redirect_stdout(io.StringIO()):
                            rc_mf = make_figures_r2.main()
                        self.assertEqual(rc_mf, 1)
                        rep_mf = json.loads((tmp_root / "cli_mf" / "figure_generation_manifest.json").read_text(encoding="utf-8"))
                        self.assertEqual(rep_mf["provenance_mode"], "missing_iapws_error")
                        self.assertFalse(rep_mf["all_files_valid"])
                        self.assertFalse(rep_mf["all_passed"])
                        self.assertFalse(rep_mf["density_backend"]["iapws_available"])

                # Isolate missing-NPZ and --archived-assets-only tests from whatever .npz files exist in REPO_ROOT
                import shutil
                with tempfile.TemporaryDirectory() as td_arch:
                    arch_repo = Path(td_arch) / "repo_no_npz"
                    (arch_repo / "data" / "observations").mkdir(parents=True)
                    (arch_repo / "data" / "traces").mkdir(parents=True)
                    (arch_repo / "results").mkdir(parents=True)
                    shutil.copy2(REPO_ROOT / "data" / "episode_metadata.csv", arch_repo / "data" / "episode_metadata.csv")
                    shutil.copy2(REPO_ROOT / "results" / "episode_results.csv", arch_repo / "results" / "episode_results.csv")
                    shutil.copytree(REPO_ROOT / "figures", arch_repo / "figures")

                    def_out = Path(td_arch) / "figs_def"
                    arch_out = Path(td_arch) / "figs_arch"
                    with mock.patch.object(make_figures_r2, "resolve_repo_root", return_value=arch_repo):
                        with mock.patch.object(sys, "argv", ["make_figures_r2.py", "--results", str(arch_repo / "results"), "--out", str(def_out)]):
                            with contextlib.redirect_stdout(io.StringIO()):
                                rc_def = make_figures_r2.main()
                        self.assertEqual(rc_def, 1)
                        def_man = json.loads((def_out / "figure_generation_manifest.json").read_text(encoding="utf-8"))
                        self.assertEqual(def_man["provenance_mode"], "missing_raw_npz_error")
                        self.assertIn("density_backend", def_man)

                        with mock.patch.object(sys, "argv", ["make_figures_r2.py", "--archived-assets-only", "--results", str(arch_repo / "results"), "--out", str(arch_out)]):
                            with contextlib.redirect_stdout(io.StringIO()):
                                rc_arch = make_figures_r2.main()
                    self.assertEqual(rc_arch, 0)
                    arch_man = json.loads((arch_out / "figure_generation_manifest.json").read_text(encoding="utf-8"))
                    self.assertEqual(arch_man["provenance_mode"], "archived_assets_only")
                    self.assertFalse(arch_man["figure_spec_verified"]["all_specs_verified"])
                    self.assertIn("density_backend", arch_man)
        finally:
            _common._sat_liquid_density_spline.cache_clear()


def main() -> int:
    npz_status = check_raw_npz_availability(REPO_ROOT)
    density_info = get_density_backend_info()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestPub053R2Analysis)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    report = {
        "script": "code/test_analysis.py",
        "provenance_mode": npz_status["mode"],
        "raw_npz_status": npz_status,
        "density_backend": density_info,
        "synthetic_if97_vs_fallback_branch_executed": bool(density_info["iapws_available"]),
        "tests_run": res.testsRun,
        "failures": len(res.failures),
        "errors": len(res.errors),
        "passed": res.wasSuccessful(),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
