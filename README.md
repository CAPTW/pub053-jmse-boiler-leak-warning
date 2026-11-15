# PUB-053 Companion Repository: Closed-Loop Tube-Leak Early Warning in a Four-State Marine Auxiliary Steam Boiler

This dedicated public companion repository (`https://github.com/CAPTW/pub053-jmse-boiler-leak-warning`) preserves the **`boiler_pdm_sim` (`ab4`) simulator source snapshot**, **structured metadata and reconstructed inputs**, **baseline R2 results and runnable verification/reproduction scripts**, **publication figures and raw assets**, **machine-readable bibliography mappings**, and **auditable provenance/execution logs** for JMSE manuscript `PUB-053`:

> **Closed-Loop Tube-Leak Early Warning in a Four-State Marine Auxiliary Steam Boiler: Demand-Versus-Flow Residuals, Functional Lead Times, and Component Attribution**

## Study Purpose & Scope
- Evaluates closed-loop tube-leak masking and early-warning performance across **12 evaluation/development blocks** (`D1`–`D4`, `E1`–`E8`; **24 paired 6 h episodes**, `259,224` total samples at `dt = 2.0 s`), comparing state-only (`B0_state`), flow-only (`Flow_only`), demand-only (`Command_only`), and max-combined (`B1_combined`) EWMA/sequential detectors (`elapsed >= 600 s`, strict `> threshold`, `1800 s` cooldown).
- Separates **Stage 1** (single deterministic simulation generation), **Stage 2** (R2 stored-data statistical reanalysis without re-running trajectories), and **Stage 3/4** (JMSE manuscript preparation, `<w:sdt>` + live Word `REF` citation automation, and independent verification).

