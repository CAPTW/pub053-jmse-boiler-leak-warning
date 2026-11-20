# Manuscript verification records

[Home](../../README.md) · [Quick start](../../REPRODUCIBILITY.md) · [Documentation](../../docs/README.md)

This directory contains static reports for the manuscript associated with `v1.0.6-pub053-r2` and a separately preserved Word COM editing log. Their evidence scopes differ.

## Static reports bound to the manuscript

| File | Recorded scope |
|---|---|
| [current_docx_verification_report.json](current_docx_verification_report.json) | DOCX/PDF hashes, document structure, text assertions and Tables 3–8 |
| [current_citations_and_manuscript_report.json](current_citations_and_manuscript_report.json) | Citation structure, input hashes, PDF checks and imported dynamic-test assertions |
| [current_manuscript_table_checks.csv](current_manuscript_table_checks.csv) | 62 table rows: `12 + 10 + 20 + 4 + 8 + 8` across Tables 3–8 |

The static JSON reports identify DOCX SHA-256:

~~~text
7f021cf05764cc737ebed70e37896135e326bc9981d841e460bf2605525fdf0b
~~~

They record 26 PDF pages, 27 reference bookmarks, 26 citation groups and 44 live REF fields. See the [manuscript verification summary](../../manuscript_verification/LATEST_MANUSCRIPT_VERIFICATION_REPORT.md) for the artifact identities and scope.

## Historical dynamic editing log

[citation_editing_and_reordering_test_log.json](citation_editing_and_reordering_test_log.json) records Word COM tests for ADD, MOVE, REORDER and DELETE operations.

The log does **not** contain an input digest or execution timestamp. The current citation report imports its success assertions; this does not establish a newly executed Word COM test on the DOCX hash above.

The [citation editing report](../../manuscript_verification/CITATION_EDITING_TEST_REPORT.md) explains those historical operations. The original JSON files are retained without modification.
