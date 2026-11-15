# Known Limitations and Verification Boundaries (`v1.0.1-pub053-r2`)

This document states the exact boundaries of what can and cannot be verified in a standalone clone of `CAPTW/pub053-jmse-boiler-leak-warning`.

1. **Primary Binary `.npz` Archives Are Not Bundled**
   - The 48 `.npz` files (`24` in `data/observations/`, `24` in `data/traces/` from `PUB053_Manuscript_Package_R2.zip`), per-episode `data/original_configs/<episode>_config_applied.json`, and the full study execution package `observable_baseline_study_20260915T215200Z_be142b32.zip` are not included in this public repository and were verified absent across all mounted drives (`C:\`, `G:\`, `O:\`) on the release workstation.
   - Without `--archived-tables-only` (or `--archived-assets-only` for `make_figures_r2.py`), default execution of `code/verify_features.py`, `code/reproduce_analysis.py`, and `code/make_figures_r2.py` **fails with exit code `1`** and `"all_passed": false`.

2. **Raw Observation Reconstruction Proven via Synthetic 24-Episode Test Fixture Only**
   - `code/_common.py::reconstruct_features_from_observations` implements Supplement S3 mathematically (horizontal-cylinder volume $V(h)$, 1,000-knot geometric $\rho_l(p)$ spline with `[0.5, 30.0]` bar detector clipping, 600 s trapezoidal mass-balance residual $r_M$, `ddof=0` OLS/EWMA scale fits on `D1_normal`–`D4_normal` $t \ge 1200\,\text{s}$, and signed `flow_z`, `command_z`, `combined_score = max(flow_z, command_z)`).
   - Because the real 48 `.npz` files are absent, this path is executed in CI/unit testing (`code/test_analysis.py::test_raw_feature_reconstruction_and_negative_mutation`) on an isolated `TemporaryDirectory` 24-episode synthetic `.npz` dataset (`144/144` array matches plus a negative mutation check perturbing `D1_normal.npz`), not on the study `.npz` trajectories.

3. **Archived-Mode Boundary for `episode_results.csv`, `cutoff_leads_by_block.csv`, and `tables_3_4_5_7_crosscheck.csv`**
   - Under `--archived-tables-only`, `code/reproduce_analysis.py` recomputes delays, strict leads, Table 6 aggregations, cutoff lead differences (`strict_lead_s = functional_start_s - alarm_s`), `delay_window_check.csv`, and internal JSON consistency checks.
   - However, upstream primary alarm timestamps (`all_alarm_times_s`), cutoff `functional_start_s`, `process_trip_s`, `domain_exit_s`, `progression_duration_s`, and Table 4 regression coefficients are read from `results/` and `data/`, not freshly re-extracted from `.npz` traces. `results/tables_3_4_5_7_crosscheck.csv` is explicitly treated as a preserved reference artifact (`preserved_or_copied_artifacts`), never copied as a newly executed check.

4. **Figure Regeneration Boundary (`--archived-assets-only`)**
   - Under `--archived-assets-only`, only `fig4_method_summary_delay_lead.png` is freshly rendered via Matplotlib from CSV. Figures 1–2 are composited/padded from preserved `figures/raw_source_assets/`, and Figures 3, 5, 6, and 7 copy preserved R2 panels (`copied_preserved_reference_assets`).

5. **Optional `iapws` Package & Upstream Snapshot Differences**
   - `iapws` (`GPL-3.0`) is intentionally excluded from the MIT-licensed repository requirements. When `iapws` is absent, `code/_common.py` uses IAPWS-IF97 Region 4 $T_{\text{sat}}(p)$ and IAPWS-95 Eq. (2.6) $\rho_l(T_{\text{sat}})$, while `simulator_source/` falls back to its built-in 9-point approximation; therefore `simulator_source/tests/` tests requiring exact `iapws` (`test_ab4_drum_model.py`, `test_ab4_furnace.py`, `test_props_if97.py`, `test_props_fuels_gas.py`) require user-installed `iapws`, and upstream repo layout tests (`test_workspace_structure.py`, `test_governance_policy_contracts.py`) do not apply to the standalone snapshot.
   - `simulator_source/` reflects clean local base commit `4fea4646723f04db41583cb682bac8b62c44bc05` rather than the pilot/study-patched `source_copy/` (`observable_baseline_study_20260915T215200Z_be142b32.zip`); see `docs/SOURCE_PROVENANCE.md`.
