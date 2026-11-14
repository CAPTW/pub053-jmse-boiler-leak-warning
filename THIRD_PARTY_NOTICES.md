# Third-Party Notices and Licensing Considerations

## 1. Repository License vs. `iapws` (GPL-3.0)
- The `boiler_pdm_sim` source snapshot in `simulator_source/` is licensed under the **MIT License** (`LICENSE`, Copyright (c) 2026 The Boiler PdM Simulator Contributors).
- One runtime thermodynamic dependency, **`iapws` (>= 1.5)**, is distributed under the **GNU General Public License v3.0 (GPL-3.0)**.
  - In `simulator_source/src/boiler_pdm_sim/core/thermo/if97.py` and `props/if97.py`, `iapws` (`IAPWS97`) is imported to generate/evaluate IAPWS-IF97 saturation tables (with 1,000-knot spline tables in `core/thermo/if97.py`).
  - Because binary or combined redistribution of derivative works statically bundling GPL-3.0 packages carries copyleft obligations, **no binary wheels or vendored `iapws` sources are bundled** in this repository. Users install external Python dependencies separately via `pip`.
  - Prior to tagging a public GitHub release, the authors should confirm whether to retain `MIT` for original code with external `iapws` installation or migrate spline knot generation to a permissive-licensed implementation.

## 2. Journal Template Exclusion
- The MDPI JMSE Microsoft Word template (`jmse-template.dot`) and formatted manuscript `.docx`/`.pdf` files are **intentionally excluded** from this public software repository (see `.gitignore`) so third-party publisher templates are not redistributed.

## 3. Core Scientific Dependencies (Installed via PyPI by User)
- `numpy`, `scipy`, `pandas`, `pyarrow`, `PyYAML`, `python-dateutil`, `Pillow`, `pytest`, `python-docx`, `lxml` — BSD / MIT / HPND / Apache-2.0 permissive licenses.
- Offline review helpers such as `PyMuPDF` / `fitz` (AGPL-3.0) are **not** required by any script in `manuscript_verification/` or `simulator_source/` and are excluded from dependencies.
