# -*- coding: utf-8 -*-
"""Unit and structural integrity tests for the PUB-053 R2 detector and statistical claims.

Usage:
    python -B code/test_analysis.py
"""

from __future__ import annotations

import json
import statistics
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    METHODS_ORDER,
    check_raw_npz_availability,
    compute_ewls_residuals,
    compute_table6_from_episode_rows,
    detect_sequential_alarms,
    load_csv,
    max_exceedance_span_s,
    resolve_repo_root,
    round_half_up_1dp,
)

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
        """Verify Table 4 OLS fit structure and zero-residual algebraic identity."""
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
        q_s = np.array([0.8, 1.4])
        l_dev = np.array([0.0, -0.02])
        q_f_exact = fit["a0"] + fit["a1"] * q_s + fit["a2"] * l_dev
        u_f_exact = fit["b0"] + fit["b1"] * q_s
        _, _, z_f, z_d = compute_ewls_residuals(q_s, l_dev, q_f_exact, u_f_exact, fit)
        np.testing.assert_allclose(z_f, 0.0, atol=1e-12)
        np.testing.assert_allclose(z_d, 0.0, atol=1e-12)

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
