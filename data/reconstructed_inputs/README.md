# Reconstructed table inputs

[Home](../../README.md) · [Quick start](../../REPRODUCIBILITY.md) · [Documentation](../../docs/README.md)

These five JSON files provide structured inputs for **Tables 1–5 and 7**. They were reconstructed from preserved R2 cross-checks, the simulator configuration and the R2 supplement.

| JSON file | Manuscript coverage |
|---|---|
| [plant_parameters_table1_table2_from_source.json](plant_parameters_table1_table2_from_source.json) | Table 1 plant and control constants; Table 2 sensor conditioning |
| [block_design_table3_reconstructed.json](block_design_table3_reconstructed.json) | Table 3 development/evaluation blocks, seeds and leak schedule |
| [ewls_fit_table4_reconstructed.json](ewls_fit_table4_reconstructed.json) | Table 4 fitted coefficients and scales; `N = 40,804` |
| [threshold_candidates_table5_reconstructed.json](threshold_candidates_table5_reconstructed.json) | Table 5 threshold candidates and development-normal alarm counts |
| [episode_event_timings_table7_reconstructed.json](episode_event_timings_table7_reconstructed.json) | Table 7 evaluation event and alarm timings |

Table 6 is supported by [episode results](../../results/episode_results.csv) and their [summary](../../results/summary.csv). Table 8 uses [normal persistence results](../../results/normal_persistence.csv).

## Origin and use

The source records include the [50-row cross-check](../../results/tables_3_4_5_7_crosscheck.csv), [R2 replay summary](../../results/r2_replay_summary.json), [base YAML](../../simulator_source/configs/ab4_marine_aux.yaml) and [R2 supplement text](../../manuscript_verification/r2_text_archive/PUB053_Supplement_R2.txt).

The same five JSON records are retained in the [audit archive](../../results_archived/reconstructed_inputs/README.md). They support archive-mode checks; they do not contain original observation trajectories, and checking them is not a new raw-data fit.

See [data provenance](../../docs/DATA_PROVENANCE.md) and the [reproduction guide](../../docs/REPRODUCTION_GUIDE.md) for those boundaries.
