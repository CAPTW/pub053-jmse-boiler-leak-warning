# Current Manuscript Verification Records (`current_manuscript_verification/`)

- Generated directly by executing `manuscript_verification/verify_revised_manuscript.py`, `manuscript_verification/verify_citations_and_manuscript.py`, and `manuscript_verification/word_update_export_and_test.py` against the latest revised DOCX and PDF (`JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx` / `.pdf`).
- `current_manuscript_table_checks.csv`: `62/62` row-by-row matches across Manuscript Tables 3–8 (`12 + 10 + 20 + 4 + 8 + 8`).
- `current_docx_verification_report.json`: Complete OOXML, `<w:sdt>`, live `REF` field, PDF page/error, abstract word count, and text disclosure report.
- `current_citations_and_manuscript_report.json`: Full citation architecture, original DOCX immutability (`5471545c...`), 4-operation dynamic test assertions, PDF text/link checks, and repository hygiene verification output.
- `citation_editing_and_reordering_test_log.json`: Microsoft Word COM verification log covering all 4 citation operations (`ADD` Scenarios 1 & 1B, `MOVE` Scenario 2, `REORDER` Scenario 3, and `DELETE` Scenario 4).
