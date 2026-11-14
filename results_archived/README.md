# Archived Numerical Results & Provenance (`results_archived/`)

## 1. Root Files — R2 Trace-Replay & Sensitivity Summaries
- `r2_replay_summary.json` — Clean R2-derived trace-replay summary (`24` episodes, `259,224` timestamps, `96/96` episode-method matches, `20` threshold candidates; `simulation_run: false`).
- `episode_results.csv` — All `96` `(24 episodes x 4 detectors)` onset/alarm/delay/strict-lead records.
- `summary.csv` — Table 6 aggregated performance for `B0_state`, `Flow_only`, `Command_only`, `B1_combined`.
- `normal_persistence.csv` — All `48` `(12 normal episodes x 4 detectors)` maximum continuous exceedance spans and peak scores (Table 8 source).
- `tables_3_4_5_7_crosscheck.csv` — `50/50` cross-checks covering Table 3 (`D1..D4`, `E1..E8`), Table 4 (EWLS fit params, `N = 40,804`), Table 5 (threshold sweeps), and Table 7 (evaluation timings).
- `tables_and_rounding_summary.json` — Summary of `50/50` cross-checks, `51.3 min` median delay reduction, `115.5 min` 1-decimal max delay, and `5/7/8` endpoint counts.
- `quantile_claim_check.json` — Observed D1–D4 empirical tail verification (`4.063845`, `4.388325`) plus counterexamples proving `Q_max != max(Q_F, Q_D)` in general.
- `cutoff_leads_by_block.csv`, `cutoff_leads_summary.csv`, `component_crossing_timing.csv` — Strict lead-time sensitivity across `0.70 / 0.75 / 0.80 m` and flow vs. demand threshold crossing order (`8/8` flow first at shared threshold).
- `delay_window_check.csv` — `32/32` identity check comparing pre-terminal first post-onset alarm vs. unrestricted first post-onset alarm.

## 2. Subdirectory Provenance Separation
- `reconstructed_inputs/` — Structured JSON files reconstructing Tables 1–5 and 7 from archived cross-checks, `simulator_source/`, and Supplement S2 (`r2_text_archive/`).
- `prior_draft_review_ce0e9a0e/` — Historical independent QA records strictly scoped to the pre-revision draft `PUB053_Manuscript_JMSE_Submission.docx` (`SHA-256: ce0e9a0e3c6c6332942d7ef99ae464832c3c3b57eaa0172130a220312103d4e5`).
- `current_manuscript_verification/` — Fresh verification table checks (`62/62` rows across Tables 3–8) and JSON report generated directly against the current revised DOCX (`JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx`).

## 3. External Primary Workstation Archives (Not Bundled)
- `PUB053_Manuscript_Package_R2.zip` and `observable_baseline_study_20260915T215200Z_be142b32.zip` reside on the study owner's external workstation and are not present inside this release candidate.
