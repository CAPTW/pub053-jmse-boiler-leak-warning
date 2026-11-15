# Reproduction and Verification Guide (`PUB-053`)

## Level A — Standalone Verification & Unit Tests (Fresh Clone, No Private Files Required)
Install dependencies into an isolated Python 3.12 virtual environment (`pip install -r requirements-lock.txt`, or `conda env create -f environment.yml`) and run all commands from the repository root without overwriting `results/`:

1. **R2 Analysis & Figure Reproduction Suite (`code/`)**:
   - **Strict Default (Fails Loudly Without Primary `.npz` Archives)**:
     Without all 48 `.npz` files under `data/observations/` and `data/traces/`, default runs exit with code `1` (`missing_raw_npz_error` / `all_passed: false`).
     ```bash
     python -B code/verify_features.py --out results_reproduced
     python -B code/reproduce_analysis.py --out results_reproduced
     python -B code/make_figures_r2.py --results results_reproduced --out figures_reproduced
     ```
     When all 48 `.npz` files from `PUB053_Manuscript_Package_R2.zip` are placed under `data/observations/` and `data/traces/`, these same default commands run `full_raw_npz_replay` (reconstructing raw features per Supplement S3 and verifying all 144 trace arrays, `fit_params.json`, keyed CSVs, and raw `.npz` trace curves).
   - **Explicit Archived Opt-In (Standalone Fresh Clone Without `.npz` Files)**:
     ```bash
     python -B code/test_analysis.py
     python -B code/verify_features.py --archived-tables-only --out results_reproduced
     python -B code/reproduce_analysis.py --archived-tables-only --out results_reproduced
     python -B code/make_figures_r2.py --archived-assets-only --results results_reproduced --out figures_reproduced
     ```
     - `code/test_analysis.py` passes `7/7` unit and synthetic raw-replay tests (including signed `r_m` EWLS checks, synthetic 24-episode Supplement S3 raw `.npz` reconstruction + 144-array comparison + negative mutation failure check, canonical keyed CSV alignment, and end-to-end synthetic raw `.npz` replay covering `tables_3_4_5_7_crosscheck.csv` 50-row cross-checking and `render_figures_from_raw_npz` Figures 1–7).
     - `verify_features.py --archived-tables-only` verifies `normal_persistence.csv` (`48/48`, `max_abs_diff = 0.0`), `component_crossing_timing.csv` (`8/8`, `max_abs_diff = 0.0`), and `fit_params.json`, reporting all 5 provenance buckets (`recomputed_from_raw_inputs` empty in archived mode).
     - `reproduce_analysis.py --archived-tables-only` reproduces `96/96` episode-method rows and `32/32` delay-window checks using keyed CSV comparison (`cutoff_leads_by_block.csv` keyed by `("episode", "level_cutoff_m", "method")`), and writes `results_reproduced/archived_tables_3_4_5_7_internal_checks.json` (`50/50` internal checks) without copying `results/tables_3_4_5_7_crosscheck.csv` as newly executed output. (In `full_raw_npz_replay`, `tables_3_4_5_7_crosscheck.csv` is freshly compared with `"kind"` provenance diffs and `"actual"` 12-sig-fig display formatting handled cleanly, and primary `meta/safety_state` / `truth/state_feasible` event timing is enforced with `raw_event_fallback_used == false`.)
     - `make_figures_r2.py --archived-assets-only` freshly renders `fig4_method_summary_delay_lead.png` (`1136x896`) from `results_reproduced/episode_results.csv`, recomposes Figures 1–2, validates preserved R2 panels for Figures 3, 5–7, and records 5 explicit asset-provenance buckets (`all_files_valid: true`, `figure_spec_verified.all_specs_verified: false`; `full_raw_npz_replay` renders Figures 1–7 from raw `.npz` arrays with `figure_spec_verified.all_specs_verified: true`).

2. **Tables 1–8, Reconstructed Inputs & Figures 1–7 Cross-Check (`manuscript_verification/`)**:
   ```bash
   python -B manuscript_verification/verify_tables_from_archived_results.py
   ```
   Checks Table 1 parameters against `simulator_source/configs/ab4_marine_aux.yaml` and `core/ab4/drum_model.py`, asserts `50/50` cross-checks, verifies `data/reconstructed_inputs/` and `results_archived/reconstructed_inputs/` plus `current_manuscript_table_checks.csv` (`62/62`), recomputes Table 6 summary stats from `results/episode_results.csv`, verifies `5/7/8` cutoff counts and `32/32` delay-window identity, and inspects `figures/` + `figures/raw_source_assets/`.

