# Study Metadata, Structured Inputs, and Archive Boundary (`data/`)

## 1. Accurate Provenance Separation of Primary Study Archives
To prevent conflating the original simulation archive with the R2 reanalysis archive:

1. **`observable_baseline_study_20260915T215200Z_be142b32.zip` (Original Study Execution Archive — Not Mounted on Packaging Workstation)**
   Contains the original study execution working tree and raw run outputs:
   - `source_copy/` (study-time simulator working copy built on local base HEAD `4fea4646723f04db41583cb682bac8b62c44bc05` with working-tree edits and already-applied pilot/study patches)
   - `analysis/`, `configs/`, `exogenous/`, `runs/`

2. **`PUB053_Manuscript_Package_R2.zip` (R2 Stored-Data Reanalysis Package — Not Mounted on Packaging Workstation)**
   Contains the 2 s downsampled trajectory and score archives used by the R2 scripts:
   - `data/observations/*.npz` (24 episode observation archives, 10,801 samples each, 259,224 total rows)
   - `data/traces/*.npz` (24 detector score trace archives)
   - `data/block_design.json` and `data/original_configs/*_config_applied.json`
   - `data/episode_metadata.csv`
   - R2 reanalysis scripts (`code/test_analysis.py`, `code/verify_features.py`, `code/reproduce_analysis.py`, `code/make_figures_r2.py`) and reference `results/`

Neither primary ZIP archive (nor the 48 raw `.npz` binary files) was mounted on the packaging workstation.

## 2. Files Provided Directly in This Public Repository (`data/`)
All structured tabular metadata, block schedules, EWLS parameters, threshold candidates, and evaluation timings recovered from preserved R2 replay artifacts (`results/episode_results.csv`, `results/summary.csv`, `results/r2_replay_summary.json`, `results/tables_3_4_5_7_crosscheck.csv`, `results/normal_persistence.csv`, and `simulator_source/configs/ab4_marine_aux.yaml`) are bundled directly so readers can run verification scripts in standalone mode without access to private folders:

- `data/episode_metadata.csv`: Complete 24-episode manifest (`D1_normal`..`E8_tube_leak`, `21,600 s`, `dt = 2.0 s`, `10,801` samples/episode, `259,224` total timestamps, leak onset/severity, functional start/confirm, process trip, domain exit).
- `data/block_design.json`: Reconstructed 12-block design (D1–D4 development, E1–E8 evaluation) matching Table 3, plus D4 `3004 -> 3104` seed-replacement note and safety policy (`process_protection_without_schedule_severity_oracle`).
- `data/original_configs/ab4_marine_aux.yaml`: Base marine auxiliary boiler YAML recovered from local upstream HEAD `4fea4646723f04db41583cb682bac8b62c44bc05`.
- `data/reconstructed_inputs/`: Five verified JSON reconstructions covering Tables 1–5 and Table 7 (`plant_parameters_table1_table2_from_source.json`, `block_design_table3_reconstructed.json`, `ewls_fit_table4_reconstructed.json`, `threshold_candidates_table5_reconstructed.json`, `episode_event_timings_table7_reconstructed.json`).

## 3. Running Full Raw `.npz` Replay When Primary Archives Are Mounted
When the 48 primary `.npz` files from `PUB053_Manuscript_Package_R2.zip` (available from the corresponding author upon reasonable request) are extracted into:
- `data/observations/<episode>.npz` (24 files)
- `data/traces/<episode>.npz` (24 files)

the scripts in `code/` (`test_analysis.py`, `verify_features.py`, `reproduce_analysis.py`, `make_figures_r2.py`) automatically detect all 48 `.npz` files and switch from **archived-table verification mode** (`mode = "archived_r2_tables"`) to **full raw `.npz` trajectory replay mode** (`mode = "full_raw_npz_replay"`).

### Expected 24 Observation Archives (`data/observations/`)
- `data/observations/D1_normal.npz`
- `data/observations/D1_tube_leak.npz`
- `data/observations/D2_normal.npz`
- `data/observations/D2_tube_leak.npz`
- `data/observations/D3_normal.npz`
- `data/observations/D3_tube_leak.npz`
- `data/observations/D4_normal.npz`
- `data/observations/D4_tube_leak.npz`
- `data/observations/E1_normal.npz`
- `data/observations/E1_tube_leak.npz`
- `data/observations/E2_normal.npz`
- `data/observations/E2_tube_leak.npz`
- `data/observations/E3_normal.npz`
- `data/observations/E3_tube_leak.npz`
- `data/observations/E4_normal.npz`
- `data/observations/E4_tube_leak.npz`
- `data/observations/E5_normal.npz`
- `data/observations/E5_tube_leak.npz`
- `data/observations/E6_normal.npz`
- `data/observations/E6_tube_leak.npz`
- `data/observations/E7_normal.npz`
- `data/observations/E7_tube_leak.npz`
- `data/observations/E8_normal.npz`
- `data/observations/E8_tube_leak.npz`

### Expected 24 Trace Archives (`data/traces/`)
- `data/traces/D1_normal.npz`
- `data/traces/D1_tube_leak.npz`
- `data/traces/D2_normal.npz`
- `data/traces/D2_tube_leak.npz`
- `data/traces/D3_normal.npz`
- `data/traces/D3_tube_leak.npz`
- `data/traces/D4_normal.npz`
- `data/traces/D4_tube_leak.npz`
- `data/traces/E1_normal.npz`
- `data/traces/E1_tube_leak.npz`
- `data/traces/E2_normal.npz`
- `data/traces/E2_tube_leak.npz`
- `data/traces/E3_normal.npz`
- `data/traces/E3_tube_leak.npz`
- `data/traces/E4_normal.npz`
- `data/traces/E4_tube_leak.npz`
- `data/traces/E5_normal.npz`
- `data/traces/E5_tube_leak.npz`
- `data/traces/E6_normal.npz`
- `data/traces/E6_tube_leak.npz`
- `data/traces/E7_normal.npz`
- `data/traces/E7_tube_leak.npz`
- `data/traces/E8_normal.npz`
- `data/traces/E8_tube_leak.npz`
