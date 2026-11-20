# Analysis and figure scripts

[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](../docs/README.md)

These scripts verify and reanalyse stored boiler trajectories. They do not run a new boiler simulation.

## Script guide

| Script | Purpose | Main output |
|---|---|---|
| [_common.py](_common.py) | Shared detector equations, reconstruction, event extraction and comparison helpers | Functions used by the scripts below |
| [test_analysis.py](test_analysis.py) | Unit tests using isolated synthetic and temporary fixtures | Test summary |
| [verify_features.py](verify_features.py) | Check reconstructed features, fitted parameters and reference traces | `feature_verification_report.json` |
| [reproduce_analysis.py](reproduce_analysis.py) | Recompute detector results and compare keyed tables | `reproduction_comparison_report.json` |
| [make_figures_r2.py](make_figures_r2.py) | Generate or assemble Figures 1–7 | `figure_generation_manifest.json` |

Use the [reproduction guide](../docs/REPRODUCTION_GUIDE.md) for installation, commands, output interpretation and recorded test results.

## Choose the input mode

A complete raw input set contains the 24 observation files and 24 trace files named in [episode_metadata.csv](../data/episode_metadata.csv).

- **Complete raw inputs:** the scripts select `full_raw_npz_replay`, including when an archive flag is present. Use the pinned `iapws==1.5.5` environment for the IF97 reference calculations.
- **Incomplete or missing raw inputs:** default execution returns `missing_raw_npz_error` and exit code `1`. Explicit `--archived-tables-only` or `--archived-assets-only` permits checks using the public tables and assets.
- **Unavailable IF97 backend with complete raw inputs:** default execution returns `missing_iapws_error`. The explicit `--allow-approx-density` option is described in the reproduction guide.

Each CLI collects backend metadata before reporting an input error. The helper reports the installed `iapws` version; it does not enforce equality with version `1.5.5`.

## What each mode checks

In raw mode, feature verification reconstructs 144 score and availability arrays and writes `recomputed_fit_params.json`. Analysis compares episode results, summaries, cutoff leads, delay-window checks and the 50-row table cross-check against [preserved results](../results/README.md).

In archive mode, feature checks use [reconstructed table inputs](../data/reconstructed_inputs/README.md). Analysis writes `archived_tables_3_4_5_7_internal_checks.json`; it does not present the preserved 50-row cross-check as a new raw calculation.

Figure 4 is rendered from an episode-results CSV in both modes. The other six figures are regenerated from raw inputs in raw mode; archive mode assembles Figures 1–2 and copies Figures 3 and 5–7 from preserved assets. See the [figure map](../figures/FIGURE_MAP.md).

## Test and comparison boundaries

The eight unit tests use isolated fixtures. With `iapws` installed, the forced-fallback test checks **132 passing and 12 failing arrays out of 144**, causing the overall synthetic comparison to fail as expected. Without `iapws`, that IF97-versus-fallback branch is skipped.

CSV comparisons use defined keys, numeric tolerances and explicit allowances for provenance text or display rounding. A successful comparison does not mean byte-identical files. Likewise, successful figure generation under approximate density does not establish numerical agreement with IF97.

Write new outputs to separate directories such as `results_reproduced/` and `figures_reproduced/`. Keep [results/](../results/) and [figures/](../figures/) as preserved references.
