# Third-party notices and reuse

[Home](README.md) · [Documentation](docs/README.md) · [Environment setup](REPRODUCIBILITY.md)

This page separates the source-code license, the existing conditions for research materials, and external dependencies. It does not extend one component's license to another.

## Source code

The companion Python scripts in `code/` and `manuscript_verification/` carry the [MIT license](LICENSE). The preserved `boiler_pdm_sim` snapshot carries its [upstream MIT notice](simulator_source/LICENSE), Copyright (c) 2026 The Boiler PdM Simulator Contributors.

## Research materials

The existing reuse conditions for this repository are:

> Reconstructed structured tables, archived verification CSV/JSON files, and author-created figures are published strictly for scholarly review, peer verification, and non-commercial academic reproducibility unless superseded by final MDPI JMSE open-access publication terms.

These conditions concern the materials in `data/`, `results/`, `results_archived/`, and `figures/`. They are separate from the source-code MIT license. This documentation update does not select a new data or figure license.

The journal template and formatted submission DOCX/PDF are excluded from the public repository. No blanket MIT license is claimed over third-party dependencies or publisher-formatted assets.

## Required thermodynamic dependency

The pinned reproduction environment uses **`iapws==1.5.5`**, an external GPL-3.0 package. It is declared in [requirements-lock.txt](requirements-lock.txt), [environment.yml](environment.yml), and [project metadata](pyproject.toml).

Install it through the pinned requirements. No `iapws` source, wheel, or virtual environment is bundled in this repository; the package retains its own license.

The analysis scripts use `iapws.IAPWS97` for the reference density calculation. Their backend helper reports availability and installed version; it does not reject a different installed version merely because its version string differs from `1.5.5`. If the backend is unavailable, full raw-data execution stops unless the approximate-density option is explicitly selected. See [reproduction behavior and limits](docs/REPRODUCTION_GUIDE.md).

The simulator's `props/if97.py` imports `iapws` directly. Other preserved simulator modules have separate approximation behavior; their presence does not establish that an approximate run reproduces the paper.

## Other dependencies

| Use | Packages or tools | Where to look |
|---|---|---|
| Analysis and plots | NumPy, SciPy, pandas, Matplotlib, PyArrow, PyYAML, python-dateutil, Pillow, lxml | [Pinned requirements](requirements-lock.txt) |
| Simulator tests | pytest | [Detailed guide](docs/REPRODUCTION_GUIDE.md) |
| Optional manuscript assembly | python-docx | [Manuscript tools](manuscript_verification/MANUSCRIPT_ARTIFACT_MAP.md) |
| Optional Microsoft Word automation | pywin32, Windows, and installed Microsoft Word | [Citation editing evidence](manuscript_verification/CITATION_EDITING_TEST_REPORT.md) |
| Optional PDF inspection | Poppler `pdftotext` and `pdfinfo` system commands | [Manuscript verification](manuscript_verification/LATEST_MANUSCRIPT_VERIFICATION_REPORT.md) |
| Optional upstream simulator integrations | PyTables and FMPy | [Upstream project metadata](simulator_source/pyproject.toml) |

Each dependency is distributed under its own license and notices. Optional manuscript and simulator tools are not required for the public archive-verification commands. Use the documented requirements installation, rather than root-level editable installation.
