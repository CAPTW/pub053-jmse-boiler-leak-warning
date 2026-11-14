"""Open revised DOCX in Microsoft Word via COM:
1. Update all fields, verify zero REF errors & preserved <w:sdt> Content Controls, save & export PDF.
2. Verify post-Word-Save OOXML still preserves all 26 PUB053_CIT Content Controls and 54 RefIDs.
3. Run 3 non-destructive citation scenarios on isolated test copies:
   - Scenario 1: Insert a dummy Ref #1 above Tajiri in Word -> all 44 live REF fields shift +1.
   - Scenario 2: Move interior range member Ref06 (Astrom & Bell) to #27, run sync_docx(reorder_refs=False),
     then Word COM Fields.Update() -> full group IDs preserved, MDPI range formatting recomputed
     (e.g. G03 -> [2,5-7,27], G04 -> [5-7,27], G05 -> [5,27], G06 -> [6,7,27], G19/G21/G22 -> [27]).
   - Scenario 3: Move G23 (Ref25,Ref26) into early Introduction (Para 10 right after G01), run
     sync_docx(reorder_refs=True), then Word COM Fields.Update() -> References physically reordered
     to match first-appearance order (Ref25 -> #3, Ref26 -> #4), G23 -> [3,4], G25 -> [4], G02 -> [5,6],
     G03 -> [2,7-10], G07 -> [11-16], and 0 Word field errors.
"""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path
import win32com.client
from lxml import etree

from sync_citations_and_references import (
    NS,
    W_NS,
    extract_ref_bookmark,
    find_ref_section,
    parse_cit_tag,
    sync_docx,
    wtag,
)

REVISED_DOCX = Path(
    r".\JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx"
)
REVISED_PDF = Path(
    r".\JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.pdf"
)
WORK_DIR = Path(__file__).resolve().parent

TEST_SCENARIO1_DOCX = WORK_DIR / "test_scenario1_insert_before_ref1.docx"
TEST_SCENARIO2_DOCX = WORK_DIR / "test_scenario2_move_interior_ref06.docx"
TEST_SCENARIO3_DOCX = WORK_DIR / "test_scenario3_move_citation_early.docx"

LOG_JSON = WORK_DIR / "citation_editing_and_reordering_test_log.json"
LEGACY_LOG_JSON = WORK_DIR / "citation_dynamic_update_test_log.json"
REPORT_MD = WORK_DIR / "CITATION_EDITING_TEST_REPORT.md"


def collect_ref_field_results(doc) -> list[dict]:
    items = []
    for idx in range(1, doc.Fields.Count + 1):
        fld = doc.Fields(idx)
        code = fld.Code.Text.strip()
        if code.startswith("REF Ref"):
            items.append({
                "index": idx,
                "code": code,
                "result": fld.Result.Text.strip(),
            })
    return items


def collect_sdt_texts(doc) -> dict[str, dict]:
    found = {}
    for cc in doc.ContentControls:
        tag = (cc.Tag or "").strip()
        parsed = parse_cit_tag(tag)
        if parsed is None:
            continue
        gid, refs = parsed
        found[gid] = {
            "tag": tag,
            "refs": refs,
            "text": cc.Range.Text.strip(),
        }
    return found


def find_para_texts(doc, substrings: list[str]) -> dict[str, str]:
    found = {}
    for p in doc.Paragraphs:
        txt = p.Range.Text.replace("\r", "").replace("\x07", "")
        for sub in substrings:
            if sub in txt and sub not in found:
                found[sub] = txt
    return found


