# Reproduction and Verification Guide (`PUB-053`)

## Level A — Direct Verification from This Repository (Fully Self-Contained)
1. **Tables 1–8, Reconstructed Inputs & Figures 1–7 Verification**:
   ```bash
   python manuscript_verification/verify_tables_from_archived_results.py
   ```
   Checks Table 1 parameters against `simulator_source/configs/ab4_marine_aux.yaml` and `core/ab4/drum_model.py`, asserts `50/50` cross-checks in `tables_3_4_5_7_crosscheck.csv`, verifies `results_archived/reconstructed_inputs/` and `current_manuscript_verification/current_manuscript_table_checks.csv` (`62/62`), recomputes Table 6 summary stats from `episode_results.csv`, verifies Table 8 against `normal_persistence.csv`, verifies `5/7/8` cutoff counts and `32/32` delay-window identity, and inspects `figures/` + `raw_source_assets/`.

2. **Physics Core (`ab4`) & Property Layer Unit Tests**:
   ```bash
   cd simulator_source
   python -m venv .venv_test && source .venv_test/bin/activate
   pip install -e .[dev]
   pytest tests/test_ab4_geometry.py tests/test_ab4_lines.py tests/test_ab4_drum_model.py tests/test_ab4_furnace.py tests/test_props_if97.py tests/test_props_fuels_gas.py tests/test_backend_protocol.py -v
   ```

3. **Current Manuscript DOCX/PDF & Structured Citation Verification**:
   ```bash
   python manuscript_verification/verify_revised_manuscript.py --docx <revised.docx> --pdf <revised.pdf>
   python manuscript_verification/verify_citations_and_manuscript.py --original-docx <orig.docx> --docx <revised.docx> --pdf <revised.pdf>
   ```

## Level B — Full Raw-Trace Replay (Requires External Workstation Archives)
When `observable_baseline_study_20260915T215200Z_be142b32.zip` and `PUB053_Manuscript_Package_R2.zip` are attached locally:
```bash
python manuscript_verification/check_cutoff_leads.py /path/to/observable_baseline_study_20260915T215200Z_be142b32.zip ./out_cutoff
python manuscript_verification/check_delay_window.py /path/to/observable_baseline_study_20260915T215200Z_be142b32.zip ./delay_window_check.csv
```
