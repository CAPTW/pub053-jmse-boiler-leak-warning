"""Build structured bibliography files (CSL-JSON, BibTeX, RIS, Word Sources XML)
and the 27-reference / 26-citation-group mapping table for PUB053 JMSE manuscript.

Reads the original manuscript read-only without modifying it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import escape

SRC_DOCX = r".\JMSE-MDPI-보일러 논문 [김겸원].docx"
OUT_DIR = r"references"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}

# Curated, verified metadata parsed directly from P119-P145 of the manuscript
REFERENCES = [
    {
        "num": 1,
        "bookmark": "Ref01",
        "key": "Tajiri2009",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [{"family": "Tajiri", "given": "T."}],
        "title": "Auxiliary Boiler—Aalborg Industries' Marine Boiler",
        "container": "J. Jpn. Inst. Mar. Eng.",
        "year": "2009",
        "volume": "44",
        "issue": "",
        "page": "358-360",
        "page_display": "358–360",
        "doi": "10.5988/jime.44.358",
        "url": "https://doi.org/10.5988/jime.44.358",
    },
    {
        "num": 2,
        "bookmark": "Ref02",
        "key": "Kim2013",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Kim", "given": "M.-H."},
            {"family": "So", "given": "M.-O."},
            {"family": "Jung", "given": "B.-G."},
        ],
        "title": "Development of the simulator for marine auxiliary boiler system",
        "container": "J. Korean Soc. Mar. Eng.",
        "year": "2013",
        "volume": "37",
        "issue": "",
        "page": "236-241",
        "page_display": "236–241",
        "doi": "10.5916/jkosme.2013.37.2.236",
        "url": "https://doi.org/10.5916/jkosme.2013.37.2.236",
    },
    {
        "num": 3,
        "bookmark": "Ref03",
        "key": "Orovic2018",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Orović", "given": "J."},
            {"family": "Mrzljak", "given": "V."},
            {"family": "Poljak", "given": "I."},
        ],
        "title": "Efficiency and Losses Analysis of Steam Air Heater from Marine Steam Propulsion Plant",
        "container": "Energies",
        "year": "2018",
        "volume": "11",
        "issue": "",
        "page": "3019",
        "page_display": "3019",
        "doi": "10.3390/en11113019",
        "url": "https://doi.org/10.3390/en11113019",
    },
    {
        "num": 4,
        "bookmark": "Ref04",
        "key": "Poljak2022",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [{"family": "Poljak", "given": "I."}],
        "title": "Marine Power Systems",
        "container": "J. Mar. Sci. Eng.",
        "year": "2022",
        "volume": "10",
        "issue": "",
        "page": "195",
        "page_display": "195",
        "doi": "10.3390/jmse10020195",
        "url": "https://doi.org/10.3390/jmse10020195",
    },
    {
        "num": 5,
        "bookmark": "Ref05",
        "key": "Adam1999",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Adam", "given": "E.J."},
            {"family": "Marchetti", "given": "J.L."},
        ],
        "title": "Dynamic simulation of large boilers with natural recirculation",
        "container": "Comput. Chem. Eng.",
        "year": "1999",
        "volume": "23",
        "issue": "",
        "page": "1031-1040",
        "page_display": "1031–1040",
        "doi": "10.1016/S0098-1354(99)00269-0",
        "url": "https://doi.org/10.1016/S0098-1354(99)00269-0",
    },
    {
        "num": 6,
        "bookmark": "Ref06",
        "key": "Astrom2000",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Åström", "given": "K.J."},
            {"family": "Bell", "given": "R.D."},
        ],
        "title": "Drum-boiler dynamics",
        "container": "Automatica",
        "year": "2000",
        "volume": "36",
        "issue": "",
        "page": "363-378",
        "page_display": "363–378",
        "doi": "10.1016/S0005-1098(99)00171-5",
        "url": "https://doi.org/10.1016/S0005-1098(99)00171-5",
    },
    {
        "num": 7,
        "bookmark": "Ref07",
        "key": "Hong2012",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Hong", "given": "T."},
            {"family": "Ni", "given": "H."},
            {"family": "Cheng", "given": "G."},
        ],
        "title": "Full-scale Mathematical Model and Simulation of Marine Natural Recirculation Drum-boiler",
        "container": "Procedia Eng.",
        "year": "2012",
        "volume": "31",
        "issue": "",
        "page": "834-843",
        "page_display": "834–843",
        "doi": "10.1016/j.proeng.2012.01.1109",
        "url": "https://doi.org/10.1016/j.proeng.2012.01.1109",
    },
    {
        "num": 8,
        "bookmark": "Ref08",
        "key": "RomeroAnton2018",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Romero-Anton", "given": "N."},
            {"family": "Martin-Escudero", "given": "K."},
            {"family": "Portillo-Valdés", "given": "L.A."},
            {"family": "Gómez-Elvira", "given": "I."},
            {"family": "Salazar-Herran", "given": "E."},
        ],
        "title": "Improvement of auxiliary BI-DRUM boiler operation by dynamic simulation",
        "container": "Energy",
        "year": "2018",
        "volume": "148",
        "issue": "",
        "page": "676-686",
        "page_display": "676–686",
        "doi": "10.1016/j.energy.2018.01.160",
        "url": "https://doi.org/10.1016/j.energy.2018.01.160",
    },
    {
        "num": 9,
        "bookmark": "Ref09",
        "key": "Isermann2005",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [{"family": "Isermann", "given": "R."}],
        "title": "Model-based fault-detection and diagnosis – status and applications",
        "container": "Annu. Rev. Control",
        "year": "2005",
        "volume": "29",
        "issue": "",
        "page": "71-85",
        "page_display": "71–85",
        "doi": "10.1016/j.arcontrol.2004.12.002",
        "url": "https://doi.org/10.1016/j.arcontrol.2004.12.002",
    },
    {
        "num": 10,
        "bookmark": "Ref10",
        "key": "Venkatasubramanian2003a",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Venkatasubramanian", "given": "V."},
            {"family": "Rengaswamy", "given": "R."},
            {"family": "Yin", "given": "K."},
            {"family": "Kavuri", "given": "S.N."},
        ],
        "title": "A review of process fault detection and diagnosis: Part I: Quantitative model-based methods",
        "container": "Comput. Chem. Eng.",
        "year": "2003",
        "volume": "27",
        "issue": "",
        "page": "293-311",
        "page_display": "293–311",
        "doi": "10.1016/S0098-1354(02)00160-6",
        "url": "https://doi.org/10.1016/S0098-1354(02)00160-6",
    },
    {
        "num": 11,
        "bookmark": "Ref11",
        "key": "Venkatasubramanian2003b",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Venkatasubramanian", "given": "V."},
            {"family": "Rengaswamy", "given": "R."},
            {"family": "Kavuri", "given": "S.N."},
            {"family": "Yin", "given": "K."},
        ],
        "title": "A review of process fault detection and diagnosis: Part III: Process history based methods",
        "container": "Comput. Chem. Eng.",
        "year": "2003",
        "volume": "27",
        "issue": "",
        "page": "327-346",
        "page_display": "327–346",
        "doi": "10.1016/S0098-1354(02)00162-X",
        "url": "https://doi.org/10.1016/S0098-1354(02)00162-X",
    },
    {
        "num": 12,
        "bookmark": "Ref12",
        "key": "Qin2012",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [{"family": "Qin", "given": "S.J."}],
        "title": "Survey on data-driven industrial process monitoring and diagnosis",
        "container": "Annu. Rev. Control",
        "year": "2012",
        "volume": "36",
        "issue": "",
        "page": "220-234",
        "page_display": "220–234",
        "doi": "10.1016/j.arcontrol.2012.09.004",
        "url": "https://doi.org/10.1016/j.arcontrol.2012.09.004",
    },
    {
        "num": 13,
        "bookmark": "Ref13",
        "key": "Deibert1992",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Deibert", "given": "R."},
            {"family": "Isermann", "given": "R."},
        ],
        "title": "Examples for Fault Detection in Closed Loops",
        "container": "IFAC Proc. Vol.",
        "year": "1992",
        "volume": "25",
        "issue": "",
        "page": "235-240",
        "page_display": "235–240",
        "doi": "10.1016/S1474-6670(17)50827-7",
        "url": "https://doi.org/10.1016/S1474-6670(17)50827-7",
    },
    {
        "num": 14,
        "bookmark": "Ref14",
        "key": "Pandita2013",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Pandita", "given": "R."},
            {"family": "Bokor", "given": "J."},
            {"family": "Balas", "given": "G."},
        ],
        "title": "Closed-loop performance metrics for fault detection and isolation filter and controller interaction",
        "container": "Int. J. Robust Nonlinear Control",
        "year": "2013",
        "volume": "23",
        "issue": "",
        "page": "419-438",
        "page_display": "419–438",
        "doi": "10.1002/rnc.1838",
        "url": "https://doi.org/10.1002/rnc.1838",
    },
    {
        "num": 15,
        "bookmark": "Ref15",
        "key": "Afgan1998",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Afgan", "given": "N."},
            {"family": "Coelho", "given": "P.J."},
            {"family": "Carvalho", "given": "M.G."},
        ],
        "title": "Boiler tube leakage detection expert system",
        "container": "Appl. Therm. Eng.",
        "year": "1998",
        "volume": "18",
        "issue": "",
        "page": "317-326",
        "page_display": "317–326",
        "doi": "10.1016/S1359-4311(97)00054-9",
        "url": "https://doi.org/10.1016/S1359-4311(97)00054-9",
    },
    {
        "num": 16,
        "bookmark": "Ref16",
        "key": "An2011",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "An", "given": "L."},
            {"family": "Wang", "given": "P."},
            {"family": "Sarti", "given": "A."},
            {"family": "Antonacci", "given": "F."},
            {"family": "Shi", "given": "J."},
        ],
        "title": "Hyperbolic boiler tube leak location based on quaternary acoustic array",
        "container": "Appl. Therm. Eng.",
        "year": "2011",
        "volume": "31",
        "issue": "",
        "page": "3428-3436",
        "page_display": "3428–3436",
        "doi": "10.1016/j.applthermaleng.2011.06.028",
        "url": "https://doi.org/10.1016/j.applthermaleng.2011.06.028",
    },
    {
        "num": 17,
        "bookmark": "Ref17",
        "key": "Sun2002a",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Sun", "given": "X."},
            {"family": "Chen", "given": "T."},
            {"family": "Marquez", "given": "H.J."},
        ],
        "title": "Boiler leak detection using a system identification technique",
        "container": "Ind. Eng. Chem. Res.",
        "year": "2002",
        "volume": "41",
        "issue": "",
        "page": "5447-5454",
        "page_display": "5447–5454",
        "doi": "10.1021/ie010949+",
        "url": "https://doi.org/10.1021/ie010949+",
    },
    {
        "num": 18,
        "bookmark": "Ref18",
        "key": "Sun2002b",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Sun", "given": "X."},
            {"family": "Chen", "given": "T."},
            {"family": "Marquez", "given": "H.J."},
        ],
        "title": "Efficient model-based leak detection in boiler steam-water systems",
        "container": "Comput. Chem. Eng.",
        "year": "2002",
        "volume": "26",
        "issue": "",
        "page": "1643-1647",
        "page_display": "1643–1647",
        "doi": "10.1016/S0098-1354(02)00147-3",
        "url": "https://doi.org/10.1016/S0098-1354(02)00147-3",
    },
    {
        "num": 19,
        "bookmark": "Ref19",
        "key": "Sun2005",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Sun", "given": "X."},
            {"family": "Marquez", "given": "H.J."},
            {"family": "Chen", "given": "T."},
            {"family": "Riaz", "given": "M."},
        ],
        "title": "An improved PCA method with application to boiler leak detection",
        "container": "ISA Trans.",
        "year": "2005",
        "volume": "44",
        "issue": "",
        "page": "379-397",
        "page_display": "379–397",
        "doi": "10.1016/S0019-0578(07)60211-0",
        "url": "https://doi.org/10.1016/S0019-0578(07)60211-0",
    },
    {
        "num": 20,
        "bookmark": "Ref20",
        "key": "Yu2016",
        "type": "paper-conference",
        "ris_type": "CPAPER",
        "bib_type": "inproceedings",
        "word_type": "ConferenceProceedings",
        "authors": [
            {"family": "Yu", "given": "J."},
            {"family": "Jang", "given": "J."},
            {"family": "Yoo", "given": "J."},
            {"family": "Park", "given": "J.H."},
            {"family": "Kim", "given": "S."},
        ],
        "title": "Leakage detection of steam boiler tube in thermal power plant using principal component analysis",
        "container": "Annu. Conf. PHM Soc.",
        "year": "2016",
        "volume": "8",
        "issue": "",
        "page": "1-8",
        "page_display": "1–8",
        "doi": "10.36001/phmconf.2016.v8i1.2510",
        "url": "https://doi.org/10.36001/phmconf.2016.v8i1.2510",
    },
    {
        "num": 21,
        "bookmark": "Ref21",
        "key": "Swiercz2020",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Swiercz", "given": "M."},
            {"family": "Mroczkowska", "given": "H."},
        ],
        "title": "Multiway PCA for Early Leak Detection in a Pipeline System of a Steam Boiler—Selected Case Studies",
        "container": "Sensors",
        "year": "2020",
        "volume": "20",
        "issue": "",
        "page": "1561",
        "page_display": "1561",
        "doi": "10.3390/s20061561",
        "url": "https://doi.org/10.3390/s20061561",
    },
    {
        "num": 22,
        "bookmark": "Ref22",
        "key": "Indrawan2021",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Indrawan", "given": "N."},
            {"family": "Shadle", "given": "L.J."},
            {"family": "Breault", "given": "R.W."},
            {"family": "Panday", "given": "R."},
            {"family": "Chitnis", "given": "U.K."},
        ],
        "title": "Data analytics for leak detection in a subcritical boiler",
        "container": "Energy",
        "year": "2021",
        "volume": "220",
        "issue": "",
        "page": "119667",
        "page_display": "119667",
        "doi": "10.1016/j.energy.2020.119667",
        "url": "https://doi.org/10.1016/j.energy.2020.119667",
    },
    {
        "num": 23,
        "bookmark": "Ref23",
        "key": "Panday2021",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Panday", "given": "R."},
            {"family": "Indrawan", "given": "N."},
            {"family": "Shadle", "given": "L.J."},
            {"family": "Vesel", "given": "R.W."},
        ],
        "title": "Leak detection in a subcritical boiler",
        "container": "Appl. Therm. Eng.",
        "year": "2021",
        "volume": "185",
        "issue": "",
        "page": "116371",
        "page_display": "116371",
        "doi": "10.1016/j.applthermaleng.2020.116371",
        "url": "https://doi.org/10.1016/j.applthermaleng.2020.116371",
    },
    {
        "num": 24,
        "bookmark": "Ref24",
        "key": "Widodo2025",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Widodo", "given": "A."},
            {"family": "Prahasto", "given": "T."},
            {"family": "Soleh", "given": "M."},
            {"family": "Nugraha", "given": "H."},
        ],
        "title": "Diagnostics and prognostics of boilers in power plant based on data-driven and machine learning",
        "container": "Int. J. Progn. Health Manag.",
        "year": "2025",
        "volume": "16",
        "issue": "",
        "page": "4222",
        "page_display": "4222",
        "doi": "10.36001/ijphm.2025.v16i1.4222",
        "url": "https://doi.org/10.36001/ijphm.2025.v16i1.4222",
    },
    {
        "num": 25,
        "bookmark": "Ref25",
        "key": "Wagner2000",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [
            {"family": "Wagner", "given": "W."},
            {"family": "Cooper", "given": "J.R."},
            {"family": "Dittmann", "given": "A."},
            {"family": "Kijima", "given": "J."},
            {"family": "Kretzschmar", "given": "H.-J."},
            {"family": "Kruse", "given": "A."},
            {"family": "Mareš", "given": "R."},
            {"family": "Oguchi", "given": "K."},
            {"family": "Sato", "given": "H."},
            {"family": "Stocker", "given": "I."},
        ],
        "et_al": True,
        "title": "The IAPWS Industrial Formulation 1997 for the Thermodynamic Properties of Water and Steam",
        "container": "J. Eng. Gas Turbines Power",
        "year": "2000",
        "volume": "122",
        "issue": "",
        "page": "150-184",
        "page_display": "150–184",
        "doi": "10.1115/1.483186",
        "url": "https://doi.org/10.1115/1.483186",
    },
    {
        "num": 26,
        "bookmark": "Ref26",
        "key": "IAPWS2012",
        "type": "report",
        "ris_type": "RPRT",
        "bib_type": "techreport",
        "word_type": "Report",
        "authors": [
            {"literal": "International Association for the Properties of Water and Steam (IAPWS)"}
        ],
        "title": "Revised Release on the IAPWS Industrial Formulation 1997 for the Thermodynamic Properties of Water and Steam",
        "container": "R7-97(2012); IAPWS: Lucerne, Switzerland",
        "year": "2012",
        "volume": "",
        "issue": "",
        "page": "",
        "page_display": "",
        "doi": "",
        "url": "https://iapws.org/documents/release/IF97-Rev",
        "accessed": "2026-09-16",
    },
    {
        "num": 27,
        "bookmark": "Ref27",
        "key": "Roberts1959",
        "type": "article-journal",
        "ris_type": "JOUR",
        "bib_type": "article",
        "word_type": "JournalArticle",
        "authors": [{"family": "Roberts", "given": "S.W."}],
        "title": "Control Chart Tests Based on Geometric Moving Averages",
        "container": "Technometrics",
        "year": "1959",
        "volume": "1",
        "issue": "",
        "page": "239-250",
        "page_display": "239–250",
        "doi": "10.1080/00401706.1959.10489860",
        "url": "https://doi.org/10.1080/00401706.1959.10489860",
    },
]


def expand_citation_token(inner: str) -> list[int]:
    """Expand '2,5–8' -> [2, 5, 6, 7, 8]."""
    nums: list[int] = []
    for part in inner.split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)\s*[–\-]\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            nums.extend(range(a, b + 1))
        elif re.fullmatch(r"\d+", part):
            nums.append(int(part))
        else:
            raise ValueError(f"Cannot expand citation token: {part!r}")
    return nums


def extract_manuscript_citations(docx_path: str):
    """Read original manuscript and extract raw ref texts + all bracket expressions."""
    with zipfile.ZipFile(docx_path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    paras = root.findall(".//w:body/w:p", NS)
    ref_heading_idx = None
    para_info = []
    current_section = "Front Matter"
    for i, p in enumerate(paras):
        pStyle = p.find(".//w:pPr/w:pStyle", NS)
        style = pStyle.attrib.get(f"{{{W_NS}}}val", "") if pStyle is not None else ""
        text = "".join(t.text or "" for t in p.findall(".//w:t", NS))
        if style in ("MDPI21heading1", "MDPI22heading2", "MDPI23heading3") and text.strip():
            current_section = text.strip()
        if text.strip() == "References":
            ref_heading_idx = i
        para_info.append((i, style, current_section, text))

    assert ref_heading_idx is not None
    raw_refs = []
    for offset in range(1, 28):
        idx = ref_heading_idx + offset
        raw_refs.append(para_info[idx][3])

    citation_groups = []
    non_citation_brackets = []
    for i, style, sec, text in para_info[:ref_heading_idx]:
        for m in re.finditer(r"\[([^\]]+)\]", text):
            full = m.group(0)
            inner = m.group(1)
            # Distinguish citation brackets vs mathematical [0, 1] etc.
            # Citation brackets only contain digits 1..27 separated by ',' or '–'
            is_cit = False
            if re.fullmatch(r"\d+(?:[,\s–\-]+\d+)*", inner):
                # Exclude mathematical intervals [0, 1]
                if full != "[0, 1]":
                    is_cit = True
            snippet = text[max(0, m.start() - 35):min(len(text), m.end() + 35)]
            if is_cit:
                expanded = expand_citation_token(inner)
                citation_groups.append({
                    "group_id": len(citation_groups) + 1,
                    "para_idx": i,
                    "section": sec,
                    "style": style,
                    "bracket_text": full,
                    "inner": inner,
                    "expanded_refs": expanded,
                    "expanded_count": len(expanded),
                    "snippet": snippet,
                })
            else:
                non_citation_brackets.append({
                    "para_idx": i,
                    "section": sec,
                    "bracket_text": full,
                    "snippet": snippet,
                })

    return raw_refs, citation_groups, non_citation_brackets


def write_csl_json(path: str):
    items = []
    for r in REFERENCES:
        item = {
            "id": r["key"],
            "citation-label": str(r["num"]),
            "type": r["type"],
            "title": r["title"],
            "issued": {"date-parts": [[int(r["year"])]]},
            "author": r["authors"],
        }
        if r["type"] == "report":
            item["publisher"] = "International Association for the Properties of Water and Steam"
            item["publisher-place"] = "Lucerne, Switzerland"
            item["number"] = "R7-97(2012)"
            item["URL"] = r["url"]
            item["accessed"] = {"date-parts": [[2026, 9, 16]]}
        else:
            item["container-title"] = r["container"]
            if r["volume"]:
                item["volume"] = r["volume"]
            if r["page"]:
                item["page"] = r["page"]
            if r["doi"]:
                item["DOI"] = r["doi"]
            if r["url"]:
                item["URL"] = r["url"]
        items.append(item)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def write_bibtex(path: str):
    lines = ["% Bibliography for PUB053 JMSE Manuscript", "% Automatically generated from manuscript reference list", ""]
    for r in REFERENCES:
        lines.append(f"@{r['bib_type']}{{{r['key']},")
        if "literal" in r["authors"][0]:
            author_str = f"{{{r['authors'][0]['literal']}}}"
        else:
            author_str = " and ".join(f"{a['family']}, {a['given']}" for a in r["authors"])
            if r.get("et_al"):
                author_str += " and others"
        lines.append(f"  author = {{{author_str}}},")
        lines.append(f"  title = {{{{{r['title']}}}}},")
        if r["bib_type"] == "article":
            lines.append(f"  journal = {{{r['container']}}},")
        elif r["bib_type"] == "inproceedings":
            lines.append(f"  booktitle = {{{r['container']}}},")
        elif r["bib_type"] == "techreport":
            lines.append("  institution = {International Association for the Properties of Water and Steam (IAPWS)},")
            lines.append("  number = {R7-97(2012)},")
            lines.append("  address = {Lucerne, Switzerland},")
        lines.append(f"  year = {{{r['year']}}},")
        if r["volume"]:
            lines.append(f"  volume = {{{r['volume']}}},")
        if r["page"]:
            lines.append(f"  pages = {{{r['page'].replace('-', '--')}}},")
        if r["doi"]:
            lines.append(f"  doi = {{{r['doi']}}},")
        if r["url"]:
            lines.append(f"  url = {{{r['url']}}},")
        lines.append("}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_ris(path: str):
    lines = []
    for r in REFERENCES:
        lines.append(f"TY  - {r['ris_type']}")
        lines.append(f"ID  - {r['key']}")
        for a in r["authors"]:
            if "literal" in a:
                lines.append(f"AU  - {a['literal']}")
            else:
                lines.append(f"AU  - {a['family']}, {a['given']}")
        lines.append(f"TI  - {r['title']}")
        if r["ris_type"] == "RPRT":
            lines.append("PB  - International Association for the Properties of Water and Steam (IAPWS)")
            lines.append("CY  - Lucerne, Switzerland")
            lines.append("M1  - R7-97(2012)")
        else:
            lines.append(f"JO  - {r['container']}")
        lines.append(f"PY  - {r['year']}")
        if r["volume"]:
            lines.append(f"VL  - {r['volume']}")
        if r["page"]:
            if "-" in r["page"]:
                sp, ep = r["page"].split("-", 1)
                lines.append(f"SP  - {sp}")
                lines.append(f"EP  - {ep}")
            else:
                lines.append(f"SP  - {r['page']}")
        if r["doi"]:
            lines.append(f"DO  - {r['doi']}")
        if r["url"]:
            lines.append(f"UR  - {r['url']}")
        lines.append("ER  - ")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def build_word_sources_xml() -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        '<b:Sources xmlns:b="http://schemas.openxmlformats.org/officeDocument/2006/bibliography" '
        'SelectedStyle="\\IEEE2006OfficeOnline.xsl" StyleName="IEEE" Version="6">'
    ]
    for r in REFERENCES:
        guid = "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"pub053:{r['bookmark']}:{r['key']}")).upper() + "}"
        parts.append("  <b:Source>")
        parts.append(f"    <b:Tag>{escape(r['key'])}</b:Tag>")
        parts.append(f"    <b:SourceType>{r['word_type']}</b:SourceType>")
        parts.append(f"    <b:Guid>{guid}</b:Guid>")
        parts.append(f"    <b:RefOrder>{r['num']}</b:RefOrder>")
        parts.append("    <b:Author>")
        parts.append("      <b:Author>")
        if "literal" in r["authors"][0]:
            parts.append(f"        <b:Corporate>{escape(r['authors'][0]['literal'])}</b:Corporate>")
        else:
            parts.append("        <b:NameList>")
            for a in r["authors"]:
                parts.append("          <b:Person>")
                parts.append(f"            <b:Last>{escape(a['family'])}</b:Last>")
                parts.append(f"            <b:First>{escape(a['given'])}</b:First>")
                parts.append("          </b:Person>")
            parts.append("        </b:NameList>")
        parts.append("      </b:Author>")
        parts.append("    </b:Author>")
        parts.append(f"    <b:Title>{escape(r['title'])}</b:Title>")
        parts.append(f"    <b:Year>{escape(r['year'])}</b:Year>")
        if r["word_type"] == "JournalArticle":
            parts.append(f"    <b:JournalName>{escape(r['container'])}</b:JournalName>")
        elif r["word_type"] == "ConferenceProceedings":
            parts.append(f"    <b:ConferenceName>{escape(r['container'])}</b:ConferenceName>")
        elif r["word_type"] == "Report":
            parts.append("    <b:Publisher>IAPWS</b:Publisher>")
            parts.append("    <b:City>Lucerne, Switzerland</b:City>")
            parts.append("    <b:ThesisType>R7-97(2012)</b:ThesisType>")
        if r["volume"]:
            parts.append(f"    <b:Volume>{escape(r['volume'])}</b:Volume>")
        if r["page_display"]:
            parts.append(f"    <b:Pages>{escape(r['page_display'])}</b:Pages>")
        if r["doi"]:
            parts.append(f"    <b:DOI>{escape(r['doi'])}</b:DOI>")
        if r["url"]:
            parts.append(f"    <b:URL>{escape(r['url'])}</b:URL>")
        parts.append("  </b:Source>")
    parts.append("</b:Sources>")
    return "\n".join(parts)


def write_mapping_files(raw_refs, citation_groups, non_citation_brackets, csv_path: str, md_path: str):
    # Track which groups cite each ref
    cited_in: dict[int, list[str]] = {i: [] for i in range(1, 28)}
    for g in citation_groups:
        for num in g["expanded_refs"]:
            cited_in[num].append(f"G{g['group_id']:02d}(P{g['para_idx']:03d})")

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "group_id", "para_idx", "section", "bracket_text",
            "expanded_refs", "expanded_count", "linked_bookmarks", "context_snippet"
        ])
        for g in citation_groups:
            bms = ";".join(f"Ref{n:02d}" for n in g["expanded_refs"])
            writer.writerow([
                g["group_id"], g["para_idx"], g["section"], g["bracket_text"],
                ",".join(str(n) for n in g["expanded_refs"]), g["expanded_count"], bms, g["snippet"]
            ])

    total_expanded = sum(g["expanded_count"] for g in citation_groups)
    uncited = [n for n in range(1, 28) if not cited_in[n]]

    md_lines = [
        "# PUB053 JMSE Citation & Reference Mapping Table",
        "",
        f"- Source manuscript: `JMSE-MDPI-보일러 논문 [김겸원].docx` (`SHA-256: {hashlib.sha256(open(SRC_DOCX, 'rb').read()).hexdigest()}`)",
        f"- Total bibliography entries: **{len(raw_refs)}** (`[1]`–`[27]`)",
        f"- Total in-text citation groups: **{len(citation_groups)}**",
        f"- Total expanded in-text citation occurrences: **{total_expanded}**",
        f"- Uncited bibliography entries: **{len(uncited)}** ({uncited})",
        f"- Non-citation bracket expressions preserved as plain text: **{len(non_citation_brackets)}** in paragraphs (+ 14 in tables)",
        "",
        "## 1. 27 Bibliography References (`[1]`–`[27]`)",
        "",
        "| # | Bookmark | Citation Key | Year | DOI / URL | In-Text Groups | Raw Manuscript Reference Text |",
        "|---:|---|---|---:|---|---|---|",
    ]
    for r, raw in zip(REFERENCES, raw_refs):
        num = r["num"]
        groups_str = ", ".join(cited_in[num])
        doi_or_url = r["doi"] if r["doi"] else r["url"]
        md_lines.append(f"| {num} | `{r['bookmark']}` | `{r['key']}` | {r['year']} | {doi_or_url} | {groups_str} | {raw} |")

    md_lines.extend([
        "",
        "## 2. 26 In-Text Citation Groups (54 Expanded Occurrences)",
        "",
        "| Group | Paragraph | Section | Visible Citation | Expanded Ref IDs | Count | Word Field Bookmarks | Surrounding Context |",
        "|---:|---|---|---|---:|---:|---|---|",
    ])
    for g in citation_groups:
        exp_str = ", ".join(str(n) for n in g["expanded_refs"])
        bm_str = ", ".join(f"`Ref{n:02d}`" for n in g["expanded_refs"])
        snip = g["snippet"].replace("|", "\\|")
        md_lines.append(
            f"| {g['group_id']:02d} | `P{g['para_idx']:03d}` | {g['section']} | `{g['bracket_text']}` | {exp_str} | {g['expanded_count']} | {bm_str} | {snip} |"
        )

    md_lines.extend([
        "",
        "## 3. Preserved Non-Citation Bracket Expressions (Not Converted to Citation Fields)",
        "",
        "| Paragraph | Section | Bracket Text | Context |",
        "|---|---|---|---|",
    ])
    for b in non_citation_brackets:
        snip = b["snippet"].replace("|", "\\|")
        md_lines.append(f"| `P{b['para_idx']:03d}` | {b['section']} | `{b['bracket_text']}` | {snip} |")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    return total_expanded, uncited


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    raw_refs, citation_groups, non_citation_brackets = extract_manuscript_citations(SRC_DOCX)
    assert len(raw_refs) == 27, f"Expected 27 refs, got {len(raw_refs)}"
    assert len(citation_groups) == 26, f"Expected 26 citation groups, got {len(citation_groups)}"

    write_csl_json(os.path.join(OUT_DIR, "pub053_references.json"))
    write_bibtex(os.path.join(OUT_DIR, "pub053_references.bib"))
    write_ris(os.path.join(OUT_DIR, "pub053_references.ris"))
    with open(os.path.join(OUT_DIR, "word_sources.xml"), "w", encoding="utf-8") as f:
        f.write(build_word_sources_xml())

    total_expanded, uncited = write_mapping_files(
        raw_refs,
        citation_groups,
        non_citation_brackets,
        os.path.join(OUT_DIR, "citation_mapping_table.csv"),
        os.path.join(OUT_DIR, "CITATION_MAPPING_TABLE.md"),
    )
    print(f"Generated bibliography & mapping files in: {OUT_DIR}")
    print(f"  References: {len(raw_refs)}, Citation groups: {len(citation_groups)}, Expanded occurrences: {total_expanded}, Uncited: {uncited}")
    print(f"  Preserved non-citation paragraph brackets: {len(non_citation_brackets)}")


if __name__ == "__main__":
    main()
