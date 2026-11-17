# Reproduction and Verification Guide (`PUB-053`)

## Level A — Standalone Verification & Unit Tests (Fresh Clone, No Private Files Required)
Install all verified R2 and core simulator dependencies (`numpy==1.26.4`, `scipy==1.13.1`, `pandas==2.2.2`, `matplotlib==3.9.2`, `pyarrow==16.1.0`, `PyYAML==6.0.1`, `pytest==7.4.4`, `python-dateutil==2.9.0.post0`, `lxml==6.0.2`, `pillow==10.4.0`, and **`iapws==1.5.5`** [GPL-3.0, required for exact IAPWS-IF97 density reconstruction in `code/` raw replay and `core/ab4` physics tests; see `THIRD_PARTY_NOTICES.md`]) into an isolated Python 3.12 virtual environment (`pip install -r requirements-lock.txt`, or `conda env create -f environment.yml`) and run all commands from the repository root without overwriting `results/`:

1. **R2 Analysis & Figure Reproduction Suite (`code/`)**:
   - **Strict Default (Fails Loudly Without Primary `.npz` Archives or `iapws==1.5.5`)**:
     Without all 48 `.npz` files under `data/observations/` and `data/traces/`, default runs of all 3 scripts exit with code `1` (`missing_raw_npz_error` / `all_passed: false`, before checking `iapws`).
     ```bash
     python -B code/verify_features.py --out results_reproduced
     python -B code/reproduce_analysis.py --out results_reproduced
     python -B code/make_figures_r2.py --results results_reproduced --out figures_reproduced
     ```
     When all 48 `.npz` files from `PUB053_Manuscript_Package_R2.zip` are placed under `data/observations/` and `data/traces/` alongside **`iapws==1.5.5`**, these same default commands run `full_raw_npz_replay` (reconstructing raw features via `IAPWS97(P=..., x=0).rho` per Supplement S3 and verifying all 144 trace arrays, `fit_params.json`, keyed CSVs, and raw `.npz` figure curves). If all 48 `.npz` files are supplied **without `iapws`**, **all three scripts (`verify_features.py`, `reproduce_analysis.py`, and `make_figures_r2.py`)** abort before raw reconstruction/plotting with exit code `1`, `"provenance_mode": "missing_iapws_error"`, and `"density_backend"` showing inactive `iapws` status (unless `--allow-approx-density` is explicitly passed for non-exact diagnostics).
   - **Explicit Archived Opt-In (Standalone Fresh Clone Without `.npz` Files)**:
     ```bash
     python -B code/test_analysis.py
     python -B code/verify_features.py --archived-tables-only --out results_reproduced
     python -B code/reproduce_analysis.py --archived-tables-only --out results_reproduced
     python -B code/make_figures_r2.py --archived-assets-only --results results_reproduced --out figures_reproduced
     ```
     - `code/test_analysis.py` passes `8/8` unit and synthetic raw-replay tests (using stdlib `unittest`; including signed `r_m` EWLS checks, `iapws==1.5.5` `IAPWS97` vs. fallback divergence + `missing_iapws_error` CLI guards across `verify_features.py`, `reproduce_analysis.py`, and `make_figures_r2.py`, `--archived-assets-only` `density_backend` manifest reporting, synthetic 24-episode Supplement S3 raw `.npz` reconstruction + 144-array comparison + negative mutation failure check, canonical keyed CSV alignment, and end-to-end synthetic raw `.npz` replay covering `tables_3_4_5_7_crosscheck.csv` 50-row cross-checking with Table 7 `None`/`null` list matching + negative check and `render_figures_from_raw_npz` Figures 1–7 specs).
     - `verify_features.py --archived-tables-only` verifies `normal_persistence.csv` (`48/48`, `max_abs_diff = 0.0`), `component_crossing_timing.csv` (`8/8`, `max_abs_diff = 0.0`), and `fit_params.json`, reporting active `density_backend` and all 5 provenance buckets (`recomputed_from_raw_inputs` empty in archived mode).
     - `reproduce_analysis.py --archived-tables-only` reproduces `96/96` episode-method rows and `32/32` delay-window checks using keyed CSV comparison (`cutoff_leads_by_block.csv` keyed by `("episode", "level_cutoff_m", "method")`), and writes `results_reproduced/archived_tables_3_4_5_7_internal_checks.json` (`50/50` internal checks) without copying `results/tables_3_4_5_7_crosscheck.csv` as newly executed output. (In `full_raw_npz_replay`, `tables_3_4_5_7_crosscheck.csv` is freshly compared with `"kind"` provenance diffs, `"actual"` 12-sig-fig display formatting, and Table 7 `None`/`null` list equivalence handled cleanly, and primary `meta/safety_state` / `truth/state_feasible` event timing is enforced with `raw_event_fallback_used == false`.)
     - `make_figures_r2.py --archived-assets-only` freshly renders `fig4_method_summary_delay_lead.png` (`1136x896`) from `results_reproduced/episode_results.csv`, recomposes Figures 1–2, validates preserved R2 panels for Figures 3, 5–7, and records `density_backend` alongside 5 explicit asset-provenance buckets (`all_files_valid: true`, `figure_spec_verified.all_specs_verified: false`; `full_raw_npz_replay` renders Figures 1–7 from raw `.npz` arrays with Figs 2, 3, and 5 matched to `[1200, min(t_end, T_confirm + 300)]` s, Fig 2 panel (b) plotting `Observed level` only, `figure_spec_verified.all_specs_verified: true`, and `raw_replay_exact_if97_backend: true`).

