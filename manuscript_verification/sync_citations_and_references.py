# -*- coding: utf-8 -*-
"""Synchronize PUB053 Word citation groups (<w:sdt> Content Controls) and References list.

Supports:
1. Reading every inline citation group <w:sdt> with w:tag="PUB053_CIT:id=GXX;refs=RefXX,..."
   so every cited work ID (including interior members of compressed ranges such as [2,5–8])
   remains bound to its group even after references or citations move.
2. Reordering the References paragraphs (MDPI81references) by first in-text appearance
   across the document body (--reorder-refs, default), or preserving manual References
   order (--no-reorder-refs) and recomputing MDPI compressed brackets around moved entries.
3. Rebuilding each <w:sdtContent> using live Word `REF RefXX \\n \\t \\h` fields formatted in
   MDPI style ([n], [a,b] for 2 consecutive numbers, [a–b] with en-dash for >=3 consecutive).
4. Optional --update-word to run Word COM Fields.Update(), save, and verify 0 REF errors.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import zipfile
from pathlib import Path
from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W_NS}


def wtag(name: str) -> str:
    return f"{{{W_NS}}}{name}"


def make_run(text: str, rpr_template: etree._Element | None = None) -> etree._Element:
    r = etree.Element(wtag("r"))
    if rpr_template is not None:
        r.append(copy.deepcopy(rpr_template))
    t = etree.SubElement(r, wtag("t"))
    if text.startswith(" ") or text.endswith(" ") or "  " in text:
        t.set(f"{{{XML_NS}}}space", "preserve")
    t.text = text
    return r


def make_ref_field_runs(
    bm_name: str,
    display_num: int,
    rpr_template: etree._Element | None = None,
) -> list[etree._Element]:
    runs: list[etree._Element] = []

    r_begin = etree.Element(wtag("r"))
    if rpr_template is not None:
        r_begin.append(copy.deepcopy(rpr_template))
    fc_begin = etree.SubElement(r_begin, wtag("fldChar"))
    fc_begin.set(wtag("fldCharType"), "begin")
    runs.append(r_begin)

    r_instr = etree.Element(wtag("r"))
    if rpr_template is not None:
        r_instr.append(copy.deepcopy(rpr_template))
    instr = etree.SubElement(r_instr, wtag("instrText"))
    instr.set(f"{{{XML_NS}}}space", "preserve")
    instr.text = f" REF {bm_name} \\n \\t \\h "
    runs.append(r_instr)

    r_sep = etree.Element(wtag("r"))
    if rpr_template is not None:
        r_sep.append(copy.deepcopy(rpr_template))
    fc_sep = etree.SubElement(r_sep, wtag("fldChar"))
    fc_sep.set(wtag("fldCharType"), "separate")
    runs.append(r_sep)

    runs.append(make_run(str(display_num), rpr_template))

    r_end = etree.Element(wtag("r"))
    if rpr_template is not None:
        r_end.append(copy.deepcopy(rpr_template))
    fc_end = etree.SubElement(r_end, wtag("fldChar"))
    fc_end.set(wtag("fldCharType"), "end")
    runs.append(r_end)

    return runs


def compress_ref_runs(ref_items: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """Group position-sorted (pos, RefID) tuples into contiguous integer runs."""
    if not ref_items:
        return []
    ordered = sorted(ref_items, key=lambda x: x[0])
    deduped: list[tuple[int, str]] = []
    seen: set[str] = set()
    for pos, ref_id in ordered:
        if ref_id not in seen:
            seen.add(ref_id)
            deduped.append((pos, ref_id))

    groups: list[list[tuple[int, str]]] = [[deduped[0]]]
    for pos, ref_id in deduped[1:]:
        if pos == groups[-1][-1][0] + 1:
            groups[-1].append((pos, ref_id))
        else:
            groups.append([(pos, ref_id)])
    return groups


def format_mdpi_expected(ref_ids: list[str], bm_to_pos: dict[str, int]) -> str:
    pos_items = [(bm_to_pos[bm], bm) for bm in ref_ids]
    grouped = compress_ref_runs(pos_items)
    parts: list[str] = []
    for grp in grouped:
        if len(grp) == 1:
            parts.append(str(grp[0][0]))
        elif len(grp) == 2:
            parts.append(f"{grp[0][0]},{grp[1][0]}")
        else:
            parts.append(f"{grp[0][0]}\u2013{grp[-1][0]}")
    return "[" + ",".join(parts) + "]"


def build_mdpi_bracket_runs(
    ref_ids: list[str],
    bm_to_pos: dict[str, int],
    rpr_template: etree._Element | None = None,
) -> list[etree._Element]:
    runs_out: list[etree._Element] = [make_run("[", rpr_template)]
    pos_items = [(bm_to_pos[bm], bm) for bm in ref_ids]
    grouped = compress_ref_runs(pos_items)
    for idx, grp in enumerate(grouped):
        if idx > 0:
            runs_out.append(make_run(",", rpr_template))
        if len(grp) == 1:
            runs_out.extend(make_ref_field_runs(grp[0][1], grp[0][0], rpr_template))
        elif len(grp) == 2:
            runs_out.extend(make_ref_field_runs(grp[0][1], grp[0][0], rpr_template))
            runs_out.append(make_run(",", rpr_template))
            runs_out.extend(make_ref_field_runs(grp[1][1], grp[1][0], rpr_template))
        else:
            runs_out.extend(make_ref_field_runs(grp[0][1], grp[0][0], rpr_template))
            runs_out.append(make_run("\u2013", rpr_template))
            runs_out.extend(make_ref_field_runs(grp[-1][1], grp[-1][0], rpr_template))
    runs_out.append(make_run("]", rpr_template))
    return runs_out


def parse_cit_tag(tag_val: str) -> tuple[str, list[str]] | None:
    if not tag_val.startswith("PUB053_CIT:"):
        return None
    m_id = re.search(r"id=([^;]+)", tag_val)
    m_refs = re.search(r"refs=([^;]+)", tag_val)
    if not m_id or not m_refs:
        return None
    ref_ids = [r.strip() for r in m_refs.group(1).split(",") if r.strip()]
    return m_id.group(1).strip(), ref_ids


def find_ref_section(body: etree._Element) -> tuple[int, list[etree._Element]]:
    """Return (index_of_References_heading_in_body, list_of_reference_p_elements)."""
    children = list(body)
    ref_heading_child_idx = None
    for idx, el in enumerate(children):
        if el.tag == wtag("p") and "".join(el.itertext()).strip() == "References":
            ref_heading_child_idx = idx
            break
    if ref_heading_child_idx is None:
        raise RuntimeError("Could not locate 'References' heading paragraph")

    ref_paras: list[etree._Element] = []
    for el in children[ref_heading_child_idx + 1:]:
        if el.tag != wtag("p"):
            continue
        ppr = el.find(wtag("pPr"))
        pstyle = ppr.find(wtag("pStyle")).get(wtag("val")) if (ppr is not None and ppr.find(wtag("pStyle")) is not None) else ""
        txt = "".join(el.itertext()).strip()
        if pstyle == "MDPI81references" or txt:
            ref_paras.append(el)
    return ref_heading_child_idx, ref_paras


def extract_ref_bookmark(p: etree._Element) -> str | None:
    for bm in p.findall(".//w:bookmarkStart", NS):
        name = bm.get(wtag("name"), "")
        if name and not name.startswith("_"):
            return name
    return None


def sync_docx(
    docx_path: Path,
    out_path: Path | None = None,
    reorder_refs: bool = True,
    prune_uncited: bool = False,
) -> dict:
    target_path = out_path if out_path is not None else docx_path
    with zipfile.ZipFile(docx_path, "r") as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}

    parser = etree.XMLParser(remove_blank_text=False)
    doc_root = etree.fromstring(entries["word/document.xml"], parser)
    body = doc_root.find(wtag("body"))
    ref_heading_child_idx, ref_paras = find_ref_section(body)
    ref_heading_el = list(body)[ref_heading_child_idx]

    # Collect all PUB053_CIT <w:sdt> elements before References heading in document order
    cited_order: list[str] = []
    seen_refs: set[str] = set()
    cit_sdts: list[tuple[str, list[str], etree._Element]] = []
    for el in list(body)[:ref_heading_child_idx]:
        for sdt in el.findall(".//w:sdt", NS):
            sdt_pr = sdt.find(wtag("sdtPr"))
            tag_el = sdt_pr.find(wtag("tag")) if sdt_pr is not None else None
            if tag_el is None:
                continue
            parsed = parse_cit_tag(tag_el.get(wtag("val"), ""))
            if parsed is None:
                continue
            gid, ref_ids = parsed
            cit_sdts.append((gid, ref_ids, sdt))
            for rid in ref_ids:
                if rid not in seen_refs:
                    seen_refs.add(rid)
                    cited_order.append(rid)

    # Map each reference paragraph to its bookmark (None if newly inserted un-bookmarked)
    para_bms = [extract_ref_bookmark(p) for p in ref_paras]
    bm_to_para: dict[str, etree._Element] = {}
    for p, bm in zip(ref_paras, para_bms):
        if bm is not None:
            bm_to_para[bm] = p

    missing_bms = [bm for bm in cited_order if bm not in bm_to_para]
    if missing_bms:
        raise RuntimeError(f"Cited bookmarks missing from References: {missing_bms}")

    # Reorder and/or prune References paragraphs if requested
    cited_set = set(cited_order)
    pruned_bms = [bm for bm in para_bms if bm is not None and bm not in cited_set] if prune_uncited else []
    if reorder_refs or prune_uncited:
        if reorder_refs:
            cited_paras = [bm_to_para[bm] for bm in cited_order]
            uncited_paras = [] if prune_uncited else [
                p for p, bm in zip(ref_paras, para_bms) if bm is None or bm not in cited_set
            ]
            new_ref_paras = cited_paras + uncited_paras
        else:
            new_ref_paras = [p for p, bm in zip(ref_paras, para_bms) if bm in cited_set]

        # Remove old ref_paras from body and reinsert immediately after ref_heading_el
        for p in ref_paras:
            body.remove(p)
        insert_base = list(body).index(ref_heading_el) + 1
        for offset, p in enumerate(new_ref_paras):
            body.insert(insert_base + offset, p)
        ref_paras = new_ref_paras

    # Compute current 1-based position of each bookmark inside References
    bm_to_pos: dict[str, int] = {}
    ref_order_after: list[dict] = []
    for pos, p in enumerate(ref_paras, start=1):
        bm = extract_ref_bookmark(p)
        if bm:
            bm_to_pos[bm] = pos
        ref_order_after.append({
            "pos": pos,
            "bookmark": bm,
            "snippet": "".join(p.itertext()).strip()[:75],
        })

    # Rebuild every <w:sdtContent> in MDPI compressed bracket format with live REF fields
    group_displays: list[dict] = []
    for gid, ref_ids, sdt in cit_sdts:
        sdt_content = sdt.find(wtag("sdtContent"))
        if sdt_content is None:
            sdt_content = etree.SubElement(sdt, wtag("sdtContent"))
        first_r = sdt_content.find(wtag("r"))
        rpr_template = first_r.find(wtag("rPr")) if first_r is not None else None
        rpr_copy = copy.deepcopy(rpr_template) if rpr_template is not None else None

        for child in list(sdt_content):
            sdt_content.remove(child)
        for rn in build_mdpi_bracket_runs(ref_ids, bm_to_pos, rpr_copy):
            sdt_content.append(rn)

        group_displays.append({
            "group_id": gid,
            "refs": ref_ids,
            "expected_display": format_mdpi_expected(ref_ids, bm_to_pos),
        })

    entries["word/document.xml"] = etree.tostring(doc_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in entries.items():
            zout.writestr(name, data)

    return {
        "docx_path": str(target_path),
        "reorder_refs": reorder_refs,
        "prune_uncited": prune_uncited,
        "pruned_bookmarks": pruned_bms,
        "sdt_groups_count": len(cit_sdts),
        "expanded_citations_count": sum(len(refs) for _, refs, _ in cit_sdts),
        "first_citation_order": cited_order,
        "bm_to_pos": bm_to_pos,
        "references_after": ref_order_after,
        "group_displays": group_displays,
    }


def word_com_update_and_verify(docx_path: Path, pdf_out: Path | None = None) -> dict:
    import win32com.client

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(docx_path.resolve()))
        doc.Fields.Update()
        fields = []
        errors = []
        for idx in range(1, doc.Fields.Count + 1):
            fld = doc.Fields(idx)
            code = fld.Code.Text.strip()
            if code.startswith("REF Ref"):
                res = fld.Result.Text.strip()
                item = {"index": idx, "code": code, "result": res}
                fields.append(item)
                if not res.isdigit():
                    errors.append(item)
        sdt_results = []
        for cc in doc.ContentControls:
            tag = (cc.Tag or "").strip()
            if tag.startswith("PUB053_CIT:"):
                sdt_results.append({
                    "title": cc.Title,
                    "tag": tag,
                    "text": cc.Range.Text.strip(),
                })
        doc.Save()
        if pdf_out is not None:
            doc.ExportAsFixedFormat(
                OutputFileName=str(pdf_out.resolve()),
                ExportFormat=17,
                OpenAfterExport=False,
                OptimizeFor=0,
                CreateBookmarks=1,
            )
        page_count = doc.ComputeStatistics(2)
        doc.Close(False)
        return {
            "ref_fields_count": len(fields),
            "ref_field_errors": errors,
            "sdt_controls_after_save": len(sdt_results),
            "sdt_results": sdt_results,
            "pdf_page_count": page_count,
        }
    finally:
        word.Quit()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("docx", type=Path, help="Input DOCX path")
    ap.add_argument("--out", type=Path, default=None, help="Optional output DOCX path (defaults to in-place)")
    ap.add_argument("--reorder-refs", dest="reorder_refs", action="store_true", default=True)
    ap.add_argument("--no-reorder-refs", dest="reorder_refs", action="store_false")
    ap.add_argument("--prune-uncited", action="store_true", default=False, help="Remove References items no longer cited in body")
    ap.add_argument("--update-word", action="store_true", help="Run Word COM Fields.Update() and save")
    ap.add_argument("--pdf-out", type=Path, default=None, help="Optional PDF export path (with --update-word)")
    args = ap.parse_args()

    res = sync_docx(args.docx, args.out, reorder_refs=args.reorder_refs, prune_uncited=args.prune_uncited)
    target = args.out if args.out is not None else args.docx
    if args.update_word:
        res["word_com"] = word_com_update_and_verify(target, args.pdf_out)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
