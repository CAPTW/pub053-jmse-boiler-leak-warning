# -*- coding: utf-8 -*-
"""Verify the current revised JMSE manuscript DOCX/PDF against archived R2 results,
simulator source configs, structured <w:sdt> citations, live REF fields, and AI/Provenance text.
Outputs fresh table checks CSV and verification JSON directly from the input DOCX/PDF.
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

DEFAULT_DOCX = Path(
    r".\JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx"
)
DEFAULT_PDF = Path(
    r".\JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.pdf"
)
DEFAULT_NUM_DIR = Path(
    r"results_archived"
)
DEFAULT_OUT_DIR = Path(__file__).resolve().parent

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def wtag(name: str) -> str:
    return f"{{{W_NS}}}{name}"


def parse_num(s: str):
    if "—" in s or s.strip() in ("", "-", "–"):
        return None
    cleaned = re.sub(r"[ab]$", "", s.strip()).replace(",", "").replace("−", "-")
    return float(cleaned)


def resolve_replay_summary(num_dir: Path) -> dict:
    r2_only = num_dir / "r2_replay_summary.json"
    if r2_only.exists():
        return json.loads(r2_only.read_text(encoding="utf-8"))
    legacy = num_dir / "review_execution_summary.json"
    if legacy.exists():
        return json.loads(legacy.read_text(encoding="utf-8"))
    prior = num_dir / "prior_draft_review_ce0e9a0e" / "review_execution_summary.json"
    return json.loads(prior.read_text(encoding="utf-8"))


def verify_all(
    docx_path: Path,
    pdf_path: Path,
    num_dir: Path,
    csv_out: Path | None = None,
    report_out: Path | None = None,
) -> dict:
    raw = zipfile.ZipFile(docx_path)
    app_xml = raw.read("docProps/app.xml").decode("utf-8", errors="ignore")
    pages_match = re.search(r"<Pages>(\d+)</Pages>", app_xml)
    office_pages = int(pages_match.group(1)) if pages_match else None

    doc_root = etree.fromstring(raw.read("word/document.xml"))

    # 1. Check <w:bidi/> and <w:bidiVisual/>
    bidi_count = len(doc_root.findall(".//w:bidi", NS)) + len(doc_root.findall(".//w:bidiVisual", NS))
    sect_bidi = bool(doc_root.findall(".//w:sectPr/w:bidi", NS))

    # 2. Check Abstract word count
    body_paras = ["".join(p.itertext()) for p in doc_root.findall(".//w:body/w:p", NS)]
    abstract_text = next(t for t in body_paras if t.startswith("Abstract:"))
    abstract_words = len(abstract_text.removeprefix("Abstract:").split())

    # 3. Extract numbered scientific tables (Tables 1..8) directly from <w:tbl>
    sci_tables = []
    for tbl in doc_root.findall(".//w:body/w:tbl", NS):
        rows_txt = [
            ["".join(tc.itertext()).strip() for tc in tr.findall("./w:tc", NS)]
            for tr in tbl.findall("./w:tr", NS)
        ]
        if len(rows_txt) >= 4 and len(rows_txt[0]) >= 3:
            sci_tables.append(rows_txt)
    assert len(sci_tables) == 8, f"Expected 8 scientific tables, got {len(sci_tables)}"
    t1, t2, t3, t4, t5, t6, t7, t8 = sci_tables

    check_rows: list[dict] = []

    # Verify Table 3 (12 rows) against tables_3_4_5_7_crosscheck.csv
    ref_3457 = list(csv.DictReader((num_dir / "tables_3_4_5_7_crosscheck.csv").open(encoding="utf-8-sig")))
    ref_t3 = {r["row"]: json.loads(r["expected"].replace("None", "null")) for r in ref_3457 if r["table"] == "3"}
    t3_matches = 0
    for row in t3[1:]:
        actual = [parse_num(y) for y in row[2:]]
        exp = [float(x) if isinstance(x, (int, float)) else None for x in ref_t3[row[0]]]
        ok = len(actual) == len(exp) and all(
            (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-8)
            for a, b in zip(actual, exp)
        )
        if ok:
            t3_matches += 1
        check_rows.append({"table": "3", "row": row[0], "match": ok, "actual": actual, "expected": exp})

    # Verify Table 4 (10 rows) against full-precision OLS fit in tables_3_4_5_7_crosscheck.csv
    ref_t4 = [r for r in ref_3457 if r["table"] == "4"]
    t4_matches = 0
    for row, ref in zip(t4[1:], ref_t4):
        actual = parse_num(row[1])
        exp = float(ref["expected"])
        # Display values in Table 4 use significant rounding (check relative tolerance 1e-4, N exact)
        if ref["row"] == "Fit sample N":
            ok = abs(actual - exp) < 1e-9
        else:
            ok = abs(actual - exp) / max(abs(exp), 1e-12) < 5e-4
        if ok:
            t4_matches += 1
        check_rows.append({"table": "4", "row": ref["row"], "match": ok, "actual": actual, "expected": round(exp, 6)})

    # Verify Table 5 (20 rows) against threshold_candidates
    summary = resolve_replay_summary(num_dir)
    method_map = {
        "State (B0)": "B0_state",
        "Flow only": "Flow_only",
        "Demand only": "Command_only",
        "Combined (B1)": "B1_combined",
    }
    t5_matches = 0
    for row in t5[1:]:
        m = method_map[row[0].replace(" [Retained]", "")]
        q = float(row[2])
        v = next(z for z in summary["threshold_candidates"] if z["method"] == m and z["quantile"] == q)
        actual = [parse_num(row[3])] + [int(y) for y in row[4:]]
        exp = [round(v["threshold"], 6)] + v["counts"]
        ok = actual == exp
        if ok:
            t5_matches += 1
        check_rows.append({"table": "5", "row": f"{row[0]}:{row[2]}", "match": ok, "actual": actual, "expected": exp})

    # Verify Table 6 (4 rows) directly against archived summary.csv
    sum_rows = list(csv.DictReader((num_dir / "summary.csv").open(encoding="utf-8-sig")))
    t6_matches = 0
    for row, s in zip(t6[1:], sum_rows):
        actual = [float(x.replace(",", "")) for x in re.findall(r"\d+(?:\.\d+)?", row[3] + " " + row[4])]
        exp = [
            round(float(s[k]), 1)
            for k in ["delay_median_min", "delay_min", "delay_max", "lead_median_min", "lead_min", "lead_max"]
        ]
        ok = actual == exp
        if ok:
            t6_matches += 1
        check_rows.append({"table": "6", "row": row[0], "match": ok, "actual": actual, "expected": exp})

    # Verify Table 7 (8 rows) against tables_3_4_5_7_crosscheck.csv
    ref_t7 = {r["row"]: json.loads(r["expected"].replace("None", "null")) for r in ref_3457 if r["table"] == "7"}
    t7_matches = 0
    for row in t7[1:]:
        actual = [parse_num(y) for y in row[1:]]
        exp = [float(x) if isinstance(x, (int, float)) else None for x in ref_t7[row[0]]]
        ok = actual == exp
        if ok:
            t7_matches += 1
        check_rows.append({"table": "7", "row": row[0], "match": ok, "actual": actual, "expected": exp})

    # Verify Table 8 (8 rows) directly against normal_persistence.csv
    np_rows = list(csv.DictReader((num_dir / "normal_persistence.csv").open(encoding="utf-8-sig")))
    methods_order = ["B0_state", "Flow_only", "Command_only", "B1_combined"]
    t8_matches = 0
    for row in t8[1:]:
        block = row[0].split()[0]
        actual = [float(x.replace("a", "")) for x in row[2:]]
        exp = [
            float(next(r["max_exceedance_span_s"] for r in np_rows if r["episode"] == f"{block}_normal" and r["method"] == m))
            for m in methods_order
        ]
        ok = actual == exp
        if ok:
            t8_matches += 1
        check_rows.append({"table": "8", "row": block, "match": ok, "actual": actual, "expected": exp})

    # 4. Inspect <w:sdt> structured citations and REF fields
    sdt_tags = []
    expanded_ids_count = 0
    for sdt in doc_root.findall(".//w:sdt", NS):
        sdt_pr = sdt.find(wtag("sdtPr"))
        tag_el = sdt_pr.find(wtag("tag")) if sdt_pr is not None else None
        if tag_el is None:
            continue
        tval = tag_el.get(wtag("val"), "")
        if tval.startswith("PUB053_CIT:"):
            sdt_tags.append(tval)
            m_refs = re.search(r"refs=([^;]+)", tval)
            if m_refs:
                expanded_ids_count += len([x for x in m_refs.group(1).split(",") if x.strip()])
    ref_instr = [el.text.strip() for el in doc_root.findall(".//w:instrText", NS) if el.text and "REF Ref" in el.text]

    # 5. Check key scientific, Codex, simulation/R2 separation, and Data Availability disclosures
    full_text = "\n".join("".join(p.itertext()) for p in doc_root.findall(".//w:body/w:p", NS))
    checks = {
        "has_policy_name": "process_protection_without_schedule_severity_oracle" in full_text,
        "has_empirical_tail_4.063845": "4.063845" in full_text and "4.386572" in full_text,
        "has_not_general_identity": "not a general mathematical identity" in full_text,
        "has_51.3_min": "51.3 min" in full_text,
        "no_115.6_in_text": "115.6" not in full_text,
        "has_115.5_in_table6": "115.5" in json.dumps(t6),
        "has_figure6_not_plotted_note": "are reported in Table 7 and are not plotted in this figure" in full_text,
        "has_cutoff_medians": (
            "54.6, 34.7 and 8.9 min" in full_text
            and "76.3, 59.0 and 54.8 min for Demand only" in full_text
            and "76.3, 59.0 and 54.9 min for Combined (B1)" in full_text
        ),
        "has_delay_window_32_32": "Removing this upper time limit returned the same first alarm in all 32 evaluation episode–detector comparisons" in full_text,
        "has_codex_verified_disclosure": (
            "OpenAI Codex" in full_text
            and "gpt-5.3-codex-spark" in full_text
            and "gpt-5.4" in full_text
            and "gpt-5.5" in full_text
            and "docs/AI_USAGE_AUDIT.md" in full_text
        ),
        "no_unverified_ai_models": (
            "gpt-5.6-sol" not in full_text
            and "Claude Opus 4.6" not in full_text
            and "Gemini 3.1 Pro" not in full_text
        ),
        "r2_did_not_generate_trajectories": "did not generate new simulation trajectories or alter physical states" in full_text,
        "has_provenance_separated_data_availability": (
            "results_archived/current_manuscript_verification" in full_text
            and "data/reconstructed_inputs" in full_text
            and "tables_3_4_5_7_crosscheck.csv" in full_text
        ),
        "has_live_public_github_url": "https://github.com/CAPTW/pub053-jmse-boiler-leak-warning" in full_text,
        "has_release_tag": "v1.0.3-pub053-r2" in full_text,
        "has_v102_provenance_and_flags": (
            "REPRODUCIBILITY.md" in full_text
            and "DATA_PROVENANCE.md" in full_text
            and "KNOWN_LIMITATIONS.md" in full_text
            and "SOURCE_PROVENANCE.md" in full_text
            and "AI_USAGE_AUDIT.md" in full_text
            and "--archived-tables-only" in full_text
            and "--archived-assets-only" in full_text
        ),
        "has_fig2_truth_clarification": (
            "whereas panel (b) plots only the conditioned observation" in full_text
            and "Tconfirm + 300 s = 11,194 s" in full_text
            and "dashed plant-truth" not in full_text
        ),
        "no_auto_fallback_overclaim": "automatic full_raw_npz_replay" not in full_text,
        "no_pending_confirmation_placeholder": "to be confirmed by the authors" not in full_text,
        "has_corrected_archive_separation": (
            "PUB053_Manuscript_Package_R2.zip" in full_text
            and "observable_baseline_study_20260915T215200Z_be142b32.zip" in full_text
            and "simulator_source/" in full_text
        ),
        "no_half_open_clamps": "[0, 1)" not in full_text and "[−1, 1)" not in full_text and "[0, 0.999)" not in full_text,
    }

    pdf_errors = None
    pdf_pages = None
    if pdf_path and pdf_path.exists():
        pdf_txt = subprocess.check_output(["pdftotext", str(pdf_path), "-"]).decode("utf-8", errors="ignore")
        pdf_errors = pdf_txt.count("Error!") + pdf_txt.count("오류!")
        pdf_info = subprocess.check_output(["pdfinfo", str(pdf_path)]).decode("utf-8", errors="ignore")
        pm = re.search(r"Pages:\s+(\d+)", pdf_info)
        pdf_pages = int(pm.group(1)) if pm else None

    if csv_out is not None:
        csv_out.parent.mkdir(parents=True, exist_ok=True)
        with csv_out.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["table", "row", "match", "actual", "expected"])
            w.writeheader()
            for r in check_rows:
                w.writerow({
                    "table": r["table"],
                    "row": r["row"],
                    "match": r["match"],
                    "actual": json.dumps(r["actual"]),
                    "expected": json.dumps(r["expected"]),
                })

    total_rows = len(check_rows)
    total_matched = sum(1 for r in check_rows if r["match"])

    report = {
        "target_docx": docx_path.name,
        "docx_sha256": hashlib.sha256(docx_path.read_bytes()).hexdigest(),
        "target_pdf": pdf_path.name,
        "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest() if pdf_path.exists() else None,
        "office_cached_pages": office_pages,
        "pdf_pages": pdf_pages,
        "pdf_field_errors": pdf_errors,
        "bidi_elements_count": bidi_count,
        "section_bidi_present": sect_bidi,
        "abstract_words": abstract_words,
        "sdt_citation_groups": len(sdt_tags),
        "sdt_expanded_ref_ids": expanded_ids_count,
        "live_ref_fields": len(ref_instr),
        "table3_matches": f"{t3_matches}/12",
        "table4_matches": f"{t4_matches}/10",
        "table5_matches": f"{t5_matches}/20",
        "table6_matches": f"{t6_matches}/4",
        "table7_matches": f"{t7_matches}/8",
        "table8_matches": f"{t8_matches}/8",
        "total_table_rows_checked": total_rows,
        "total_table_rows_matched": total_matched,
        "text_checks": checks,
        "all_passed": (
            bidi_count == 0
            and not sect_bidi
            and abstract_words <= 198
            and len(sdt_tags) == 26
            and expanded_ids_count == 54
            and len(ref_instr) == 44
            and total_matched == total_rows == 62
            and (pdf_errors == 0 if pdf_errors is not None else True)
            and all(checks.values())
        ),
    }

    if report_out is not None:
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docx", type=Path, default=DEFAULT_DOCX)
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--num-dir", type=Path, default=DEFAULT_NUM_DIR)
    ap.add_argument("--tables-csv-out", type=Path, default=DEFAULT_OUT_DIR / "current_manuscript_table_checks.csv")
    ap.add_argument("--report-out", type=Path, default=DEFAULT_OUT_DIR / "current_docx_verification_report.json")
    args = ap.parse_args()

    rep = verify_all(args.docx, args.pdf, args.num_dir, args.tables_csv_out, args.report_out)
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    assert rep["all_passed"], "One or more verification checks failed!"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
