# Reproduction and Verification Guide (`PUB-053`)

## Level A — Direct Standalone Reproduction & Verification (Fresh Clone, No Private Files Required)
Install dependencies into an isolated Python 3.12 virtual environment (`pip install -r requirements-lock.txt`, or `conda env create -f environment.yml`) and run all commands from the repository root without overwriting `results/`:

1. **R2 Analysis & Figure Reproduction Suite (`code/`)**:
   ```bash
   python -B code/test_analysis.py
   python -B code/verify_features.py --out results_reproduced
   python -B code/reproduce_analysis.py --out results_reproduced
   python -B code/make_figures_r2.py --results results_reproduced --out figures_reproduced
   ```
   - Automatically detects whether the 48 binary `.npz` arrays (`data/observations/*.npz` and `data/traces/*.npz` from `PUB053_Manuscript_Package_R2.zip`) are mounted locally.
   - When the 48 binary `.npz` files are absent (default public fresh clone), runs cleanly in `archived_r2_tables_and_reconstructed_inputs` mode against `data/`, `results/`, `results_archived/`, and `simulator_source/`, verifying `4/4` unit tests, `48/48` normal-persistence checks (`max_abs_diff = 0.0`), `8/8` component-crossing checks (`max_abs_diff = 0.0`), `96/96` episode-method rows, `32/32` delay-window checks, `50/50` Table 3/4/5/7 cross-checks, freshly rendering `fig4_method_summary_delay_lead.png` from `results_reproduced/episode_results.csv`, and validating all 7 manuscript figures in `figures_reproduced/`.
   - When all 48 `.npz` files from `PUB053_Manuscript_Package_R2.zip` are placed under `data/observations/` and `data/traces/`, switches automatically to `full_raw_npz_replay` mode without changing CLI invocations.

2. **Tables 1–8, Reconstructed Inputs & Figures 1–7 Cross-Check (`manuscript_verification/`)**:
   ```bash
   python -B manuscript_verification/verify_tables_from_archived_results.py
   ```
   Checks Table 1 parameters against `simulator_source/configs/ab4_marine_aux.yaml` and `core/ab4/drum_model.py`, asserts `50/50` cross-checks, verifies `data/reconstructed_inputs/` and `results_archived/reconstructed_inputs/` plus `current_manuscript_table_checks.csv` (`62/62`), recomputes Table 6 summary stats from `results/episode_results.csv`, verifies `5/7/8` cutoff counts and `32/32` delay-window identity, and inspects `figures/` + `figures/raw_source_assets/`.

3. **Physics Core (`ab4`) & Property Layer Unit Tests (`simulator_source/`)**:
   ```bash
   PYTHONPATH=simulator_source/src python -m pytest simulator_source/tests/test_ab4_geometry.py \
     simulator_source/tests/test_ab4_lines.py simulator_source/tests/test_ab4_drum_model.py \
     simulator_source/tests/test_ab4_furnace.py simulator_source/tests/test_props_if97.py \
     simulator_source/tests/test_props_fuels_gas.py simulator_source/tests/test_backend_protocol.py -v
   ```
   Runs the `88` core `ab4` + property tests in ~16 s. Running the entire `simulator_source/tests/` directory (requiring `pyarrow==16.1.0` with `numpy==1.26.4` and `iapws==1.5.5`) also passes the pipeline/closed-loop/cross-model suites, while reporting 2 expected failures in `test_workspace_structure.py` and `test_governance_policy_contracts.py` because top-level compatibility wrappers (`blueprint.md`, `scripts/check_dataset_governance.py`) were excluded from the minimal `simulator_source/` snapshot (see `docs/SOURCE_PROVENANCE.md`).

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
