# Latest Manuscript Verification Report (`JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx` / `.pdf`)

This report summarizes the verification checks run directly against the final revised manuscript DOCX and exported PDF (the `.docx`/`.pdf` files themselves are excluded from the public repository per MDPI JMSE template licensing).

## 1. Verified Manuscript Artifacts
- **Original unmodified DOCX SHA-256**: `5471545c033549ed08fcbf4bea81957d6a35a7b76aad3e42fa4dfa4f8bf99309` (`original_docx_unchanged: true`)
- **Latest revised DOCX SHA-256**: `81d1e24f97c44b25f1a34c5197fb0d12ad6a0fb5582fcfec758aca4eec0c595d`
- **Latest exported PDF SHA-256**: `7797b66183acfbc405810731f037a6d8bfef7aea3df971e340d4d3a086cd1409`
- **PDF layout & fields**: `26` pages, `87,994` extracted text characters, `0` Word field errors (`pdf_field_errors: 0`, `pdf_ref_errors: 0`), `0` bidi elements (`bidi_elements_count: 0`), `198` abstract words.

## 2. Numerical Table Cross-Checks (`62/62` Matched)
Generated via `manuscript_verification/verify_revised_manuscript.py` (`results_archived/current_manuscript_verification/current_manuscript_table_checks.csv` and `current_docx_verification_report.json`):
- Table 3 (Block design): `12/12`
- Table 4 (EWLS fit parameters): `10/10`
- Table 5 (Threshold candidates): `20/20`
- Table 6 (Detection delay & warning lead summary): `4/4`
- Table 7 (Episode event timings): `8/8`
- Table 8 (Block alarm / lead breakdown): `8/8`
- Key disclosure & text integrity assertions: all `19/19` checks `true` (including OpenAI Codex CLI `0.104.0`–`0.142.3` / `gpt-5.3-codex-spark`, `gpt-5.4`, `gpt-5.5` & `PR_BODY.md` `Claude Code` summary footer, Methods separation of original deterministic simulation from R2 readonly reanalysis, archive provenance separation between `observable_baseline_study_20260915T215200Z_be142b32.zip` and `PUB053_Manuscript_Package_R2.zip`, live repository URL `https://github.com/CAPTW/pub053-jmse-boiler-leak-warning`, release tag `v1.0.0-pub053-r2`, and closed interval bounds `[0, 1]`, `[−1, 1]`, `[0, 0.999]`).

## 3. Citation Automation & 4-Operation Word COM Tests
Generated via `manuscript_verification/word_update_export_and_test.py` and `manuscript_verification/verify_citations_and_manuscript.py` (`results_archived/current_manuscript_verification/citation_editing_and_reordering_test_log.json` and `current_citations_and_manuscript_report.json`):
- **Structure**: `27` Reference bookmarks (`Ref01`–`Ref27`), `26` inline `<w:sdt>` citation groups preserving `54` expanded Ref IDs, `44` live Word `REF` cross-reference fields, `27` CustomXML bibliography sources, `first_citation_order_matches_references: true`.
- **Operation 1 (`ADD`)**:
  - Scenario 1A (insert dummy ref before `#1` + Word `Fields.Update()`): `44/44` live `REF` fields shifted `+1`, `0` errors (`passed: true`).
  - Scenario 1B (add new `<w:sdt>` `G27` + `Ref28` + Word sync/update): `passed: true`.
- **Operation 2 (`MOVE` without reordering)**: Move interior `Ref06` to `#27` with `--no-reorder-refs`; all `54` IDs retained and split ranges updated via live `REF` fields (`passed: true`).
- **Operation 3 (`REORDER` on first citation)**: Move `G23` earlier with `--reorder-refs`; `References` bookmarks and citations renumbered cleanly in first-citation order (`passed: true`).
- **Operation 4 (`DELETE`)**: Remove `G02` with `--prune-uncited`; uncited bibliography entry pruned and remaining references renumbered cleanly (`passed: true`).

## 4. Prior Draft Historical Record Separation
QA records strictly scoped to the earlier pre-revision submission draft `PUB053_Manuscript_JMSE_Submission.docx` (`SHA-256: ce0e9a0e3c6c6332942d7ef99ae464832c3c3b57eaa0172130a220312103d4e5`) remain isolated in `results_archived/prior_draft_review_ce0e9a0e/` and are not presented as verification of the current revised DOCX/PDF.
