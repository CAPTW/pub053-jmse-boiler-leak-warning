# Reproducibility Guide (`v1.0.5-pub053-r2`)

## 1. Environment Setup
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements-lock.txt
```
`requirements-lock.txt` installs all verified R2 analysis and core simulator packages (`numpy==1.26.4`, `scipy==1.13.1`, `pandas==2.2.2`, `matplotlib==3.9.2`, `pyarrow==16.1.0`, `PyYAML==6.0.1`, `pytest==7.4.4`, `python-dateutil==2.9.0.post0`, `lxml==6.0.2`, `pillow==10.4.0`, and **`iapws==1.5.5`**). External PyPI **`iapws==1.5.5`** (GPL-3.0, not vendored in git; see `THIRD_PARTY_NOTICES.md`) IS **required** both for exact IAPWS-IF97 saturated-liquid density spline reconstruction in `code/verify_features.py`, `code/reproduce_analysis.py`, and `code/make_figures_r2.py` against raw `.npz` files (the built-in IAPWS-95 fallback deviates by `~0.00079 kg/m^3` at `7 bar` and up to `0.20 kg/m^3` over `0.5`–`120 bar`) and for `simulator_source` `core/ab4` physics tests. Optional local manuscript tools (`python-docx`, Windows `pywin32`, Poppler `pdftotext`/`pdfinfo`) are separate.

## 2. Mode A — Unit Tests & Strict Pre-Flight Checks (Standalone Clone)
Default CLI invocations of `verify_features.py`, `reproduce_analysis.py`, and `make_figures_r2.py` **require all 48 primary `.npz` files** (`data/observations/*.npz` and `data/traces/*.npz` from `PUB053_Manuscript_Package_R2.zip`) AND **`iapws==1.5.5`**:
- When the 48 `.npz` files are absent (current public clone), all 3 commands fail immediately at the pre-flight file check (`exit 1`, `"all_passed": false`, `"provenance_mode": "missing_raw_npz_error"`, before touching `iapws`).
- When all 48 `.npz` files are present without `iapws`, all 3 commands fail at the pre-flight dependency guard (`exit 1`, `"all_passed": false`, `"provenance_mode": "missing_iapws_error"` unless `--allow-approx-density` is explicitly passed; `--allow-approx-density` shifts density by `0.00079`–`0.20 kg/m^3`, risking numerical mismatch against IF97 `.npz` traces, though not executed directly on the real `.npz` files here because `PUB053_Manuscript_Package_R2.zip` is absent).
- By contrast, **`code/test_analysis.py` runs on an isolated synthetic 24-episode fixture and always exits `0` (`8/8`)**: with `iapws==1.5.5` (`Python 3.12`), it builds an `IAPWS97` fixture and proves forced fallback fails inside 144-array comparison (`132/144` passed, `max_diff = 0.0001328 > 1e-4`, `"synthetic_if97_vs_fallback_branch_executed": true`) alongside mocked CLI `missing_iapws_error` guards across all 3 scripts; without `iapws` (`Python 3.14`), the IF97-vs-fallback branch is skipped (`"synthetic_if97_vs_fallback_branch_executed": false`) and the synthetic fixture uses the same fallback cleanly, so passing `test_analysis.py` without `iapws` does **not** certify IF97 replay on real data. (See `docs/REPRODUCTION_GUIDE.md` for the complete failure-point table.)

```bash
python -B code/test_analysis.py
python -B code/verify_features.py --out results_reproduced          # exits 1 when .npz absent
python -B code/reproduce_analysis.py --out results_reproduced       # exits 1 when .npz absent
python -B code/make_figures_r2.py --results results_reproduced --out figures_reproduced  # exits 1 when .npz absent
```

`code/test_analysis.py` (`8/8` tests) validates sequential detector rules, signed EWLS residuals (`+`/`-` without `np.abs()`), IAPWS-97 (`iapws==1.5.5`) vs. fallback divergence (executed only when `iapws` is installed; skipped when absent) + mocked `missing_iapws_error` CLI guards across all 3 scripts (`verify_features.py`, `reproduce_analysis.py`, `make_figures_r2.py`) + `--archived-assets-only` `density_backend` manifest reporting, quantile dominance vs. general counterexample, 24-episode Table 6 rounding (`51.3 min` / `115.5 min`), keyed CSV alignment (`cutoff_leads_by_block.csv`), full 24-episode (`144`-array) Supplement S3 raw reconstruction + negative mutation detection, and end-to-end synthetic raw-`.npz` replay (`tables_3_4_5_7_crosscheck.csv` 50-row cross-check including Table 7 `None`/`null` list matching + negative check, primary trip/feasibility event extraction, and `render_figures_from_raw_npz` Figures 1–7 panel/window specs matching `[1200, min(t_end, T_confirm + 300)]` s and panel (b) `Observed level`-only plotting) over an isolated temporary `.npz` fixture.

## 3. Mode B — Explicit Standalone Verification (`--archived-tables-only` / `--archived-assets-only`)
In a public clone without the 48 binary `.npz` files, pass the explicit opt-in flags to audit all algebraic/tabular invariants, derived delays/leads, Table 6 summaries, cutoff leads (`5/7/8`), delay-window identity (`32/32`), Figure 4 Matplotlib rendering, and archived graphic validation into separate output directories (`results_reproduced/`, `figures_reproduced/`) without overwriting `results/` or `figures/`:

```bash
python -B code/verify_features.py --archived-tables-only --out results_reproduced
python -B code/reproduce_analysis.py --archived-tables-only --out results_reproduced
python -B code/make_figures_r2.py --archived-assets-only --results results_reproduced --out figures_reproduced
python -B manuscript_verification/verify_tables_from_archived_results.py
```

Inspect `"density_backend"` and the provenance buckets (`recomputed_from_raw_inputs`, `compared_against_reference_results`, `archived_table_internal_checks`, `preserved_or_copied_artifacts`, and `unexecuted_items`) across all three JSON reports (`feature_verification_report.json`, `reproduction_comparison_report.json`, `figure_generation_manifest.json`).

## 4. Mode C — Full Raw Replay (When Primary `.npz` Files Are Supplied Alongside `iapws==1.5.5`)
Note that `PUB053_Manuscript_Package_R2.zip` (48 `.npz` files and per-episode `*_config_applied.json`) and `observable_baseline_study_20260915T215200Z_be142b32.zip` (study-patched `source_copy/`) remain external/unbundled on the owner's workstation. If all 24 `data/observations/<episode>.npz` and 24 `data/traces/<episode>.npz` files are placed locally alongside `iapws==1.5.5`, run without `--archived-*-only` (all three commands abort with `exit 1` / `missing_iapws_error` if `iapws` is missing unless `--allow-approx-density` is explicitly passed):

```bash
python -B code/verify_features.py --out results_reproduced
python -B code/reproduce_analysis.py --out results_reproduced
python -B code/make_figures_r2.py --results results_reproduced --out figures_reproduced
```

## 5. Simulator Source Unit Tests (`simulator_source/`)
Notice tests under `simulator_source/tests/` read YAML paths relative to `simulator_source/`. With `iapws==1.5.5` (GPL-3.0, included in `requirements-lock.txt`) installed, the 7 core physics/props/protocol modules pass **`88/88` tests** and the full `simulator_source/tests/` suite yields `151 passed, 2 skipped, 1 deselected, 2 failed` (the 2 skipped are external-FMU tests; the 1 deselected item is `-m 'not slow'` for the 24 h gate; and the 2 failures reference upstream workspace files intentionally excluded from `simulator_source/`):

```bash
cd simulator_source
PYTHONPATH=src python -B -m pytest tests/test_ab4_geometry.py tests/test_ab4_lines.py tests/test_ab4_drum_model.py tests/test_ab4_furnace.py tests/test_props_if97.py tests/test_props_fuels_gas.py tests/test_backend_protocol.py -q
```
(Without `iapws`, the 7 non-`iapws` contract/smoke modules pass `45 passed, 1 skipped` while `ab4`/IF97 modules skip via `pytest.importorskip("iapws")`.)