3. **Physics Core & Contract Tests (`simulator_source/`)**:
   Run from inside `simulator_source/` so relative `configs/base.yaml` fixtures resolve cleanly:
   ```bash
   cd simulator_source
   PYTHONPATH=src python -B -m pytest tests/test_ab4_geometry.py \
     tests/test_ab4_lines.py tests/test_backend_protocol.py \
     tests/test_fmu_contract.py tests/test_manifest_integrity.py \
     tests/test_pipeline_contracts.py tests/test_simulator_run_to_file_smoke.py -q
   ```
   In a base environment without optional `iapws`, these 7 non-`iapws` modules pass `45 passed, 1 skipped`. When optional user-installed `iapws` (`1.5.5`, GPL-3.0) is present, the 7 physics/props/protocol modules (`test_ab4_geometry.py`, `test_ab4_lines.py`, `test_ab4_drum_model.py`, `test_ab4_furnace.py`, `test_props_if97.py`, `test_props_fuels_gas.py`, `test_backend_protocol.py`) pass `88 passed`, and the full `simulator_source/tests/` suite returns `151 passed, 2 skipped, 1 deselected, 2 failed` (with the only 2 failures in `test_workspace_structure.py` and `test_governance_policy_contracts.py` referencing excluded upstream non-core files; see `docs/SOURCE_PROVENANCE.md` and `docs/KNOWN_LIMITATIONS.md`).

## Level B — Optional Manuscript DOCX/PDF Checks (Author Local Copy Only)
Formatted submission `.docx` and `.pdf` files are excluded from GitHub (`.gitignore`). If supplied locally by the author:
```bash
python -B manuscript_verification/verify_revised_manuscript.py --docx <revised.docx> --pdf <revised.pdf>
python -B manuscript_verification/verify_citations_and_manuscript.py --original-docx <orig.docx> --docx <revised.docx> --pdf <revised.pdf>
```

## Level C — Optional Raw Study ZIP Inspection (External Workstation Archives)
When `observable_baseline_study_20260915T215200Z_be142b32.zip` (`source_copy/`, `analysis/`, `configs/`, `exogenous/`, `runs/`) or `PUB053_Manuscript_Package_R2.zip` (`data/observations/*.npz`, `data/traces/*.npz`, `data/block_design.json`, `data/original_configs/`, R2 `code/`, `results/`) are available locally:
```bash
python -B manuscript_verification/check_cutoff_leads.py /path/to/PUB053_Manuscript_Package_R2.zip ./out_cutoff
python -B manuscript_verification/check_delay_window.py /path/to/PUB053_Manuscript_Package_R2.zip ./delay_window_check.csv
```

## Verified Fresh-Clone Run Record
- Tested on a fresh clone of `https://github.com/CAPTW/pub053-jmse-boiler-leak-warning.git` (`v1.0.2-pub053-r2` verification baseline commit `5170c4a4e539e7a0c84d739fa362087736f76bf8`; superseding `v1.0.1-pub053-r2` baseline `37b0ded2f43f9fb874e45069202bf43f2c20ec4f` and `v1.0.0-pub053-r2` baseline `31636c66bf664512795ce20ee886a0631de04a92`) using `Python 3.12.13`.
- Verified `279/279` files against `docs/FILE_MANIFEST.json` with **`0` byte/SHA-256 mismatches** and **`0` CRLF/mixed EOL text files** (`bad_eol_count = 0`).
- Verified strict default exit code `1` without primary `.npz` files for `code/verify_features.py`, `code/reproduce_analysis.py`, and `code/make_figures_r2.py`.
- Verified exit code `0` for `code/test_analysis.py` (`7/7` tests), `code/verify_features.py --archived-tables-only --out build/reproduced_results`, `code/reproduce_analysis.py --archived-tables-only --out build/reproduced_results`, `code/make_figures_r2.py --archived-assets-only --results build/reproduced_results --out build/reproduced_figures`, `manuscript_verification/verify_tables_from_archived_results.py`, and the 7 core `simulator_source/tests/` modules (`88 passed` with `iapws==1.5.5`), with `results/` and `figures/` bit-for-bit unmodified (`git status --short` empty; logged in `docs/execution_logs/fresh_clone_reproduction_log.json`).
