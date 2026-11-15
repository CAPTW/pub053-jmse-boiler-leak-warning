# Latest Manuscript Verification Report (`PUB-053`, `v1.0.1-pub053-r2`)

This report summarizes direct verification checks executed against the latest revised JMSE manuscript DOCX/PDF synchronized with companion release **`v1.0.1-pub053-r2`**:

- **Unmodified Source DOCX**: `JMSE-MDPI-보일러 논문 [김겸원].docx` (`SHA-256: 5471545c033549ed08fcbf4bea81957d6a35a7b76aad3e42fa4dfa4f8bf99309`, unchanged)
- **Target Revised DOCX**: `JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx` (`SHA-256: ed8da10299682a833e1dee942ca0099c359f962753620d529e9ac47963d59e9c`; supersedes `v1.0.0-pub053-r2` DOCX `81d1e24f97c44b25f1a34c5197fb0d12ad6a0fb5582fcfec758aca4eec0c595d`)
- **Exported PDF**: `JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.pdf` (`SHA-256: b5e5a3c296d013ae6661c18e7474a690f21371b58c824751bd73abfd43702345`; supersedes `v1.0.0-pub053-r2` PDF `7797b66183acfbc405810731f037a6d8bfef7aea3df971e340d4d3a086cd1409`)

## Summary of Verified Results

- **Layout & OOXML Integrity (`verify_revised_manuscript.py`)**:
  - PDF pages: `26`, extracted characters: `89,340`, Word field errors in exported PDF: `0`.
  - Bidirectional layout elements: `bidi_elements_count = 0`, `section_bidi_present = false`.
  - Abstract word count: `198` words (MDPI <= 200 words).
- **Table & Numerical Cross-Checks (`current_manuscript_table_checks.csv`)**:
  - `62/62` row-by-row matches across Tables 3–8 (`Table 3: 12/12`, `Table 4: 10/10`, `Table 5: 20/20`, `Table 6: 4/4`, `Table 7: 8/8`, `Table 8: 8/8`).
  - `verify_tables_from_archived_results.py`: `all_passed: true` (`50/50` cross-checks, `96/96` episode-method rows, `32/32` delay-window checks, `8/8` Table 8 blocks, `7/7` figures + `8` raw assets).
- **Text Disclosure Integrity (`21/21` assertions `true`)**:
  - OpenAI Codex CLI (`0.104.0`–`0.142.3`, `gpt-5.3-codex-spark`, `gpt-5.4`, `gpt-5.5`) and `PR_BODY.md` `Claude Code` summary footer, with explicit boundary for unverified external workstation/R2 logs and separation between deterministic simulation (`observable_baseline_study_20260915T215200Z_be142b32.zip`) and readonly R2 reanalysis (`PUB053_Manuscript_Package_R2.zip`).
  - Live companion repository `https://github.com/CAPTW/pub053-jmse-boiler-leak-warning` citing release tag `v1.0.1-pub053-r2` (superseding `v1.0.0-pub053-r2`), `REPRODUCIBILITY.md`, `docs/DATA_PROVENANCE.md`, `docs/KNOWN_LIMITATIONS.md`, strict nonzero default when `.npz` files are absent, explicit `--archived-tables-only` / `--archived-assets-only` flags, and closed interval notation (`[0, 1]`, `[−1, 1]`, `[0, 0.999]`), with `"automatic full_raw_npz_replay"` absent (`no_auto_fallback_overclaim: true`).
- **Live Citations & 4-Operation Word COM Editing Suite (`word_update_export_and_test.py`, `verify_citations_and_manuscript.py`)**:
  - `27` bookmarked References (`Ref01`..`Ref27`), `27` CustomXML bibliography sources, `26` `<w:sdt>` controls carrying `54` expanded member IDs, `44` live `REF` fields (`REF RefXX \n \t \h`), and `first_citation_order_matches_references: true`.
  - Microsoft Word COM dynamic operations passed (`ADD` Scenarios `1A`/`1B`, `MOVE` Scenario `2`, `REORDER` Scenario `3`, `DELETE` Scenario `4`), archived in `citation_editing_and_reordering_test_log.json` and `CITATION_EDITING_TEST_REPORT.md`.
  - Release repository hygiene check: `release_repo_forbidden_files: []`, `all_passed: true`.
