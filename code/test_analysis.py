# -*- coding: utf-8 -*-
"""Unit and structural integrity tests for the PUB-053 R2 detector and statistical claims.

Usage:
    python -B code/test_analysis.py
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    METHODS_ORDER,
    check_raw_npz_availability,
    compare_csv_files,
    compute_ewls_residuals,
    compute_table6_from_episode_rows,
    detect_sequential_alarms,
    load_csv,
    max_exceedance_span_s,
    reconstruct_features_from_observations,
    resolve_repo_root,
    round_half_up_1dp,
    write_csv,
)
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

    def test_raw_feature_reconstruction_and_negative_mutation(self) -> None:
        """Exercise end-to-end 24-episode raw NPZ reconstruction (144/144 arrays) and fail on perturbation."""
        base_meta = load_csv(REPO_ROOT / "data" / "episode_metadata.csv")
        t = np.arange(0.0, 2602.0, 2.0)
        q_bd = np.where(np.mod(t, 1800.0) < (60.0 - 1e-9), 0.05, 0.0)

        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            (tmp_root / "data" / "observations").mkdir(parents=True)
            (tmp_root / "data" / "traces").mkdir(parents=True)
            (tmp_root / "results").mkdir(parents=True)

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

                if m["condition"] == "tube_leak":
                    onset = 1300.0
                    row["onset_s"] = str(onset)
                    after = t >= onset
                    # Flow leak anomaly starts at onset, well before feedwater command saturation
                    q_f = np.where(after, q_f + 0.90, q_f)
                    u_fw = 0.40 + 0.30 * base_qs + np.where(t >= onset + 320.0, 0.40, 0.0)
                    l_obs = np.where(t >= onset + 320.0, l_obs - 0.08, l_obs)
                synth_meta.append(row)

                obs_ep = {
                    "time": t,
                    "meta/obs_held_drum_pressure": p_obs,
                    "meta/obs_held_drum_level": l_obs,
                    "meta/obs_held_feedwater_flow": q_f,
                    "meta/obs_held_steam_flow": base_qs,
                    "meta/fw_cmd": u_fw,
                    "meta/q_bd": q_bd,
                    "truth/drum_level": l_obs,
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


def main() -> int:
    npz_status = check_raw_npz_availability(REPO_ROOT)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestPub053R2Analysis)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    report = {
        "script": "code/test_analysis.py",
        "provenance_mode": npz_status["mode"],
        "raw_npz_status": npz_status,
        "tests_run": res.testsRun,
        "failures": len(res.failures),
        "errors": len(res.errors),
        "passed": res.wasSuccessful(),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
