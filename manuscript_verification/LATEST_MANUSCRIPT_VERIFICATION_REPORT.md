# Manuscript verification record

[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](../docs/README.md)

This page summarizes the preserved verification records associated with manuscript release **`v1.0.6-pub053-r2`**. It identifies the inputs and separates static checks from historical Word COM tests.

## Recorded manuscript inputs

The [DOCX report](../results_archived/current_manuscript_verification/current_docx_verification_report.json) and [citation report](../results_archived/current_manuscript_verification/current_citations_and_manuscript_report.json) identify these SHA-256 digests:

~~~text
DOCX
7f021cf05764cc737ebed70e37896135e326bc9981d841e460bf2605525fdf0b

PDF
854fc3d3fb6eab0550768eb2ee376e1b429eae6a91e274563dcd3fa03e7fbf13
~~~

The revised file is named `JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx`. The formatted DOCX and PDF are author-held submission files and are not bundled in this repository.

The citation report separately records that its original source DOCX, digest `5471545c033549ed08fcbf4bea81957d6a35a7b76aad3e42fa4dfa4f8bf99309`, was unchanged.

## Static document and citation checks

| Check | Recorded result |
|---|---|
| Exported PDF | 26 pages; zero reported Word field errors |
| Abstract | 198 words |
| Reference bookmarks and CustomXML sources | 27 of each |
| Content-control citation groups | 26 groups, 54 expanded member IDs |
| Live Word REF fields | 44 |
| First-citation order | Matches reference order |
| Bidirectional layout elements | Zero reported |
| Required text assertions | 21 of 21 true |

These results come from the preserved reports. They do not imply that Word field updates or rendering were rerun during this documentation change.

## Table checks

The [row-level table record](../results_archived/current_manuscript_verification/current_manuscript_table_checks.csv) reports **62 matching rows out of 62**.

| Table | Subject | Matching rows |
|---|---|---:|
| 3 | Development and evaluation design | 12/12 |
| 4 | Fitted coefficients and scales | 10/10 |
| 5 | Threshold candidates | 20/20 |
| 6 | Detector performance | 4/4 |
| 7 | Evaluation event timings | 8/8 |
| 8 | Normal persistence | 8/8 |

The separate [archived-result check log](../docs/execution_logs/verify_tables_from_archived_results_log.json) reports 50 table cross-checks, 96 episode–detector matches, 32 delay-window comparisons and checks of the seven figures and eight source assets. These checks compare the manuscript and reference records; they do not, by themselves, demonstrate a new replay from the external NPZ inputs.

## Disclosures and figure definitions

The static text checks cover the release reference, the Codex/Antigravity role disclosure, the distinction between original simulation and R2 stored-data analysis, and the raw-data/dependency requirements.

They also cover the Figure 2 distinction between the plotted observed level and plant truth used for endpoint-dwell annotation. The detailed [figure map](../figures/FIGURE_MAP.md) gives the **1,200–11,194 s** interval for Figures 2, 3 and 5.

## Historical Word COM operations

The preserved [editing log](citation_editing_and_reordering_test_log.json) records successful ADD, MOVE, REORDER and DELETE scenarios. It has no input hash or execution timestamp, so it cannot establish that these operations were newly executed on the DOCX identified above.

The current citation report imports those scenario assertions. See the [editing test record](CITATION_EDITING_TEST_REPORT.md) for the operation details and this evidence limitation.

## Repeating the checks

Use the [detailed reproduction guide](../docs/REPRODUCTION_GUIDE.md) for the optional author-local DOCX/PDF checks and their dependencies. Use the [artifact map](MANUSCRIPT_ARTIFACT_MAP.md) to trace each table and figure to its public source.
