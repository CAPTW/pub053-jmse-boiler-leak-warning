# -*- coding: utf-8 -*-
"""Verify DOCX live REF citations, <w:sdt> Content Controls, first-citation Reference ordering,
CustomXML bibliography sources, 3-scenario citation editing log, PDF render, AI/Provenance text,
and release repo hygiene + current verification CSVs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path
from lxml import etree

from sync_citations_and_references import (
    NS,
    extract_ref_bookmark,
    find_ref_section,
    format_mdpi_expected,
    parse_cit_tag,
    wtag,
)

DEFAULT_ORIG_DOCX = Path(
    r".\JMSE-MDPI-보일러 논문 [김겸원].docx"
)
DEFAULT_ORIG_SHA256 = "5471545c033549ed08fcbf4bea81957d6a35a7b76aad3e42fa4dfa4f8bf99309"
DEFAULT_REV_DOCX = Path(
    r".\JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx"
)
DEFAULT_REV_PDF = Path(
    r".\JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.pdf"
)
DEFAULT_DYN_LOG = Path(
    r"manuscript_verification\citation_editing_and_reordering_test_log.json"
)
DEFAULT_REPO_DIR = Path(__file__).resolve().parent.parent

BIB_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/bibliography}"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_checks(orig_docx: Path, rev_docx: Path, rev_pdf: Path, dyn_log: Path, repo_dir: Path) -> dict:
    # 1. Original DOCX hash unchanged
    orig_sha = sha256_file(orig_docx)
    assert orig_sha == DEFAULT_ORIG_SHA256, f"Original DOCX SHA-256 changed! {orig_sha}"

    # 2. Revised DOCX inspection
    with zipfile.ZipFile(rev_docx) as zf:
        doc_xml = zf.read("word/document.xml")
        custom_xml = zf.read("customXml/item1.xml") if "customXml/item1.xml" in zf.namelist() else b""

    root = etree.fromstring(doc_xml)
    body = root.find(wtag("body"))
    ref_heading_idx, ref_paras = find_ref_section(body)
    ref_bms_in_section = [extract_ref_bookmark(p) for p in ref_paras]
    expected_bms = [f"Ref{i:02d}" for i in range(1, 28)]
    assert ref_bms_in_section == expected_bms, f"Bookmarks in References mismatch: {ref_bms_in_section}"
    bm_to_pos = {bm: pos for pos, bm in enumerate(ref_bms_in_section, start=1)}

    # Collect <w:sdt> citations & verify first-citation order == References order & MDPI bracket display
    sdt_groups = []
    first_citation_order = []
    seen = set()
    expanded_count = 0
    for el in list(body)[:ref_heading_idx]:
        for sdt in el.findall(".//w:sdt", NS):
            sdt_pr = sdt.find(wtag("sdtPr"))
            tag_el = sdt_pr.find(wtag("tag")) if sdt_pr is not None else None
            if tag_el is None:
                continue
            parsed = parse_cit_tag(tag_el.get(wtag("val"), ""))
            if parsed is None:
                continue
            gid, refs = parsed
            sdt_c = sdt.find(wtag("sdtContent"))
            displayed = "".join(t.text or "" for t in sdt_c.iter(wtag("t"))) if sdt_c is not None else ""
            expected_disp = format_mdpi_expected(refs, bm_to_pos)
            assert displayed == expected_disp, f"{gid} display mismatch: {displayed} != {expected_disp}"
            sdt_groups.append({"id": gid, "refs": refs, "display": displayed})
            expanded_count += len(refs)
            for rid in refs:
                if rid not in seen:
                    seen.add(rid)
                    first_citation_order.append(rid)

    assert len(sdt_groups) == 26, f"Expected 26 SDT groups, got {len(sdt_groups)}"
    assert expanded_count == 54, f"Expected 54 expanded member IDs, got {expanded_count}"
    assert first_citation_order == ref_bms_in_section, (
        f"First citation order != References order: {first_citation_order} vs {ref_bms_in_section}"
    )

    instr_texts = [el.text for el in root.findall(".//w:instrText", NS) if el.text]
    ref_fields = [t.strip() for t in instr_texts if "REF Ref" in t]
    assert len(ref_fields) == 44, f"Expected 44 live REF fields, got {len(ref_fields)}"
    assert all(r"\n \t \h" in t for t in ref_fields), "All REF fields must include \\n \\t \\h switches"

    # 3. CustomXML bibliography sources
    assert custom_xml, "customXml/item1.xml missing in revised DOCX"
    import xml.etree.ElementTree as ET
    bib_root = ET.fromstring(custom_xml)
    sources = list(bib_root.iter(f"{BIB_NS}Source"))
    assert len(sources) == 27, f"Expected 27 bibliography sources in customXml/item1.xml, got {len(sources)}"

    # 4. Bidi check
    bidi_count = len(root.findall(".//w:bidi", NS)) + len(root.findall(".//w:bidiVisual", NS))
    assert bidi_count == 0, f"Found {bidi_count} bidi/bidiVisual elements"

    # 5. Disclosures, R2 separation, provenance, and non-citation brackets
    para_texts = ["".join(p.itertext()) for p in body.findall(wtag("p"))]
    full_text = "\n".join(para_texts)
    assert "OpenAI Codex" in full_text
    assert "gpt-5.3-codex-spark" in full_text and "gpt-5.4" in full_text and "gpt-5.5" in full_text
    assert "gpt-5.6-sol" not in full_text
    assert "Claude Opus 4.6" not in full_text
    assert "Gemini 3.1 Pro" not in full_text
    assert "did not generate new simulation trajectories or alter physical states" in full_text
    assert "results_archived/current_manuscript_verification" in full_text
    assert "data/reconstructed_inputs" in full_text
    assert "https://github.com/CAPTW/pub053-jmse-boiler-leak-warning" in full_text
    assert "v1.0.4-pub053-r2" in full_text
    assert "REPRODUCIBILITY.md" in full_text and "DATA_PROVENANCE.md" in full_text and "KNOWN_LIMITATIONS.md" in full_text
    assert "SOURCE_PROVENANCE.md" in full_text and "AI_USAGE_AUDIT.md" in full_text
    assert "--archived-tables-only" in full_text and "--archived-assets-only" in full_text
    assert "whereas panel (b) plots only the conditioned observation" in full_text
    assert "Tconfirm + 300 s = 11,194 s" in full_text
    assert "dashed plant-truth" not in full_text
    assert "automatic full_raw_npz_replay" not in full_text
    assert "to be confirmed by the authors" not in full_text
    assert "boiler_pdm_sim" in full_text and "ab4" in full_text
    assert "Firstname Lastname 2,*" in full_text
    assert "[0, 1]" in full_text and "[−1, 1]" in full_text and "[0, 0.999]" in full_text
    assert "[0, 1)" not in full_text and "[−1, 1)" not in full_text and "[0, 0.999)" not in full_text
    assert "episode_results.csv" in full_text and "summary.csv" in full_text and "normal_persistence.csv" in full_text

    # 6. 4-Operation Citation Test Log
    dyn = json.loads(dyn_log.read_text(encoding="utf-8"))
    assert dyn["ref_field_count"] == 44
    assert dyn["ref_field_errors"] == []
    assert dyn["all_44_fields_shifted_plus_1"] is True
    assert dyn["scenario_1_insert_before_ref1"]["passed"] is True
    assert dyn["scenario_1b_add_new_sdt_g27_and_ref28"]["passed"] is True
    assert dyn["scenario_2_move_interior_ref06_to_27_no_reorder"]["passed"] is True
    assert dyn["scenario_3_move_g23_early_and_reorder_refs"]["passed"] is True
    assert dyn["scenario_4_delete_g02_and_prune_uncited"]["passed"] is True

    # 7. PDF checks
    assert rev_pdf.exists(), f"Missing PDF: {rev_pdf}"
    pdf_txt = subprocess.check_output(["pdftotext", str(rev_pdf), "-"]).decode("utf-8")
    assert pdf_txt.count("Error!") + pdf_txt.count("오류!") == 0
    pdf_norm = re.sub(r"-\s*(?:\r?\n\s*(?:\d+\s*\r?\n\s*)?)", "", pdf_txt)
    pdf_norm = re.sub(r"\s+", " ", pdf_norm)
    assert "OpenAI Codex" in pdf_norm
    assert "episode_results.csv" in pdf_norm
    for forbidden_local in ("\u0043\u003a\\Users\\", "\u0047\u003a\\\ub0b4 \ub4dc\ub77c\uc774\ube0c", "\u0047\u003a\\\ub2e4\ub978 \ucef4\ud4e8\ud130", "D\u003a\\dev\\"):
        assert forbidden_local not in full_text, f"Local path leaked into DOCX: {forbidden_local}"
        assert forbidden_local not in pdf_txt, f"Local path leaked into PDF: {forbidden_local}"
    pdf_info = subprocess.check_output(["pdfinfo", str(rev_pdf)]).decode("utf-8", errors="ignore")
    pages_match = re.search(r"Pages:\s+(\d+)", pdf_info)
    office_pages = int(pages_match.group(1)) if pages_match else dyn["pdf_page_count"]

    # 8. Release repo hygiene & current verification table checks (if repo exists)
    forbidden_exts = (".docx", ".dot", ".pdf", ".pyc", ".pyo")
    forbidden_parts = {"__pycache__", ".pytest_cache", ".codex"}
    bad_paths = []
    cur_table_rows_ok = None
    if repo_dir.exists():
        for p in repo_dir.rglob("*"):
            rel = p.relative_to(repo_dir).as_posix()
            parts = rel.split("/")
            if parts[0] == ".git":
                continue
            if rel.lower().endswith(forbidden_exts) or any(
                part in forbidden_parts or part.startswith(".venv") for part in parts
            ):
                bad_paths.append(rel)
        assert not bad_paths, f"Forbidden files/dirs in release repo: {bad_paths}"

        cur_csv = repo_dir / "results_archived" / "current_manuscript_verification" / "current_manuscript_table_checks.csv"
        if cur_csv.exists():
            with cur_csv.open("r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            assert len(rows) == 62 and all(r["match"] == "True" for r in rows), (
                f"Expected 62/62 matches in {cur_csv}"
            )
            cur_table_rows_ok = f"{len(rows)}/{len(rows)}"

    return {
        "original_docx_sha256": orig_sha,
        "original_docx_unchanged": True,
        "revised_docx_sha256": sha256_file(rev_docx),
        "revised_pdf_sha256": sha256_file(rev_pdf),
        "bookmarks_count": len(ref_bms_in_section),
        "sdt_citation_groups_count": len(sdt_groups),
        "sdt_expanded_ref_ids_count": expanded_count,
        "first_citation_order_matches_references": True,
        "live_ref_fields_count": len(ref_fields),
        "customxml_sources_count": len(sources),
        "bidi_elements_count": bidi_count,
        "scenario_1_passed": True,
        "scenario_1b_add_passed": True,
        "scenario_2_move_passed": True,
        "scenario_3_reorder_passed": True,
        "scenario_4_delete_passed": True,
        "pdf_pages": office_pages,
        "pdf_text_chars": len(pdf_txt),
        "pdf_ref_errors": 0,
        "disclosures_verified": True,
        "second_author_placeholder_preserved": True,
        "current_manuscript_table_checks": cur_table_rows_ok,
        "release_repo_forbidden_files": bad_paths,
        "all_passed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-docx", type=Path, default=DEFAULT_ORIG_DOCX)
    parser.add_argument("--docx", type=Path, default=DEFAULT_REV_DOCX)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_REV_PDF)
    parser.add_argument("--dyn-log", type=Path, default=DEFAULT_DYN_LOG)
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    args = parser.parse_args()
    res = run_checks(args.original_docx, args.docx, args.pdf, args.dyn_log, args.repo_dir)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
