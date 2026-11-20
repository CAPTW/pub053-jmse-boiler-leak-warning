# Closed-Loop Tube-Leak Early Warning

**Research companion for PUB-053 · Marine auxiliary boiler simulation**

[Quick start](REPRODUCIBILITY.md) · [Documentation](docs/README.md) · [Figures](figures/FIGURE_MAP.md) · [Cite this work](CITATION.cff)

This repository supports the manuscript:

> **Closed-Loop Tube-Leak Early Warning in a Four-State Marine Auxiliary Steam Boiler: Demand-Versus-Flow Residuals, Functional Lead Times, and Component Attribution**

The study examines how closed-loop boiler control can mask a tube leak and compares four warning methods: state-only, flow-only, demand-only, and combined detection. It uses 24 deterministic six-hour episodes arranged in four development blocks and eight evaluation blocks. R2 is a reanalysis of stored simulation outputs.

The manuscript cites the frozen [v1.0.6-pub053-r2 research release](https://github.com/CAPTW/pub053-jmse-boiler-leak-warning/releases/tag/v1.0.6-pub053-r2). The default branch carries maintained documentation. Use the release tag to identify the research version and these guides for current instructions.

## What is available?

| Included in this repository | Not bundled in this repository |
|---|---|
| R2 analysis and verification scripts | 24 observation and 24 score-trace NPZ files |
| Episode metadata and reconstructed table inputs | Per-episode applied configurations |
| Reference results, manuscript figures, and bibliography | Study-time patched simulator and original run archive |
| Base simulator source snapshot and verification records | Formatted submission DOCX/PDF |

**A public clone can verify the bundled tables and figure assets. Full reconstruction from the original trajectories requires the 48 external NPZ files.** The public base simulator snapshot also differs from the patched copy used for the original study. See [data provenance](docs/DATA_PROVENANCE.md) and [source provenance](docs/SOURCE_PROVENANCE.md) before interpreting a reproduction result.

## Start with the public files

Use the [Python 3.12 setup instructions](REPRODUCIBILITY.md), then run these commands from the repository root:

```bash
python -B code/verify_features.py --archived-tables-only --out results_reproduced
python -B code/reproduce_analysis.py --archived-tables-only --out results_reproduced
python -B code/make_figures_r2.py --archived-assets-only --results results_reproduced --out figures_reproduced
```

These commands write to new output directories. Archive mode checks stored results and reconstructs Figure 4 from the episode-result table; the other figures use preserved assets. It does not reconstruct the original time series.

Run the isolated unit tests with `python -B code/test_analysis.py`. Tests use synthetic fixtures, so their success is separate from reproducing the original study data.

For raw-data reconstruction, expected exit codes, numerical comparisons, and optional checks, follow the [detailed reproduction guide](docs/REPRODUCTION_GUIDE.md). Default raw commands return an error when required inputs are missing.

## Explore the repository

| Area | Contents |
|---|---|
| [Analysis code](code/README.md) | Script purposes, inputs, and output reports |
| [Data](data/README.md) | Episode registry, table inputs, and external-file layout |
| [Reference results](results/README.md) | Frozen CSV/JSON results and their meanings |
| [Figures](figures/FIGURE_MAP.md) | Figures 1–7, source assets, and rendering definitions |
| [Simulator source](docs/SOURCE_PROVENANCE.md) | Base snapshot, study-time differences, and exclusions |
| [Manuscript verification](manuscript_verification/MANUSCRIPT_ARTIFACT_MAP.md) | Table checks, citation tools, and document evidence |
| [Bibliography](references/CITATION_MAPPING_TABLE.md) | 27 references and their in-text citation groups |
| [Verification archive](results_archived/README.md) | R2 records, current manuscript checks, and earlier draft checks |

## Evidence and limits

The [reproduction guide](docs/REPRODUCTION_GUIDE.md) explains what each check establishes. The [known limitations](docs/KNOWN_LIMITATIONS.md) distinguish archive checks, original-data reconstruction, and simulation regeneration. The [file manifest](docs/FILE_MANIFEST.md) records the current public file identities.

Preserved execution records describe the inputs and environments used for those runs. They are not an unconditional guarantee that every test or every environment passes.

## AI assistance

OpenAI Codex was the principal AI coding tool for the boiler simulator and `ab4` physical model under author specification and review. Antigravity assisted with manuscript preparation, citation automation, and companion-repository assembly. The [AI usage statement](docs/AI_USAGE_AUDIT.md) separates these roles from unverified private session details. The authors retain responsibility for the work.

## Citation and reuse

Use [CITATION.cff](CITATION.cff) for software and manuscript attribution. No journal acceptance, publication date, or DOI is asserted here.

Repository source code is covered by the [MIT license](LICENSE). Data, figures, third-party libraries, and publisher assets have separate conditions described in [Third-party notices and reuse](THIRD_PARTY_NOTICES.md). In particular, `iapws` is an external dependency with its own license.
