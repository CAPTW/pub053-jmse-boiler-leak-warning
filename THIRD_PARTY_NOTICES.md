# Third-Party Notices and Licensing Boundaries

## 1. Code License vs. External `iapws` Dependency (GPL-3.0)
- The `boiler_pdm_sim` source snapshot in `simulator_source/` (`LICENSE`, Copyright (c) 2026 The Boiler PdM Simulator Contributors) and the companion verification/reproduction Python scripts in `code/` and `manuscript_verification/` carry the **MIT License** where permitted by upstream author notice.
- One optional runtime thermodynamic dependency, **`iapws` (>= 1.5)**, is distributed under the **GNU General Public License v3.0 (GPL-3.0)**.
  - In `simulator_source/src/boiler_pdm_sim/core/thermo/if97.py` and `props/if97.py`, `iapws` (`IAPWS97`) is imported when available to generate/evaluate IAPWS-IF97 saturation tables (with 1,000-knot spline tables in `core/thermo/if97.py`); when `iapws` is absent (and `BOILER_STRICT_PROPS` is unset), the simulator uses built-in lightweight approximate properties.
  - Because combined or binary redistribution of works bundling GPL-3.0 libraries carries copyleft obligations, **no binary wheels, virtual environments, or vendored `iapws` sources are bundled** in this repository. Users who enable strict IF97 lookup install external `iapws` separately from PyPI and comply with its GPL-3.0 license.

## 2. Scientific Data, Figures, and Excluded Journal Assets
- **Excluded Journal Template & Formatted Manuscript Files**: The MDPI JMSE Microsoft Word template (`jmse-template.dot`) and formatted manuscript `.docx`/`.pdf` files are **intentionally excluded** from this public GitHub repository (`.gitignore`), as redistribution rights belong to MDPI / author submission agreements.
- **Data (`data/`, `results/`, `results_archived/`) and Author-Generated Figures (`figures/`)**: Reconstructed structured tables, archived verification CSV/JSON files, and author-created figures are published strictly for scholarly review, peer verification, and non-commercial academic reproducibility unless superseded by final MDPI JMSE open-access publication terms. No blanket MIT license is claimed over third-party dependencies or publisher-formatted assets.

## 3. Core Scientific Dependencies (Installed via PyPI by User)
- `numpy`, `scipy`, `pandas`, `matplotlib`, `pyarrow`, `PyYAML`, `python-dateutil`, `Pillow`, `pytest`, `lxml`, `python-docx` (optional) — BSD / MIT / PSF / HPND / Apache-2.0 permissive or standard Python ecosystem licenses.
- `PyMuPDF` / `fitz` (AGPL-3.0) and `pywin32` (PSF) are **not** required for headless data/code reproduction (`code/` and `simulator_source/`). Windows Word COM helpers are only invoked optionally for local DOCX field-update testing (`--update-word`).
