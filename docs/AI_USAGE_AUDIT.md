[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](README.md)

# AI use and author responsibility

This disclosure describes AI-assisted software development and manuscript
preparation for PUB-053. It follows the roles stated in manuscript Section 2.4
and Acknowledgments. It distinguishes the author's development history from
evidence a reader can inspect in the public repository.

## Roles

| Stage | Recorded tool role | Human responsibility |
|---|---|---|
| Boiler simulator development | **OpenAI Codex** was the principal AI-assisted coding tool for `boiler_pdm_sim` and the `ab4` core. | Authors specified the physical model, scenarios and acceptance criteria, and reviewed the implementation. |
| Original simulation | The deterministic simulator generated the paired study episodes. | Authors controlled the study settings and evaluated the outputs. |
| R2 reanalysis | Scripts read the frozen trajectories; separate AI-session attribution for this stage is unverified. | Authors selected and checked the analysis and reported results. |
| Manuscript and companion preparation | **Google Antigravity** and Python scripts supported template assembly, citations, numerical checks and public-repository packaging. | Authors reviewed the manuscript, data statements and final scientific claims. |

The reported Codex work includes software structure, IF97 property integration,
closed-loop wiring and test development. This assistance does not transfer
responsibility for model assumptions, interpretation or scientific claims to an
AI tool.

R2 analysis and manuscript preparation did not generate new boiler trajectories
or change the simulated physical states. The boundary between original simulation
and stored-output reanalysis is described in [data provenance](DATA_PROVENANCE.md).

## Evidence available to readers

| Evidence | What it supports | What it does not establish |
|---|---|---|
| Public source snapshot and analysis scripts | The code distributed with the companion and its implemented calculations. | Authorship of each line or the exact model used in every development session. |
| Published numerical and test logs | The recorded inputs, checks and outcomes within each log's scope. | Unrecorded tests, new runs after publication, or complete study-data availability. |
| Input-hashed manuscript reports | Static checks against identified DOCX/PDF files. | A new Word COM run when only an older dynamic log is reused. |
| Author's local session-history summary | The author's reported CLI versions, models and development chronology. | Publicly verifiable access to the private session database. |

See the [reproduction evidence](REPRODUCTION_GUIDE.md#7-published-verification-evidence),
[manuscript verification report](../manuscript_verification/LATEST_MANUSCRIPT_VERIFICATION_REPORT.md)
and [source provenance](SOURCE_PROVENANCE.md) for these boundaries.

## Author-reported development history

The original disclosure reports locally inspected Codex CLI records spanning
versions `0.104.0` to `0.142.3`, with model identifiers `gpt-5.3-codex-spark`,
`gpt-5.4` and `gpt-5.5`. These are retained as an author-reported historical
summary. The private session database and complete transcripts are not part of
the public companion, and this documentation update has not independently
authenticated those private records.

Per-session model attribution for development on a separate workstation and for
later R2 sessions remains unverified. A local base commit or a public source hash
does not supply that missing session evidence.

The original disclosure also records a **Claude Code attribution footer** in the
upstream Phase A pull-request body. That footer supports the stated attribution
of the PR text; it does not by itself establish additional model-design or code
authorship. No further Claude contribution is inferred from it.

The fuller historical chronology is retained in the
[frozen v1.0.6 disclosure](https://github.com/CAPTW/pub053-jmse-boiler-leak-warning/blob/v1.0.6-pub053-r2/docs/AI_USAGE_AUDIT.md).
Later edits to the explanatory pages on `main` do not change the scientific
release or turn these historical records into new verification evidence.

## Author review and accountability

The authors retain responsibility for the physical assumptions, study design,
implementation decisions, citations, numerical results and manuscript.
Reported verification covers the checks identified in the linked records;
it is not a claim that every possible simulator test passes or that the public
clone alone reproduces the original study.
