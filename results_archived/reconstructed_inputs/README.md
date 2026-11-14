# Reconstructed Structured Inputs (`results_archived/reconstructed_inputs/`)

These five JSON files preserve the machine-readable inputs and parameters behind Tables 1–7, extracted programmatically from archived R2 cross-checks (`tables_3_4_5_7_crosscheck.csv`, `r2_replay_summary.json`), `simulator_source/configs/ab4_marine_aux.yaml`, `simulator_source/src/boiler_pdm_sim/core/ab4/drum_model.py`, and `manuscript_verification/r2_text_archive/PUB053_Supplement_R2.txt`.

- `plant_parameters_table1_table2_from_source.json` — Table 1 plant/control constants and Table 2 sensor conditioning specifications.
- `block_design_table3_reconstructed.json` — Table 3 block schedule (D1–D4, E1–E8, seeds, leak timing/severity, D4 seed `3004 -> 3104` note).
- `ewls_fit_table4_reconstructed.json` — Table 4 full-precision OLS regression constants (`N = 40,804`).
- `threshold_candidates_table5_reconstructed.json` — Table 5 empirical quantile candidates and D1–D4 alarm counts.
- `episode_event_timings_table7_reconstructed.json` — Table 7 evaluation event/alarm timestamps for E1–E8.

**External Workstation Boundary**: Raw binary episode `.npz` trajectories (`observable_baseline_study_20260915T215200Z_be142b32.zip`) and `PUB053_Manuscript_Package_R2.zip` remain on the primary research workstation and are excluded from this repository.
