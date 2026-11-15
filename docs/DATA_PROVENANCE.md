# Data & Archive Provenance (`CAPTW/pub053-jmse-boiler-leak-warning`)

This document specifies the exact origin, storage location, and public inclusion status of all datasets, metadata, configurations, and derived results referenced by JMSE manuscript `PUB-053`.

## 1. Upstream Study Archives vs. Public Release Boundary

The study materials originate from two distinct private archives created at different project stages:

1. **Stage 1 — Original Simulation Archive (`observable_baseline_study_20260915T215200Z_be142b32.zip`)**
   - **Role**: Preserves the single deterministic simulation execution that produced the 24 paired 6 h episodes (`D1`–`D4` development, `E1`–`E8` evaluation; `259,224` timestamps at `dt = 2.0 s`).
   - **Contents**: Study-patched simulator copy `source_copy/` (with pilot and study economizer-leak patches pre-applied; `dt = 2.0 s`, `horizon_s = 21600 s`, `closed_loop_source = "obs"`, `safety.scheduler_intervention_policy = "process_protection_without_schedule_severity_oracle"`), `analysis/`, `configs/`, `exogenous/`, and `runs/` (including study-only conditioning/tape utilities not present in clean `4fea4646...`).
   - **Public availability**: **Not bundled** in this public GitHub repository; absent on this workstation across exhaustive local and mounted drive searches (`C:\`, `G:\`, `O:\`).

2. **Stage 2 — R2 Frozen Statistical Reanalysis Archive (`PUB053_Manuscript_Package_R2.zip`)**
   - **Role**: Read-only statistical reanalysis of the Stage 1 outputs; did **not** re-run or alter boiler trajectories.
   - **Contents**: Frozen 24 `data/observations/<episode>.npz` and 24 `data/traces/<episode>.npz` arrays, `data/block_design.json`, `data/original_configs/<episode>_config_applied.json`, R2 `code/` scripts, and baseline `results/` CSV/JSON files.
   - **Public availability**: **Binary `.npz` arrays (48 files) and per-episode `*_config_applied.json` files are NOT bundled** in this public release and are absent on this workstation. All non-binary R2 reference outputs (`results/`), metadata (`data/episode_metadata.csv`, `data/block_design.json`), clean upstream snapshot (`simulator_source/` + `data/original_configs/ab4_marine_aux.yaml`), reconstructed table JSONs (`data/reconstructed_inputs/`), and runnable R2 verification/reproduction code (`code/`) ARE included here.

## 2. Files Included in This Repository

| Path | Role & Provenance | Editable / Mutable? |
|---|---|---|
| `data/episode_metadata.csv` | 24-episode registry (`D1..D4`, `E1..E8`, seeds, leak onset/severity, functional start/confirm, trip/domain-exit times, expected `.npz` relpaths) | Immutable input |
| `data/block_design.json` | 12-block design specification extracted for PUB-053 | Immutable input |
| `data/original_configs/ab4_marine_aux.yaml` | Base upstream YAML config from local commit `4fea4646...` (`dt = 1.0 s`, `closed_loop_source = "truth"`), distinct from study runtime `source_copy/` | Immutable reference |
| `data/reconstructed_inputs/*.json` | Structured JSON tables (`Tables 1, 2, 3, 4, 5, 7`) reconstructed from R2 cross-checks and simulator configs | Immutable input |
| `results/` | 12 frozen baseline R2 reference CSV/JSON files (`episode_results.csv`, `summary.csv`, `normal_persistence.csv`, `cutoff_leads_by_block.csv`, `cutoff_leads_summary.csv`, `delay_window_check.csv`, `component_crossing_timing.csv`, `tables_3_4_5_7_crosscheck.csv`, `quantile_claim_check.json`, `r2_replay_summary.json`, `recomputed_vs_archived.csv`, `tables_and_rounding_summary.json`) | Immutable reference |
| `results_archived/` | Provenance-separated audit tree (`R2` reference copies, `prior_draft_review_ce0e9a0e/` scoped strictly to pre-revision draft `ce0e9a0e...`, and `current_manuscript_verification/` for the latest DOCX/PDF) | Immutable archive |
| `figures/` & `figures/raw_source_assets/` | Publication Figures 1–7 and uncomposited upstream R2 visual assets (`FIGURE_MAP.md`) | Immutable reference |
| `code/` | Verification and reproduction pipeline (`_common.py`, `test_analysis.py`, `verify_features.py`, `reproduce_analysis.py`, `make_figures_r2.py`) writing exclusively to `--out` | Public code (MIT) |

## 3. Execution Provenance Separation (`v1.0.2-pub053-r2`)

Starting in `v1.0.1-pub053-r2` and completed in `v1.0.2-pub053-r2`, `code/verify_features.py`, `code/reproduce_analysis.py`, and `code/make_figures_r2.py` enforce strict separation between raw-array execution and archived-table verification:

- **Default invocation (no opt-in flag)**: Checks `check_raw_npz_availability(repo_root)`. When the 48 primary `.npz` files are missing, every script writes an explicit error report with `"provenance_mode": "missing_raw_npz_error"`, `"all_passed": false`, and `"unexecuted_items"`, and exits with code **`1`**.
- **Full Raw Replay (`all_raw_npz_present == true`)**: If the user places all 24 `data/observations/<episode>.npz` and 24 `data/traces/<episode>.npz` files from `PUB053_Manuscript_Package_R2.zip`, the scripts reconstruct Supplement S3 features (`r_M`, causal `B0` EWMA, `ddof=0` OLS/scale fits), verify `144/144` trace arrays, calibrate thresholds (`calibrate_thresholds_from_traces`), extract post-onset alarms and primary `meta/safety_state` (`label/safety_state`) / `truth/state_feasible` event timings without silent metadata fallback (`raw_event_fallback_used == false`), verify `96/96` episode-method records, `32/32` delay-window checks, and the `50`-row `tables_3_4_5_7_crosscheck.csv` (accounting for `"kind"` provenance tags and 12-significant-figure display formatting on `a2`), and render manuscript-matched Figures 1–7 (`figure_spec_verified.all_specs_verified: true`).
- **Explicit Standalone Opt-In (`--archived-tables-only` / `--archived-assets-only`)**: Reports every output under five explicit provenance buckets (`recomputed_from_raw_inputs`, `compared_against_reference_results`, `archived_table_internal_checks`, `preserved_or_copied_artifacts`, and `unexecuted_items`), sets `figure_spec_verified.all_specs_verified: false` in archived figure mode, and does **not** copy `results/tables_3_4_5_7_crosscheck.csv` as a newly executed raw verification.