## Repository Layout
- `code/` — Runnable R2 verification, raw `.npz` Supplement S3 reconstruction (`reconstruct_features_from_observations`), keyed tabular reproduction, and figure-generation suite (`_common.py`, `test_analysis.py`, `verify_features.py`, `reproduce_analysis.py`, `make_figures_r2.py`). Default CLI runs require all 48 primary `.npz` files (`data/observations/*.npz`, `data/traces/*.npz`) and fail loudly (`rc=1`) if absent; explicit `--archived-tables-only` / `--archived-assets-only` flags verify bundled R2 tables and preserved assets into separate output folders without modifying `results/`.
- `data/` — Episode design and metadata (`episode_metadata.csv` [24 episodes], `block_design.json` [12 blocks]), `original_configs/ab4_marine_aux.yaml`, `reconstructed_inputs/` (5 structured JSON files for Tables 1–5 & 7), and README documenting upstream archives (`observable_baseline_study_20260915T215200Z_be142b32.zip` vs. `PUB053_Manuscript_Package_R2.zip`). See [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) and [`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md).
- `results/` — Preserved baseline R2 reference outputs (12 CSV/JSON files, including `episode_results.csv`, `summary.csv`, `normal_persistence.csv`, `delay_window_check.csv`, `cutoff_leads_by_block.csv`, `cutoff_leads_summary.csv`, `component_crossing_timing.csv`, `tables_3_4_5_7_crosscheck.csv`, `r2_replay_summary.json`, `quantile_claim_check.json`). Never overwritten by `--out results_reproduced`.
- `results_archived/` — Provenance-separated audit archive: R2 replay tables (`results_archived/*.csv|json`), `reconstructed_inputs/`, historical pre-revision draft QA logs (`prior_draft_review_ce0e9a0e/`, strictly for original draft `SHA-256: ce0e9a0e...`), and latest revised-manuscript table checks (`current_manuscript_verification/`).
- `simulator_source/` — Self-contained snapshot of `boiler_pdm_sim` extracted from local development base commit `4fea4646723f04db41583cb682bac8b62c44bc05` (5 commits ahead of private `CAPTW/boiler-pdm-sim` `origin/phase-a/revive-kickoff` `497db42`; `4fea4646...` returns HTTP `422` upstream). See `docs/SOURCE_PROVENANCE.md` for exact differences against the patched study `source_copy/`.
- `figures/` — Manuscript Figures 1–7 (`fig1_normal_overview.png` through `fig7_normal_score_traces.jpeg`), `raw_source_assets/` (upstream uncomposited plots), and `FIGURE_MAP.md`.
- `manuscript_verification/` — JMSE manuscript assembly, `<w:sdt>` + live Word `REF` citation synchronization (`ADD`, `MOVE`, `DELETE`, `REORDER`), table cross-check scripts, `MANUSCRIPT_ARTIFACT_MAP.md`, and `r2_text_archive/`.
- `references/` — All 27 bibliography entries and 26 in-text citation groups (`pub053_references.json`, `.bib`, `.ris`, `word_sources.xml`, `citation_mapping_table.csv`, `CITATION_MAPPING_TABLE.md`).
- `docs/` — [`REPRODUCTION_GUIDE.md`](docs/REPRODUCTION_GUIDE.md), [`DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md), [`KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md), [`SOURCE_PROVENANCE.md`](docs/SOURCE_PROVENANCE.md), [`AI_USAGE_AUDIT.md`](docs/AI_USAGE_AUDIT.md), `FILE_MANIFEST.json`, `FILE_MANIFEST.md`, and `execution_logs/`.
- [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) — Top-level reproduction contract distinguishing `full_raw_npz_replay` vs. `--archived-tables-only` / `--archived-assets-only` provenance buckets (`v1.0.2-pub053-r2`).

## Environment Setup & Reproduction Commands
Recommended isolated Python 3.12 setup:
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-lock.txt
```
(Alternatively use `conda env create -f environment.yml` or `pip install -e .`).

By default (without all 48 primary `.npz` archives in `data/observations/` and `data/traces/`), `code/verify_features.py`, `code/reproduce_analysis.py`, and `code/make_figures_r2.py` exit with code `1` (`missing_raw_npz_error` / `all_passed: false`). When all 48 `.npz` files are supplied locally, the same commands execute `full_raw_npz_replay`.

To verify the bundled standalone repository assets without the unbundled `.npz` archives into separate output folders (`results_reproduced/`, `figures_reproduced/`) so `results/` remains untouched, pass the explicit archived opt-in flags:
```bash
python -B code/test_analysis.py
python -B code/verify_features.py --archived-tables-only --out results_reproduced
python -B code/reproduce_analysis.py --archived-tables-only --out results_reproduced
python -B code/make_figures_r2.py --archived-assets-only --results results_reproduced --out figures_reproduced
python -B manuscript_verification/verify_tables_from_archived_results.py
```
To run the simulator unit tests in a base environment without optional `iapws` (run from `simulator_source/` so relative `configs/base.yaml` paths resolve cleanly):
```bash
cd simulator_source
PYTHONPATH=src python -B -m pytest tests/test_ab4_geometry.py tests/test_ab4_lines.py tests/test_backend_protocol.py tests/test_fmu_contract.py tests/test_manifest_integrity.py tests/test_pipeline_contracts.py tests/test_simulator_run_to_file_smoke.py -q
```

## Expected Results & Known Limitations / Archive Boundaries (`v1.0.2-pub053-r2`)
- **Verified Standalone Outputs**:
  - `code/test_analysis.py`: `7/7` unit and raw-replay tests pass (signed `r_m` EWLS residuals, synthetic 24-episode Supplement S3 raw `.npz` reconstruction + 144-array verification + negative mutation failure test, canonical keyed CSV alignment for `cutoff_leads_by_block.csv`, and end-to-end synthetic raw-`.npz` replay of `reproduce_analysis.py` 50-row Table 3/4/5/7 cross-checks + `render_figures_from_raw_npz` Figures 1–7).
  - `code/verify_features.py`, `code/reproduce_analysis.py`, `code/make_figures_r2.py` (default without `.npz`): exit with code `1` (`all_passed: false`, explicit `missing_raw_npz_error`).
  - `code/verify_features.py --archived-tables-only`: verifies archived `normal_persistence.csv` (`48/48`, `max_abs_diff = 0.0`), `component_crossing_timing.csv` (`8/8`, `max_abs_diff = 0.0`, `Flow_only` crossed first in `8/8` evaluation blocks), and `fit_params.json`, reporting 5 explicit provenance buckets (`recomputed_from_raw_inputs` empty in archived mode).
  - `code/reproduce_analysis.py --archived-tables-only`: reproduces `96/96` episode-method records using keyed comparison (`("episode", "level_cutoff_m", "method")` on `cutoff_leads_by_block.csv`; `("episode", "method")` on `episode_results.csv` and `delay_window_check.csv`), Table 6 (`B1_combined` & `Command_only` median delay `75.9 min`, max `115.5 min`, `B0_state` median `127.3 min`, `51.3 min` median reduction, `5/7/8` cutoffs at `0.70/0.75/0.80 m`), `32/32` delay-window checks, and writes `archived_tables_3_4_5_7_internal_checks.json` (`50/50` archived internal checks) instead of copying `results/tables_3_4_5_7_crosscheck.csv` as newly executed output. In `full_raw_npz_replay`, `tables_3_4_5_7_crosscheck.csv` is freshly compared (`50` unique rows with `"kind"` provenance diffs and `"actual"` 12-sig-fig display formatting handled cleanly) and raw event timing enforces primary `meta/safety_state` (`label/safety_state`) and `truth/state_feasible` extraction (`raw_event_fallback_used == false`).
  - `code/make_figures_r2.py --archived-assets-only`: freshly renders `fig4_method_summary_delay_lead.png` (`1136x896`) via matplotlib from `results_reproduced/episode_results.csv`, validates preserved R2 graphic assets for `fig1`–`fig3` and `fig5`–`fig7` with explicit asset-provenance buckets, and sets `figure_spec_verified.all_specs_verified: false` (distinct from `all_files_valid: true`). In `full_raw_npz_replay`, `render_figures_from_raw_npz` renders all 7 manuscript-matched panels (`fig1`–`fig7`) directly from `.npz` arrays with `figure_spec_verified.all_specs_verified: true`.
  - `simulator_source/tests/`: in a base environment without optional `iapws`, running the 7 non-`iapws` core/contract/smoke modules from `simulator_source/` (`PYTHONPATH=src`) passes `45 passed, 1 skipped`. With optional `iapws==1.5.5` installed, the 7 core physics/props/protocol modules (`test_ab4_geometry.py`, `test_ab4_lines.py`, `test_ab4_drum_model.py`, `test_ab4_furnace.py`, `test_props_if97.py`, `test_props_fuels_gas.py`, `test_backend_protocol.py`) pass `88 passed`, and the full `simulator_source/tests/` suite reports `151 passed, 2 skipped, 1 deselected, 2 failed` (the 2 failures are `test_governance_policy_enforces_classification_and_retention` and `test_workspace_compatibility_paths_exist`, which reference excluded upstream non-core files; see `docs/SOURCE_PROVENANCE.md` and `docs/KNOWN_LIMITATIONS.md`).
- **Known Limitations (Primary Workstation Binary Archives Not Bundled)**:
  - `observable_baseline_study_20260915T215200Z_be142b32.zip` (study-time execution archive: `source_copy/` with pilot/study patches applied, `analysis/`, `configs/`, `exogenous/`, `runs/`) and `PUB053_Manuscript_Package_R2.zip` (`data/observations/*.npz` [24 files], `data/traces/*.npz` [24 files], `data/block_design.json`, `data/original_configs/`, R2 `code/`, baseline `results/`) reside on the study owner's external workstation and were not bundled in this release. See [`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md) and [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).
  - Consequently, standalone fresh clones cannot recompute `fit_params.json`, the `144` trace arrays in `data/traces/*.npz`, or raw `.npz` figure curves unless all 48 `.npz` files are supplied under `data/observations/` and `data/traces/`. Tracked text files are normalized to LF and governed by `.gitattributes` so fresh clones match `docs/FILE_MANIFEST.json` across operating systems.
  - Clean `4fea4646...` snapshot configs (`dt = 1.0 s`, `closed_loop_source = "truth"`) differ from the patched study `source_copy/` (`dt = 2.0 s`, `horizon_s = 21600`, `closed_loop_source = "obs"`, `safety.scheduler_intervention_policy = "process_protection_without_schedule_severity_oracle"`); see `docs/SOURCE_PROVENANCE.md`.

## Licensing, Third-Party Dependencies & Citation
- **Code License**: The `boiler_pdm_sim` snapshot (`simulator_source/`) and companion Python verification/reproduction code (`code/`, `manuscript_verification/`) are licensed under the **MIT License** (`LICENSE`).
- **External Dependencies (Not Bundled)**: Optional thermodynamic lookup `iapws` is distributed under **GPL-3.0** and is not bundled (simulator falls back cleanly to lightweight approximate properties unless `BOILER_STRICT_PROPS=1` and user-installed `iapws` are enabled). See `THIRD_PARTY_NOTICES.md`.
- **Journal Template & Manuscript Files**: The MDPI JMSE template (`jmse-template.dot`) and formatted `.docx`/`.pdf` manuscript files are excluded (`.gitignore`). Data artifacts and author-generated figures are shared strictly for scholarly peer review and academic reproducibility unless superseded by JMSE publication terms.
- **Citation**: See `CITATION.cff` (`repository-code: https://github.com/CAPTW/pub053-jmse-boiler-leak-warning`; publication DOI/volume remain unassigned pending peer review).

## GenAI Disclosure Summary
As declared in the manuscript (**Section 2.4** and **Acknowledgments**), **OpenAI Codex** served as the principal AI-assisted coding tool during development of `boiler_pdm_sim` / `ab4` under author physical specification and verification (verified local CLI versions `0.104.0`–`0.142.3`; models `gpt-5.3-codex-spark`, `gpt-5.4`, `gpt-5.5`; Phase A `ab4` commits through `2026-06-30`; upstream `PR_BODY.md` also carries a Claude Code footer on `2026-06-30`; external-workstation R2 session logs remain unverified). Google Antigravity and deterministic scripts handled Stage 3/4 JMSE assembly, citation automation, verification, and public packaging. See `docs/AI_USAGE_AUDIT.md`.
