# Reproduce and verify the study

[Home](README.md) · [Documentation](docs/README.md) · [Detailed guide](docs/REPRODUCTION_GUIDE.md)

Start here to choose a workflow and install the analysis environment. The [detailed guide](docs/REPRODUCTION_GUIDE.md) is the reference for mode selection, output interpretation, dependency behavior, and additional checks.

## 1. Choose your workflow

| Your inputs | Workflow | What it establishes |
|---|---|---|
| Public repository only | Explicit archive verification | Consistency of stored tables and preserved figure assets |
| Public repository plus all 48 original NPZ files | Full raw-data reconstruction | Features and analysis tables compared with references; figures regenerated |
| Original study runtime, configurations, and run inputs | Original simulation regeneration | Outside the standalone public repository |

The [data guide](data/README.md) describes the missing inputs and their expected locations. Synthetic unit tests are available with either of the first two workflows.

## 2. Set up Python 3.12

Clone the repository:

```bash
git clone https://github.com/CAPTW/pub053-jmse-boiler-leak-warning.git
cd pub053-jmse-boiler-leak-warning
```

Create and activate a virtual environment.

**Linux or macOS**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the pinned dependencies:

```bash
python -m pip install -r requirements-lock.txt
```

If your PowerShell policy prevents activation, invoke `.\.venv\Scripts\python.exe` directly in place of `python` in the commands below. Activation is a convenience, not a requirement.

[requirements-lock.txt](requirements-lock.txt) pins the analysis packages, including `iapws==1.5.5`. The runtime helper reports the installed version and backend availability; it does not enforce an exact version comparison. Root-level editable installation (`pip install -e .`) is not a supported setup path for this repository layout.

## 3. Verify a public clone

From the repository root, with no external NPZ files installed:

```bash
python -B code/test_analysis.py
python -B code/verify_features.py --archived-tables-only --out results_reproduced
python -B code/reproduce_analysis.py --archived-tables-only --out results_reproduced
python -B code/make_figures_r2.py --archived-assets-only --results results_reproduced --out figures_reproduced
```

Inspect these reports:

| Report in your output directory | Main purpose |
|---|---|
| `feature_verification_report.json` | Archived feature/table checks and execution mode |
| `reproduction_comparison_report.json` | Derived analysis and comparisons with reference tables |
| `figure_generation_manifest.json` | Figure provenance, file validity, and specification checks |

In archive mode, Figure 4 is rendered from the derived episode table; other figures use preserved assets. The figure report can have `all_files_valid=true` while `all_specs_verified=false`, because original time-series reconstruction was not executed.

Default calls without the archive flags return `missing_raw_npz_error` and exit code `1` when the required raw set is incomplete. Backend metadata is still collected for the error report.

## 4. Reconstruct from the original NPZ files

Place all 24 observation files and all 24 trace files at the paths listed in [episode_metadata.csv](data/episode_metadata.csv). Use the pinned environment above, then run:

```bash
python -B code/verify_features.py --out results_raw
python -B code/reproduce_analysis.py --out results_raw
python -B code/make_figures_r2.py --results results_raw --out figures_raw
```

When all 48 files are present, the scripts select `full_raw_npz_replay`, even if archive flags are supplied. A complete raw set takes precedence.

Use [the detailed guide](docs/REPRODUCTION_GUIDE.md) to interpret array tolerances, keyed CSV comparisons, provenance differences, and the explicit approximate-density option. That option does not certify numerical equivalence with the IF97 reference data.

## 5. Check the scope of the evidence

- [Recorded runs and interpretation](docs/REPRODUCTION_GUIDE.md)
- [Scientific and public-data limitations](docs/KNOWN_LIMITATIONS.md)
- [Current manuscript checks and historical Word automation](manuscript_verification/LATEST_MANUSCRIPT_VERIFICATION_REPORT.md)
- [Base simulator versus the study-time source](docs/SOURCE_PROVENANCE.md)

Write regenerated outputs to separate directories. Keep the frozen [results](results/README.md), [figures](figures/FIGURE_MAP.md), and existing execution records unchanged.
