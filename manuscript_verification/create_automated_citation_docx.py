"""Create the revised JMSE manuscript DOCX with automated, Word-field-linked
citations, embedded Word Bibliography XML, and updated AI / Methods /
Data Availability / Acknowledgments disclosures.

Preserves the original DOCX completely untouched.
"""

from __future__ import annotations

import copy
import hashlib
import os
import re
import zipfile
from lxml import etree

SRC_DOCX = r".\JMSE-MDPI-보일러 논문 [김겸원].docx"
DST_DOCX = r".\JMSE-MDPI-보일러 논문 [김겸원]_인용자동화_개정본.docx"
WORD_SOURCES_XML = r"references\word_sources.xml"

EXPECTED_SRC_SHA256 = "5471545c033549ed08fcbf4bea81957d6a35a7b76aad3e42fa4dfa4f8bf99309"

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


def make_ref_field_runs(ref_num: int, rpr_template: etree._Element | None = None) -> list[etree._Element]:
    """Create Word complex field runs: REF RefXX \\n \\t \\h displaying ref_num."""
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
    instr.text = f" REF Ref{ref_num:02d} \\n \\t \\h "
    runs.append(r_instr)

    r_sep = etree.Element(wtag("r"))
    if rpr_template is not None:
        r_sep.append(copy.deepcopy(rpr_template))
    fc_sep = etree.SubElement(r_sep, wtag("fldChar"))
    fc_sep.set(wtag("fldCharType"), "separate")
    runs.append(r_sep)

    runs.append(make_run(str(ref_num), rpr_template))

    r_end = etree.Element(wtag("r"))
    if rpr_template is not None:
        r_end.append(copy.deepcopy(rpr_template))
    fc_end = etree.SubElement(r_end, wtag("fldChar"))
    fc_end.set(wtag("fldCharType"), "end")
    runs.append(r_end)

    return runs


def parse_bracket_nums(bracket_inner: str) -> list[int]:
    """Expand '2,5–8' or '20,22–24' into [2, 5, 6, 7, 8] or [20, 22, 23, 24]."""
    nums: list[int] = []
    for part in [p.strip() for p in bracket_inner.split(",")]:
        m = re.fullmatch(r"(\d+)\s*([–\-])\s*(\d+)", part)
        if m:
            n1, n2 = int(m.group(1)), int(m.group(3))
            step = 1 if n2 >= n1 else -1
            nums.extend(range(n1, n2 + step, step))
        else:
            nums.append(int(part))
    return nums


