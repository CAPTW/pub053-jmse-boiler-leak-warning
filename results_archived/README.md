# Audit archive

[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](../docs/README.md)

This directory preserves R2 reference records and manuscript-review evidence. Records from different inputs or stages remain separate.

## Find the relevant record

| Location | Scope |
|---|---|
| [R2 replay summary](r2_replay_summary.json) and root CSV/JSON files | Stored-data reanalysis of 24 episodes; no new simulation |
| [Reconstructed inputs](reconstructed_inputs/README.md) | Five JSON records for Tables 1–5 and 7 |
| [Manuscript verification](current_manuscript_verification/README.md) | Static reports bound to the v1.0.6 manuscript and separately retained historical Word COM results |
| [Prior-draft review](prior_draft_review_ce0e9a0e/README.md) | Findings for the earlier manuscript with SHA-256 beginning `ce0e9a0e` |

The root result files are also exposed in [results/](../results/README.md), which provides a compact file-by-file guide.

## Read the evidence in context

The preserved R2 records include 96 episode–detector results, the 50-row table cross-check, 32 delay-window comparisons and threshold-sensitivity outputs. These are records of the stored analysis, not evidence that a new simulation ran during documentation maintenance.

The directory name `current_manuscript_verification` identifies the maintained manuscript record set. Each report's input hash determines its scope; a filename alone does not prove that a dynamic Word test was rerun.

The original NPZ files and study-patched runtime source are not bundled. See [data provenance](../docs/DATA_PROVENANCE.md) for the external packages and [reproduction instructions](../docs/REPRODUCTION_GUIDE.md) for checks possible from a public clone.