## Real-Data vs. Synthetic-Test Failure Points

To avoid conflating standalone synthetic unit-test behavior with real-data `.npz` verification behavior, failure points differ by input regime and `iapws==1.5.5` availability:

| Execution Target & Condition | Exit Code | Exact Failure / Skip Point & Mechanism | What It Does (and Does Not) Prove |
|---|---|---|---|
| **Real Data CLI** (`verify_features.py`, `reproduce_analysis.py`, `make_figures_r2.py`) — **`.npz` absent** (current public clone, regardless of `iapws`) | `1` | Fails immediately at pre-flight file check (`provenance_mode: "missing_raw_npz_error"`) before checking `iapws` or touching density splines. | Confirms no silent fallback to `results/` or `figures/`; archived opt-in (`--archived-*`) still exits `0` without `.npz` or `iapws`. |
| **Real Data CLI** (same 3 scripts) — **48 `.npz` present, `iapws` absent** | `1` | Fails at pre-flight dependency guard (`provenance_mode: "missing_iapws_error"`, `density_backend.iapws_available: false`) before `reconstruct_features_from_observations` or plotting. | Blocks unverified IF97-vs-IAPWS95 drift across feature check, analysis replay, and raw figure curves (Figs 2, 5, 7). |
| **Real Data CLI** with `--allow-approx-density` — **48 `.npz` present, `iapws` absent** | N/A (not executed locally) | Bypasses CLI guard; `_sat_liquid_density_spline()` emits `RuntimeWarning` and falls back to IAPWS-95 (`0.00079 kg/m^3` diff at `7 bar`, up to `0.20 kg/m^3` over `0.5`–`120 bar`). Divergence hits downstream trace/table numerical comparisons. | **Not executed on the real 48 `.npz` files** here because `PUB053_Manuscript_Package_R2.zip` is unmounted on this workstation. |
| **Synthetic Test** (`code/test_analysis.py`) — **with `iapws==1.5.5`** (`Python 3.12`) | `0` (`8/8` ok) | Inside `test_iapws_density_backend_and_missing_iapws_guard`: builds synthetic 24-episode `IAPWS97` `.npz` fixture, masks `sys.modules["iapws"] = None`, and asserts **`verify_from_raw_npz` fails inside 144-array comparison (`132/144` passed, `max_diff = 0.0001328 > 1e-4`, `all_passed == False`)**, plus asserts mocked CLI `missing_iapws_error` (`rc=1`) on all 3 scripts (`synthetic_if97_vs_fallback_branch_executed: true`). | Proves exact mathematical sensitivity and CLI guard logic on a synthetic IF97 fixture; does **not** prove the external 48 `.npz` files are bundled or re-executed. |
| **Synthetic Test** (`code/test_analysis.py`) — **without `iapws`** (`Python 3.14`) | `0` (`8/8` ok) | Does **not** execute the IF97-vs-fallback mismatch assertion (`if find_spec("iapws") is not None:` is skipped; `synthetic_if97_vs_fallback_branch_executed: false`). `_build_synthetic_raw_repo()` builds its synthetic fixture with the **same approximate fallback** so internal `144/144` checks are self-consistent, and CLI guards are checked via `mock.patch`. | Tests structural invariants and mocked CLI guards cleanly, **not** IF97 compliance; a zero exit without `iapws` does **not** mean real IF97 `.npz` files would pass. |
| **`simulator_source/tests/`** — **with vs. without `iapws==1.5.5`** | `1` (full) / `0` (7 core) | With `iapws==1.5.5`: 7 core modules `88 passed`; full suite `151 passed, 2 skipped, 1 deselected, 2 failed` (the 2 failures target excluded upstream repo files, unrelated to `.npz`/`iapws`). Without `iapws`: `ab4`/IF97 modules skip via `pytest.importorskip("iapws")`; non-`iapws` 7 modules pass `45 passed, 1 skipped`. | Confirms `core/ab4` physics (`iapws==1.5.5`) and snapshot exclusions (`docs/SOURCE_PROVENANCE.md`). |

