# PUB053 Citation Architecture & Dynamic Reordering Test Report

- **Target Revised DOCX**: `JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx`
- **Exported PDF**: `JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.pdf` (26 pages, 0 Word field errors)
- **Inline Content Controls (`<w:sdt>`)**: **26** controls carrying all **54** expanded `RefXX` member IDs (`PUB053_CIT:id=GXX;refs=...`), preserved across Microsoft Word COM `Fields.Update()` + `Save()`
- **Live Cross-Reference Fields (`REF RefXX \n \t \h`)**: **44** active fields verified with 0 errors

## Scenario 1: Insert New Reference Above `[1]` (Word COM Only)
- Inserted dummy reference above `[1] Tajiri, T.` and ran `doc.Fields.Update()` in Microsoft Word.
- **Result**: `44/44` live `REF` fields shifted automatically by `+1`, `0` errors.

## Scenario 2: Move Interior Range Member `Ref06` (`Åström & Bell`) to `#27` (`--no-reorder-refs`)
- Moved `Ref06` to bottom `#27` and ran `sync_citations_and_references.py --no-reorder-refs` + Word COM `Fields.Update()`.
- **Result**: All 54 member IDs remained intact in `<w:sdt>` tags, Word updated to **47** live `REF` fields with **0 errors**, and MDPI range compression automatically split around `#27`:
  - `G03` (`Ref02,Ref05,Ref06,Ref07,Ref08`): **`[2,5–7,27]`**
  - `G04` (`Ref05,Ref06,Ref07,Ref08`): **`[5–7,27]`**
  - `G05` (`Ref05,Ref06`): **`[5,27]`**
  - `G06` (`Ref06,Ref07,Ref08`): **`[6,7,27]`**
  - `G19`, `G21`, `G22` (`Ref06`): **`[27]`**
  - `G07` (`Ref09..Ref14`): **`[8–13]`**

## Scenario 3: Move In-Text Citation `G23` (`[25,26]`) to Early Introduction (`--reorder-refs`)
- Moved `G23` (`Ref25,Ref26`) into Paragraph 10 right after `G01 [1,2]` and ran `sync_citations_and_references.py --reorder-refs` + Word COM `Fields.Update()`.
- **Result**: `References` physically reordered to match first in-text appearance (`Ref25 -> #3`, `Ref26 -> #4`, `Ref03 -> #5`, `Ref04 -> #6`, `Ref05 -> #7`, ..., `Ref27 -> #27`), **0 errors** in Word COM, and MDPI bracket displays updated cleanly:
  - `G01`: **`[1,2]`**, moved `G23`: **`[3,4]`**, `G02`: **`[5,6]`**, `G03`: **`[2,7–10]`**, `G04`: **`[7–10]`**, `G07`: **`[11–16]`**, `G25` (still in §2.3 `P045`, citing `Ref26`): **`[4]`**, `G24`: **`[27]`**.
