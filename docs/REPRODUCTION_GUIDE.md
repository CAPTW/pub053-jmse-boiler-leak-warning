[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](README.md)

# Reproduction guide

This guide describes the analysis code in the manuscript's frozen
[v1.0.6 release](https://github.com/CAPTW/pub053-jmse-boiler-leak-warning/releases/tag/v1.0.6-pub053-r2).
Documentation maintenance on `main` does not change that release or rerun the study.

Choose a path:

- [Check the public files](#2-check-the-public-files): no external study data needed.
- [Reanalyse the frozen observations](#3-reanalyse-the-frozen-observations): requires the original 48 NPZ files.
- [Run optional checks](#6-optional-checks): simulator tests or a locally supplied manuscript.

## 1. Set up the environment

Run commands from the repository root using Python 3.12.

```bash
python -m venv .venv
```

Activate the environment with the command for your shell:

| Shell | Command |
|---|---|
| Linux/macOS | `source .venv/bin/activate` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows Command Prompt | `.venv\Scripts\activate.bat` |

Then install the pinned dependencies:

```bash
python -m pip install -r requirements-lock.txt
```

The [dependency file](../requirements-lock.txt) pins `iapws==1.5.5` and the numerical
and plotting packages used for verification. The runtime helper checks whether the
IF97 backend is usable and reports its installed version; it does not reject a
usable backend solely because its version differs from 1.5.5. Use the pinned
environment for the documented results.

## 2. Check the public files

A public clone contains archived tables, reconstructed parameters, figures and
synthetic tests. It does not contain the original 48 NPZ files.

```bash
python -B code/test_analysis.py
python -B code/verify_features.py --archived-tables-only --out results_reproduced
python -B code/reproduce_analysis.py --archived-tables-only --out results_reproduced
python -B code/make_figures_r2.py --archived-assets-only --results results_reproduced --out figures_reproduced
python -B manuscript_verification/verify_tables_from_archived_results.py
```

Use separate output directories as shown. Keep the reference files in `results/`
and `figures/` unchanged.

| Step | What it checks or produces |
|---|---|
| Unit tests | Eight tests using isolated synthetic and temporary fixtures. |
| Feature checks | Reconstructed fit/threshold JSONs and internal checks on 48 normal-persistence rows and eight component-crossing rows. |
| Analysis checks | Derived delays, lead times, summaries and 50 archived table checks. |
| Figures | Figure 4 plotted from CSV; Figures 1–2 recomposed; Figures 3 and 5–7 copied from preserved assets. |
| Manuscript table checks | Consistency of the bundled reference tables and manuscript-check records. |

Archive mode does not refit the model from observations and does not create
`recomputed_fit_params.json`. Its 50 table checks are written to
`archived_tables_3_4_5_7_internal_checks.json`; they are not presented as a new
raw-data execution of the archived cross-check CSV.

**Mode selection depends on the inputs.** The archive flags permit archive mode
when the raw set is incomplete or absent. If all 48 expected NPZ files are present,
raw reanalysis takes precedence even when an archive flag is supplied.

## 3. Reanalyse the frozen observations

Obtain the original R2 data from the corresponding author and place all expected
files under `data/observations/` and `data/traces/`: 24 files in each directory.
The episode names and expected paths are recorded in
[episode_metadata.csv](../data/episode_metadata.csv). See
[data provenance](DATA_PROVENANCE.md) for the archive boundary.

With the complete raw set and the pinned environment, run:

```bash
python -B code/verify_features.py --out results_reproduced
python -B code/reproduce_analysis.py --out results_reproduced
python -B code/make_figures_r2.py --results results_reproduced --out figures_reproduced
```

Run the analysis step before the figure step so Figure 4 uses the newly generated
`episode_results.csv`. The figure script otherwise falls back to the bundled
reference CSV if that output file is missing.

| Step | Raw-mode work |
|---|---|
| Features | Reconstruct scores, refit OLS/EWMA parameters, compare 144 trace arrays and write `recomputed_fit_params.json`. |
| Analysis | Recompute alarms, event times and six comparison CSVs from the frozen observations. |
| Figures | Render Figures 1–3 and 5–7 from NPZ inputs, and Figure 4 from the episode-results CSV. |

This is stored-output reanalysis. It does not execute the original boiler
simulation. Regenerating the original trajectories also requires the study-time
source tree and applied configurations; see [source provenance](SOURCE_PROVENANCE.md).

## 4. Read the reports and exit codes

| Report | Default output location |
|---|---|
| Feature checks | `results_reproduced/feature_verification_report.json` |
| Analysis comparisons | `results_reproduced/reproduction_comparison_report.json` |
| Figure generation | `figures_reproduced/figure_generation_manifest.json` |

Check `provenance_mode`, `density_backend`, `all_passed` and the detailed
comparison or generation records. An exit code of 0 means that the checks for the
selected mode passed; it does not establish checks outside that mode.

| Inputs and options | Selected mode | Normal outcome |
|---|---|---|
| Incomplete raw set, no archive flag | `missing_raw_npz_error` | Exit 1; no raw reconstruction or plotting. |
| Incomplete raw set, archive flag | `archived_tables_only` or `archived_assets_only` | Exit 0 if the archive checks succeed. |
| Complete raw set, usable IF97 backend | `full_raw_npz_replay` | Exit 0 if that script's checks succeed. |
| Complete raw set, unusable IF97 backend | `missing_iapws_error` | Exit 1 unless the approximate option is explicit. |

All three CLI scripts collect backend metadata before returning a missing-input
error. If available, this includes an IF97 density calculation at 7 bar. With no
archive opt-in, missing raw inputs stop the pipeline before raw feature
reconstruction, density-spline construction and plotting.

The feature comparison uses an absolute trace tolerance of `1e-4`. Analysis
comparisons align rows by their keys. The 50-row cross-check also records allowed
provenance-label differences and display-rounding matches. A comparison result
does not imply byte-identical CSV files. See the
[comparison implementation](../code/_common.py) and
[analysis script](../code/reproduce_analysis.py).

In archive figure mode, `all_files_valid=true` can coexist with
`figure_spec_verified.all_specs_verified=false`: the raw figure specifications
were not re-executed. In raw mode, also inspect `raw_replay_exact_if97_backend`
and `allow_approx_density_override`. Figure generation does not independently
check numerical equivalence against reference traces or CSVs.

## 5. Approximate density and synthetic tests

`--allow-approx-density` permits a diagnostic raw run when the IF97 backend is
unavailable. It uses the implemented approximate density fallback. Feature and
analysis scripts still compare numerical outputs and may return 1. The figure
script can return 0 while recording `raw_replay_exact_if97_backend=false` and
`allow_approx_density_override=true`; successful plotting does not certify
IF97 numerical reproduction.

The synthetic IF97 test deliberately forces that fallback. Its assertions require
**132 of 144 arrays to pass and 12 to fail**, with a maximum absolute difference
above `1e-4`, so the overall comparison fails. The test passes by detecting that
expected discrepancy. When `iapws` is unavailable, this particular branch is
skipped and `synthetic_if97_vs_fallback_branch_executed=false` is reported.
Passing the remaining synthetic tests does not validate real IF97 trajectories.

## 6. Optional checks

### Simulator core

The source snapshot includes the seven core physics/property/protocol test modules
listed in the historical record below. Run them from `simulator_source/` with
`PYTHONPATH` set to `src`.

Linux/macOS:

```bash
cd simulator_source
PYTHONPATH=src python -B -m pytest -p no:cacheprovider -q \
  tests/test_ab4_geometry.py tests/test_ab4_lines.py \
  tests/test_ab4_drum_model.py tests/test_ab4_furnace.py \
  tests/test_props_if97.py tests/test_props_fuels_gas.py \
  tests/test_backend_protocol.py
```

Windows PowerShell:

```powershell
cd simulator_source
$env:PYTHONPATH = "src"
python -B -m pytest -p no:cacheprovider -q `
  tests/test_ab4_geometry.py tests/test_ab4_lines.py `
  tests/test_ab4_drum_model.py tests/test_ab4_furnace.py `
  tests/test_props_if97.py tests/test_props_fuels_gas.py `
  tests/test_backend_protocol.py
```

Return to the repository root with `cd ..` afterwards. The broader non-slow suite
has two recorded failures involving excluded upstream files; it is not an
all-passing release gate. See [known limitations](KNOWN_LIMITATIONS.md).

### Local manuscript

The formatted DOCX/PDF and journal template are not bundled. With local copies
and the external Poppler tools (`pdftotext`, `pdfinfo`), run the static verifier
with explicit inputs and separate output paths:

```bash
python -B manuscript_verification/verify_revised_manuscript.py --docx "path/to/revised.docx" --pdf "path/to/revised.pdf" --num-dir results_archived --tables-csv-out results_reproduced/manuscript/table_checks.csv --report-out results_reproduced/manuscript/docx_report.json
```

`python-docx` is needed for rebuilding the manuscript, and Windows `pywin32` plus
Microsoft Word are needed for Word COM automation. These are optional author tools,
not requirements for the analysis commands above. See
[third-party notices](../THIRD_PARTY_NOTICES.md) and the
[manuscript verification report](../manuscript_verification/LATEST_MANUSCRIPT_VERIFICATION_REPORT.md).
Reusing an archived Word COM log is not a new dynamic check of a supplied DOCX.

## 7. Published verification evidence

The following are retained results from the v1.0.6 packaging runs. They are not
new runs performed by this documentation update.

| Published record | Recorded result | Scope |
|---|---|---|
| [Fresh-clone log](execution_logs/fresh_clone_reproduction_log.json) | 12/12 expected outcomes: nine exit 0, three expected exit 1. | No original NPZ inputs on the packaging workstation. |
| Unit-test entries in that log | 8/8 on Python 3.12 with `iapws`; 8/8 on Python 3.14 without it. | Synthetic fixtures; the IF97 comparison branch runs only with `iapws`. |
| Core-test entry in that log | 88 passed. | Seven core modules with `iapws==1.5.5`. |
| [Non-slow simulator log](execution_logs/pytest_ab4_integration_log.txt) | 151 passed, two skipped, one deselected, two failed. | `pytest -m "not slow"`; excluded upstream paths cause the two failures. |

The three expected exit-1 runs verify missing-raw-input handling. The logged
dependency guards are mocked unit-test checks; they are not an unmocked run on
the unavailable original data. Current manuscript evidence is separated from
historical Word COM evidence in the
[manuscript report](../manuscript_verification/LATEST_MANUSCRIPT_VERIFICATION_REPORT.md).