2. **Tables 1–8, Reconstructed Inputs & Figures 1–7 Cross-Check (`manuscript_verification/`)**:
   ```bash
   python -B manuscript_verification/verify_tables_from_archived_results.py
   ```
   Checks Table 1 parameters against `simulator_source/configs/ab4_marine_aux.yaml` and `core/ab4/drum_model.py`, asserts `50/50` cross-checks, verifies `data/reconstructed_inputs/` and `results_archived/reconstructed_inputs/` plus `current_manuscript_table_checks.csv` (`62/62`), recomputes Table 6 summary stats from `results/episode_results.csv`, verifies `5/7/8` cutoff counts and `32/32` delay-window identity, and inspects `figures/` + `figures/raw_source_assets/`.

3. **Physics Core & Contract Tests (`simulator_source/`)**:
   Run from inside `simulator_source/` so relative `configs/base.yaml` fixtures resolve cleanly (requires `iapws==1.5.5` from `requirements-lock.txt` for `ab4`/IF97 physics modules):
   ```bash
   cd simulator_source
   PYTHONPATH=src python -B -m pytest tests/test_ab4_geometry.py \
     tests/test_ab4_lines.py tests/test_ab4_drum_model.py \
     tests/test_ab4_furnace.py tests/test_props_if97.py \
     tests/test_props_fuels_gas.py tests/test_backend_protocol.py -q
   ```
   With `iapws==1.5.5` installed (`requirements-lock.txt`), these 7 physics/props/protocol modules pass **`88 passed`**, and the full `simulator_source/tests/` suite returns `151 passed, 2 skipped, 1 deselected, 2 failed` (with the only 2 failures in `test_workspace_structure.py` and `test_governance_policy_contracts.py` referencing excluded upstream non-core files; see `docs/SOURCE_PROVENANCE.md` and `docs/KNOWN_LIMITATIONS.md`; without `iapws`, the 7 non-`iapws` modules pass `45 passed, 1 skipped`).

## Level B — Optional Manuscript DOCX/PDF Checks (Author Local Copy Only)
Formatted submission `.docx` and `.pdf` files are excluded from GitHub (`.gitignore`). If supplied locally by the author (requires external Poppler `pdftotext`/`pdfinfo`, plus optional `python-docx` for `build_full_paper.py` and Windows `pywin32` for Word COM field-update/PDF export):
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
- Tested on a fresh clone of `https://github.com/CAPTW/pub053-jmse-boiler-leak-warning.git` (`v1.0.4-pub053-r2` verification baseline commit `8e38fa1c711289abddaae2c656e2433d07604f6f`; superseding `v1.0.3-pub053-r2` baseline `914f60ef2d4e68b910241cc4cfe61b9095523e23`, `v1.0.2-pub053-r2` baseline `5170c4a4e539e7a0c84d739fa362087736f76bf8`, `v1.0.1-pub053-r2` baseline `37b0ded2f43f9fb874e45069202bf43f2c20ec4f`, and `v1.0.0-pub053-r2` baseline `31636c66bf664512795ce20ee886a0631de04a92`) using `Python 3.12.13` (with required `iapws==1.5.5`) and `Python 3.14.3` (without `iapws`, fallback-guard/mock test only).
- Verified `279/279` files against `docs/FILE_MANIFEST.json` with **`0` byte/SHA-256 mismatches** and **`0` CRLF/mixed EOL text files** (`bad_eol_count = 0`).
- Verified strict default exit code `1` without primary `.npz` files for `code/verify_features.py`, `code/reproduce_analysis.py`, and `code/make_figures_r2.py` (and documented `missing_iapws_error` guard when all 48 `.npz` files are supplied without `iapws`).
- Verified exit code `0` for `code/test_analysis.py` (`8/8` tests on both Python 3.12 with `iapws==1.5.5` and Python 3.14 with fallback warning + mock CLI guard), `code/verify_features.py --archived-tables-only --out build/reproduced_results`, `code/reproduce_analysis.py --archived-tables-only --out build/reproduced_results`, `code/make_figures_r2.py --archived-assets-only --results build/reproduced_results --out build/reproduced_figures`, `manuscript_verification/verify_tables_from_archived_results.py`, the 7 core `simulator_source/tests/` modules (`88 passed in 2.86s` with `iapws==1.5.5`), and the 7 non-`iapws` simulator contract modules (`45 passed, 1 skipped, 1 warning in 5.12s` without `iapws`), with `results/` and `figures/` bit-for-bit unmodified (`git status --short` empty; logged in `docs/execution_logs/fresh_clone_reproduction_log.json`).
