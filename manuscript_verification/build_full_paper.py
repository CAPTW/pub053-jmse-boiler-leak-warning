# -*- coding: utf-8 -*-
import os
import re
import copy
import shutil
import docx
from docx.shared import Inches, Pt
from docx.oxml import parse_xml
from docx.oxml.ns import qn, nsdecls
from PIL import Image

TEMPLATE_DOCX = r"manuscript_verification\jmse-template-converted.docx"
OUT_WORK_DOCX = r"manuscript_verification\PUB053_Manuscript_JMSE_Submission.docx"
OUT_WORK_PDF  = r"manuscript_verification\PUB053_Manuscript_JMSE_Submission.pdf"

DRIVE_DIR      = r"."
OUT_DRIVE_DOCX = os.path.join(DRIVE_DIR, "PUB053_Manuscript_JMSE_Submission.docx")
OUT_DRIVE_PDF  = os.path.join(DRIVE_DIR, "PUB053_Manuscript_JMSE_Submission.pdf")

MEDIA_DIR = r"figures"
SUPP_DIR  = r"figures/raw_source_assets"

def ensure_padded_fig2():
    src = os.path.join(MEDIA_DIR, "rId27.png")
    dst = os.path.join(MEDIA_DIR, "rId27_padded.png")
    im = Image.open(src).convert("RGB")
    w, h = im.size
    pad_bottom = 32
    new_im = Image.new("RGB", (w, h + pad_bottom), (255, 255, 255))
    new_im.paste(im, (0, 0))
    new_im.save(dst, format="PNG")
    return dst

FIG1_PATH = os.path.join(MEDIA_DIR, "fig_e1_normal.png")       # E1 normal pressure & level (from Figs S2 & S3)
FIG2_PATH = ensure_padded_fig2()                               # E1 fault pressure, level, feedwater command (Main Fig 1, padded)
FIG3_PATH = os.path.join(SUPP_DIR,  "page1_img5_475.jpeg")     # E1 fault feedwater & steam flows (Fig S5)
FIG4_PATH = os.path.join(MEDIA_DIR, "rId31.png")               # Blockwise post-onset alarm delay (Main Fig 2)
FIG5_PATH = os.path.join(MEDIA_DIR, "rId34.png")               # E1 normalized scores (Main Fig 3)
FIG6_PATH = os.path.join(SUPP_DIR,  "page1_img1_1103.jpeg")    # Cross-block event/trip/domain timeline (Fig S1)
FIG7_PATH = os.path.join(SUPP_DIR,  "page1_img2_1217.jpeg")    # Normal exceedance persistence spans (Fig S4)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

# ---------------------------------------------------------------------------
# OMML Math Builder Helpers
# ---------------------------------------------------------------------------
def m_r(text, plain=False):
    # Put <m:nor/><m:sty m:val="p"/> on alphabetic text tokens so both Word and LibreOffice
    # StarMath treat multi-letter identifiers (e.g. "bar", "max", "sat") as literal upright text
    # rather than StarMath accent/operator keywords, while keeping numbers/operators as pure math runs.
    has_alpha = any(c.isalpha() for c in text)
    rpr = '<m:rPr><m:nor/><m:sty m:val="p"/></m:rPr>' if (plain and has_alpha) else ''
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<m:r>{rpr}<m:t>{esc}</m:t></m:r>'

def m_sub(base_xml, sub_xml):
    return f'<m:sSub><m:e>{base_xml}</m:e><m:sub>{sub_xml}</m:sub></m:sSub>'

def m_sup(base_xml, sup_xml):
    return f'<m:sSup><m:e>{base_xml}</m:e><m:sup>{sup_xml}</m:sup></m:sSup>'

def m_subsup(base_xml, sub_xml, sup_xml):
    return f'<m:sSubSup><m:e>{base_xml}</m:e><m:sub>{sub_xml}</m:sub><m:sup>{sup_xml}</m:sup></m:sSubSup>'

def m_frac(num_xml, den_xml):
    return f'<m:f><m:num>{num_xml}</m:num><m:den>{den_xml}</m:den></m:f>'

def m_sqrt(expr_xml):
    return f'<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>{expr_xml}</m:e></m:rad>'

def m_acc(base_xml, chr_val="\u0307"):
    return f'<m:acc><m:accPr><m:chr m:val="{chr_val}"/></m:accPr><m:e>{base_xml}</m:e></m:acc>'

def m_delim(inner_xml, beg="(", end=")"):
    return f'<m:d><m:dPr><m:begChr m:val="{beg}"/><m:endChr m:val="{end}"/></m:dPr><m:e>{inner_xml}</m:e></m:d>'

def m_matrix(rows_xml_list, beg="[", end="]"):
    rows_str = "".join(
        "<m:mr>" + "".join(f"<m:e>{col}</m:e>" for col in row) + "</m:mr>"
        for row in rows_xml_list
    )
    return f'<m:d><m:dPr><m:begChr m:val="{beg}"/><m:endChr m:val="{end}"/></m:dPr><m:e><m:m>{rows_str}</m:m></m:e></m:d>'

def m_int(sub_xml, sup_xml, body_xml):
    return (
        f'<m:nary><m:naryPr><m:chr m:val="\u222b"/><m:limLoc m:val="subSup"/></m:naryPr>'
        f'<m:sub>{sub_xml}</m:sub><m:sup>{sup_xml}</m:sup><m:e>{body_xml}</m:e></m:nary>'
    )

def make_omath(inner_xml):
    xml_str = f'<m:oMath xmlns:m="{M_NS}" xmlns:w="{W_NS}">{inner_xml}</m:oMath>'
    return parse_xml(xml_str)

# Pre-built inline OMML tokens for accented variables so Palatino Linotype never shifts combining marks
INLINE_MATH_MAP = {
    "Mhat":      m_acc(m_r("M"), "\u0302"),
    "Mhat(t)":   m_acc(m_r("M"), "\u0302") + m_delim(m_r("t")),
    "dMhat(t)":  m_r("\u0394", plain=True) + m_acc(m_r("M"), "\u0302") + m_delim(m_r("t")),
    "Mhat_diff": m_r("\u0394", plain=True) + m_acc(m_r("M"), "\u0302") + m_delim(m_r("t")) + m_r("=", plain=True) + m_acc(m_r("M"), "\u0302") + m_delim(m_r("t")) + m_r("\u2212", plain=True) + m_acc(m_r("M"), "\u0302") + m_delim(m_r("t") + m_r("\u2212", plain=True) + m_r("W")),
    "qbar_s":    m_sub(m_acc(m_r("q"), "\u0304"), m_r("s")),
    "qbar_s(t)": m_sub(m_acc(m_r("q"), "\u0304"), m_r("s")) + m_delim(m_r("t")),
    "lbar_d":    m_sub(m_acc(m_r("l"), "\u0304"), m_r("d")),
    "lbar_d(t)": m_sub(m_acc(m_r("l"), "\u0304"), m_r("d")) + m_delim(m_r("t")),
    "ubar_f":    m_sub(m_acc(m_r("u"), "\u0304"), m_r("f")),
    "ubar_f(t)": m_sub(m_acc(m_r("u"), "\u0304"), m_r("f")) + m_delim(m_r("t")),
}


# ---------------------------------------------------------------------------
# Document Construction Helpers
# ---------------------------------------------------------------------------
class PaperBuilder:
    def __init__(self, doc, sectPr, eq_table_proto):
        self.doc = doc
        self.sectPr = sectPr
        self.eq_table_proto = eq_table_proto

    def add_p(self, style_name, text="", keep_with_next=False, space_before=None, space_after=None, bold_default=False):
        p = self.doc.add_paragraph(style=style_name)
        if text:
            self.append_formatted_runs(p, text, bold_state=bold_default)
        if keep_with_next:
            p.paragraph_format.keep_with_next = True
        if space_before is not None:
            p.paragraph_format.space_before = Pt(space_before)
        if space_after is not None:
            p.paragraph_format.space_after = Pt(space_after)
        self.sectPr.addprevious(p._p)
        return p

    def append_formatted_runs(self, p, text, bold_state=False, italic_state=False):
        """
        Recursive inline formatter supporting:
        - **bold** (can contain *italic*, _{sub}, ^{sup}, {{math:...}})
        - *italic* (can contain _{sub}, ^{sup})
        - _{sub}
        - ^{sup}
        - {{math:KEY}} -> inline OMML equation from INLINE_MATH_MAP
        """
        i = 0
        n = len(text)
        while i < n:
            if text.startswith("{{math:", i):
                end = text.find("}}", i + 7)
                if end != -1:
                    key = text[i + 7:end]
                    if key in INLINE_MATH_MAP:
                        p._p.append(make_omath(INLINE_MATH_MAP[key]))
                    i = end + 2
                    continue
            if text.startswith("**", i):
                end = text.find("**", i + 2)
                if end != -1:
                    self.append_formatted_runs(p, text[i + 2:end], bold_state=True, italic_state=italic_state)
                    i = end + 2
                    continue
            if text.startswith("*", i):
                end = text.find("*", i + 1)
                if end != -1:
                    self.append_formatted_runs(p, text[i + 1:end], bold_state=bold_state, italic_state=True)
                    i = end + 1
                    continue
            if text.startswith("_{", i):
                end = text.find("}", i + 2)
                if end != -1:
                    sub_txt = text[i + 2:end]
                    if sub_txt.startswith("*") and sub_txt.endswith("*") and len(sub_txt) > 2:
                        r = p.add_run(sub_txt[1:-1])
                        r.italic = True
                    else:
                        r = p.add_run(sub_txt)
                        r.italic = italic_state
                    r.bold = bold_state
                    r.font.subscript = True
                    i = end + 1
                    continue
            if text.startswith("^{", i):
                end = text.find("}", i + 2)
                if end != -1:
                    sup_txt = text[i + 2:end]
                    r = p.add_run(sup_txt)
                    r.bold = bold_state
                    r.italic = italic_state
                    r.font.superscript = True
                    i = end + 1
                    continue

            next_pos = n
            for tok in ("{{math:", "**", "*", "_{", "^{"):
                pos = text.find(tok, i)
                if pos != -1 and pos < next_pos:
                    next_pos = pos
            if next_pos == i:
                r = p.add_run(text[i])
                r.bold = bold_state
                r.italic = italic_state
                i += 1
            else:
                r = p.add_run(text[i:next_pos])
                r.bold = bold_state
                r.italic = italic_state
                i = next_pos

    def add_equation(self, omath_inner_xml, eq_num_str, keep_with_next=False):
        tbl_el = copy.deepcopy(self.eq_table_proto)
        for bidi_el in tbl_el.xpath(".//w:bidi") + tbl_el.xpath(".//w:bidiVisual"):
            bidi_el.getparent().remove(bidi_el)
        tbl = docx.table.Table(tbl_el, self.doc)
        row_trPr = tbl.rows[0]._tr.get_or_add_trPr()
        row_trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
        c0 = tbl.rows[0].cells[0]
        c1 = tbl.rows[0].cells[1]
        p0 = c0.paragraphs[0]
        p0.text = ""
        p0.style = "MDPI_3.9_equation"
        p0.paragraph_format.keep_together = True
        if keep_with_next:
            p0.paragraph_format.keep_with_next = True
        p0._p.append(make_omath(omath_inner_xml))
        p1 = c1.paragraphs[0]
        p1.text = eq_num_str
        p1.style = "MDPI_3.a_equation_number"
        p1.paragraph_format.keep_together = True
        if keep_with_next:
            p1.paragraph_format.keep_with_next = True
        self.sectPr.addprevious(tbl_el)
        return tbl

    def add_three_line_table(self, caption_text, col_widths_dxa, headers, rows_data, footer_text=None, align_cols=None, bold_rows=None):
        """
        Creates a clean MDPI three-line table (total width 7857 dxa, indent 2608 dxa)
        with non-breaking caption and repeating header row.
        """
        p_cap = self.add_p("MDPI_4.1_table_caption", caption_text, keep_with_next=True)
        p_cap.paragraph_format.keep_together = True

        num_rows = 1 + len(rows_data)
        num_cols = len(headers)
        tbl = self.doc.add_table(rows=num_rows, cols=num_cols)
        tblPr = tbl._tbl.tblPr
        for tag in ("w:tblW", "w:tblInd", "w:tblBorders", "w:tblLayout", "w:tblCellMar", "w:bidiVisual"):
            old = tblPr.find(qn(tag))
            if old is not None:
                tblPr.remove(old)

        total_w = sum(col_widths_dxa)
        tblPr.append(parse_xml(f'<w:tblW {nsdecls("w")} w:w="{total_w}" w:type="dxa"/>'))
        tblPr.append(parse_xml(f'<w:tblInd {nsdecls("w")} w:w="2608" w:type="dxa"/>'))
        tblPr.append(parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            f'<w:top w:val="single" w:sz="8" w:space="0" w:color="000000"/>'
            f'<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            f'<w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/>'
            f'<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            f'<w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            f'<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            f'</w:tblBorders>'
        ))
        tblPr.append(parse_xml(f'<w:tblLayout {nsdecls("w")} w:type="fixed"/>'))
        tblPr.append(parse_xml(
            f'<w:tblCellMar {nsdecls("w")}>'
            f'<w:top w:w="45" w:type="dxa"/>'
            f'<w:left w:w="25" w:type="dxa"/>'
            f'<w:bottom w:w="45" w:type="dxa"/>'
            f'<w:right w:w="25" w:type="dxa"/>'
            f'</w:tblCellMar>'
        ))

        old_grid = tbl._tbl.find(qn("w:tblGrid"))
        if old_grid is not None:
            tbl._tbl.remove(old_grid)
        grid_xml = f'<w:tblGrid {nsdecls("w")}>' + "".join(
            f'<w:gridCol w:w="{w}"/>' for w in col_widths_dxa
        ) + '</w:tblGrid>'
        tblPr.addnext(parse_xml(grid_xml))

        # Populate header row
        hdr_row = tbl.rows[0]
        trPr = hdr_row._tr.get_or_add_trPr()
        trPr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))
        trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
        for c_idx, h_text in enumerate(headers):
            cell = hdr_row.cells[c_idx]
            tcPr = cell._tc.get_or_add_tcPr()
            old_tcw = tcPr.find(qn("w:tcW"))
            if old_tcw is not None:
                tcPr.remove(old_tcw)
            tcPr.append(parse_xml(f'<w:tcW {nsdecls("w")} w:w="{col_widths_dxa[c_idx]}" w:type="dxa"/>'))
            tcPr.append(parse_xml(f'<w:vAlign {nsdecls("w")} w:val="center"/>'))
            tcPr.append(parse_xml(
                f'<w:tcBorders {nsdecls("w")}>'
                f'<w:top w:val="single" w:sz="8" w:space="0" w:color="000000"/>'
                f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                f'</w:tcBorders>'
            ))
            p = cell.paragraphs[0]
            p.style = "MDPI_4.2_table_body"
            p._p.get_or_add_pPr().append(parse_xml(f'<w:suppressAutoHyphens {nsdecls("w")}/>'))
            p.paragraph_format.keep_with_next = True
            if align_cols and c_idx < len(align_cols):
                p.alignment = align_cols[c_idx]
            self.append_formatted_runs(p, h_text, bold_state=True)

        # Populate data rows
        bold_row_set = set(bold_rows or [])
        for r_idx, r_data in enumerate(rows_data):
            row = tbl.rows[r_idx + 1]
            r_trPr = row._tr.get_or_add_trPr()
            r_trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
            is_last = (r_idx == len(rows_data) - 1)
            row_is_bold = (r_idx in bold_row_set)
            for c_idx, val_text in enumerate(r_data):
                cell = row.cells[c_idx]
                tcPr = cell._tc.get_or_add_tcPr()
                old_tcw = tcPr.find(qn("w:tcW"))
                if old_tcw is not None:
                    tcPr.remove(old_tcw)
                tcPr.append(parse_xml(f'<w:tcW {nsdecls("w")} w:w="{col_widths_dxa[c_idx]}" w:type="dxa"/>'))
                tcPr.append(parse_xml(f'<w:vAlign {nsdecls("w")} w:val="center"/>'))
                if is_last:
                    tcPr.append(parse_xml(
                        f'<w:tcBorders {nsdecls("w")}>'
                        f'<w:bottom w:val="single" w:sz="8" w:space="0" w:color="000000"/>'
                        f'</w:tcBorders>'
                    ))
                p = cell.paragraphs[0]
                p.style = "MDPI_4.2_table_body"
                p._p.get_or_add_pPr().append(parse_xml(f'<w:suppressAutoHyphens {nsdecls("w")}/>'))
                if is_last and footer_text:
                    p.paragraph_format.keep_with_next = True
                if align_cols and c_idx < len(align_cols):
                    p.alignment = align_cols[c_idx]
                self.append_formatted_runs(p, val_text, bold_state=row_is_bold)

        self.sectPr.addprevious(tbl._tbl)

        if footer_text:
            self.add_p("MDPI_4.3_table_footer", footer_text, space_after=6)

        return tbl

    def add_abbreviations_table(self, rows_data):
        tbl = self.doc.add_table(rows=len(rows_data), cols=2)
        tblPr = tbl._tbl.tblPr
        for tag in ("w:tblW", "w:tblInd", "w:tblBorders", "w:tblLayout", "w:tblCellMar", "w:bidiVisual"):
            old = tblPr.find(qn(tag))
            if old is not None:
                tblPr.remove(old)
        tblPr.append(parse_xml(f'<w:tblW {nsdecls("w")} w:w="7857" w:type="dxa"/>'))
        tblPr.append(parse_xml(f'<w:tblInd {nsdecls("w")} w:w="2608" w:type="dxa"/>'))
        tblPr.append(parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            f'<w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            f'<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            f'<w:bottom w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            f'<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            f'<w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            f'<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            f'</w:tblBorders>'
        ))
        tblPr.append(parse_xml(f'<w:tblLayout {nsdecls("w")} w:type="fixed"/>'))
        tblPr.append(parse_xml(
            f'<w:tblCellMar {nsdecls("w")}>'
            f'<w:top w:w="30" w:type="dxa"/>'
            f'<w:left w:w="0" w:type="dxa"/>'
            f'<w:bottom w:w="30" w:type="dxa"/>'
            f'<w:right w:w="80" w:type="dxa"/>'
            f'</w:tblCellMar>'
        ))
        old_grid = tbl._tbl.find(qn("w:tblGrid"))
        if old_grid is not None:
            tbl._tbl.remove(old_grid)
        tblPr.addnext(parse_xml(
            f'<w:tblGrid {nsdecls("w")}><w:gridCol w:w="1450"/><w:gridCol w:w="6407"/></w:tblGrid>'
        ))
        widths = [1450, 6407]
        for r_idx, (abbr, full_name) in enumerate(rows_data):
            row = tbl.rows[r_idx]
            r_trPr = row._tr.get_or_add_trPr()
            r_trPr.append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
            is_last_row = (r_idx == len(rows_data) - 1)
            for c_idx, txt in enumerate((abbr, full_name)):
                cell = row.cells[c_idx]
                tcPr = cell._tc.get_or_add_tcPr()
                old_tcw = tcPr.find(qn("w:tcW"))
                if old_tcw is not None:
                    tcPr.remove(old_tcw)
                tcPr.append(parse_xml(f'<w:tcW {nsdecls("w")} w:w="{widths[c_idx]}" w:type="dxa"/>'))
                tcPr.append(parse_xml(f'<w:vAlign {nsdecls("w")} w:val="center"/>'))
                p = cell.paragraphs[0]
                p.style = "MDPI_4.2_table_body"
                p.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.LEFT
                p.paragraph_format.keep_together = True
                if not is_last_row:
                    p.paragraph_format.keep_with_next = True
                self.append_formatted_runs(p, txt)
        self.sectPr.addprevious(tbl._tbl)
        return tbl

    def add_figure(self, img_path, caption_text, width_inches=5.15):
        p_fig = self.doc.add_paragraph(style="MDPI_5.2_figure")
        p_fig.paragraph_format.keep_with_next = True
        p_fig.paragraph_format.keep_together = True
        p_fig.paragraph_format.line_spacing_rule = docx.enum.text.WD_LINE_SPACING.SINGLE
        p_fig.paragraph_format.space_before = Pt(8)
        p_fig.paragraph_format.space_after = Pt(4)
        r = p_fig.add_run()
        r.add_picture(img_path, width=Inches(width_inches))
        self.sectPr.addprevious(p_fig._p)
        p_cap = self.add_p("MDPI_5.1_figure_caption", caption_text, space_after=8)
        p_cap.paragraph_format.keep_together = True


