# Citation editing test record

[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](../docs/README.md)

This page explains the preserved Microsoft Word COM tests for the manuscript's citation system. The [operation log](citation_editing_and_reordering_test_log.json) reports successful ADD, MOVE, REORDER and DELETE scenarios.

## Evidence scope

The operation log names the revised DOCX and PDF, but contains **no input digest or execution timestamp**. It is historical evidence of the editing scenarios. It does not establish a new COM run against the manuscript hash in the [static verification record](LATEST_MANUSCRIPT_VERIFICATION_REPORT.md).

The [current citation report](../results_archived/current_manuscript_verification/current_citations_and_manuscript_report.json) imports these scenario results alongside current static checks. Keep those two evidence types separate.

## Citation architecture

The logged baseline contains:

- 27 reference bookmarks, `Ref01` through `Ref27`.
- 26 content controls (`w:sdt`), carrying 54 expanded reference-member IDs.
- 44 live Word `REF` fields.

Content-control tags preserve each citation group's members. [sync_citations_and_references.py](sync_citations_and_references.py) synchronizes groups and reference order; Word updates the displayed REF field values. See the [citation mapping](../references/CITATION_MAPPING_TABLE.md) for the reference and group identities.

## Recorded operations

| Scenario | Operation | Recorded outcome |
|---|---|---|
| 1A | Insert a reference above reference 1, then update Word fields | All 44 REF fields shift by `+1`; no field errors |
| 1B | Add citation group `G27` with `Ref28`, then reorder | 27 groups, 55 member IDs and 28 references; no field errors |
| 2 | Move the interior range member `Ref06` to reference 27 without reordering | 54 member IDs preserved; 47 live fields; ranges split correctly |
| 3 | Move group `G23` early in the text, then reorder | References follow first appearance; no field errors |
| 4 | Delete group `G02` and prune uncited references | 25 groups, 52 member IDs and 25 references; no field errors |

### ADD: scenarios 1A and 1B

Scenario 1A inserts a dummy reference above the first reference and calls Word `Fields.Update()`. It checks automatic numbering changes without replacing the 44 REF fields.

Scenario 1B adds `G27` immediately after `G01` and appends `Ref28`. After synchronization and a Word update, `G27` displays `[3]`, `G02` displays `[4,5]` and `G24` displays `[28]`.

### MOVE: scenario 2

Moving `Ref06` to position 27 splits ranges without losing citation members. Examples recorded in the log are:

- `G03`: `[2,5–7,27]`.
- `G04`: `[5–7,27]`.
- `G05`: `[5,27]`.
- `G06`: `[6,7,27]`.

### REORDER: scenario 3

Moving `G23`, containing `Ref25` and `Ref26`, after the first citation group makes those references numbers 3 and 4. The log records `G23 = [3,4]`, `G02 = [5,6]` and the subsequent groups in the new first-appearance order.

### DELETE: scenario 4

Deleting `G02` removes the only citation group using `Ref03` and `Ref04`. Synchronization with pruning removes those references and renumbers the remaining list from 1 to 25. Recorded examples include `G03 = [2–6]` and `G24 = [25]`.

## Source records

- [Editing and reordering log](citation_editing_and_reordering_test_log.json)
- [Dynamic update log](citation_dynamic_update_test_log.json)
- [Word automation script](word_update_export_and_test.py)
- [Current manuscript record set](../results_archived/current_manuscript_verification/README.md)

The logs are retained as recorded. No new Word COM execution is claimed by this documentation update.