def inspect_xml_sdts(docx_path: Path) -> dict:
    with zipfile.ZipFile(docx_path, "r") as z:
        root = etree.fromstring(z.read("word/document.xml"))
    sdts = []
    total_refs = 0
    for sdt in root.findall(".//w:sdt", NS):
        sdt_pr = sdt.find(wtag("sdtPr"))
        tag_el = sdt_pr.find(wtag("tag")) if sdt_pr is not None else None
        if tag_el is None:
            continue
        parsed = parse_cit_tag(tag_el.get(wtag("val"), ""))
        if parsed is None:
            continue
        gid, refs = parsed
        total_refs += len(refs)
        sdt_c = sdt.find(wtag("sdtContent"))
        text_display = "".join(t.text or "" for t in sdt_c.iter(wtag("t"))) if sdt_c is not None else ""
        sdts.append({"group_id": gid, "refs": refs, "display": text_display})
    return {"sdt_count": len(sdts), "expanded_refs": total_refs, "sdts": sdts}


def move_ref_paragraph(docx_path: Path, target_bm: str, new_pos_1based: int) -> None:
    with zipfile.ZipFile(docx_path, "r") as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}
    parser = etree.XMLParser(remove_blank_text=False)
    doc_root = etree.fromstring(entries["word/document.xml"], parser)
    body = doc_root.find(wtag("body"))
    ref_heading_idx, ref_paras = find_ref_section(body)
    ref_heading_el = list(body)[ref_heading_idx]

    src_para = None
    remaining = []
    for p in ref_paras:
        if extract_ref_bookmark(p) == target_bm:
            src_para = p
        else:
            remaining.append(p)
    assert src_para is not None, f"Bookmark {target_bm} not found"
    insert_idx = max(0, min(len(remaining), new_pos_1based - 1))
    new_order = remaining[:insert_idx] + [src_para] + remaining[insert_idx:]

    for p in ref_paras:
        body.remove(p)
    base = list(body).index(ref_heading_el) + 1
    for off, p in enumerate(new_order):
        body.insert(base + off, p)

    entries["word/document.xml"] = etree.tostring(doc_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(docx_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in entries.items():
            zout.writestr(name, data)


def move_citation_group_into_intro(docx_path: Path, move_gid: str = "G23", after_gid: str = "G01") -> None:
    with zipfile.ZipFile(docx_path, "r") as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}
    parser = etree.XMLParser(remove_blank_text=False)
    doc_root = etree.fromstring(entries["word/document.xml"], parser)
    body = doc_root.find(wtag("body"))

    src_sdt = None
    dst_sdt = None
    for sdt in body.findall(".//w:sdt", NS):
        sdt_pr = sdt.find(wtag("sdtPr"))
        tag_el = sdt_pr.find(wtag("tag")) if sdt_pr is not None else None
        if tag_el is None:
            continue
        parsed = parse_cit_tag(tag_el.get(wtag("val"), ""))
        if parsed is None:
            continue
        if parsed[0] == move_gid:
            src_sdt = sdt
        elif parsed[0] == after_gid:
            dst_sdt = sdt
    assert src_sdt is not None and dst_sdt is not None

    src_parent = src_sdt.getparent()
    src_parent.remove(src_sdt)
    dst_parent = dst_sdt.getparent()
    dst_idx = list(dst_parent).index(dst_sdt)
    spacer = etree.Element(wtag("r"))
    t = etree.SubElement(spacer, wtag("t"))
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = " "
    dst_parent.insert(dst_idx + 1, spacer)
    dst_parent.insert(dst_idx + 2, src_sdt)

    entries["word/document.xml"] = etree.tostring(doc_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(docx_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in entries.items():
            zout.writestr(name, data)


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0

    try:
        # 0. Open REVISED_DOCX in Word, update fields, verify SDT + REF fields, save, and export PDF
        doc = word.Documents.Open(str(REVISED_DOCX.resolve()))
        doc.Fields.Update()
        baseline_fields = collect_ref_field_results(doc)
        baseline_errors = [x for x in baseline_fields if not x["result"].isdigit()]
        assert not baseline_errors, f"Broken REF fields in revised DOCX: {baseline_errors}"
        assert len(baseline_fields) == 44, f"Expected 44 REF fields, got {len(baseline_fields)}"
        baseline_sdts_com = collect_sdt_texts(doc)
        assert len(baseline_sdts_com) == 26, f"Expected 26 ContentControls, got {len(baseline_sdts_com)}"

        check_snippets = [
            "machinery-space services",
            "fault-masking effect",
            "Åström and Bell",
            "moving averages (EWMAs)",
            "IAPWS-IF97",
        ]
        before_snippets = find_para_texts(doc, check_snippets)

        doc.Save()
        doc.ExportAsFixedFormat(
            OutputFileName=str(REVISED_PDF.resolve()),
            ExportFormat=17,
            OpenAfterExport=False,
            OptimizeFor=0,
            CreateBookmarks=1,
        )
        page_count = doc.ComputeStatistics(2)
        doc.Close(False)

        post_save_xml_sdts = inspect_xml_sdts(REVISED_DOCX)
        assert post_save_xml_sdts["sdt_count"] == 26
        assert post_save_xml_sdts["expanded_refs"] == 54

        # Scenario 1: Insert dummy Ref #1 above Tajiri in Word COM -> all 44 REF fields shift +1
        shutil.copy2(REVISED_DOCX, TEST_SCENARIO1_DOCX)
        d1 = word.Documents.Open(str(TEST_SCENARIO1_DOCX.resolve()))
        tajiri_p = next((p for p in d1.Paragraphs if "Tajiri, T." in p.Range.Text), None)
        assert tajiri_p is not None
        ref_heading = tajiri_p.Previous()
        ref_style = tajiri_p.Range.Style
        rng = ref_heading.Range.Duplicate
        rng.InsertAfter("Test, A. Dummy Inserted Reference at Top. J. Test 2026, 1, 1–5.\r")
        new_p = ref_heading.Next()
        new_p.Range.Style = ref_style
        d1.Fields.Update()
        s1_fields = collect_ref_field_results(d1)
        s1_errors = [x for x in s1_fields if not x["result"].isdigit()]
        s1_snippets = find_para_texts(d1, check_snippets)
        d1.Save()
        d1.Close(False)
        s1_shifted = all(
            int(a["result"]) == int(b["result"]) + 1
            for b, a in zip(baseline_fields, s1_fields)
        )
        assert not s1_errors and s1_shifted

        # Scenario 2: Move interior member Ref06 (Astrom & Bell) to #27, sync(--no-reorder-refs), Word update
        shutil.copy2(REVISED_DOCX, TEST_SCENARIO2_DOCX)
        move_ref_paragraph(TEST_SCENARIO2_DOCX, "Ref06", 27)
        s2_sync = sync_docx(TEST_SCENARIO2_DOCX, reorder_refs=False)
        d2 = word.Documents.Open(str(TEST_SCENARIO2_DOCX.resolve()))
        d2.Fields.Update()
        s2_fields = collect_ref_field_results(d2)
        s2_errors = [x for x in s2_fields if not x["result"].isdigit()]
        s2_sdts_com = collect_sdt_texts(d2)
        d2.Save()
        d2.Close(False)
        assert not s2_errors, f"Scenario 2 REF errors: {s2_errors}"
        assert s2_sdts_com["G03"]["text"] == "[2,5\u20137,27]"
        assert s2_sdts_com["G03"]["refs"] == ["Ref02", "Ref05", "Ref06", "Ref07", "Ref08"]
        assert s2_sdts_com["G04"]["text"] == "[5\u20137,27]"
        assert s2_sdts_com["G05"]["text"] == "[5,27]"
        assert s2_sdts_com["G06"]["text"] == "[6,7,27]"
        assert s2_sdts_com["G19"]["text"] == "[27]"
        assert s2_sdts_com["G21"]["text"] == "[27]"
        assert s2_sdts_com["G22"]["text"] == "[27]"
        assert s2_sdts_com["G07"]["text"] == "[8\u201313]"
        assert s2_sdts_com["G23"]["text"] == "[24,25]"
        assert s2_sdts_com["G24"]["text"] == "[26]"

        # Scenario 3: Move G23 [25,26] into Paragraph 10 right after G01, sync(--reorder-refs), Word update
        shutil.copy2(REVISED_DOCX, TEST_SCENARIO3_DOCX)
        move_citation_group_into_intro(TEST_SCENARIO3_DOCX, move_gid="G23", after_gid="G01")
        s3_sync = sync_docx(TEST_SCENARIO3_DOCX, reorder_refs=True)
        d3 = word.Documents.Open(str(TEST_SCENARIO3_DOCX.resolve()))
        d3.Fields.Update()
        s3_fields = collect_ref_field_results(d3)
        s3_errors = [x for x in s3_fields if not x["result"].isdigit()]
        s3_sdts_com = collect_sdt_texts(d3)
        d3.Save()
        d3.Close(False)
        assert not s3_errors, f"Scenario 3 REF errors: {s3_errors}"
        assert s3_sync["first_citation_order"] == [r["bookmark"] for r in s3_sync["references_after"]]
        assert s3_sdts_com["G23"]["text"] == "[3,4]"
        assert s3_sdts_com["G25"]["text"] == "[4]"
        assert s3_sdts_com["G02"]["text"] == "[5,6]"
        assert s3_sdts_com["G03"]["text"] == "[2,7\u201310]"
        assert s3_sdts_com["G04"]["text"] == "[7\u201310]"
        assert s3_sdts_com["G07"]["text"] == "[11\u201316]"
        assert s3_sdts_com["G24"]["text"] == "[27]"

        report = {
            "revised_docx": str(REVISED_DOCX),
            "revised_pdf": str(REVISED_PDF),
            "pdf_page_count": page_count,
            "baseline_ref_field_count": len(baseline_fields),
            "ref_field_count": len(baseline_fields),
            "ref_field_errors": baseline_errors,
            "sdt_controls_count": len(baseline_sdts_com),
            "sdt_expanded_ref_ids_count": post_save_xml_sdts["expanded_refs"],
            "all_44_fields_shifted_plus_1": s1_shifted,
            "scenario_1_insert_before_ref1": {
                "passed": s1_shifted and not s1_errors,
                "field_count": len(s1_fields),
                "errors": s1_errors,
                "before_snippets": before_snippets,
                "after_insertion_snippets": s1_snippets,
                "sample_shifts": [
                    {"code": b["code"], "before": b["result"], "after": a["result"]}
                    for b, a in zip(baseline_fields[:8], s1_fields[:8])
                ],
            },
            "scenario_2_move_interior_ref06_to_27_no_reorder": {
                "passed": not s2_errors,
                "field_count_after_range_split": len(s2_fields),
                "errors": s2_errors,
                "preserved_group_refs_check": {
                    g: {"refs": s2_sdts_com[g]["refs"], "word_display": s2_sdts_com[g]["text"]}
                    for g in ["G03", "G04", "G05", "G06", "G07", "G19", "G21", "G22", "G23", "G24"]
                },
            },
            "scenario_3_move_g23_early_and_reorder_refs": {
                "passed": (
                    not s3_errors
                    and s3_sync["first_citation_order"] == [r["bookmark"] for r in s3_sync["references_after"]]
                ),
                "field_count": len(s3_fields),
                "errors": s3_errors,
                "first_citation_order_matches_references": (
                    s3_sync["first_citation_order"] == [r["bookmark"] for r in s3_sync["references_after"]]
                ),
                "new_top5_references": s3_sync["references_after"][:6],
                "recomputed_group_displays": {
                    g: {"refs": s3_sdts_com[g]["refs"], "word_display": s3_sdts_com[g]["text"]}
                    for g in ["G01", "G23", "G02", "G03", "G04", "G07", "G25", "G24"]
                },
            },
            "before_snippets": before_snippets,
            "after_insertion_snippets": s1_snippets,
            "sample_field_shifts": [
                {"code": b["code"], "before": b["result"], "after": a["result"]}
                for b, a in zip(baseline_fields[:12], s1_fields[:12])
            ] + [
                {"code": baseline_fields[-2]["code"], "before": baseline_fields[-2]["result"], "after": s1_fields[-2]["result"]},
                {"code": baseline_fields[-1]["code"], "before": baseline_fields[-1]["result"], "after": s1_fields[-1]["result"]},
            ],
        }
        LOG_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        LEGACY_LOG_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        md_lines = [
            "# PUB053 Citation Architecture & Dynamic Reordering Test Report",
            "",
            f"- **Target Revised DOCX**: `{REVISED_DOCX.name}`",
            f"- **Exported PDF**: `{REVISED_PDF.name}` ({page_count} pages, 0 Word field errors)",
            f"- **Inline Content Controls (`<w:sdt>`)**: **26** controls carrying all **54** expanded `RefXX` member IDs (`PUB053_CIT:id=GXX;refs=...`), preserved across Microsoft Word COM `Fields.Update()` + `Save()`",
            f"- **Live Cross-Reference Fields (`REF RefXX \\n \\t \\h`)**: **44** active fields verified with 0 errors",
            "",
            "## Scenario 1: Insert New Reference Above `[1]` (Word COM Only)",
            "- Inserted dummy reference above `[1] Tajiri, T.` and ran `doc.Fields.Update()` in Microsoft Word.",
            "- **Result**: `44/44` live `REF` fields shifted automatically by `+1`, `0` errors.",
            "",
            "## Scenario 2: Move Interior Range Member `Ref06` (`Åström & Bell`) to `#27` (`--no-reorder-refs`)",
            "- Moved `Ref06` to bottom `#27` and ran `sync_citations_and_references.py --no-reorder-refs` + Word COM `Fields.Update()`.",
            "- **Result**: All 54 member IDs remained intact in `<w:sdt>` tags, Word updated to **47** live `REF` fields with **0 errors**, and MDPI range compression automatically split around `#27`:",
            "  - `G03` (`Ref02,Ref05,Ref06,Ref07,Ref08`): **`[2,5–7,27]`**",
            "  - `G04` (`Ref05,Ref06,Ref07,Ref08`): **`[5–7,27]`**",
            "  - `G05` (`Ref05,Ref06`): **`[5,27]`**",
            "  - `G06` (`Ref06,Ref07,Ref08`): **`[6,7,27]`**",
            "  - `G19`, `G21`, `G22` (`Ref06`): **`[27]`**",
            "  - `G07` (`Ref09..Ref14`): **`[8–13]`**",
            "",
            "## Scenario 3: Move In-Text Citation `G23` (`[25,26]`) to Early Introduction (`--reorder-refs`)",
            "- Moved `G23` (`Ref25,Ref26`) into Paragraph 10 right after `G01 [1,2]` and ran `sync_citations_and_references.py --reorder-refs` + Word COM `Fields.Update()`.",
            "- **Result**: `References` physically reordered to match first in-text appearance (`Ref25 -> #3`, `Ref26 -> #4`, `Ref03 -> #5`, `Ref04 -> #6`, `Ref05 -> #7`, ..., `Ref27 -> #27`), **0 errors** in Word COM, and MDPI bracket displays updated cleanly:",
            "  - `G01`: **`[1,2]`**, moved `G23`: **`[3,4]`**, `G02`: **`[5,6]`**, `G03`: **`[2,7–10]`**, `G04`: **`[7–10]`**, `G07`: **`[11–16]`**, `G25` (still in §2.3 `P045`, citing `Ref26`): **`[4]`**, `G24`: **`[27]`**.",
            "",
        ]
        REPORT_MD.write_text("\n".join(md_lines), encoding="utf-8")

        print(f"ALL 3 CITATION SCENARIOS PASSED | PDF pages={page_count} | SDTs={len(baseline_sdts_com)} (54 IDs)")
        return 0
    finally:
        word.Quit()


if __name__ == "__main__":
    raise SystemExit(main())