# ---------------------------------------------------------------------------
# Main Manuscript Generation Routine
# ---------------------------------------------------------------------------
def build_manuscript():
    doc = docx.Document(TEMPLATE_DOCX)
    L = docx.enum.text.WD_ALIGN_PARAGRAPH.LEFT
    C = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
    R = docx.enum.text.WD_ALIGN_PARAGRAPH.RIGHT

    # 0. Remove all <w:bidi/> and <w:bidiVisual/> tags across document and styles (F13)
    for el in list(doc.element.xpath(".//w:bidi")) + list(doc.element.xpath(".//w:bidiVisual")):
        el.getparent().remove(el)
    for el in list(doc.styles.element.xpath(".//w:bidi")) + list(doc.styles.element.xpath(".//w:bidiVisual")):
        el.getparent().remove(el)

    # 1. Fix Header and Footer runs ('2025' -> '2026', ' 13' -> ' 14')
    for sec in doc.sections:
        for hf in (sec.header, sec.first_page_header, sec.footer, sec.first_page_footer):
            for p in hf.paragraphs:
                for el in list(p._p.xpath(".//w:bidi")):
                    el.getparent().remove(el)
                for r in p.runs:
                    if r.text == "2025":
                        r.text = "2026"
                    elif r.text == " 13":
                        r.text = " 14"
                    elif "2025, 13" in r.text:
                        r.text = r.text.replace("2025, 13", "2026, 14")

    # Update '2025' -> '2026' in Table 0 (Left sidebar Academic Editor / Copyright box)
    # and prevent 2410+198=2608 twip collision with body left indent and bottom-margin overflow in LibreOffice (F13)
    if doc.tables:
        t0 = doc.tables[0]
        t0_tblPr = t0._tbl.tblPr
        if t0_tblPr is not None:
            tblpPr = t0_tblPr.find(qn("w:tblpPr"))
            if tblpPr is not None:
                tblpPr.set(qn("w:rightFromText"), "120")
                tblpPr.set(qn("w:leftFromText"), "120")
                tblpPr.set(qn("w:tblpY"), "9800")
            tblW = t0_tblPr.find(qn("w:tblW"))
            if tblW is not None:
                tblW.set(qn("w:w"), "2350")
        for row in t0.rows:
            row._tr.get_or_add_trPr().append(parse_xml(f'<w:cantSplit {nsdecls("w")}/>'))
            for cell in row.cells:
                tcPr = cell._tc.find(qn("w:tcPr"))
                if tcPr is not None:
                    tcW = tcPr.find(qn("w:tcW"))
                    if tcW is not None:
                        tcW.set(qn("w:w"), "2350")
                for p in cell.paragraphs:
                    for r in p.runs:
                        if "2025" in r.text:
                            r.text = r.text.replace("2025", "2026")

    # Save a deep copy of Table 4 (the MDPI 2-col equation container) before clearing body
    eq_table_proto = copy.deepcopy(doc.tables[4]._tbl)

    # 2. Populate Front Matter in template paragraphs
    p_art = doc.paragraphs[0]
    p_art.text = "Article"

    p_title = doc.paragraphs[1]
    p_title.text = "Feedwater-Demand Residuals for Early Tube-Leak Warning in a Closed-Loop Auxiliary-Boiler Simulation"

    # P6 in jmse-template-converted.docx is an extra standalone "Abstract" heading; remove it
    p_extra_abs = doc.paragraphs[6]._p
    p_abs = doc.paragraphs[7]
    p_abs.text = ""
    r_ab_lbl = p_abs.add_run("Abstract: ")
    r_ab_lbl.bold = True
    abstract_body = (
        "Closed-loop regulation can keep boiler drum pressure and water level near setpoints during an incipient tube leak by increasing firing and feedwater replenishment. "
        "This simulation study compares confirmed early-warning times of a state-deviation baseline, a drum-only mass-balance flow residual, a feedwater-command demand residual, and their composite maximum score in a four-state saturated-steam auxiliary-boiler model under three-element cascade control. "
        "Across twelve six-hour paired blocks, four development-normal episodes supplied ordinary least-squares references, scales, and quantile thresholds under a 600 s persistence rule, and eight blocks provided evaluation trajectories. "
        "Every detector confirmed a post-onset alarm in all eight evaluation leaks (8/8) and preceded functional-degradation start in all seven uncensored events (7/7; one censored at 6 h). "
        "Median post-onset delay fell from 127.3 min (state baseline) to 86.4 min (flow alone) and 75.9 min (demand alone and combined; 51.3 min reduction), with median strict leads of 34.7, 48.9, and 59.0 min. "
        "Demand alone matched the combined first alarm in seven blocks (8 s later in one), while flow alone confirmed earlier in two lower-load blocks. "
        "Over 45.33 h of normal monitoring, only the state baseline issued a false alarm. "
        "Results support a bounded detector comparison, not intrinsic sensor superiority or field validation."
    )
    assert len(abstract_body.split()) <= 198, f"Abstract too long: {len(abstract_body.split())} words"
    p_abs.add_run(abstract_body)

    p_kw = doc.paragraphs[8]
    p_kw.text = ""
    r_kw_lbl = p_kw.add_run("Keywords: ")
    r_kw_lbl.bold = True
    p_kw.add_run(
        "marine auxiliary boiler; tube-leak monitoring; closed-loop simulation; feedwater control demand; residual-based fault detection; component attribution; functional degradation endpoint"
    )

    # Remove all body elements after P9 (the horizontal line after Keywords), preserving sectPr
    body_el = doc._body._element
    sectPr = body_el.find(qn("w:sectPr"))
    line_p_el = doc.paragraphs[9]._p
    if p_extra_abs.getparent() is body_el:
        body_el.remove(p_extra_abs)
    removing = False
    for child in list(body_el):
        if child is line_p_el:
            removing = True
            continue
        if removing and child is not sectPr:
            body_el.remove(child)

    pb = PaperBuilder(doc, sectPr, eq_table_proto)

    # =========================================================================
    # SECTION 1. INTRODUCTION
    # =========================================================================
    pb.add_p("MDPI_2.1_heading1", "1. Introduction", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "Auxiliary steam boilers are essential service units aboard commercial seagoing vessels, supplying saturated steam for fuel heating, cargo and tank heating, fresh-water generation, and machinery-space services [1,2], alongside broader steam-plant heat exchangers and auxiliary power loops [3,4]. In marine drum-boiler operation, incipient waterwall or riser tube leakage withdraws pressurized saturated liquid and liquid enthalpy from the natural-circulation loop; if uncompensated or allowed to progress until feedwater replenishment capacity is exhausted, the resulting inventory loss leads to water-level depression and pressure-part overheating hazards that motivate early fault warning [2,5–8]."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "Early detection of boiler tube leakage from standard process instrumentation is complicated by two-phase drum-riser-downcomer thermohydraulics and active closed-loop feedback control [5–8]. Physical drum boilers exhibit pronounced non-minimum-phase shrink-and-swell behavior driven by subsurface steam void dynamics, thermal capacitance in the drum and riser metal, and natural circulation coupling [5,6]. To stabilize operation under fluctuating shipboard or industrial steam loads, drum boilers employ pressure proportional–integral (PI) controllers acting on fuel firing rate together with three-element cascade controllers that regulate apparent drum water level by trimming feedwater flow relative to measured steam output [6–8]. From a fault-diagnosis perspective, this regulatory architecture creates a classic closed-loop fault-masking effect [9–14]: as a leak begins to drain liquid inventory and saturated-liquid enthalpy, the pressure controller increases firing request and the level/flow cascade increases feedwater valve command to maintain regulated drum pressure and apparent water level near their setpoints. Consequently, univariate alarms on regulated state variables may remain silent until the leak rate approaches the available feedwater actuator or inventory margin [13,14]."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "A substantial literature has examined boiler leak detection across hardware-based, model-based, and data-driven paradigms. Hardware-focused approaches include radiation-heat-flux-based expert systems [15] and four-element acoustic arrays for hyperbolic leak localization [16]; however, these methods require dedicated furnace or acoustic instrumentation outside the standard pressure, level, and flow control loop examined in this study. Using standard plant measurements, Sun et al. [17,18] formulated a steam-drum mass balance and applied forgetting-factor least-squares parameter estimation to feedwater flow residuals to detect leaks in boiler steam-water systems. To mitigate false alarms induced by nonstationary load changes, Sun et al. [19] subsequently introduced a dynamic principal component analysis (PCA) monitoring scheme. Yu et al. [20] applied multivariate PCA with exponentially weighted moving average (EWMA) filtering to thermal power plant boiler records and explicitly noted that small tube leaks are initially accommodated by increased make-up and feedwater flow margin before large drum-level excursions emerge. More recently, Swiercz and Mroczkowska [21] evaluated multiway PCA on boiler pipeline leak case studies, Indrawan et al. [22] evaluated multivariate data-analytic techniques—including PCA, canonical variate analysis (CVA), and Fisher discriminant analysis (FDA)—on a 650 MW subcritical boiler, Panday et al. [23] developed feedwater-to-steam flow-ratio monitoring with optimal exponential filtering and variable thresholds, and Widodo et al. [24] investigated support vector machine (SVM) and random forest anomaly detection alongside dynamic time warping (DTW) remaining useful life (RUL) estimation across three power-plant boilers."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "That feedwater replenishment effort carries diagnostic information during a closed-loop boiler leak is therefore well established in prior plant studies [17,20,22,23]. However, when an anomaly detector combines an approximate drum mass-balance residual with a feedwater control-demand residual under a sustained confirmation persistence requirement, a narrower methodological question arises: how much confirmed warning lead time do the specified residual pipelines gain over a smoothed pressure/level baseline, and which underlying component—the flow-imbalance residual or the feedwater-demand residual—governs the combined detector's first confirmed warning? Answering this question requires isolating component-level alarm timing under identical development-normal threshold calibration and persistence rules while explicitly accounting for normal-operation false alarms, horizon censoring, and the relationship between the detector signals and the defined functional degradation endpoint."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "This article addresses that question through a controlled numerical investigation using a four-state saturated-steam auxiliary-boiler simulation (ab4) inspired by the physical formulation of Åström and Bell [6]. Rather than proposing a universal fault-classification architecture, replicating the plant validations of [20,22–24], or claiming field-validated prognostic accuracy, this study provides a transparent episode-level comparison across 12 paired normal and fault operating blocks (four development blocks and eight evaluation blocks, comprising 24 six-hour episodes and 259,224 correlated time-series samples at 2 s resolution). Specifically, the contributions of this work are threefold: (i) we document the implemented four-state plant dynamics, pressure-dependent line hydraulics, three-element cascade control loop, protection policy, and four causal monitoring pipelines (State (B0), Flow only, Demand only, and Combined (B1)); (ii) we quantify both exogenous post-onset detection delays and strict lead times prior to a retrospective functional degradation criterion across the eight evaluation blocks; and (iii) we perform a post-hoc component attribution and threshold-persistence analysis that explains why the composite score's upper development-normal tail coincides with the demand component while identifying lower-load scenarios where separately calibrated flow residuals confirm earlier."
    )

    # =========================================================================
    # SECTION 2. MATERIALS AND METHODS
    # =========================================================================
    pb.add_p("MDPI_2.1_heading1", "2. Materials and Methods", keep_with_next=True)
    pb.add_p("MDPI_2.2_heading2", "2.1. Auxiliary-Boiler Plant Model and Physical Leak Coupling", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "The simulation experiments were conducted using the four-state saturated-steam auxiliary-boiler backend (ab4), whose physical structure adapts the nonlinear drum-boiler conservation framework of Åström and Bell [6] to an MGO-fired auxiliary water-tube drum boiler operating at a nominal absolute pressure of 7 bar. Validation of the published Åström–Bell power-boiler model [6] does not transfer automatically to this reduced auxiliary-boiler implementation. The continuous-time plant state vector is *x* = (*p*, *V*_{w}, *α*_{r}, *V*_{sd}), where *p* is absolute drum steam pressure (evaluated in Pa internally and reported in bar), *V*_{w} is total liquid water volume across the drum, downcomer, and risers (m^{3}), *α*_{r} is the riser-exit steam mass quality (dimensionless), and *V*_{sd} is the volume of subsurface steam bubbles entrained below the liquid level in the drum (m^{3})."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "Let *V*_{T} = *V*_{d} + *V*_{r} + *V*_{dc} denote the total pressurized water-steam volume of the drum (*V*_{d}), risers (*V*_{r}), and downcomer (*V*_{dc}), so that total vapor volume is *V*_{s} = *V*_{T} − *V*_{w}. Saturated liquid and vapor densities (*ρ*_{w}, *ρ*_{s}), specific enthalpies (*h*_{w}, *h*_{s}), latent heat of vaporization (*h*_{fg} = *h*_{s} − *h*_{w}), and saturation temperature *T*_{sat}(*p*) are evaluated along the saturation curve using the International Association for the Properties of Water and Steam Industrial Formulation 1997 (IAPWS-IF97) [25,26]. The global stored fluid mass *M* and total internal energy *U* (including the lumped thermal capacitance *C*_{m} of the pressure-part metal in thermal equilibrium at *T*_{sat}) are expressed as:",
        keep_with_next=True
    )

    # Eq (1a) & (1b)
    eq1a_xml = (
        m_r("M") + m_r("=", plain=True)
        + m_sub(m_r("ρ"), m_r("w")) + m_sub(m_r("V"), m_r("w"))
        + m_r("+", plain=True)
        + m_sub(m_r("ρ"), m_r("s")) + m_sub(m_r("V"), m_r("s"))
        + m_r(",", plain=True)
    )
    pb.add_equation(eq1a_xml, "(1a)")

    eq1b_xml = (
        m_r("U") + m_r("=", plain=True)
        + m_sub(m_r("ρ"), m_r("w")) + m_sub(m_r("h"), m_r("w")) + m_sub(m_r("V"), m_r("w"))
        + m_r("+", plain=True)
        + m_sub(m_r("ρ"), m_r("s")) + m_sub(m_r("h"), m_r("s")) + m_sub(m_r("V"), m_r("s"))
        + m_r("\u2212", plain=True)
        + m_r("p") + m_sub(m_r("V"), m_r("T"))
        + m_r("+", plain=True)
        + m_sub(m_r("C"), m_r("m")) + m_sub(m_r("T"), m_r("sat", plain=True))
        + m_r(".", plain=True)
    )
    pb.add_equation(eq1b_xml, "(1b)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "Denoting the mass flow rates (kg/s) of incoming feedwater, exiting main steam, scheduled blowdown, and waterwall/riser tube leakage by *q*_{f}, *q*_{s}, *q*_{bd}, and *q*_{ℓ}, respectively, and the net heat transfer rate delivered from the furnace gas side to the boiling fluid by *Q* (W), the global mass and energy conservation balances are:",
        keep_with_next=True
    )

    # Eq (2a) & (2b)
    eq2a_xml = (
        m_acc(m_r("M"), "\u0307") + m_r("=", plain=True)
        + m_sub(m_r("q"), m_r("f")) + m_r("\u2212", plain=True)
        + m_sub(m_r("q"), m_r("s")) + m_r("\u2212", plain=True)
        + m_sub(m_r("q"), m_r("bd", plain=True)) + m_r("\u2212", plain=True)
        + m_sub(m_r("q"), m_r("\u2113"))
        + m_r(",", plain=True)
    )
    pb.add_equation(eq2a_xml, "(2a)")

    eq2b_xml = (
        m_acc(m_r("U"), "\u0307") + m_r("=", plain=True)
        + m_r("Q") + m_r("+", plain=True)
        + m_sub(m_r("q"), m_r("f")) + m_sub(m_r("h"), m_r("f"))
        + m_r("\u2212", plain=True)
        + m_sub(m_r("q"), m_r("s")) + m_sub(m_r("h"), m_r("s"))
        + m_r("\u2212", plain=True)
        + m_delim(m_sub(m_r("q"), m_r("bd", plain=True)) + m_r("+", plain=True) + m_sub(m_r("q"), m_r("\u2113")))
        + m_sub(m_r("h"), m_r("w"))
        + m_r(".", plain=True)
    )
    pb.add_equation(eq2b_xml, "(2b)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "Equations (2a) and (2b) ensure that tube leakage *q*_{ℓ} acts as a physical boundary sink that simultaneously withdraws liquid mass and saturated-liquid enthalpy *q*_{ℓ}*h*_{w} from the circulation loop, rather than injecting an artificial additive offset into a sensor channel. Applying the chain rule to Equations (1a) and (1b) yields the coupled 2 × 2 linear system solved at each integration step for the pressure and liquid-volume time derivatives:",
        keep_with_next=True
    )

    # Eq (3) from Supplement Eq (S1)
    eq3_xml = (
        m_matrix([
            [m_sub(m_r("M"), m_r("p")), m_sub(m_r("M"), m_r("V"))],
            [m_sub(m_r("U"), m_r("p")), m_sub(m_r("U"), m_r("V"))]
        ])
        + m_matrix([
            [m_acc(m_r("p"), "\u0307")],
            [m_sub(m_acc(m_r("V"), "\u0307"), m_r("w"))]
        ])
        + m_r("=", plain=True)
        + m_matrix([
            [m_sub(m_r("q"), m_r("f")) + m_r("\u2212", plain=True) + m_sub(m_r("q"), m_r("s")) + m_r("\u2212", plain=True) + m_sub(m_r("q"), m_r("\u2113")) + m_r("\u2212", plain=True) + m_sub(m_r("q"), m_r("bd", plain=True))],
            [m_r("Q") + m_r("+", plain=True) + m_sub(m_r("q"), m_r("f")) + m_sub(m_r("h"), m_r("f")) + m_r("\u2212", plain=True) + m_sub(m_r("q"), m_r("s")) + m_sub(m_r("h"), m_r("s")) + m_r("\u2212", plain=True) + m_delim(m_sub(m_r("q"), m_r("\u2113")) + m_r("+", plain=True) + m_sub(m_r("q"), m_r("bd", plain=True))) + m_sub(m_r("h"), m_r("w"))]
        ])
        + m_r(",", plain=True)
    )
    pb.add_equation(eq3_xml, "(3)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "where subscripts *p* and *V* denote partial derivatives with respect to drum pressure and total liquid volume, respectively; specifically, *M*_{V} = *ρ*_{w} − *ρ*_{s} and *U*_{V} = *ρ*_{w}*h*_{w} − *ρ*_{s}*h*_{s}, while *M*_{p} and *U*_{p} incorporate the saturation-curve derivatives of the fluid properties and the metal capacitance term *C*_{m}(d*T*_{sat}/d*p*)."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "The remaining two states (*α*_{r} and *V*_{sd}) capture two-phase riser circulation and drum shrink–swell relaxation. Let *z* = (*ρ*_{w} − *ρ*_{s})*α*_{r}/*ρ*_{s}; the mean riser steam void fraction *α*_{v} is evaluated analytically via the logarithmic profile relation *α*_{v} = [*ρ*_{w}/(*ρ*_{w} − *ρ*_{s})][1 − ln(1 + *z*)/*z*] (with a Taylor branch for small *α*_{r} and numerical clipping to the closed interval [0, 0.999]). Downcomer natural-circulation mass flow *q*_{dc} and the rate of change of riser-exit steam quality are governed by:",
        keep_with_next=True
    )

    # Eq (4) from Supplement Eq (S2)
    eq4_xml = (
        m_sub(m_r("q"), m_r("dc", plain=True)) + m_r("=", plain=True)
        + m_sqrt(
            m_frac(
                m_r("2", plain=True) + m_sub(m_r("ρ"), m_r("w")) + m_sub(m_r("A"), m_r("dc", plain=True))
                + m_delim(m_sub(m_r("ρ"), m_r("w")) + m_r("\u2212", plain=True) + m_sub(m_r("ρ"), m_r("s")))
                + m_r("g") + m_sub(m_r("α"), m_r("v")) + m_sub(m_r("V"), m_r("r")),
                m_sub(m_r("K"), m_r("f"))
            )
        )
        + m_r(",   ", plain=True)
        + m_sub(m_acc(m_r("α"), "\u0307"), m_r("r")) + m_r("=", plain=True)
        + m_frac(
            m_r("max", plain=True) + m_delim(m_r("Q") + m_r(",", plain=True) + m_r("0", plain=True)) + m_r("/", plain=True) + m_sub(m_r("h"), m_r("fg", plain=True))
            + m_r("\u2212", plain=True) + m_sub(m_r("α"), m_r("r")) + m_sub(m_r("q"), m_r("dc", plain=True)),
            m_sub(m_r("ρ"), m_r("w")) + m_sub(m_r("V"), m_r("r"))
        )
        + m_r(",", plain=True)
    )
    pb.add_equation(eq4_xml, "(4)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "where *A*_{dc} is the downcomer cross-sectional area, *g* is gravitational acceleration, and *K*_{f} is the implementation's loop friction sizing coefficient (initialized at 25 and rescaled during plant construction toward a target circulation ratio of 20). Subsurface steam volume *V*_{sd} in the drum relaxes with residence time constant *T*_{d} toward its equilibrium volume *V*_{sd,0} plus empirical riser bubble entrainment weighted by *β*:",
        keep_with_next=True
    )

    # Eq (5) from Supplement Eq (S3)
    eq5_xml = (
        m_sub(m_acc(m_r("V"), "\u0307"), m_r("sd", plain=True)) + m_r("=", plain=True)
        + m_frac(
            m_r("β") + m_sub(m_r("α"), m_r("r")) + m_sub(m_r("q"), m_r("dc", plain=True)),
            m_sub(m_r("ρ"), m_r("s"))
        )
        + m_r("\u2212", plain=True)
        + m_frac(
            m_sub(m_r("V"), m_r("sd", plain=True)) + m_r("\u2212", plain=True) + m_sub(m_r("V"), m_r("sd,0", plain=True)),
            m_sub(m_r("T"), m_r("d"))
        )
        + m_r(".", plain=True)
    )
    pb.add_equation(eq5_xml, "(5)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "Crucially, the true apparent water level in the horizontal cylindrical drum (radius *R*_{d} = 0.75 m, length *L*_{d} = 5.0 m) is reconstructed by inverting the horizontal-cylinder volume map at the combined drum liquid-and-bubble volume *V*_{wd} + *V*_{sd}, where *V*_{wd} = *V*_{w} − *V*_{dc} − (1 − *α*_{v})*V*_{r}. Consequently, apparent drum level reflects both two-phase riser void redistribution and subsurface bubble swell, rather than total liquid inventory *V*_{w} alone."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "On the boundary side, the MGO-fired furnace computes net heat input *Q* from applied fuel command *u*_{fuel} (with excess-air ratio 1.15, inlet-air temperature 25 °C, and wall-loss fraction 0.015) by balancing flue-gas enthalpy loss against a logarithmic-mean-temperature-difference heat-transfer relation referenced to *T*_{sat}(*p*); no superheater is included in the ab4 configuration. Neither the feedwater valve nor the main steam valve imposes a direct mass flow rate. Instead, for an applied feedwater valve opening clamped to *u*_{f} ∈ [0, 1], feedwater tank pressure *p*_{tank} = 1.2 bar, fixed-speed centrifugal pump head curve Δ*p*_{pump} = *a*_{p0} − *a*_{p1}*q*_{f}^{2}, and valve conductance *C*_{f} (sized at the nominal flow of 1.4 kg/s with valve opening 0.5, a rated valve pressure drop equal to 25% of the nominal static pressure rise *p*_{sp} − *p*_{tank}, and pump shutoff head *a*_{p0} equal to 1.6 times rated pump head), the preserved implementation (FeedwaterLine.flow_kg_s) returns *q*_{f} = 0 when *u*_{f} ≤ 10^{−6} (a branch reached upon protection trip in blocks E1–E3) and otherwise solves actual feedwater mass flow *q*_{f} from the coupled hydraulic balance:",
        keep_with_next=True
    )

    # Eq (6) from Supplement Eq (S4) with explicit closed-valve branch (u_f <= 10^-6)
    eq6_xml = (
        m_sub(m_r("q"), m_r("f")) + m_r("=", plain=True) + m_r("0", plain=True)
        + m_delim(m_sub(m_r("u"), m_r("f")) + m_r("\u2264", plain=True) + m_sup(m_r("10", plain=True), m_r("\u2212") + m_r("6")))
        + m_r(",   ", plain=True)
        + m_subsup(m_r("q"), m_r("f"), m_r("2", plain=True)) + m_r("=", plain=True)
        + m_frac(
            m_r("max", plain=True) + m_delim(m_sub(m_r("p"), m_r("tank", plain=True)) + m_r("+", plain=True) + m_sub(m_r("a"), m_r("p0", plain=True)) + m_r("\u2212", plain=True) + m_r("p") + m_r(",", plain=True) + m_r("0", plain=True)),
            m_sub(m_r("a"), m_r("p1", plain=True)) + m_r("+", plain=True) + m_r("1", plain=True) + m_r("/", plain=True)
            + m_delim(m_sub(m_r("ρ"), m_r("w")) + m_sup(m_delim(m_sub(m_r("C"), m_r("f")) + m_sub(m_r("u"), m_r("f"))), m_r("2", plain=True)), beg="[", end="]")
        )
        + m_delim(m_sup(m_r("10", plain=True), m_r("\u2212") + m_r("6")) + m_r("<", plain=True) + m_sub(m_r("u"), m_r("f")) + m_r("\u2264", plain=True) + m_r("1", plain=True))
        + m_r(".", plain=True)
    )
    pb.add_equation(eq6_xml, "(6)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "Similarly, for steam valve opening *u*_{s} ∈ [0, 1] and downstream header pressure *p*_{down} = 4.2 bar (0.6*p*_{sp}), exiting steam mass flow (SteamLine.flow_kg_s) does not permit reverse flow and follows the unchoked discharge relation *q*_{s} = *C*_{s}*u*_{s}√(*ρ*_{s} max(*p* − *p*_{down}, 0)) when *p*_{down}/*p* > 0.577 (with *C*_{s} sized at 1.4 kg/s, valve opening 0.6, and nominal pressure 7.0 bar), transitioning below that critical pressure ratio to a pressure-proportional choked branch matched at the nominal critical point. The two nominal operating regime labels examined in this study (*u*_{s,base} = 0.55 and 0.50) represent dimensionless base steam-valve command settings around which stochastic load fluctuations occur, rather than fixed percentages of the 1.4 kg/s rated steam flow. Periodic blowdown *q*_{bd} removes 0.05 kg/s during the first 60 s of every 1,800 s cycle. In each fault trajectory, tube-leak mass flow *q*_{ℓ} (kg/s) is driven by the pressure-dependent orifice law:",
        keep_with_next=True
    )

    # Eq (7) Leak law (with <m:nor/> on "bar" and "max" and separate math runs for -1, 0)
    eq7_xml = (
        m_sub(m_r("q"), m_r("\u2113")) + m_r("=", plain=True)
        + m_r("k") + m_r("s") + m_delim(m_r("t"))
        + m_sqrt(
            m_r("max", plain=True) + m_delim(m_sub(m_r("p"), m_r("bar", plain=True)) + m_r("\u2212") + m_r("1") + m_r(",") + m_r("0"))
        )
        + m_r(",", plain=True)
    )
    pb.add_equation(eq7_xml, "(7)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "where *p*_{bar} is absolute drum pressure in bar, 1 bar is the ambient backpressure reference, *k* (kg s^{−1} bar^{−1/2}) is the episode's maximum leak conductance coefficient, and *s*(*t*) ∈ [0, 1] is the dimensionless fault progression ramp that remains zero prior to leak onset (*t* < *t*_{onset}), rises linearly from 0 to 1 over the episode's progression duration, and remains at 1 thereafter. This linear ramp is an accelerated liquid-loss scenario design rather than an empirical tube-crack propagation law. Table 1 summarizes the geometric, thermodynamic, hydraulic, and numerical integration parameters implemented by the Ab4Backend.from_config constructor."
    )

    # Table 1 (from Supplement Table S2a)
    t1_headers = ["Quantity", "Value or Sizing Rule", "Physical / Numerical Role"]
    t1_widths  = [2350, 2557, 2950]
    t1_rows = [
        ["Drum radius *R*_{d}, length *L*_{d}", "0.75 m, 5.0 m", "Horizontal cylindrical steam drum geometry"],
        ["Drum volume *V*_{d}", "π(0.75)^{2}(5.0) ≈ 8.836 m^{3}", "Primary drum two-phase containment volume"],
        ["Riser and downcomer volumes", "*V*_{r} = 0.35*V*_{d}, *V*_{dc} = 0.15*V*_{d}", "Geometry-scaled circulation loop volumes"],
        ["Total pressurized volume *V*_{T}", "*V*_{d} + *V*_{r} + *V*_{dc} ≈ 13.254 m^{3}", "Total fluid boundary volume in Equation (1b)"],
        ["Downcomer flow area *A*_{dc}", "0.03 m^{2}", "Natural circulation cross-section in Equation (4)"],
        ["Lumped metal heat capacity *C*_{m}", "6,000 × 490 = 2.94 × 10^{6} J/K", "Pressure-part thermal capacitance in Equation (1b)"],
        ["Subsurface bubble closure (*T*_{d}, *β*, *V*_{sd,0})", "12 s, 0.3, 0.05*V*_{d}", "Empirical drum shrink–swell relaxation in Equation (5)"],
        ["Nominal pressure setpoint *p*_{sp}", "7.0 bar absolute (7.0 × 10^{5} Pa)", "Regulated drum pressure target; IF97 properties"],
        ["Nominal apparent level setpoint *l*_{sp}", "0.85 m (hot-start target 0.5667 × 1.5 m)", "Regulated horizontal-cylinder liquid level target"],
        ["Rated steam mass flow *q*_{s,nom}", "1.4 kg/s", "Design sizing point for furnace, pump, and valves"],
        ["Feedwater line / pump sizing", "1.4 kg/s at *u*_{f} = 0.5; *p*_{tank} = 1.2 bar", "25% static-rise valve drop; shutoff head 1.6 × rated"],
        ["Steam line sizing (*C*_{s}, *p*_{down})", "1.4 kg/s at *u*_{s} = 0.6; *p*_{down} = 4.2 bar", "Unchoked/choked transition at *p*_{down}/*p* = 0.577"],
        ["Feedwater temperature and enthalpy", "60 °C; *h*_{f} = 4,200 × 60 = 2.52 × 10^{5} J/kg", "Fixed subcooled feedwater supply approximation"],
        ["Scheduled blowdown *q*_{bd}", "0.05 kg/s for 60 s every 1,800 s", "Known periodic liquid mass and enthalpy sink"],
        ["BDF solver relative / absolute tolerances", "rtol = 10^{−6}; atol = (100, 10^{−4}, 10^{−5}, 10^{−5})", "Adaptive internal integration for (*p*, *V*_{w}, *α*_{r}, *V*_{sd})"],
        ["Outer control / sensor / logger period", "Δ*t* = 2.0 s", "Discrete-time execution step across 6 h (21,600 s)"]
    ]
    pb.add_three_line_table(
        "**Table 1.** Geometry, thermodynamic, hydraulic, and numerical integration parameters of the ab4 auxiliary-boiler simulation.",
        t1_widths, t1_headers, t1_rows,
        footer_text="Note: Parameters define the reduced simulation configuration (Ab4Backend.from_config) and do not represent certified pressure-vessel specifications.",
        align_cols=[L, L, L]
    )

    # =========================================================================
    # SECTION 2.2
    # =========================================================================
    pb.add_p("MDPI_2.2_heading2", "2.2. Three-Element Cascade Control, Protection Policy, Sensor Conditioning, and Block Design", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "Each six-hour (21,600 s) simulation episode begins with a 60 s manual hot-start hold (fuel command fixed at 0.66 for the 0.55 base regime and 0.61 for the 0.50 base regime, feedwater valve opening fixed at 0.03, and steam valve at its base setting) before transferring to automatic closed-loop regulation. In automatic mode, a pressure PI controller acts on the conditioned pressure error *p*_{sp} − *p*^{obs} (in bar) with proportional and integral gains (*K*_{p}, *K*_{i}) = (0.7 bar^{−1}, 0.02 bar^{−1} s^{−1}) and output clamped to the closed interval [0, 1] to generate the fuel firing request. Drum water level is regulated by a three-element cascade loop: an outer level PI controller acts on the conditioned level error *l*_{sp} − *l*^{obs} (in m) with gains (*K*_{p}, *K*_{i}) = (3.0 m^{−1}, 0.01 m^{−1} s^{−1}) to produce a dimensionless trim signal *v*_{l} clamped to [−1, 1], which adjusts the measured steam flow *q*_{s}^{obs} to form the inner feedwater mass-flow setpoint *q*_{f,sp}:",
        keep_with_next=True
    )

    # Eq (8) from Supplement Eq (S5)
    eq8_xml = (
        m_sub(m_r("q"), m_r("f,sp", plain=True)) + m_r("=", plain=True)
        + m_subsup(m_r("q"), m_r("s"), m_r("obs", plain=True))
        + m_r("+", plain=True)
        + m_r("0.5", plain=True) + m_delim(m_r("1.4 kg/s", plain=True)) + m_sub(m_r("v"), m_r("l"))
        + m_r(".", plain=True)
    )
    pb.add_equation(eq8_xml, "(8)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "An inner flow PI controller then acts on *q*_{f,sp} − *q*_{f}^{obs} (in kg/s) with gains (*K*_{p}, *K*_{i}) = (0.3 (kg/s)^{−1}, 0.03 (kg/s)^{−1} s^{−1}) and output clamped to [0, 1] to request the feedwater valve opening. All three PI loops use zero derivative gain and an anti-windup tracking gain of 1.0 s^{−1}. Actuator dynamics apply first-order time lags of 2.0, 3.0, and 0.5 s, rate limits of 0.8, 0.7, and 1.2 s^{−1}, and deadbands of 0.002, 0.003, and 0.0 to the fuel, feedwater, and steam valves, respectively, distinguishing raw controller requests from applied valve commands *u*_{f}."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "All measurement channels and control updates execute at a discrete sampling period of Δ*t* = 2 s, with the controller receiving the previous step's conditioned observations. The sensor conditioning layer models first-order measurement lag, additive Gaussian noise, random sample dropouts, sporadic pressure spikes (probability 0.0002 per sample, standard deviation 0.15 bar), and slow level sensor drift (0.0002 m/h), as summarized in Table 2. When a finite 'good' or 'degraded' sample arrives, the conditioner updates the channel; during 'bad' or non-finite samples, the conditioner holds the last valid value for at most 10 s (five samples), after which the channel is marked unavailable (thus, sensor quality-alarm logging and observation usability evaluation serve distinct roles). A strict information boundary separates the simulation layers: the online detectors consume only causal conditioned observations (*p*^{obs}, *l*^{obs}, *q*_{s}^{obs}, *q*_{f}^{obs}), known blowdown *q*_{bd}, and applied feedwater command *u*_{f}; the cascade controller consumes previous-step conditioned observations; and the background process-protection layer (pipeline/step_loop.py, safety/alarms.py) evaluates process variables from idealized plant truth while also reading controller saturation duration and sensor quality flags. Process alarms (which cap commands at 0.95), trips (which force commands to zero), and lockout were actuated from those protection checks, whereas scheduler-severity crossings were logged as diagnostic labels but excluded from actuation under the predefined process-protection-without-schedule-severity-oracle policy (safety.scheduler_intervention_policy = process_protection_without_schedule_severity_oracle). Detector outputs did not alter the controller or protection logic, and an inherited ambiguity in saturation-timeout logic was left unmodified rather than treated as a validated protective guarantee."
    )

    # Table 2 (from Supplement Table S2)
    t2_headers = ["Measurement Channel", "First-Order Lag (s)", "Noise Std. Dev.", "Dropout Prob. / Sample", "Valid Instrument Range"]
    t2_widths  = [1857, 1450, 1500, 1650, 1400]
    t2_rows = [
        ["Drum pressure (*p*^{obs})", "0.2", "0.02 bar", "0.0005", "0.0–20.0 bar"],
        ["Apparent drum level (*l*^{obs})", "0.6", "0.004 m", "0.0003", "0.0–1.5 m"],
        ["Main steam flow (*q*_{s}^{obs})", "0.3", "0.01 kg/s", "0.0005", "0.0–3.0 kg/s"],
        ["Feedwater flow (*q*_{f}^{obs})", "0.5", "0.01 kg/s", "0.0005", "0.0–3.0 kg/s"]
    ]
    pb.add_three_line_table(
        "**Table 2.** Configured sensor conditioning parameters across the four primary measurement channels.",
        t2_widths, t2_headers, t2_rows,
        footer_text="Note: Pressure conditioning additionally includes random spikes (probability 0.0002 per sample, standard deviation 0.15 bar), and drum level includes a configured drift of 0.0002 m/h. Invalid samples hold the last good value for at most 10 s before channel unavailability.",
        align_cols=[L, C, C, C, C]
    )

    pb.add_p(
        "MDPI_3.1_text",
        "The experimental design comprises 12 operating blocks split into four development blocks (D1–D4) and eight evaluation blocks (E1–E8), each containing a 6 h normal episode and a paired 6 h tube-leak episode (24 episodes and 259,224 timestamps in total). Both splits are balanced across the two base steam-valve regimes (0.55 and 0.50). Within each block, the normal and fault branches share identical random draws for plant construction parameters, physical-time load trajectories, and sensor noise/dropout innovation tapes, differing only by the injection of the linear leak ramp after *t*_{onset} in the fault branch. Because paired branches share exogenous realizations, they represent matched counterfactual trajectories rather than independent replicates; however, the paired normal trajectory is never supplied to any fault-branch detector. Leak onset times, progression durations, and leak conductance coefficients *k* were sampled within 2,700–5,400 s, 5,400–10,800 s, and 0.16–0.24 kg s^{−1} bar^{−1/2}, respectively, as listed in Table 3. During dataset generation, the initial plant parameter seed for block D4 (seed 3004) failed a furnace construction feasibility check before simulated time advanced; it was replaced by construction-valid plant seed 3104 while preserving D4's exogenous load, sensor, and fault streams. All regression references, standardization scales, and alarm thresholds were fitted exclusively to the four development-normal episodes (D1–D4)."
    )

    # Table 3 (from Supplement Table S1; widened col 1 to 1450 dxa so "Development" never wraps)
    t3_headers = ["Block", "Dataset Split", "Base Regime", "Plant Seed", "Leak Onset (s)", "Progression (s)", "*k* (kg s^{−1} bar^{−1/2})"]
    t3_widths  = [650, 1450, 1100, 900, 1150, 1200, 1407]
    t3_rows = [
        ["D1", "Development", "0.55", "3001", "3,196", "6,996", "0.1635"],
        ["D2", "Development", "0.55", "3002", "4,238", "10,206", "0.2384"],
        ["D3", "Development", "0.50", "3003", "3,738", "10,684", "0.2400"],
        ["D4", "Development", "0.50", "3104^{a}", "3,350", "6,638", "0.2340"],
        ["E1", "Evaluation", "0.55", "3005", "3,374", "7,342", "0.2177"],
        ["E2", "Evaluation", "0.55", "3006", "4,568", "6,548", "0.2351"],
        ["E3", "Evaluation", "0.55", "3007", "3,946", "5,724", "0.2092"],
        ["E4", "Evaluation", "0.55", "3008", "4,078", "5,460", "0.1749"],
        ["E5", "Evaluation", "0.50", "3009", "4,830", "9,602", "0.1993"],
        ["E6", "Evaluation", "0.50", "3010", "5,254", "7,770", "0.1824"],
        ["E7", "Evaluation", "0.50", "3011", "4,324", "9,960", "0.2218"],
        ["E8", "Evaluation", "0.50", "3012", "3,838", "10,656", "0.2152"]
    ]
    pb.add_three_line_table(
        "**Table 3.** Retained block parameters and random draws across development (D1–D4) and evaluation (E1–E8) splits.",
        t3_widths, t3_headers, t3_rows,
        footer_text="^{a} In block D4, nominal plant seed 3004 failed at furnace construction before time integration and was replaced by construction-valid seed 3104 while retaining the original load, sensor, and fault streams.",
        align_cols=[C, C, C, C, C, C, C]
    )

    # =========================================================================
    # SECTION 2.3
    # =========================================================================
    pb.add_p("MDPI_2.2_heading2", "2.3. Detector Pipelines and Score Standardization", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "To exclude initial startup and cascade handoff transients from alarm evaluation, detector score monitoring starts at *t* = 1,200 s (sample index 600) in every episode, yielding 10,201 active monitoring timestamps (5.6667 h) per six-hour trajectory. Four detector pipelines are evaluated using only causal windows of available conditioned observations and applied commands:"
    )

    pb.add_p(
        "MDPI_3.1_text",
        "1. **State Baseline (State (B0))**: The baseline detector tracks exponentially weighted moving averages (EWMAs) [27] of observed drum water level and pressure deviations from their setpoints, *d*_{l}(*t*) = *l*^{obs}(*t*) − 0.85 m and *d*_{p}(*t*) = *p*^{obs}(*t*) − 7.0 bar. Using a 120 s smoothing time constant on the 2 s grid, the recursive smoothing weight is *a* = 1 − exp(−2/120). Each EWMA initializes at the first available observation and updates on valid samples according to *e*(*t*) = *e*(*t* − 2) + *a*[*d*(*t*) − *e*(*t* − 2)], with standardized two-sided score:",
        keep_with_next=True
    )

    # Eq (9) State (B0)
    eq9_xml = (
        m_sub(m_r("B"), m_r("0", plain=True)) + m_delim(m_r("t")) + m_r("=", plain=True)
        + m_r("max", plain=True) + m_delim(
            m_frac(m_delim(m_sub(m_r("e"), m_r("l")) + m_delim(m_r("t")), beg="|", end="|"), m_sub(m_r("σ"), m_r("l")))
            + m_r(", ", plain=True)
            + m_frac(m_delim(m_sub(m_r("e"), m_r("p")) + m_delim(m_r("t")), beg="|", end="|"), m_sub(m_r("σ"), m_r("p")))
        )
        + m_r(",", plain=True)
    )
    pb.add_equation(eq9_xml, "(9)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "where *σ*_{l} and *σ*_{p} are the population standard deviations of *e*_{l} and *e*_{p} over the pooled development-normal monitoring rows."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "2. **Flow-Imbalance Residual (Flow only)**: The flow pipeline evaluates a trailing mass-balance residual over a causal window of length *W* = 600 s (301 inclusive timestamps at Δ*t* = 2 s) using trapezoidal integration of observed net inflow minus the change in an empirical drum-liquid mass proxy:",
        keep_with_next=True
    )

    # Eq (10) Flow imbalance (Manuscript Eq 3)
    eq10_xml = (
        m_sub(m_r("r"), m_r("M")) + m_delim(m_r("t")) + m_r("=", plain=True)
        + m_frac(
            m_int(
                m_r("t") + m_r("\u2212", plain=True) + m_r("W"),
                m_r("t"),
                m_delim(m_subsup(m_r("q"), m_r("f"), m_r("obs", plain=True)) + m_r("\u2212", plain=True) + m_subsup(m_r("q"), m_r("s"), m_r("obs", plain=True)) + m_r("\u2212", plain=True) + m_sub(m_r("q"), m_r("bd", plain=True))) + m_r("d", plain=True) + m_r("u")
            )
            + m_r("\u2212", plain=True)
            + m_r("\u0394", plain=True) + m_acc(m_r("M"), "\u0302") + m_delim(m_r("t")),
            m_r("W")
        )
        + m_r(",", plain=True)
    )
    pb.add_equation(eq10_xml, "(10)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "where {{math:Mhat_diff}}. For clipped observed drum level *h* = clip(*l*^{obs}, 0, 1.5 m), the horizontal-cylinder liquid volume map *V*(*h*) for *R*_{d} = 0.75 m and *L*_{d} = 5.0 m is given by:",
        keep_with_next=True
    )

    # Eq (11) Horizontal cylinder volume V(h)
    eq11_xml = (
        m_r("V") + m_delim(m_r("h")) + m_r("=", plain=True)
        + m_r("5", plain=True) + m_delim(
            m_sup(m_r("0.75", plain=True), m_r("2", plain=True)) + m_r("arccos", plain=True)
            + m_delim(m_frac(m_r("0.75", plain=True) + m_r("\u2212", plain=True) + m_r("h"), m_r("0.75", plain=True)))
            + m_r("\u2212", plain=True)
            + m_delim(m_r("0.75", plain=True) + m_r("\u2212", plain=True) + m_r("h"))
            + m_sqrt(m_r("max", plain=True) + m_delim(m_r("1.5", plain=True) + m_r("h") + m_r("\u2212", plain=True) + m_sup(m_r("h"), m_r("2", plain=True)) + m_r(",", plain=True) + m_r("0", plain=True))),
            beg="[", end="]"
        )
        + m_r(",", plain=True)
    )
    pb.add_equation(eq11_xml, "(11)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "and the drum-only mass estimator is {{math:Mhat(t)}} = *ρ*_{l}(*p*^{obs})*V*(*h*), where saturated-liquid density *ρ*_{l}(*p*^{obs}) is evaluated via cubic interpolation over a 1,000-knot geometric pressure grid (0.5–120 bar, with detector pressure input clipped to 0.5–30 bar) generated from IAPWS-IF97 [26]. Unlike the true global fluid mass *M* in Equation (1a), {{math:Mhat(t)}} uses only observed drum level and liquid density; as shown by Equations (3)–(5), it does not reconstruct riser/downcomer liquid storage or subsurface steam bubble volume *V*_{sd}. To adjust empirically for normal operating variations across load and level, an ordinary least-squares (OLS) linear reference *r*_{ref}(*t*) is fitted on the trailing 600 s arithmetic mean steam flow {{math:qbar_s(t)}} and trailing mean level deviation {{math:lbar_d(t)}}. Accordingly, *r*_{M}(*t*) − *r*_{ref}(*t*) is an empirical mass-balance anomaly residual rather than a direct physical measurement of leak mass flow."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "3. **Feedwater-Demand Residual (Demand only) and Composite Score (Combined (B1))**: The demand pipeline computes the trailing 600 s arithmetic mean of the applied feedwater valve command {{math:ubar_f(t)}} and subtracts a linear OLS normal reference *u*_{ref}(*t*) conditioned on trailing mean observed steam flow {{math:qbar_s(t)}}:",
        keep_with_next=True
    )

    # Eq (12a) & (12b) OLS Reference Models
    eq12a_xml = (
        m_sub(m_r("r"), m_r("ref", plain=True)) + m_delim(m_r("t")) + m_r("=", plain=True)
        + m_sub(m_r("a"), m_r("0", plain=True)) + m_r("+", plain=True)
        + m_sub(m_r("a"), m_r("1", plain=True)) + m_sub(m_acc(m_r("q"), "\u0304"), m_r("s")) + m_delim(m_r("t"))
        + m_r("+", plain=True)
        + m_sub(m_r("a"), m_r("2", plain=True)) + m_sub(m_acc(m_r("l"), "\u0304"), m_r("d")) + m_delim(m_r("t"))
        + m_r(",", plain=True)
    )
    pb.add_equation(eq12a_xml, "(12a)")

    eq12b_xml = (
        m_sub(m_r("u"), m_r("ref", plain=True)) + m_delim(m_r("t")) + m_r("=", plain=True)
        + m_sub(m_r("b"), m_r("0", plain=True)) + m_r("+", plain=True)
        + m_sub(m_r("b"), m_r("1", plain=True)) + m_sub(m_acc(m_r("q"), "\u0304"), m_r("s")) + m_delim(m_r("t"))
        + m_r(".", plain=True)
    )
    pb.add_equation(eq12b_xml, "(12b)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "Dividing each residual by its development-normal population standard deviation (*σ*_{F}, *σ*_{D}) yields the one-sided standardized component scores *z*_{F}(*t*) and *z*_{D}(*t*), and their pointwise maximum defines the combined detector *B*_{1}(*t*):",
        keep_with_next=True
    )

    # Eq (13) split across two lines so closing parentheses never collide with (13) in LibreOffice
    eq13_top_xml = (
        m_sub(m_r("z"), m_r("F")) + m_delim(m_r("t")) + m_r("=", plain=True)
        + m_frac(
            m_sub(m_r("r"), m_r("M")) + m_delim(m_r("t")) + m_r("\u2212", plain=True) + m_sub(m_r("r"), m_r("ref", plain=True)) + m_delim(m_r("t")),
            m_sub(m_r("σ"), m_r("F"))
        )
        + m_r(",   ", plain=True)
        + m_sub(m_r("z"), m_r("D")) + m_delim(m_r("t")) + m_r("=", plain=True)
        + m_frac(
            m_sub(m_acc(m_r("u"), "\u0304"), m_r("f")) + m_delim(m_r("t")) + m_r("\u2212", plain=True) + m_sub(m_r("u"), m_r("ref", plain=True)) + m_delim(m_r("t")),
            m_sub(m_r("σ"), m_r("D"))
        )
        + m_r(",", plain=True)
    )
    pb.add_equation(eq13_top_xml, "", keep_with_next=True)

    eq13_bot_xml = (
        m_sub(m_r("B"), m_r("1", plain=True)) + m_delim(m_r("t")) + m_r("=", plain=True)
        + m_r("max", plain=True) + m_delim(m_sub(m_r("z"), m_r("F")) + m_delim(m_r("t")) + m_r(", ", plain=True) + m_sub(m_r("z"), m_r("D")) + m_delim(m_r("t")))
        + m_r(".", plain=True)
    )
    pb.add_equation(eq13_bot_xml, "(13)")

    pb.add_p(
        "MDPI_3.2_text_no_indent",
        "Table 4 lists the OLS regression coefficients and residual standardization scales (rounded for display; full floating-point precision in results/independent_fit.json) fitted across the 40,804 pooled development-normal monitoring rows (4 episodes × 10,201 rows). Neither *z*_{F} nor *z*_{D} is clipped at zero prior to threshold selection. In the post-hoc component comparison, Flow only and Demand only evaluate *z*_{F}(*t*) and *z*_{D}(*t*) separately while retaining Combined (B1)'s four-channel window-availability requirement; thus, the component comparison isolates score attribution rather than testing a reduced-sensor hardware configuration. Moreover, State (B0) and the residual pipelines differ structurally in memory, reference conditioning, and sidedness (a two-sided 120 s EWMA around fixed setpoints versus one-sided 600 s trailing windows around load-conditioned OLS references)."
    )

    # Table 4 (from Supplement Table S3)
    t4_headers = ["Parameter", "Reconstructed Value", "Role and Physical / Statistical Units"]
    t4_widths  = [1400, 2257, 4200]
    t4_rows = [
        ["*a*_{0}", "0.0107829644171", "Flow-residual OLS intercept (kg/s) in Equation (12a)"],
        ["*a*_{1}", "−0.00810778822474", "Flow-residual OLS slope on trailing mean steam flow {{math:qbar_s}} (dimensionless)"],
        ["*a*_{2}", "1.63198387636", "Flow-residual OLS slope on trailing mean level deviation {{math:lbar_d}} (kg s^{−1} m^{−1})"],
        ["*b*_{0}", "−0.403728207267", "Demand-residual OLS intercept (dimensionless command) in Equation (12b)"],
        ["*b*_{1}", "0.617687937742", "Demand-residual OLS slope on trailing mean steam flow {{math:qbar_s}} (s/kg)"],
        ["*σ*_{F}", "0.0642100702339", "Development-normal residual standard deviation for *r*_{M} − *r*_{ref} (kg/s, ddof = 0)"],
        ["*σ*_{D}", "0.0572613102938", "Development-normal residual standard deviation for {{math:ubar_f}} − *u*_{ref} (dimensionless, ddof = 0)"],
        ["*σ*_{l}", "0.00692987017346", "Development-normal EWMA standard deviation for drum level deviation *e*_{l} (m)"],
        ["*σ*_{p}", "0.00125315658028", "Development-normal EWMA standard deviation for drum pressure deviation *e*_{p} (bar)"],
        ["Fit sample *N*", "40,804", "Pooled development-normal monitoring timestamps across D1–D4 (4 × 10,201 rows)"]
    ]
    pb.add_three_line_table(
        "**Table 4.** Reconstructed ordinary least-squares (OLS) regression coefficients and score standardization scales fitted on pooled development-normal monitoring records.",
        t4_widths, t4_headers, t4_rows,
        footer_text="Note: Values are rounded for display; full floating-point precision is preserved in results/independent_fit.json.",
        align_cols=[C, C, L]
    )

    # =========================================================================
    # SECTION 2.4
    # =========================================================================
    pb.add_p("MDPI_2.2_heading2", "2.4. Threshold Selection, Sequential Alarm Policy, and Outcome Definitions", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "To place all four detector pipelines under a common nonparametric calibration rule, candidate alarm thresholds *θ* were evaluated from the empirical quantile set *q* ∈ {0.990, 0.995, 0.999, 0.9995, 1.000} of each detector's pooled development-normal monitoring scores using linear interpolation. In the sequential alarm state machine, a confirmed alarm requires a score strictly above its threshold (score > *θ*) continuously for at least 600 elapsed seconds (301 consecutive timestamps at 2 s resolution) and is emitted at the confirmation timestamp rather than backdated to the start of the exceedance interval. Any unavailable sample resets the persistence counter to zero. Following confirmation, an 1,800 s cooldown suppresses repeated notifications during a sustained fault; reconfirmations after cooldown are logged as repeat notifications rather than counted as new independent alarm episodes. For each detector variant, the smallest candidate quantile *q* yielding zero confirmed alarms across all four development-normal episodes (D1–D4) was retained. As shown in Table 5, State (B0) produced one development-normal alarm in block D3 at *q* = 0.990 (*θ* = 3.767425) and therefore selected *q* = 0.995 (*θ* = 3.927338), whereas Flow only, Demand only, and Combined (B1) achieved zero development-normal alarms at the lowest candidate quantile *q* = 0.990, selecting *θ*_{F} = 2.328681, *θ*_{D} = 4.388325, and *θ*_{B1} = 4.388325, respectively."
    )

    # Table 5 (Integrating Main Table 1 and Supplement Table S4)
    t5_headers = ["Detector Variant", "Score Process", "Quantile *q*", "Threshold *θ*", "D1", "D2", "D3", "D4"]
    t5_widths  = [1657, 1750, 900, 1150, 600, 600, 600, 600]
    t5_rows = [
        ["State (B0)", "max(|*e*_{l}|/*σ*_{l}, |*e*_{p}|/*σ*_{p})", "0.990", "3.767425", "0", "0", "1", "0"],
        ["State (B0) [Retained]", "max(|*e*_{l}|/*σ*_{l}, |*e*_{p}|/*σ*_{p})", "0.995", "3.927338", "0", "0", "0", "0"],
        ["State (B0)", "max(|*e*_{l}|/*σ*_{l}, |*e*_{p}|/*σ*_{p})", "0.999", "3.970749", "0", "0", "0", "0"],
        ["State (B0)", "max(|*e*_{l}|/*σ*_{l}, |*e*_{p}|/*σ*_{p})", "0.9995", "3.979331", "0", "0", "0", "0"],
        ["State (B0)", "max(|*e*_{l}|/*σ*_{l}, |*e*_{p}|/*σ*_{p})", "1.000", "5.307179", "0", "0", "0", "0"],
        ["Flow only [Retained]", "Flow residual *z*_{F}", "0.990", "2.328681", "0", "0", "0", "0"],
        ["Flow only", "Flow residual *z*_{F}", "0.995", "2.574599", "0", "0", "0", "0"],
        ["Flow only", "Flow residual *z*_{F}", "0.999", "3.116660", "0", "0", "0", "0"],
        ["Flow only", "Flow residual *z*_{F}", "0.9995", "3.288148", "0", "0", "0", "0"],
        ["Flow only", "Flow residual *z*_{F}", "1.000", "4.063845", "0", "0", "0", "0"],
        ["Demand only [Retained]", "Command residual *z*_{D}", "0.990", "4.388325", "0", "0", "0", "0"],
        ["Demand only", "Command residual *z*_{D}", "0.995", "4.594975", "0", "0", "0", "0"],
        ["Demand only", "Command residual *z*_{D}", "0.999", "4.822598", "0", "0", "0", "0"],
        ["Demand only", "Command residual *z*_{D}", "0.9995", "4.830538", "0", "0", "0", "0"],
        ["Demand only", "Command residual *z*_{D}", "1.000", "4.833258", "0", "0", "0", "0"],
        ["Combined (B1) [Retained]", "max(*z*_{F}, *z*_{D})", "0.990", "4.388325", "0", "0", "0", "0"],
        ["Combined (B1)", "max(*z*_{F}, *z*_{D})", "0.995", "4.594975", "0", "0", "0", "0"],
        ["Combined (B1)", "max(*z*_{F}, *z*_{D})", "0.999", "4.822598", "0", "0", "0", "0"],
        ["Combined (B1)", "max(*z*_{F}, *z*_{D})", "0.9995", "4.830538", "0", "0", "0", "0"],
        ["Combined (B1)", "max(*z*_{F}, *z*_{D})", "1.000", "4.833258", "0", "0", "0", "0"]
    ]
    pb.add_three_line_table(
        "**Table 5.** Candidate development-normal score quantile thresholds and confirmed normal alarm counts across development blocks D1–D4 (retained thresholds highlighted in bold).",
        t5_widths, t5_headers, t5_rows,
        footer_text="Note: The smallest candidate quantile *q* producing zero confirmed alarms (score strictly above *θ* for at least 600 elapsed seconds) across all four development-normal episodes is retained for evaluation.",
        align_cols=[L, L, C, C, C, C, C, C],
        bold_rows=[1, 5, 10, 15]
    )

    pb.add_p(
        "MDPI_3.1_text",
        "To evaluate whether warnings arrive before closed-loop regulation loses effective control margin, a retrospective functional degradation predicate is defined by the simultaneous condition that applied feedwater valve command reaches at least 95% of full travel (*u*_{f}(*t*) ≥ 0.95) and plant-truth apparent drum water level drops to at most 0.75 m (*l*_{true}(*t*) ≤ 0.75 m, 0.10 m below the 0.85 m setpoint), sustained continuously for at least 120 elapsed seconds (61 inclusive timestamps). Let *T*_{start} denote the first timestamp of that confirmed 120 s degradation interval, and *T*_{confirm} = *T*_{start} + 120 s denote the primary functional confirmation event. This engineering criterion represents sustained exhaustion of feedwater control margin accompanied by material water-level depression rather than physical tube rupture; because it includes *u*_{f}(*t*) ≥ 0.95, it deliberately shares a command variable with the demand detector."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "Accordingly, two complementary timing metrics are evaluated on the eight evaluation fault episodes (E1–E8): (i) **post-onset detection delay**, defined as Δ*t*_{delay} = *t*_{alarm} − *t*_{onset}, where *t*_{alarm} is the first confirmed alarm at or after scheduled leak onset *t*_{onset}; and (ii) **strict warning lead time**, defined as Δ*t*_{lead} = *T*_{start} − *t*_{alarm}, which requires alarm confirmation prior to the start *T*_{start} of the functional degradation interval to be positive. Detection delay was measured from scheduled leak onset. The archived analysis retained the first alarm before functional confirmation, or before the six-hour horizon in censored episodes. Removing this upper time limit returned the same first alarm in all 32 evaluation episode–detector comparisons (8 episodes × 4 detectors). Pre-onset alarms (*t*_{alarm} < *t*_{onset}) are recorded separately. If functional degradation confirmation is absent at the 6 h (21,600 s) simulation horizon, the episode is treated as right-censored for endpoint lead time rather than assigned an artificial failure time."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "All simulator trajectories, regression fits, quantile thresholds, and alarm timestamps were produced by the preserved R2 study archive (code/reproduce_analysis.py, code/verify_features.py, code/test_analysis.py, and code/make_figures_r2.py). During the preparation of this Full Paper submission from the preserved archive, generative artificial intelligence (GenAI) assistance was used only for journal template conversion, assembling the automated document-generation script (build_full_paper.py) and numerical/table cross-check scripts (verify_revised_manuscript.py, check_cutoff_leads.py, check_delay_window.py), and polishing English prose under direct author verification, without generating new simulation data or modifying the underlying statistical results."
    )

    # =========================================================================
    # SECTION 3. RESULTS
    # =========================================================================
    pb.add_p("MDPI_2.1_heading1", "3. Results", keep_with_next=True)
    pb.add_p("MDPI_2.2_heading2", "3.1. Physical Response under Closed-Loop Compensation", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "To establish the baseline dynamic behavior of the regulated auxiliary boiler prior to fault injection, Figure 1 displays the conditioned drum pressure *p*^{obs} and apparent water level *l*^{obs} recorded during the six-hour normal evaluation trajectory of block E1 (*u*_{s,base} = 0.55). Following the initial 60 s manual hot-start hold and cascade transfer transient (which settles well before detector monitoring starts at *t* = 1,200 s), the pressure PI loop and three-element feedwater cascade maintain drum pressure tightly around 7.0 bar and apparent water level near 0.85 m across stochastic load variations and periodic 1,800 s blowdown pulses."
    )

    pb.add_figure(
        FIG1_PATH,
        "**Figure 1.** Conditioned drum pressure (top) and apparent drum water level (bottom) during the six-hour normal evaluation trajectory in block E1 (*u*_{s,base} = 0.55). The vertical dotted line at *t* = 1,200 s marks the start of active detector monitoring following initial startup transient settling.",
        width_inches=4.65
    )

    pb.add_p(
        "MDPI_3.1_text",
        "Figure 2 illustrates how closed-loop feedback alters the observable symptom evolution when a tube leak initiates at *t*_{onset} = 3,374 s in the paired fault branch of block E1 (with progression duration 7,342 s and maximum conductance *k* = 0.2177 kg s^{−1} bar^{−1/2}). Throughout the first two hours following leak onset, conditioned drum pressure remains tightly regulated near its 7.0 bar setpoint because the pressure PI controller increases firing effort to offset the saturated-liquid enthalpy loss *q*_{ℓ}*h*_{w}. Concurrently, the three-element cascade loop increases the applied feedwater valve command *u*_{f} well above the development-normal OLS reference *u*_{ref} (fitted solely to D1–D4 normal records) to replenish the escaping liquid mass. As shown by the accompanying conditioned flow trajectories in Figure 3, observed feedwater flow *q*_{f}^{obs} diverges progressively above observed steam flow *q*_{s}^{obs} as leak severity *s*(*t*) ramps upward."
    )

    pb.add_figure(
        FIG2_PATH,
        "**Figure 2.** Recorded E1 tube-leak observations (*p*^{obs}, *l*^{obs}) and applied feedwater command (*u*_{f}) versus the development-normal OLS command reference (*u*_{ref}). The vertical dotted line marks physical leak onset (*t*_{onset} = 3,374 s), and the shaded band indicates the retrospective 120 s functional degradation dwell (*T*_{start} = 10,774 s to *T*_{confirm} = 10,894 s). The level degradation threshold (0.75 m) is evaluated on plant truth for annotation, whereas the plotted trace shows the conditioned observation.",
        width_inches=4.15
    )

    pb.add_figure(
        FIG3_PATH,
        "**Figure 3.** Conditioned feedwater mass flow (*q*_{f}^{obs}) and main steam mass flow (*q*_{s}^{obs}) during the E1 tube-leak trajectory corresponding to Figure 2. The vertical dotted line denotes leak onset (*t*_{onset} = 3,374 s) and the shaded band denotes functional degradation dwell. Because drum storage variations and periodic blowdown also enter Equation (2a), the instantaneous flow difference is not by itself an isolated leak-flow measurement.",
        width_inches=4.65
    )

    pb.add_p(
        "MDPI_3.1_text",
        "Because closed-loop replenishment compensates for the leak while actuator margin remains available, apparent drum level *l*^{obs} exhibits only a gradual downward sag during the early stage of the fault before declining more steeply as *u*_{f} approaches saturation near its upper command limit. In block E1, Demand only and Combined (B1) emit their first confirmed post-onset alarms at *t* = 7,232 s (64.3 min after leak onset), Flow only confirms at *t* = 7,840 s (74.4 min after onset), and the state-deviation baseline State (B0) confirms at *t* = 8,996 s (93.7 min after onset). The retrospective functional degradation interval (*u*_{f} ≥ 0.95 and *l*_{true} ≤ 0.75 m) begins at *T*_{start} = 10,774 s and reaches 120 s confirmation at *T*_{confirm} = 10,894 s, demonstrating that control-demand divergence precedes state-level functional exhaustion by nearly one hour in E1."
    )

    # =========================================================================
    # SECTION 3.2
    # =========================================================================
    pb.add_p("MDPI_2.2_heading2", "3.2. Detection Delay, Warning Lead Times, and Component Attribution", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "Across the eight evaluation fault blocks (E1–E8), every detector variant confirmed a post-onset alarm in all eight fault episodes (8/8) and yielded a positive strict warning lead time (alarm confirmed prior to *T*_{start}) in all seven uncensored event episodes (7/7). Evaluation block E5 (*u*_{s,base} = 0.50, *t*_{onset} = 4,830 s, progression duration 9,602 s, *k* = 0.1993 kg s^{−1} bar^{−1/2}) did not reach the functional degradation predicate prior to the 21,600 s simulation horizon and is therefore right-censored for endpoint lead time while contributing an observed post-onset detection delay. Table 6 summarizes the aggregate evaluation metrics across the eight fault blocks and 45.33 h of normal monitoring, and Table 7 reports the complete block-by-block alarm timestamps, functional degradation times, process trips, and model-domain exits."
    )

    # Table 6 (with 115.5 min exact rounding from (11762 - 4830)/60 = 115.5333 min; F07)
    t6_headers = ["Detector Variant", "Normal Alarms (45.33 h)", "Post-Onset Detections", "Detection Delay Median [Range] (min, *n* = 8)", "Strict Lead Median [Range] (min, *n* = 7)"]
    t6_widths  = [1657, 1300, 1300, 1800, 1800]
    t6_rows = [
        ["State (B0)", "1", "8 / 8", "127.3 [65.4–187.9]", "34.7 [29.6–100.0]"],
        ["Flow only", "0", "8 / 8", "86.4 [64.5–116.1]", "48.9 [31.1–164.2]"],
        ["Demand only", "0", "8 / 8", "75.9 [54.8–115.5]", "59.0 [40.8–179.4]"],
        ["Combined (B1)", "0", "8 / 8", "75.9 [54.8–115.5]", "59.0 [40.8–179.4]"]
    ]
    pb.add_three_line_table(
        "**Table 6.** Summary of evaluation outcomes across normal and fault episodes (all timing metrics in minutes).",
        t6_widths, t6_headers, t6_rows,
        footer_text="Note: Normal monitoring exposure is 45.33 h (8 blocks × 5.6667 h) per detector variant. Bracketed values denote min–max observed ranges across episodes (*n* = 8 for post-onset delay; *n* = 7 uncensored episodes for strict lead prior to *T*_{start}). Block E5 is right-censored at the 6 h horizon for functional degradation.",
        align_cols=[L, C, C, C, C]
    )

    # Table 7 (Integrating Supplement Tables S5 and S6)
    t7_headers = ["Block", "Onset", "State (B0)", "Flow Only", "Demand Only", "Combined (B1)", "Func. Start", "Func. Confirm", "Process Trip", "Domain Exit"]
    t7_widths  = [635, 645, 675, 675, 920, 1030, 710, 895, 825, 847]
    t7_rows = [
        ["E1", "3,374", "8,996", "7,840", "7,232", "7,232", "10,774", "10,894", "18,870", "20,248"],
        ["E2", "4,568", "8,580", "8,574", "7,860", "7,860", "10,664", "10,784", "19,532", "20,976"],
        ["E3", "3,946", "7,872", "7,818", "7,236", "7,236", "9,684", "9,804", "17,942", "19,324"],
        ["E4", "4,078", "8,682", "8,322", "7,580", "7,580", "10,668", "10,788", "—", "—"],
        ["E5", "4,830", "15,830", "11,380", "11,762", "11,762", "—^{a}", "—^{a}", "—", "—"],
        ["E6", "5,254", "15,010", "11,158", "11,856", "11,848", "21,010", "21,130", "—", "—"],
        ["E7", "4,324", "13,974", "10,572", "9,578", "9,578", "16,294", "16,414", "—", "—"],
        ["E8", "3,838", "15,110^{b}", "10,806", "9,692", "9,692", "20,458", "20,578", "—", "—"]
    ]
    pb.add_three_line_table(
        "**Table 7.** Blockwise leak onset, first confirmed post-onset alarm times, retrospective functional degradation start (*T*_{start}) and confirmation (*T*_{confirm}) times, process trips, and model-domain exits across evaluation fault blocks E1–E8 (all timestamps in seconds from episode start).",
        t7_widths, t7_headers, t7_rows,
        footer_text="^{a} Block E5 did not reach the functional degradation predicate before the 21,600 s horizon (right-censored). ^{b} In block E8, State (B0) also emitted a pre-onset false alarm at *t* = 3,276 s prior to *t*_{onset} = 3,838 s; the table lists its first confirmed post-onset alarm.",
        align_cols=[C, C, C, C, C, C, C, C, C, C]
    )

    pb.add_p(
        "MDPI_3.1_text",
        "Evaluating **post-onset detection delay** (Δ*t*_{delay} = *t*_{alarm} − *t*_{onset}) measured from scheduled leak onset—where the archived analysis retained the first alarm before functional confirmation (or before the 6 h horizon in censored episodes) and removing that upper time limit returned the same first alarm in all 32 evaluation episode–detector comparisons—shows earlier confirmed warnings for the residual detectors across all eight blocks (Figure 4). Median post-onset detection delay decreases from 127.3 min (range 65.4–187.9 min) for State (B0) to 86.4 min (range 64.5–116.1 min) for Flow only and 75.9 min (range 54.8–115.5 min) for Demand only and Combined (B1), corresponding to a 51.3 min (3,080 s) reduction in median delay relative to the state baseline. On a blockwise paired basis across E1–E8, Combined (B1) precedes State (B0)'s first post-onset confirmation by 10.6 to 90.3 min, with a median paired improvement of 41.1 min (2,463 s). Relative to the retrospective functional degradation start *T*_{start} across the seven uncensored blocks (Tables 6 and 7), median strict warning lead time increases from 34.7 min (range 29.6–100.0 min) for State (B0) to 48.9 min (range 31.1–164.2 min) for Flow only and 59.0 min (range 40.8–179.4 min) for Demand only and Combined (B1)."
    )

    pb.add_figure(
        FIG4_PATH,
        "**Figure 4.** First confirmed post-onset alarm delay (min) from physical leak onset (*t*_{onset}) across evaluation blocks E1–E8. Markers are horizontally offset within each categorical block for visibility; no interpolation between blocks is implied. Block E5 is right-censored for the functional endpoint but contributes an observed post-onset detection delay.",
        width_inches=4.95
    )

    pb.add_p(
        "MDPI_3.1_text",
        "The post-hoc component attribution explains why Combined (B1) and Demand only share the same retained threshold and nearly identical alarm times. In the pooled development-normal records, the maximum flow-component score (max(*z*_{F}) = 4.063845) was strictly below both demand-score order statistics (4.386572 and 4.388380) used to linearly interpolate *z*_{D}'s 0.990 quantile. The upper tail of the pointwise maximum score *B*_{1} = max(*z*_{F}, *z*_{D}) at *q* ≥ 0.990 therefore coincided with the demand tail in these data, yielding the exact same retained threshold (*θ*_{B1} = *θ*_{D} = 4.388325; Table 5). This equality is an empirical property of the joint development-normal score records, not a general mathematical identity relating marginal quantiles to the quantile of a maximum. At the shared threshold (*θ*_{B1} = 4.388325), flow crossed before demand in all eight evaluation leaks (at 5,068, 6,502, 5,860, 6,166, 7,244, 6,794, 7,750, and 7,068 s versus 6,632, 7,260, 6,636, 6,980, 11,162, 11,256, 8,978, and 9,092 s for demand across E1–E8). Its exceedances, however, did not sustain a flow-only confirmation before the combined alarm (standalone flow confirmations at the shared threshold occurred at 9,822, 9,678, 8,890, 9,378, 14,246, 13,970, 12,832, and 13,510 s). Demand alone reproduced seven combined alarm times (E1–E5, E7, and E8; Figure 5 and Table 7). In E6, four initial 2 s samples where only flow exceeded the shared threshold entered the combined confirmation window and advanced the combined confirmation by 8 s ahead of demand alone (11,848 s vs. 11,856 s). Meanwhile, when Flow only is calibrated independently using its own development-normal threshold (*θ*_{F} = 2.328681; Table 6), it confirms 382 s (6.4 min) earlier than Combined (B1) in block E5 (11,380 s vs. 11,762 s) and 690 s (11.5 min) earlier in block E6 (11,158 s vs. 11,848 s)."
    )

    pb.add_figure(
        FIG5_PATH,
        "**Figure 5.** Normalized detector score trajectories (each score divided by its own retained threshold *θ*) during the E1 fault episode. Horizontal dashed line indicates the normalized confirmation threshold (score/*θ* = 1.0); markers denote confirmed alarms after at least 600 elapsed seconds of continuous strict exceedance. The Demand only and Combined (B1) traces closely overlap.",
        width_inches=4.95
    )

    pb.add_figure(
        FIG6_PATH,
        "**Figure 6.** Cross-block timeline of retrospective functional degradation start (*T*_{start}) and confirmation (*T*_{confirm}), later process trips, model-domain exits, and 6 h horizon censoring across evaluation blocks E1–E8. Seven evaluation blocks had observed functional events, whereas block E5 was right-censored at the 6 h horizon. Physical leak onset and detector alarm times are reported in Table 7 and are not plotted in this figure.",
        width_inches=5.15
    )

    # =========================================================================
    # SECTION 3.3
    # =========================================================================
    pb.add_p("MDPI_2.2_heading2", "3.3. Normal-Operation Alarms, Persistence Diagnostics, and Numerical Sensitivity", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "Each six-hour normal evaluation episode contributes (21,600 − 1,200)/3,600 = 5.6667 h of continuous active monitoring exposure (no unavailable sensor intervals occurred in the main normal trajectories), totaling 45.33 h across E1–E8. Over this normal evaluation exposure, Flow only, Demand only, and Combined (B1) issued zero confirmed false alarms, whereas State (B0) issued one confirmed false alarm in block E8 (Table 6). Because normal and fault branches within each block share identical exogenous load and sensor realizations prior to leak onset, that same State (B0) excursion also triggered a pre-onset alarm at *t* = 3,276 s in E8's paired fault branch (prior to *t*_{onset} = 3,838 s); it represents a single shared normal-regime excursion rather than an independent second false alarm."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "To examine how close each detector came to issuing a confirmed false alarm during normal operation, Table 8 and Figure 7 report the longest continuous threshold-exceedance span (in elapsed seconds) recorded in each normal evaluation block E1–E8. In blocks E1–E4 (*u*_{s,base} = 0.55), continuous exceedances were at most 6 s for State (B0) in E1 and 2 s for Flow only in E1, E3, and E4. In the lower base-load regime (*u*_{s,base} = 0.50, blocks E5–E8), transient demand and composite score excursions exceeded *θ* = 4.388325 for continuous spans of 176 to 464 s. Specifically, in normal block E8, Demand only and Combined (B1) reached a peak score of 4.6167 above threshold 4.388325, but the longest continuous exceedance persisted for 464 elapsed seconds—below the 600 s confirmation requirement—and the highest minimum score sustained across any full 600 s window in E8 normal was 4.2438. Only State (B0) in E8 reached the 600 elapsed-second confirmation requirement (with an 850 s continuous threshold-exceedance interval), showing how the persistence filter suppresses shorter load-induced score excursions on these trajectories."
    )

    # Table 8 (from Supplement Table S7; updated caption per F09)
    t8_headers = ["Evaluation Block", "Base Regime", "State (B0) (s)", "Flow Only (s)", "Demand Only (s)", "Combined (B1) (s)"]
    t8_widths  = [1557, 1300, 1250, 1250, 1250, 1250]
    t8_rows = [
        ["E1 (Normal)", "0.55", "6", "2", "0", "0"],
        ["E2 (Normal)", "0.55", "0", "0", "0", "0"],
        ["E3 (Normal)", "0.55", "0", "2", "0", "0"],
        ["E4 (Normal)", "0.55", "0", "2", "0", "0"],
        ["E5 (Normal)", "0.50", "0", "2", "208", "208"],
        ["E6 (Normal)", "0.50", "104", "2", "184", "184"],
        ["E7 (Normal)", "0.50", "0", "0", "176", "176"],
        ["E8 (Normal)", "0.50", "**850**^{a}", "2", "464", "464"]
    ]
    pb.add_three_line_table(
        "**Table 8.** Longest continuous threshold-exceedance span (s) across normal evaluation blocks E1–E8 at retained method-specific thresholds. Alarm confirmation requires a score strictly above its threshold for at least 600 elapsed seconds; the reported spans describe threshold exceedances, not alarm duration.",
        t8_widths, t8_headers, t8_rows,
        footer_text="^{a} Only State (B0) in block E8 reached at least 600 elapsed seconds of continuous strict exceedance, emitting one confirmed normal alarm (and the corresponding pre-onset alarm at *t* = 3,276 s in E8's paired fault branch). A single-sample exceedance corresponds to 0 s elapsed span.",
        align_cols=[C, C, C, C, C, C]
    )

    pb.add_figure(
        FIG7_PATH,
        "**Figure 7.** Normal threshold-exceedance persistence spans (s) across evaluation blocks E1–E8 displayed as categorical blockwise points relative to the 600 elapsed-second confirmation requirement (horizontal dashed line). Transient peaks above threshold that decay before 600 elapsed seconds do not emit confirmed alarms.",
        width_inches=5.15
    )

    pb.add_p(
        "MDPI_3.1_text",
        "For the recorded D1 normal and leak trajectories, tightening the BDF tolerances (relative tolerance from 10^{−6} to 10^{−8} and absolute tolerances scaled by 0.01) while holding physical-time input tapes, controller policy, and outer 2 s execution periods fixed produced small maximum state differences (1.60 × 10^{−4} bar in drum pressure and 3.84 × 10^{−5} m in drum water level) and unchanged D1 functional-event start and confirmation times (12,592 and 12,712 s). This single comparison provides a bounded numerical-sensitivity check on D1; it is not a general error bound across all blocks or evidence of field validation. Across all 24 main episodes, the solver completed to 21,600 s without logged integration exceptions. Later process trips (18,870, 19,532, and 17,942 s) and liquid-volume-fraction model-domain exits (violating the 0.05–0.95 feasible liquid-fraction bounds at 20,248, 20,976, and 19,324 s) occurred only in severe fault blocks E1, E2, and E3 (Table 7 and Figure 6). Within those three blocks, first confirmed post-onset alarms (7,232–8,996 s) and primary functional degradation confirmations (9,804–10,894 s) preceded the corresponding trips and domain exits by more than 7,000 s, ensuring that no post-trip or out-of-domain trajectory segment influences the primary warning metrics."
    )

    # =========================================================================
    # SECTION 4. DISCUSSION
    # =========================================================================
    pb.add_p("MDPI_2.1_heading1", "4. Discussion", keep_with_next=True)
    pb.add_p("MDPI_2.2_heading2", "4.1. Control Compensation and Component Attribution Mechanisms", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "The simulation results illustrate closed-loop fault masking and signal redistribution in a regulated drum boiler [9,13,14]. As tube leakage withdraws pressurized saturated water and liquid enthalpy from the circulation loop, the three-element cascade controller counters the inventory deficit by increasing the feedwater valve command *u*_{f}, while the pressure PI controller increases firing rate to maintain drum pressure near 7.0 bar. Because this feedback action transfers the incipient fault effect into the manipulated control input (*u*_{f}) and net mass inflow (*q*_{f} − *q*_{s}), both the flow-imbalance residual and the feedwater-demand residual confirmed alarms earlier than the state-deviation baseline State (B0) in all eight evaluation blocks. The magnitude of that gain, however, varied by component and operating regime: Demand only and Combined (B1) preceded State (B0) by 10.6 to 90.3 min across all eight blocks, whereas Flow only preceded State (B0) by only 6 s (0.1 min) in E2 and 54 s (0.9 min) in E3, by 6.0 to 19.3 min in E1 and E4, and by 56.7 to 74.2 min in the lower base-load blocks E5–E8."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "The component attribution further clarifies how equal-scale pointwise maximum fusion behaves under empirical quantile thresholding. Because the maximum development-normal flow score (4.063845) lay below the order statistics defining the 0.990 demand quantile (4.388325), the composite score *B*_{1} = max(*z*_{F}, *z*_{D}) inherited the demand threshold on the development set. At the shared threshold, flow crossed before demand in all eight evaluation leaks. Its exceedances, however, did not sustain a flow-only confirmation before the combined alarm. Demand alone reproduced seven combined alarm times. In E6, flow advanced the combined confirmation by 8 s. When Flow only was instead calibrated against its own 0.990 development-normal quantile (*θ*_{F} = 2.328681), it confirmed earlier warnings than Demand only and Combined (B1) in blocks E5 and E6. Thus, the near-equivalence of Combined (B1) and Demand only reflects threshold-dependent persistence behavior under unrescaled max-score fusion rather than absence of early flow response."
    )

    pb.add_p("MDPI_2.2_heading2", "4.2. Methodological Boundaries: Pipeline Asymmetry, Endpoint Coupling, and Sensor Availability", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "Three structural aspects of the experimental design bound the interpretation of the comparative timing results:"
    )

    pb.add_p(
        "MDPI_3.1_text",
        "1. **Pipeline Filtering and Reference Conditioning Asymmetry**: State (B0) and the residual pipelines (Flow only, Demand only, Combined (B1)) are distinct end-to-end signal-processing implementations rather than matched filters applied to different raw channels. Specifically, State (B0) evaluates a two-sided 120 s EWMA of deviations from fixed setpoints, whereas the flow and demand pipelines evaluate one-sided 600 s trailing window averages adjusted by load-conditioned OLS regression references (*r*_{ref}, *u*_{ref}). Applying an identical development-normal quantile selection rule and 600 s persistence requirement standardizes the decision layer but does not eliminate the underlying differences in window memory, regression adjustment, and score sidedness. Therefore, the observed 51.3 min reduction in median detection delay reflects the performance of the complete specified pipelines rather than the intrinsic information content of pressure/level versus flow/command sensors under matched filtering."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "2. **Endpoint Coupling and Level-Cutoff Sensitivity**: The retrospective functional degradation criterion (*u*_{f} ≥ 0.95 and *l*_{true} ≤ 0.75 m sustained for 120 s) represents an engineering definition of control-margin and water-level degradation rather than physical tube rupture. Because this predicate includes the applied feedwater command *u*_{f}, a detector driven by *u*_{f} tracks one of the variables participating in the endpoint definition. While all detectors operate causally without access to future fault labels, sharing a variable with the endpoint limits endpoint-independent claims of lead-time utility. Two analyses bound this issue. First, detection delay was measured from scheduled leak onset. The archived analysis retained the first alarm before functional confirmation, or before the six-hour horizon in censored episodes. Removing this upper time limit returned the same first alarm in all 32 evaluation episode–detector comparisons, although all 32 comparisons come from the same eight fault episodes rather than a new independent sample. Second, in post-hoc sensitivity checks on the stored evaluation trajectories (results/endpoint_sensitivity.csv), changing the drum-level cutoff while holding detector alarm times fixed alters both which episodes reach the endpoint and the observed median lead times (blocks E1–E4 and E7 at 0.70 m; adding E6 and E8 at 0.75 m; and adding E5 at 0.80 m). At level cutoffs of 0.70, 0.75 and 0.80 m, 5, 7 and 8 of the eight evaluation blocks reached the endpoint, respectively. All four detectors confirmed before the start of each observed event. Median strict leads were 54.6, 34.7 and 8.9 min (8.85 min unrounded, 531 s) for State (B0), 66.2, 48.9 and 43.5 min for Flow only, 76.3, 59.0 and 54.8 min for Demand only, and 76.3, 59.0 and 54.9 min for Combined (B1). Within a single block, however, a common shift of the endpoint *T* changes every detector's lead time by the same constant ((*T* − *t*_{A}) − (*T* − *t*_{B}) = *t*_{B} − *t*_{A}) and cannot by itself alter blockwise lead-time rank; the cutoff sensitivity therefore characterizes changes in absolute lead magnitude and endpoint observability rather than providing independent evidence of detector superiority or removing the shared command condition."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "3. **Sensor Availability Masking and Post-Hoc Reanalysis Status**: In the component attribution study, both Flow only and Demand only retained the four-channel window-availability mask of Combined (B1) so that timestamp comparisons isolate score behavior on identical valid domains. Consequently, evaluating Demand only in software is not equivalent to physically removing the feedwater and drum-level instruments from a deployed plant, where sensor dropouts and failure modes would differ. Furthermore, whereas the State (B0) and Combined (B1) specifications were fixed in the primary study archive, the separately thresholded Flow only and Demand only comparisons were conducted as a post-hoc decomposition on the already inspected evaluation trajectories (and the final D4 construction-valid seed replacement and refit occurred after E1–E8 trajectory generation, as documented in the execution chronology). The component attribution should therefore be interpreted as an exploratory diagnostic decomposition rather than a pre-registered prospective trial."
    )

    pb.add_p("MDPI_2.2_heading2", "4.3. Simulation Scope and Directions for Future Marine Engineering Validation", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "The experimental scope of this study is intentionally compact and synthetic: detector calibration rests on four development-normal episodes (D1–D4), and comparative evaluation rests on eight paired evaluation blocks (E1–E8) spanning two base steam-valve command settings (0.55 and 0.50) and one linear-ramp orifice leak family. Although the 24 six-hour trajectories contain 259,224 timestamps at 2 s resolution, consecutive timestamps within an episode are strongly autocorrelated and paired branches share exogenous inputs; thus, the effective sample size for detector comparison is eight evaluation blocks (and seven uncensored episodes for strict lead time), not 259,224 independent trials. Likewise, observing 8/8 post-onset detections and zero confirmed residual false alarms across 45.33 h of normal evaluation monitoring describes finite-sample behavior within the tested two-regime envelope and does not establish population-level detection probabilities, statistical confidence bounds, or long-run false-alarm guarantees under seaway-induced drum sloshing, burner cycling, or sustained sensor drift."
    )

    pb.add_p(
        "MDPI_3.1_text",
        "From a physical modeling perspective, the ab4 backend captures essential closed-loop thermohydraulic interactions of a saturated-steam drum boiler—including IAPWS-IF97 saturation properties, two-phase riser circulation, subsurface steam swell, pressure-dependent pump/valve characteristics, and three-element cascade control—but simplifies geometry-scaled riser and downcomer volumes (0.35*V*_{d} and 0.15*V*_{d}), empirical bubble relaxation constants, fixed 60 °C feedwater supply, and an unmodeled superheater. Similarly, the drum-only inventory proxy {{math:Mhat(t)}} omits riser/downcomer liquid mass and subsurface void volume, and linear OLS regression on steam load and level deviation adjusts normal imbalance empirically without identifying those unmodeled storage states. Future work should therefore evaluate these fixed causal pipelines against independent hardware-in-the-loop (HIL) or shipboard auxiliary-boiler records across broader load turndown and multi-fault conditions, explore component-rescaled fusion to preserve low-load flow sensitivity alongside demand responsiveness, and pair residual monitoring with a purely thermal or structural failure criterion independent of the feedwater command."
    )

    # =========================================================================
    # SECTION 5. CONCLUSIONS (MDPI_3.7_itemize has built-in auto-numbering!)
    # =========================================================================
    pb.add_p("MDPI_2.1_heading1", "5. Conclusions", keep_with_next=True)

    pb.add_p(
        "MDPI_3.1_text",
        "This study compared confirmed early-warning times and component attribution across four specified causal detector pipelines—a pressure/level EWMA baseline (State (B0)), a drum-only mass-balance residual (Flow only), a feedwater valve command residual (Demand only), and their composite maximum (Combined (B1))—in a four-state closed-loop auxiliary-boiler simulation under three-element cascade control. Across four development blocks and eight evaluation blocks (24 six-hour episodes), the principal findings are:"
    )

    pb.add_p(
        "MDPI_3.7_itemize",
        "**Early Warning under Closed-Loop Compensation**: All four detector pipelines issued a confirmed post-onset alarm in all eight evaluation fault episodes (8/8) and preceded the retrospective functional degradation start (*T*_{start}) in all seven uncensored event episodes (7/7), while one block (E5) was right-censored at the 6 h horizon. Median post-onset detection delay decreased from 127.3 min for State (B0) to 86.4 min for Flow only and 75.9 min for Demand only and Combined (B1) (a 51.3 min reduction from unrounded medians), while median strict warning lead time increased from 34.7 min to 48.9 and 59.0 min, respectively."
    )

    pb.add_p(
        "MDPI_3.7_itemize",
        "**Empirical Tail Attribution of the Composite Score**: Because the maximum development-normal flow score (4.063845) was below the order statistics defining the 0.990 demand quantile (4.388325), Combined (B1) inherited the demand threshold on the development set and matched Demand only's first confirmed alarm in seven of the eight evaluation blocks (differing by 8 s in E6). When calibrated independently at its own 0.990 development-normal quantile (*θ*_{F} = 2.328681), Flow only confirmed 6.4 and 11.5 min earlier than Combined (B1) in lower-load blocks E5 and E6."
    )

    pb.add_p(
        "MDPI_3.7_itemize",
        "**Persistence Filtering and Scope Boundaries**: Over 45.33 h of active normal evaluation monitoring, State (B0) emitted one confirmed false alarm in block E8 (from an 850 s continuous threshold-exceedance interval), whereas Flow only, Demand only, and Combined (B1) emitted zero confirmed alarms because transient load-induced threshold exceedances (at most 464 s in E8) decayed before reaching the 600 elapsed-second confirmation requirement. These results characterize pipeline and component behavior within a small, synthetic closed-loop benchmark and do not establish intrinsic sensor superiority, general fusion optimality, remaining-life prediction accuracy, or field readiness."
    )

    pb.add_p(
        "MDPI_3.6_text_after_list",
        "Together, the documented model equations, fitted constants, and episode-level records provide a transparent, reproducible baseline for evaluating how closed-loop boiler control redistributes incipient leak effects between state, flow, and control-demand channels."
    )

    # =========================================================================
    # BACK MATTER & ABBREVIATIONS
    # =========================================================================
    pb.add_p("MDPI_6.2_back_matter", "**Author Contributions:** Conceptualization, Firstname Lastname; methodology, Firstname Lastname; software, Firstname Lastname; validation, Firstname Lastname; formal analysis, Firstname Lastname; investigation, Firstname Lastname; data curation, Firstname Lastname; writing—original draft preparation, Firstname Lastname; writing—review and editing, Firstname Lastname; visualization, Firstname Lastname. All authors have read and agreed to the published version of the manuscript. *(Note: Author names, affiliations, and contribution assignments are template placeholders to be finalized by the manuscript owner prior to journal submission.)*")

    pb.add_p("MDPI_6.2_back_matter", "**Funding:** This research received no external funding. *(To be confirmed by the manuscript owner at submission.)*")

    pb.add_p("MDPI_6.2_back_matter", "**Institutional Review Board Statement:** Not applicable.")

    pb.add_p("MDPI_6.2_back_matter", "**Informed Consent Statement:** Not applicable.")

    pb.add_p("MDPI_6.2_back_matter", "**Data Availability Statement:** The reproducibility materials accompanying this manuscript are organized in two layers: (i) the preserved R2 study analysis package containing the non-pickled column-preserving observation projections (data/observations/<episode>.npz), detector score traces (data/traces/<episode>.npz), applied block configurations (data/original_configs/<episode>_config_applied.json, data/block_design.json, data/episode_metadata.csv), reconstructed OLS fit and episode results (results/independent_fit.json, results/episode_method_results.csv, results/endpoint_sensitivity.csv), and verification/figure scripts (code/test_analysis.py, code/verify_features.py, code/reproduce_analysis.py, code/make_figures_r2.py, and legacy code/make_figures.py); and (ii) the Full Paper manuscript assembly and numerical/table cross-check scripts provided in the submission directory (build_full_paper.py, verify_revised_manuscript.py, check_cutoff_leads.py, check_delay_window.py, and MANUSCRIPT_ARTIFACT_MAP.md), which map the preserved R2 outputs to Tables 1–8 and Figures 1–7 of this article (where Figure 1 is a two-panel vertical composite of R2 Figures S2 and S3 from E1_normal.npz, Figures 2, 4, and 5 correspond to R2 Figures 1, 2, and 3, and Figures 3, 6, and 7 correspond to R2 Figures S5, S1, and S4). Original raw simulator execution archives are privately held by the study owner; final public repository deposition or supplementary archive packaging will be confirmed by the authors prior to publication.")

    pb.add_p("MDPI_6.2_back_matter", "**Acknowledgments:** The authors acknowledge the use of the ab4 saturated-steam auxiliary-boiler simulation architecture for generating the paired operating block trajectories analyzed in this study. During the preparation of this Full Paper manuscript from the preserved R2 study archive, the authors used generative artificial intelligence (GenAI) tools (Google Antigravity agentic coding environment with Gemini 3.1 Pro, alongside OpenAI GPT-5 and Anthropic Claude Opus 4.6; exact environment versions to be confirmed in the journal submission system) under direct author supervision to convert the manuscript into the journal template, assemble the automated document-generation and figure-compositing script (build_full_paper.py), and execute numerical and table cross-check scripts (verify_revised_manuscript.py, check_cutoff_leads.py, check_delay_window.py). No new boiler simulations or threshold adjustments were generated by GenAI. The authors independently reviewed, verified, and edited all mathematical equations, numerical tables, citations, and scientific interpretations, and take full responsibility for the content of the publication.")

    pb.add_p("MDPI_6.2_back_matter", "**Conflicts of Interest:** The authors declare no conflicts of interest. *(To be confirmed by the manuscript owner at submission.)*")

    pb.add_p("MDPI_2.1_heading1", "Abbreviations", keep_with_next=True)
    pb.add_p("MDPI_3.2_text_no_indent", "The following abbreviations are used in this manuscript:", keep_with_next=True)

    abbr_rows = [
        ("AB4 / ab4", "Four-state saturated-steam auxiliary-boiler simulation backend"),
        ("BDF", "Backward differentiation formula (stiff ODE solver)"),
        ("CVA", "Canonical variate analysis"),
        ("DTW", "Dynamic time warping"),
        ("EWMA", "Exponentially weighted moving average"),
        ("FDA", "Fisher discriminant analysis"),
        ("HIL", "Hardware-in-the-loop"),
        ("IAPWS-IF97", "International Association for the Properties of Water and Steam Industrial Formulation 1997"),
        ("MGO", "Marine gas oil"),
        ("ODE", "Ordinary differential equation"),
        ("OLS", "Ordinary least squares"),
        ("PCA", "Principal component analysis"),
        ("PI", "Proportional–integral (controller)"),
        ("RUL", "Remaining useful life"),
        ("SVM", "Support vector machine")
    ]
    pb.add_abbreviations_table(abbr_rows)

    # =========================================================================
    # REFERENCES (MDPI_8.1_references has built-in auto-numbering!)
    # =========================================================================
    pb.add_p("MDPI_2.1_heading1", "References", keep_with_next=True)

    references = [
        "Tajiri, T. Auxiliary Boiler—Aalborg Industries' Marine Boiler. *J. Jpn. Inst. Mar. Eng.* **2009**, *44*, 358–360. https://doi.org/10.5988/jime.44.358",
        "Kim, M.-H.; So, M.-O.; Jung, B.-G. Development of the simulator for marine auxiliary boiler system. *J. Korean Soc. Mar. Eng.* **2013**, *37*, 236–241. https://doi.org/10.5916/jkosme.2013.37.2.236",
        "Orović, J.; Mrzljak, V.; Poljak, I. Efficiency and Losses Analysis of Steam Air Heater from Marine Steam Propulsion Plant. *Energies* **2018**, *11*, 3019. https://doi.org/10.3390/en11113019",
        "Poljak, I. Marine Power Systems. *J. Mar. Sci. Eng.* **2022**, *10*, 195. https://doi.org/10.3390/jmse10020195",
        "Adam, E.J.; Marchetti, J.L. Dynamic simulation of large boilers with natural recirculation. *Comput. Chem. Eng.* **1999**, *23*, 1031–1040. https://doi.org/10.1016/S0098-1354(99)00269-0",
        "Åström, K.J.; Bell, R.D. Drum-boiler dynamics. *Automatica* **2000**, *36*, 363–378. https://doi.org/10.1016/S0005-1098(99)00171-5",
        "Hong, T.; Ni, H.; Cheng, G. Full-scale Mathematical Model and Simulation of Marine Natural Recirculation Drum-boiler. *Procedia Eng.* **2012**, *31*, 834–843. https://doi.org/10.1016/j.proeng.2012.01.1109",
        "Romero-Anton, N.; Martin-Escudero, K.; Portillo-Valdés, L.A.; Gómez-Elvira, I.; Salazar-Herran, E. Improvement of auxiliary BI-DRUM boiler operation by dynamic simulation. *Energy* **2018**, *148*, 676–686. https://doi.org/10.1016/j.energy.2018.01.160",
        "Isermann, R. Model-based fault-detection and diagnosis – status and applications. *Annu. Rev. Control* **2005**, *29*, 71–85. https://doi.org/10.1016/j.arcontrol.2004.12.002",
        "Venkatasubramanian, V.; Rengaswamy, R.; Yin, K.; Kavuri, S.N. A review of process fault detection and diagnosis: Part I: Quantitative model-based methods. *Comput. Chem. Eng.* **2003**, *27*, 293–311. https://doi.org/10.1016/S0098-1354(02)00160-6",
        "Venkatasubramanian, V.; Rengaswamy, R.; Kavuri, S.N.; Yin, K. A review of process fault detection and diagnosis: Part III: Process history based methods. *Comput. Chem. Eng.* **2003**, *27*, 327–346. https://doi.org/10.1016/S0098-1354(02)00162-X",
        "Qin, S.J. Survey on data-driven industrial process monitoring and diagnosis. *Annu. Rev. Control* **2012**, *36*, 220–234. https://doi.org/10.1016/j.arcontrol.2012.09.004",
        "Deibert, R.; Isermann, R. Examples for Fault Detection in Closed Loops. *IFAC Proc. Vol.* **1992**, *25*, 235–240. https://doi.org/10.1016/S1474-6670(17)50827-7",
        "Pandita, R.; Bokor, J.; Balas, G. Closed-loop performance metrics for fault detection and isolation filter and controller interaction. *Int. J. Robust Nonlinear Control* **2013**, *23*, 419–438. https://doi.org/10.1002/rnc.1838",
        "Afgan, N.; Coelho, P.J.; Carvalho, M.G. Boiler tube leakage detection expert system. *Appl. Therm. Eng.* **1998**, *18*, 317–326. https://doi.org/10.1016/S1359-4311(97)00054-9",
        "An, L.; Wang, P.; Sarti, A.; Antonacci, F.; Shi, J. Hyperbolic boiler tube leak location based on quaternary acoustic array. *Appl. Therm. Eng.* **2011**, *31*, 3428–3436. https://doi.org/10.1016/j.applthermaleng.2011.06.028",
        "Sun, X.; Chen, T.; Marquez, H.J. Boiler leak detection using a system identification technique. *Ind. Eng. Chem. Res.* **2002**, *41*, 5447–5454. https://doi.org/10.1021/ie010949+",
        "Sun, X.; Chen, T.; Marquez, H.J. Efficient model-based leak detection in boiler steam-water systems. *Comput. Chem. Eng.* **2002**, *26*, 1643–1647. https://doi.org/10.1016/S0098-1354(02)00147-3",
        "Sun, X.; Marquez, H.J.; Chen, T.; Riaz, M. An improved PCA method with application to boiler leak detection. *ISA Trans.* **2005**, *44*, 379–397. https://doi.org/10.1016/S0019-0578(07)60211-0",
        "Yu, J.; Jang, J.; Yoo, J.; Park, J.H.; Kim, S. Leakage detection of steam boiler tube in thermal power plant using principal component analysis. *Annu. Conf. PHM Soc.* **2016**, *8*, 1–8. https://doi.org/10.36001/phmconf.2016.v8i1.2510",
        "Swiercz, M.; Mroczkowska, H. Multiway PCA for Early Leak Detection in a Pipeline System of a Steam Boiler—Selected Case Studies. *Sensors* **2020**, *20*, 1561. https://doi.org/10.3390/s20061561",
        "Indrawan, N.; Shadle, L.J.; Breault, R.W.; Panday, R.; Chitnis, U.K. Data analytics for leak detection in a subcritical boiler. *Energy* **2021**, *220*, 119667. https://doi.org/10.1016/j.energy.2020.119667",
        "Panday, R.; Indrawan, N.; Shadle, L.J.; Vesel, R.W. Leak detection in a subcritical boiler. *Appl. Therm. Eng.* **2021**, *185*, 116371. https://doi.org/10.1016/j.applthermaleng.2020.116371",
        "Widodo, A.; Prahasto, T.; Soleh, M.; Nugraha, H. Diagnostics and prognostics of boilers in power plant based on data-driven and machine learning. *Int. J. Progn. Health Manag.* **2025**, *16*, 4222. https://doi.org/10.36001/ijphm.2025.v16i1.4222",
        "Wagner, W.; Cooper, J.R.; Dittmann, A.; Kijima, J.; Kretzschmar, H.-J.; Kruse, A.; Mareš, R.; Oguchi, K.; Sato, H.; Stocker, I.; et al. The IAPWS Industrial Formulation 1997 for the Thermodynamic Properties of Water and Steam. *J. Eng. Gas Turbines Power* **2000**, *122*, 150–184. https://doi.org/10.1115/1.483186",
        "International Association for the Properties of Water and Steam (IAPWS). *Revised Release on the IAPWS Industrial Formulation 1997 for the Thermodynamic Properties of Water and Steam*; R7-97(2012); IAPWS: Lucerne, Switzerland, 2012. Available online: https://iapws.org/documents/release/IF97-Rev (accessed on 16 September 2026).",
        "Roberts, S.W. Control Chart Tests Based on Geometric Moving Averages. *Technometrics* **1959**, *1*, 239–250. https://doi.org/10.1080/00401706.1959.10489860"
    ]

    for ref_str in references:
        pb.add_p("MDPI_8.1_references", ref_str)

    # Final pass to guarantee zero <w:bidi/> or <w:bidiVisual/> anywhere in the document
    for el in list(doc.element.xpath(".//w:bidi")) + list(doc.element.xpath(".//w:bidiVisual")):
        el.getparent().remove(el)

    # Save output DOCX
    doc.save(OUT_WORK_DOCX)
    print("Saved DOCX to:", OUT_WORK_DOCX)

    # Update fields and export to PDF via Microsoft Word COM
    import win32com.client
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        wdoc = word.Documents.Open(OUT_WORK_DOCX)
        wdoc.Repaginate()
        wdoc.Fields.Update()
        for sec_i in range(1, wdoc.Sections.Count + 1):
            sec_obj = wdoc.Sections(sec_i)
            for hf_i in range(1, 4):
                try:
                    sec_obj.Headers(hf_i).Range.Fields.Update()
                except Exception:
                    pass
                try:
                    sec_obj.Footers(hf_i).Range.Fields.Update()
                except Exception:
                    pass
        wdoc.Save()
        wdoc.ExportAsFixedFormat(
            OutputFileName=OUT_WORK_PDF,
            ExportFormat=17,  # wdExportFormatPDF
            OpenAfterExport=False,
            OptimizeFor=0,
            CreateBookmarks=1
        )
        wdoc.Close(SaveChanges=False)
        print("Exported PDF to:", OUT_WORK_PDF)
    finally:
        word.Quit()

    # Verify that Word COM Save did not re-introduce <w:bidi/> on sectPr
    doc_check = docx.Document(OUT_WORK_DOCX)
    bidi_elements = list(doc_check.element.xpath(".//w:bidi")) + list(doc_check.element.xpath(".//w:bidiVisual"))
    if bidi_elements:
        for el in bidi_elements:
            el.getparent().remove(el)
        doc_check.save(OUT_WORK_DOCX)
        print("Stripped post-Word-save bidi elements:", len(bidi_elements))

    # Copy both DOCX and PDF to Google Drive target directory
    shutil.copy2(OUT_WORK_DOCX, OUT_DRIVE_DOCX)
    shutil.copy2(OUT_WORK_PDF, OUT_DRIVE_PDF)
    print("Copied DOCX and PDF to Google Drive successfully.")


if __name__ == "__main__":
    build_manuscript()
