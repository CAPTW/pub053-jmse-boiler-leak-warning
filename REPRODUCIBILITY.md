# Reproducibility Guide (`v1.0.1-pub053-r2`)

## 1. Environment Setup
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements-lock.txt
```

## 2. Mode A — Unit Tests & Strict Missing-Raw-NPZ Check (Standalone Clone)
Default CLI invocations of `verify_features.py`, `reproduce_analysis.py`, and `make_figures_r2.py` **require all 48 primary `.npz` files** (`data/observations/*.npz` and `data/traces/*.npz` from `PUB053_Manuscript_Package_R2.zip`) and fail loudly (`exit 1`, `"all_passed": false`, `"provenance_mode": "missing_raw_npz_error"`) when those files are absent:

```bash
python -B code/test_analysis.py
python -B code/verify_features.py --out results_reproduced          # exits 1 when .npz absent
python -B code/reproduce_analysis.py --out results_reproduced       # exits 1 when .npz absent
python -B code/make_figures_r2.py --results results_reproduced --out figures_reproduced  # exits 1 when .npz absent
```

`code/test_analysis.py` (`6/6` tests) validates sequential detector rules, signed EWLS residuals (`+`/`-` without `np.abs()`), quantile dominance vs. general counterexample, 24-episode Table 6 rounding (`51.3 min` / `115.5 min`), keyed CSV alignment (`cutoff_leads_by_block.csv`), and full 24-episode (`144`-array) Supplement S3 raw reconstruction + negative mutation detection over an isolated temporary `.npz` fixture.

## 3. Mode B — Explicit Standalone Verification (`--archived-tables-only` / `--archived-assets-only`)
In a public clone without the 48 binary `.npz` files, pass the explicit opt-in flags to audit all algebraic/tabular invariants, derived delays/leads, Table 6 summaries, cutoff leads (`5/7/8`), delay-window identity (`32/32`), Figure 4 Matplotlib rendering, and archived graphic validation into separate output directories (`results_reproduced/`, `figures_reproduced/`) without overwriting `results/` or `figures/`:

```bash
python -B code/verify_features.py --archived-tables-only --out results_reproduced
python -B code/reproduce_analysis.py --archived-tables-only --out results_reproduced
python -B code/make_figures_r2.py --archived-assets-only --results results_reproduced --out figures_reproduced
python -B manuscript_verification/verify_tables_from_archived_results.py
```

Inspect the JSON reports (`feature_verification_report.json`, `reproduction_comparison_report.json`, `figure_generation_manifest.json`) for exact separation between `recomputed_from_raw_inputs`, `compared_against_reference_results`, `archived_table_internal_checks`, `preserved_or_copied_artifacts`, and `unexecuted_items`.

## 4. Mode C — Full Raw Replay (When Primary `.npz` Files Are Supplied)
Place all 24 `data/observations/<episode>.npz` and 24 `data/traces/<episode>.npz` files from `PUB053_Manuscript_Package_R2.zip` under `data/` and run without `--archived-*-only`:

```bash
python -B code/verify_features.py --out results_reproduced
python -B code/reproduce_analysis.py --out results_reproduced
python -B code/make_figures_r2.py --results results_reproduced --out figures_reproduced
```

## 5. Simulator Source Unit Tests (`simulator_source/`)
Notice tests under `simulator_source/tests/` read YAML paths relative to `simulator_source/`. Tests not requiring optional GPL `iapws` run directly from `simulator_source/`:

```bash
cd simulator_source
PYTHONPATH=src python -B -m pytest tests/test_ab4_geometry.py tests/test_ab4_lines.py tests/test_backend_protocol.py tests/test_fmu_contract.py tests/test_manifest_integrity.py tests/test_pipeline_contracts.py tests/test_simulator_run_to_file_smoke.py -q
```
(Optional: installing `iapws` enables `test_ab4_drum_model.py`, `test_ab4_furnace.py`, `test_props_if97.py`, and `test_props_fuels_gas.py`.)