def compress_ref_runs(ref_items: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """Group position-sorted (pos, RefID) tuples into contiguous integer runs."""
    if not ref_items:
        return []
    ordered = sorted(ref_items, key=lambda x: x[0])
    deduped: list[tuple[int, str]] = []
    seen_ids: set[str] = set()
    for pos, ref_id in ordered:
        if ref_id not in seen_ids:
            seen_ids.add(ref_id)
            deduped.append((pos, ref_id))

    runs: list[list[tuple[int, str]]] = [[deduped[0]]]
    for pos, ref_id in deduped[1:]:
        if pos == runs[-1][-1][0] + 1:
            runs[-1].append((pos, ref_id))
        else:
            runs.append([(pos, ref_id)])
    return runs


def build_mdpi_bracket_runs(
    ref_ids: list[str],
    bm_to_pos: dict[str, int],
    rpr_template: etree._Element | None = None,
) -> list[etree._Element]:
    """Format ref_ids in MDPI bracket syntax using live REF fields:
    - 1 item -> [n]
    - 2 consecutive items -> [a,b]
    - >=3 consecutive items -> [a–b]
    """
    runs_out: list[etree._Element] = [make_run("[", rpr_template)]
    pos_items = [(bm_to_pos[bm], bm) for bm in ref_ids]
    grouped = compress_ref_runs(pos_items)
    for idx, grp in enumerate(grouped):
        if idx > 0:
            runs_out.append(make_run(",", rpr_template))
        if len(grp) == 1:
            n = int(grp[0][1].replace("Ref", ""))
            runs_out.extend(make_ref_field_runs(n, rpr_template))
            # overwrite placeholder text to actual current pos
            runs_out[-2].find(wtag("t")).text = str(grp[0][0])
        elif len(grp) == 2:
            n1 = int(grp[0][1].replace("Ref", ""))
            n2 = int(grp[1][1].replace("Ref", ""))
            runs_out.extend(make_ref_field_runs(n1, rpr_template))
            runs_out[-2].find(wtag("t")).text = str(grp[0][0])
            runs_out.append(make_run(",", rpr_template))
            runs_out.extend(make_ref_field_runs(n2, rpr_template))
            runs_out[-2].find(wtag("t")).text = str(grp[1][0])
        else:
            n1 = int(grp[0][1].replace("Ref", ""))
            n2 = int(grp[-1][1].replace("Ref", ""))
            runs_out.extend(make_ref_field_runs(n1, rpr_template))
            runs_out[-2].find(wtag("t")).text = str(grp[0][0])
            runs_out.append(make_run("\u2013", rpr_template))
            runs_out.extend(make_ref_field_runs(n2, rpr_template))
            runs_out[-2].find(wtag("t")).text = str(grp[-1][0])
    runs_out.append(make_run("]", rpr_template))
    return runs_out


def build_citation_sdt(
    group_id: str,
    ref_ids: list[str],
    bm_to_pos: dict[str, int],
    sdt_id: int,
    rpr_template: etree._Element | None = None,
) -> etree._Element:
    """Wrap an inline citation group in a Word <w:sdt> preserving every RefID in w:tag."""
    sdt = etree.Element(wtag("sdt"))
    sdt_pr = etree.SubElement(sdt, wtag("sdtPr"))
    alias = etree.SubElement(sdt_pr, wtag("alias"))
    alias.set(wtag("val"), f"PUB053_Citation_{group_id}")
    tag = etree.SubElement(sdt_pr, wtag("tag"))
    tag.set(wtag("val"), f"PUB053_CIT:id={group_id};refs={','.join(ref_ids)}")
    wid = etree.SubElement(sdt_pr, wtag("id"))
    wid.set(wtag("val"), str(sdt_id))
    sdt_content = etree.SubElement(sdt, wtag("sdtContent"))
    for rn in build_mdpi_bracket_runs(ref_ids, bm_to_pos, rpr_template):
        sdt_content.append(rn)
    return sdt


def is_citation_bracket(full_match: str, inner: str) -> bool:
    if not re.fullmatch(r"\d+(?:[,\s–\-]+\d+)*", inner):
        return False
    if full_match == "[0, 1]":
        return False
    return True


def replace_citations_in_paragraph(p: etree._Element, state: dict[str, int]) -> tuple[int, int, int]:
    """Replace all genuine citation brackets in paragraph p with <w:sdt> controls
    containing full member IDs in w:tag and live REF fields in w:sdtContent.
    Returns (groups_converted, field_links_created, expanded_member_count).
    """
    groups = 0
    fields = 0
    expanded = 0
    bm_to_pos = {f"Ref{i:02d}": i for i in range(1, 28)}
    for child in list(p):
        if child.tag != wtag("r"):
            continue
        if child.find(wtag("fldChar")) is not None or child.find(wtag("instrText")) is not None:
            continue
        t_elems = child.findall(wtag("t"))
        if len(t_elems) != 1:
            continue
        text = t_elems[0].text or ""
        matches = [m for m in re.finditer(r"\[([^\]]+)\]", text) if is_citation_bracket(m.group(0), m.group(1))]
        if not matches:
            continue

        rpr = child.find(wtag("rPr"))
        new_nodes: list[etree._Element] = []
        cursor = 0
        for m in matches:
            if m.start() > cursor:
                new_nodes.append(make_run(text[cursor:m.start()], rpr))
            nums = parse_bracket_nums(m.group(1))
            ref_ids = [f"Ref{n:02d}" for n in nums]
            state["group_idx"] += 1
            state["sdt_id"] += 1
            group_id = f"G{state['group_idx']:02d}"
            sdt = build_citation_sdt(group_id, ref_ids, bm_to_pos, state["sdt_id"], rpr)
            new_nodes.append(sdt)
            groups += 1
            expanded += len(ref_ids)
            fields += sum(1 for rn in sdt.iter(wtag("instrText")))
            cursor = m.end()
        if cursor < len(text):
            new_nodes.append(make_run(text[cursor:], rpr))

        insert_pos = list(p).index(child)
        p.remove(child)
        for offset, node in enumerate(new_nodes):
            p.insert(insert_pos + offset, node)
    return groups, fields, expanded


def replace_paragraph_text(p: etree._Element, bold_prefix: str | None, body_text: str) -> None:
    """Clear runs in p (preserving pPr) and insert optional bold prefix + body text."""
    ppr = p.find(wtag("pPr"))
    for child in list(p):
        if child is not ppr:
            p.remove(child)
    if bold_prefix:
        r_bold = etree.Element(wtag("r"))
        rpr_b = etree.SubElement(r_bold, wtag("rPr"))
        etree.SubElement(rpr_b, wtag("b"))
        t_b = etree.SubElement(r_bold, wtag("t"))
        t_b.text = bold_prefix
        p.append(r_bold)
        p.append(make_run(" " + body_text))
    else:
        p.append(make_run(body_text))


def main():
    import argparse
    global SRC_DOCX, DST_DOCX, WORD_SOURCES_XML
    ap = argparse.ArgumentParser(description="Create citation-automated JMSE DOCX with <w:sdt>, REF fields, and v1.0.1 disclosures.")
    ap.add_argument("--src-docx", default=SRC_DOCX)
    ap.add_argument("--dst-docx", default=DST_DOCX)
    ap.add_argument("--word-sources-xml", default=WORD_SOURCES_XML)
    args = ap.parse_args()
    SRC_DOCX = args.src_docx
    DST_DOCX = args.dst_docx
    WORD_SOURCES_XML = args.word_sources_xml

    actual_sha = hashlib.sha256(open(SRC_DOCX, "rb").read()).hexdigest()
    assert actual_sha == EXPECTED_SRC_SHA256, f"Source SHA mismatch: {actual_sha}"

    with zipfile.ZipFile(SRC_DOCX, "r") as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}

    parser = etree.XMLParser(remove_blank_text=False)
    doc_root = etree.fromstring(entries["word/document.xml"], parser)
    body = doc_root.find(wtag("body"))
    paras = body.findall(wtag("p"))

    # Find max existing bookmark id
    existing_ids = []
    for bm in doc_root.findall(".//w:bookmarkStart", NS):
        bid = bm.get(wtag("id"))
        if bid and bid.isdigit():
            existing_ids.append(int(bid))
    next_bm_id = max(existing_ids, default=-1) + 1

    # 1. Locate References heading and bookmark P119..P145 as Ref01..Ref27
    ref_heading_idx = next(
        i for i, p in enumerate(paras)
        if "".join(p.itertext()).strip() == "References"
    )
    assert len(paras) - (ref_heading_idx + 1) >= 27, "Expected 27 reference paragraphs"

    for ref_idx in range(27):
        p = paras[ref_heading_idx + 1 + ref_idx]
        bm_name = f"Ref{ref_idx + 1:02d}"
        bm_id = str(next_bm_id)
        next_bm_id += 1

        bm_start = etree.Element(wtag("bookmarkStart"))
        bm_start.set(wtag("id"), bm_id)
        bm_start.set(wtag("name"), bm_name)

        bm_end = etree.Element(wtag("bookmarkEnd"))
        bm_end.set(wtag("id"), bm_id)

        # Place bookmarkStart strictly inside the paragraph's text (after the first run's
        # first character) so inserting a new reference immediately before Ref01 does not
        # pull Ref01's bookmarkStart backward onto the newly inserted paragraph.
        first_r = p.find(wtag("r"))
        placed_inside = False
        if first_r is not None:
            t_el = first_r.find(wtag("t"))
            if t_el is not None and t_el.text and len(t_el.text) >= 2:
                rpr = first_r.find(wtag("rPr"))
                r_head = make_run(t_el.text[0], rpr)
                r_tail = make_run(t_el.text[1:], rpr)
                idx_r = list(p).index(first_r)
                p.remove(first_r)
                p.insert(idx_r, r_head)
                p.insert(idx_r + 1, bm_start)
                p.insert(idx_r + 2, r_tail)
                placed_inside = True
        if not placed_inside:
            ppr = p.find(wtag("pPr"))
            insert_idx = list(p).index(ppr) + 1 if ppr is not None else 0
            p.insert(insert_idx, bm_start)
        p.append(bm_end)

    # 2. Replace the 26 in-text citation groups (before References) with <w:sdt> content controls + live REF fields
    existing_sdt_ids = []
    for el in doc_root.findall(".//w:sdtPr/w:id", NS):
        val = el.get(wtag("val"))
        if val and val.isdigit():
            existing_sdt_ids.append(int(val))
    state = {"group_idx": 0, "sdt_id": max(existing_sdt_ids, default=9000000)}

    total_groups = 0
    total_fields = 0
    total_expanded = 0
    for i in range(ref_heading_idx):
        g, f, exp = replace_citations_in_paragraph(paras[i], state)
        total_groups += g
        total_fields += f
        total_expanded += exp

    assert total_groups == 26, f"Expected 26 citation groups converted, got {total_groups}"
    assert total_expanded == 54, f"Expected 54 expanded citation IDs, got {total_expanded}"

    # 3. Update P057 (Section 2.4 final paragraph), P113 (Data Availability Statement), P114 (Acknowledgments)
    p57_old = "".join(paras[57].itertext())
    assert "All simulator trajectories, regression fits, quantile thresholds" in p57_old
    p57_new = (
        "OpenAI Codex served as the principal AI-assisted coding tool during development of the upstream "
        "boiler_pdm_sim simulation framework and its four-state saturated-steam auxiliary-boiler (ab4) physics "
        "backend under author-specified physical conservation laws, governing equations, and verification gates "
        "(including core/ab4 drum conservation, geometry, feedwater and steam line hydraulics, and enthalpy-based "
        "furnace modules, spline IAPWS-IF97 and flue-gas property layers in props/, closed-loop pipeline/step_loop.py "
        "wiring, and ab4 unit and integration test suites; local Codex CLI records verify 46 Boiler coding threads "
        "across versions 0.104.0\u20130.119.0-alpha.28 using gpt-5.3-codex-spark and gpt-5.4 plus migration session "
        "0.142.3 using gpt-5.5, upstream Git history records Phase A commits bb0c2d5\u20134fea464 through 2026-06-30 as the "
        "unpushed local base HEAD, and upstream PR_BODY.md carries a 2026-06-30 Claude Code summary footer, while "
        "per-session model logs for the separate-workstation 2026-06-30 commits and external R2 sessions are unverified "
        "in the local CLI database). The 24 paired six-hour simulation trajectories (259,224 timestamps) analyzed in "
        "this study were generated once during the original deterministic simulator execution preserved in the primary "
        "study archive (observable_baseline_study_20260915T215200Z_be142b32.zip, comprising source_copy/ with pilot "
        "and study patches applied over base 4fea4646..., analysis/, configs/, exogenous/, and runs/). The subsequent "
        "R2 reanalysis scripts (code/reproduce_analysis.py, code/verify_features.py, code/test_analysis.py, and "
        "code/make_figures_r2.py in PUB053_Manuscript_Package_R2.zip alongside data/observations/<episode>.npz, "
        "data/traces/<episode>.npz, data/block_design.json, data/original_configs/, and reference results/) did not "
        "generate new simulation trajectories or alter physical states; instead, they read the frozen observation "
        "projections and detector score traces to verify ordinary least-squares references, compute empirical quantile "
        "thresholds, verify sequential versus interval alarm timings, and render R2 analysis figures. In the public "
        "companion release (v1.0.1-pub053-r2), the verification scripts (code/_common.py, code/verify_features.py, "
        "code/reproduce_analysis.py, and code/make_figures_r2.py) implement Supplement S3 feature and EWMA "
        "reconstruction for full raw replay when the 48 external .npz files are supplied, fail with a nonzero exit "
        "code when those primary .npz files are omitted by default, and provide explicit --archived-tables-only and "
        "--archived-assets-only modes to inspect bundled R2 tables and preserved graphic assets on a standalone fresh "
        "clone without fabricating raw binary files. During preparation of this Full Paper manuscript and its public "
        "companion release repository, Google Antigravity agentic coding tools and deterministic Python scripts "
        "(build_full_paper.py, combine_normal_figs.py, create_automated_citation_docx.py, "
        "sync_citations_and_references.py, word_update_export_and_test.py, verify_revised_manuscript.py, "
        "verify_tables_from_archived_results.py, verify_citations_and_manuscript.py, check_cutoff_leads.py, "
        "check_delay_window.py, and independent_numeric_review.py) were used under direct author supervision for "
        "journal template conversion, figure compositing, four-operation structured Word citation synchronization "
        "(addition, movement, deletion, and first-citation reordering), and deterministic numerical cross-checking "
        "against the archived outputs, without generating new simulation trajectories or modifying any calibrated "
        "thresholds or episode statistics. The authors specified, inspected, and verified the physical model "
        "formulations, ab4 test suites, standalone verification runs, table and figure cross-checks, citation "
        "mappings, and scientific conclusions."
    )
    replace_paragraph_text(paras[57], None, p57_new)

    p113_old = "".join(paras[113].itertext())
    assert p113_old.startswith("Data Availability Statement:")
    p113_new_body = (
        "The reproducibility code, metadata, reconstructed inputs, reference tables, figures, bibliography mappings, "
        "and verification logs supporting this manuscript are publicly published in the dedicated companion GitHub "
        "repository https://github.com/CAPTW/pub053-jmse-boiler-leak-warning (release tag v1.0.1-pub053-r2, "
        "superseding initial release v1.0.0-pub053-r2 at commit 24bc7a06deaaec9a646e0e44930b356b755dc119 and prior "
        "fresh-clone verification baseline commit 31636c66bf664512795ce20ee886a0631de04a92; archival DOI unassigned "
        "prior to publication), with explicit provenance separation while keeping the upstream development repository "
        "CAPTW/boiler-pdm-sim private: (i) simulator_source/, containing the self-contained boiler_pdm_sim and ab4 "
        "physics snapshot extracted from local development base HEAD 4fea4646723f04db41583cb682bac8b62c44bc05 "
        "(five commits ahead of the private remote branch and intentionally not public at upstream HEAD, so public "
        "identification relies on this repository's commit and file-level SHA-256 hashes documented in "
        "docs/SOURCE_PROVENANCE.md alongside documented configuration differences relative to the patched study "
        "source_copy/); (ii) data/, code/, and results/, providing 24-episode metadata (episode_metadata.csv), "
        "block_design.json, original_configs/ab4_marine_aux.yaml, five reconstructed structured JSON inputs "
        "(data/reconstructed_inputs/), runnable verification and reproduction scripts (code/_common.py, "
        "code/test_analysis.py, code/verify_features.py, code/reproduce_analysis.py, and code/make_figures_r2.py, "
        "implementing Supplement S3 feature reconstruction and signed residual computation for full_raw_npz_replay when "
        "external .npz arrays are supplied, failing explicitly with nonzero exit status when primary .npz files are "
        "absent by default, and supporting explicit --archived-tables-only and --archived-assets-only verification "
        "of the bundled archived tables and graphic assets with five separate provenance buckets), and the 12 "
        "immutable R2 reference CSV/JSON outputs in results/ (including episode_results.csv, summary.csv, and "
        "normal_persistence.csv); (iii) results_archived/, mirroring the R2 reference files and reconstructed inputs "
        "(results_archived/reconstructed_inputs/), retaining historical QA logs scoped strictly to the earlier "
        "pre-revision submission draft PUB053_Manuscript_JMSE_Submission.docx (SHA-256 "
        "ce0e9a0e3c6c6332942d7ef99ae464832c3c3b57eaa0172130a220312103d4e5) in "
        "results_archived/prior_draft_review_ce0e9a0e/, and archiving fresh verification checks of the latest revised "
        "manuscript in results_archived/current_manuscript_verification/ (current_manuscript_table_checks.csv, "
        "current_docx_verification_report.json, and citation_editing_and_reordering_test_log.json); "
        "(iv) REPRODUCIBILITY.md at the repository root, figures/ (Figures 1\u20137, raw_source_assets/, and FIGURE_MAP.md), "
        "references/ (bibliography files and citation_mapping_table.csv), manuscript_verification/ (assembly, "
        "four-operation citation synchronization, table cross-check scripts, MANUSCRIPT_ARTIFACT_MAP.md, "
        "LATEST_MANUSCRIPT_VERIFICATION_REPORT.md, and R2 text archives in r2_text_archive/), and docs/ "
        "(REPRODUCTION_GUIDE.md, DATA_PROVENANCE.md, KNOWN_LIMITATIONS.md, SOURCE_PROVENANCE.md, AI_USAGE_AUDIT.md, "
        "FILE_MANIFEST synchronized via .gitattributes LF normalization, and execution_logs/ including fresh-clone "
        "reproduction logs); and (v) an external workstation boundary noting that the full raw binary archives\u2014"
        "observable_baseline_study_20260915T215200Z_be142b32.zip (containing the study-time patched source_copy/, "
        "analysis/, configs/, exogenous/, and runs/) and PUB053_Manuscript_Package_R2.zip (containing "
        "data/observations/<episode>.npz, data/traces/<episode>.npz, data/block_design.json, "
        "data/original_configs/<episode>_config_applied.json, R2 code/ scripts, and reference results/)\u2014remain on "
        "the study owner's external workstation outside GitHub (never fabricated) and are available from the "
        "corresponding author upon reasonable request (code components under MIT License; optional PyPI iapws GPL-3.0 "
        "dependency unbundled and MDPI JMSE manuscript/template files excluded per THIRD_PARTY_NOTICES.md). Figure 1 "
        "composites R2 Supplement Figures S2 and S3 (from E1_normal.npz); Figures 2, 4, and 5 correspond to R2 Main "
        "Figures 1, 2, and 3; and Figures 3, 6, and 7 correspond to R2 Supplement Figures S5, S1, and S4."
    )
    replace_paragraph_text(paras[113], "Data Availability Statement:", p113_new_body)

    p114_old = "".join(paras[114].itertext())
    assert p114_old.startswith("Acknowledgments:")
    p114_new_body = (
        "The authors acknowledge the use of the boiler_pdm_sim / ab4 saturated-steam auxiliary-boiler simulation "
        "architecture for generating the paired operating block trajectories analyzed in this study. During development "
        "of the upstream simulator codebase, OpenAI Codex served as the principal AI-assisted coding tool under author "
        "specification and supervision: local Codex CLI session records confirm CLI versions 0.104.0 through 0.142.3 "
        "and models gpt-5.3-codex-spark, gpt-5.4, and gpt-5.5 across Boiler framework and migration work, upstream "
        "repository history records Phase A commits bb0c2d5\u20134fea464 through 2026-06-30 (local base HEAD) implementing "
        "the core/ab4 four-state drum, geometry, hydraulics, and furnace modules, props/ spline IAPWS-IF97 and flue-gas "
        "modules, pipeline/step_loop.py closed-loop wiring, and ab4 test suites, and upstream PR_BODY.md carries a "
        "2026-06-30 Claude Code summary footer (per-session model logs for the separate-workstation 2026-06-30 commits "
        "and external R2 sessions are not stored in the local CLI database). Subsequently, during preparation of this "
        "Full Paper manuscript and its dedicated public companion repository "
        "(https://github.com/CAPTW/pub053-jmse-boiler-leak-warning), the Google Antigravity agentic coding environment "
        "and deterministic Python scripts (build_full_paper.py, combine_normal_figs.py, "
        "create_automated_citation_docx.py, sync_citations_and_references.py, word_update_export_and_test.py, "
        "verify_revised_manuscript.py, verify_tables_from_archived_results.py, verify_citations_and_manuscript.py, "
        "check_cutoff_leads.py, check_delay_window.py, and independent_numeric_review.py) assisted under author "
        "supervision with JMSE template conversion, figure compositing, structured Word citation linking, and automated "
        "table and citation verification without generating new boiler simulation trajectories or modifying archived "
        "numerical results. The authors specified the governing equations, fault scenarios, and detector policies, "
        "executed and inspected verification runs across the ab4 unit and pipeline tests, fresh-clone reproduction "
        "checks, four-operation Word citation editing and reordering tests, and manuscript table cross-checks, and "
        "take full responsibility for the content of the publication."
    )
    replace_paragraph_text(paras[114], "Acknowledgments:", p114_new_body)

    # 4. Serialize modified document.xml & embed word_sources.xml into customXml/item1.xml
    entries["word/document.xml"] = etree.tostring(doc_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with open(WORD_SOURCES_XML, "rb") as f:
        entries["customXml/item1.xml"] = f.read()

    # Enable updateFields in word/settings.xml if not present so Word auto-updates fields on open
    settings_root = etree.fromstring(entries["word/settings.xml"], parser)
    if settings_root.find(wtag("updateFields")) is None:
        uf = etree.Element(wtag("updateFields"))
        uf.set(wtag("val"), "true")
        settings_root.insert(0, uf)
        entries["word/settings.xml"] = etree.tostring(settings_root, xml_declaration=True, encoding="UTF-8", standalone=True)

    with zipfile.ZipFile(DST_DOCX, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in entries.items():
            zout.writestr(name, data)

    post_src_sha = hashlib.sha256(open(SRC_DOCX, "rb").read()).hexdigest()
    assert post_src_sha == EXPECTED_SRC_SHA256
    dst_sha = hashlib.sha256(open(DST_DOCX, "rb").read()).hexdigest()
    print(f"Created revised DOCX: {DST_DOCX}")
    print(
        f"  SDT citation controls: {total_groups} ({total_expanded} expanded member IDs), "
        f"Live REF fields inserted: {total_fields}"
    )
    print(f"  Bookmarks added: Ref01..Ref27")
    print(f"  Source DOCX SHA-256 unchanged: {post_src_sha}")
    print(f"  Revised DOCX SHA-256: {dst_sha}")


if __name__ == "__main__":
    main()
