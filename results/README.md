# Preserved R2 results

[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](../docs/README.md)

These 12 CSV and JSON files are reference outputs from the R2 stored-data reanalysis. They cover 24 episodes and 96 episode–detector evaluations.

## Result files

| Files | Contents |
|---|---|
| [episode_results.csv](episode_results.csv), [summary.csv](summary.csv) | Episode-level alarms, delays and leads; detector summaries |
| [normal_persistence.csv](normal_persistence.csv) | Normal-episode exceedance spans and peak scores |
| [cutoff_leads_by_block.csv](cutoff_leads_by_block.csv), [cutoff_leads_summary.csv](cutoff_leads_summary.csv) | Lead times for the three functional-level criteria |
| [delay_window_check.csv](delay_window_check.csv) | 32 comparisons of alarm-window definitions |
| [component_crossing_timing.csv](component_crossing_timing.csv) | Flow and demand threshold-crossing order |
| [tables_3_4_5_7_crosscheck.csv](tables_3_4_5_7_crosscheck.csv) | 50 table cross-check rows |
| [recomputed_vs_archived.csv](recomputed_vs_archived.csv) | 96 episode–detector comparison rows |
| [r2_replay_summary.json](r2_replay_summary.json), [tables_and_rounding_summary.json](tables_and_rounding_summary.json) | Stored replay and reporting summaries |
| [quantile_claim_check.json](quantile_claim_check.json) | Empirical quantile checks and general counterexamples |

## Reproduction and preservation

Keep this directory unchanged. Write new outputs to `results_reproduced/` or another separate directory, then compare them with these references.

The [reproduction guide](../docs/REPRODUCTION_GUIDE.md) distinguishes raw calculations from archive-table checks. Successful numeric comparisons can allow specified provenance-text or display-rounding differences; they do not establish byte identity.

Copies of these records and separate manuscript-review records are retained in [results_archived/](../results_archived/README.md).
