# PUB053 Citation Architecture & 4-Operation Dynamic Editing Report

- **Target Revised DOCX**: `JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx`
- **Exported PDF**: `JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.pdf` (26 pages, 0 Word field errors)
- **Inline Content Controls (`<w:sdt>`)**: **26** controls carrying all **54** expanded `RefXX` member IDs (`PUB053_CIT:id=GXX;refs=...`), preserved across Microsoft Word COM `Fields.Update()` + `Save()`
- **Live Cross-Reference Fields (`REF RefXX \n \t \h`)**: **44** active fields verified with 0 errors

## Operation 1A (ADD): Insert New Reference Above `[1]` (Word COM Only)
- Inserted dummy reference above `[1] Tajiri, T.` and ran `doc.Fields.Update()` in Microsoft Word.
- **Result**: `44/44` live `REF` fields shifted automatically by `+1`, `0` errors.

## Operation 1B (ADD): Add New `<w:sdt>` Group `G27` (`Ref28`) + Reference (`--reorder-refs`)
- Added `G27` (`Ref28`) immediately after `G01` and appended bookmarked `Ref28` in References, then ran `sync_docx(reorder_refs=True)` + Word COM `Fields.Update()`.
- **Result**: **27** `<w:sdt>` controls (**55** member IDs), **28** References ordered cleanly (`G27` = **`[3]`**, `G02` = **`[4,5]`**, `G03` = **`[2,6–9]`**, `G24` = **`[28]`**), **0 errors**.

## Operation 2 (MOVE): Move Interior Range Member `Ref06` (`Åström & Bell`) to `#27` (`--no-reorder-refs`)
- Moved `Ref06` to bottom `#27` and ran `sync_citations_and_references.py --no-reorder-refs` + Word COM `Fields.Update()`.
- **Result**: All 54 member IDs remained intact in `<w:sdt>` tags, Word updated to **47** live `REF` fields with **0 errors**, and MDPI range compression automatically split around `#27`:
  - `G03` (`Ref02,Ref05,Ref06,Ref07,Ref08`): **`[2,5–7,27]`**
  - `G04` (`Ref05,Ref06,Ref07,Ref08`): **`[5–7,27]`**
  - `G05` (`Ref05,Ref06`): **`[5,27]`**
  - `G06` (`Ref06,Ref07,Ref08`): **`[6,7,27]`**
  - `G19`, `G21`, `G22` (`Ref06`): **`[27]`**
  - `G07` (`Ref09..Ref14`): **`[8–13]`**

## Operation 3 (REORDER): Move In-Text Citation `G23` (`[25,26]`) to Early Introduction (`--reorder-refs`)
- Moved `G23` (`Ref25,Ref26`) into Paragraph 10 right after `G01 [1,2]` and ran `sync_citations_and_references.py --reorder-refs` + Word COM `Fields.Update()`.
- **Result**: `References` physically reordered to match first in-text appearance (`Ref25 -> #3`, `Ref26 -> #4`, `Ref03 -> #5`, `Ref04 -> #6`, `Ref05 -> #7`, ..., `Ref27 -> #27`), **0 errors** in Word COM, and MDPI bracket displays updated cleanly:
  - `G01`: **`[1,2]`**, moved `G23`: **`[3,4]`**, `G02`: **`[5,6]`**, `G03`: **`[2,7–10]`**, `G04`: **`[7–10]`**, `G07`: **`[11–16]`**, `G25` (still in §2.3 `P045`, citing `Ref26`): **`[4]`**, `G24`: **`[27]`**.

## Operation 4 (DELETE): Remove Citation Group `G02` (`Ref03,Ref04`) & Prune Uncited (`--reorder-refs --prune-uncited`)
- Removed `<w:sdt>` `G02` (sole citation site of `Ref03,Ref04`), then ran `sync_citations_and_references.py --reorder-refs --prune-uncited` + Word COM `Fields.Update()`.
- **Result**: `Ref03` and `Ref04` pruned cleanly (**25** `<w:sdt>` groups, **52** member IDs, **25** References renumbered `1..25`), `G03` compressed to **`[2–6]`**, `G04` = **`[3–6]`**, `G07` = **`[7–12]`**, `G24` = **`[25]`**, **0 errors**.
