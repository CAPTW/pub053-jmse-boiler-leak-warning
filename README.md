# PUB-053 JMSE Release Candidate: Closed-Loop Tube-Leak Early Warning in a Four-State Marine Auxiliary Steam Boiler

This dedicated companion repository packages the **physics-core snapshot (`ab4` inside `boiler_pdm_sim`)**, **provenance-separated R2 and current-manuscript verification artifacts**, **reconstructed structured inputs**, **publication figures and raw assets**, **machine-readable bibliography mappings**, and **auditable AI-usage & reproduction scripts** supporting the JMSE manuscript:

> **Closed-Loop Tube-Leak Early Warning in a Four-State Marine Auxiliary Steam Boiler: Demand-Versus-Flow Residuals, Functional Lead Times, and Component Attribution**

## Repository Structure
- `simulator_source/` — Self-contained snapshot of `boiler_pdm_sim` (`commit 4fea4646723f04db41583cb682bac8b62c44bc05`, upstream `https://github.com/CAPTW/boiler-pdm-sim.git`), containing `src/boiler_pdm_sim/`, `configs/ab4_marine_aux.yaml`, `tests/`, and architecture specs.
- `results_archived/` — Provenance-separated verification archive:
  - Root: R2-derived trace-replay outputs (`r2_replay_summary.json`, `episode_results.csv`, `summary.csv`, `normal_persistence.csv`, `recomputed_vs_archived.csv`, `quantile_claim_check.json`, `tables_3_4_5_7_crosscheck.csv`, `tables_and_rounding_summary.json`, `cutoff_leads_by_block.csv`, `cutoff_leads_summary.csv`, `component_crossing_timing.csv`, `delay_window_check.csv`).
  - `reconstructed_inputs/`: Five structured JSON files reconstructing Tables 1–5 and 7 from archived cross-checks, YAML configs, and Supplement S2.
  - `prior_draft_review_ce0e9a0e/`: Historical QA logs strictly auditing the pre-revision draft `PUB053_Manuscript_JMSE_Submission.docx` (`SHA-256: ce0e9a0e3c6c6332942d7ef99ae464832c3c3b57eaa0172130a220312103d4e5`).
  - `current_manuscript_verification/`: Fresh verification table checks (`62/62` rows across Tables 3–8) and JSON report generated directly from the current revised DOCX (`JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx`).
- `figures/` — Manuscript Figures 1–7 (`fig1_normal_overview.png` through `fig7_normal_score_traces.jpeg`), `raw_source_assets/` (upstream uncomposited image assets), and `FIGURE_MAP.md`.
- `references/` — All 27 bibliography entries and 26 in-text citation groups (`pub053_references.json`, `.bib`, `.ris`, `word_sources.xml`, `citation_mapping_table.csv`, `CITATION_MAPPING_TABLE.md`).
- `manuscript_verification/` — Manuscript assembly, `<w:sdt>` + live Word `REF` citation synchronization, and verification scripts (`build_full_paper.py`, `combine_normal_figs.py`, `create_automated_citation_docx.py`, `sync_citations_and_references.py`, `word_update_export_and_test.py`, `verify_revised_manuscript.py`, `verify_tables_from_archived_results.py`, `verify_citations_and_manuscript.py`, `check_cutoff_leads.py`, `check_delay_window.py`, `MANUSCRIPT_ARTIFACT_MAP.md`, `citation_editing_and_reordering_test_log.json`, `CITATION_EDITING_TEST_REPORT.md`, and `r2_text_archive/`).
- `docs/` — `REPRODUCTION_GUIDE.md`, `AI_USAGE_AUDIT.md`, `FILE_MANIFEST.json`, `FILE_MANIFEST.md`, and `execution_logs/`.

## Scope & Availability of External Primary Binary Archives
- **Directly verifiable inside this repository**:
  1. `ab4` four-state saturated-steam drum-boiler geometry, line hydraulics, spline IAPWS-IF97 thermodynamics (`core/thermo/if97.py` / `props/if97.py`), closed-loop `obs` operation, and backend protocol (`pytest` unit suite in `simulator_source/tests/`).
  2. All numerical values in Manuscript Tables 1–8 and text claims (`24` episodes / `259,224` samples / `96` episode-method comparisons, `51.3 min` median delay reduction, `115.5 min` max demand/combined delay, `5/7/8` cutoff counts at `0.70/0.75/0.80 m`, `32/32` delay-window identity) via `results_archived/` and `simulator_source/`.
  3. Manuscript Figures 1–7 and `raw_source_assets/` image integrity.
- **External primary workstation boundary (not bundled here)**:
  - `observable_baseline_study_20260915T215200Z_be142b32.zip` (`data/observations/*.npz`, `data/traces/*.npz`, `data/block_design.json`, `data/original_configs/*.json`) and `PUB053_Manuscript_Package_R2.zip` (`code/reproduce_analysis.py`, `code/verify_features.py`, `code/test_analysis.py`, `code/make_figures_r2.py`, `results/independent_fit.json`, `results/episode_method_results.csv`, `results/endpoint_sensitivity.csv`) reside on the study owner's external workstation and were not present on the packaging machine.

## Quick Verification Commands
```bash
# 1. Verify Tables 1-8, reconstructed inputs & Figures 1-7 from archived artifacts
python manuscript_verification/verify_tables_from_archived_results.py

# 2. Verify latest DOCX & PDF (pass local manuscript paths after copying DOCX/PDF locally)
python manuscript_verification/verify_revised_manuscript.py --docx <path-to-revised.docx> --pdf <path-to-revised.pdf>

# 3. Run ab4 physics & property core unit tests inside simulator_source/
cd simulator_source
PYTHONPATH=src pytest tests/test_ab4_geometry.py tests/test_ab4_lines.py tests/test_ab4_drum_model.py tests/test_ab4_furnace.py tests/test_props_if97.py tests/test_props_fuels_gas.py tests/test_backend_protocol.py -v
```

## GenAI Disclosure Summary
As declared in the manuscript (**Section 2.4** and **Acknowledgments**), **OpenAI Codex** served as the principal AI-assisted coding tool during development of `boiler_pdm_sim` / `ab4` under author physical specification and verification (verified CLI versions `0.104.0`–`0.142.3` and models `gpt-5.3-codex-spark`, `gpt-5.4`, `gpt-5.5` across local logs plus Phase A commits `bb0c2d5`–`4fea464` through `2026-06-30`; separate-workstation per-session logs for `2026-06-30` are unrecorded in the local database). During JMSE manuscript preparation, Google Antigravity and deterministic Python scripts assisted with template formatting, `<w:sdt>` + live `REF` citation automation, and table/text verification without generating new simulation trajectories or modifying numerical results. See `docs/AI_USAGE_AUDIT.md`.
