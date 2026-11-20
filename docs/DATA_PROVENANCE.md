[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](README.md)

# Data provenance

This page distinguishes original simulation outputs, the R2 stored-data analysis
and the material included in the public companion repository. For commands and
mode selection, use the [reproduction guide](REPRODUCTION_GUIDE.md).

## Study and archive lineage

The study contains 12 paired blocks: D1–D4 for development and E1–E8 for evaluation.
Each block has a normal episode and a tube-leak episode, giving **24 six-hour
episodes**. At the stored 2 s interval, each episode has 10,801 samples:
259,224 sample times across the dataset.

| Stage | Archive | Purpose |
|---|---|---|
| Original simulation | `observable_baseline_study_20260915T215200Z_be142b32.zip` | Study-time source, applied settings, exogenous inputs and run outputs. |
| R2 reanalysis | `PUB053_Manuscript_Package_R2.zip` | Frozen observations and detector traces, metadata, applied configurations and analysis results. |
| Public companion | This repository | Selected source, structured inputs, reference results, figures and verification tools. |

The original study generated the trajectories. R2 read those frozen outputs;
it did not generate a new simulation or alter the physical states.

## Included in the public repository

| Location | Contents | Provenance |
|---|---|---|
| [Episode metadata](../data/episode_metadata.csv) | 24 episodes, expected NPZ paths and recorded event metadata. | R2 study registry. |
| [Block design](../data/block_design.json) | Development/evaluation blocks, seeds and leak schedule. | Structured design recovered for the companion. |
| [Base configuration](../data/original_configs/ab4_marine_aux.yaml) | Marine auxiliary boiler base settings. | Public simulator snapshot; not the applied study configuration. |
| [Reconstructed inputs](../data/reconstructed_inputs/) | Five JSON files covering Tables 1–5 and 7. | Archived results, source constants and R2 supplement. |
| [Reference results](../results/) | Preserved R2 CSV/JSON outputs. | Fixed comparison targets for reanalysis. |
| [Archived records](../results_archived/) | R2 results and separate manuscript-check records. | Each subdirectory identifies its target and scope. |
| [Figures](../figures/) | Manuscript figures and source image assets. | Preserved R2 graphics and manuscript composition. |

Reconstructed parameter JSONs support internal consistency checks. They do not
replace the observations needed to refit the model or regenerate the time series.
The normal-persistence table contains 12 normal episodes, while Table 8 reports
the eight evaluation blocks; those counts refer to different scopes.

## External inputs

The following are **not bundled** in the public repository:

- 24 `data/observations/<episode>.npz` files and 24 `data/traces/<episode>.npz` files.
- Per-episode `data/original_configs/*_config_applied.json` files.
- The study-patched `source_copy/`, complete execution settings and exogenous inputs
  from the original simulation archive.

The original archives are retained by the study owner. The manuscript's data
availability arrangement is to provide them through the corresponding author
upon reasonable request. This statement does not make them downloadable from
the public clone.

The NPZ files used by the companion reanalysis belong to the R2 archive. The
original simulation archive has a different role and layout. Do not substitute
the public base YAML for an applied per-episode study configuration.

## Recomputed, reconstructed and preserved outputs

Keep the reference directories unchanged and write new results to separate output
directories. Reports distinguish these categories:

| Report category | Meaning |
|---|---|
| `recomputed_from_raw_inputs` | Derived from original NPZ inputs during that run. |
| `compared_against_reference_results` | Compared with the preserved reference outputs. |
| `archived_table_internal_checks` | Checked within supplied tables or reconstructed parameters. |
| `preserved_or_copied_artifacts` | Retained or copied assets, not newly measured outputs. |
| `unexecuted_items` | Work the selected mode did not perform. |

Figure manifests additionally identify plots rendered from NPZ or CSV, images
recomposed from preserved assets, and copied reference panels. See the
[figure map](../figures/FIGURE_MAP.md) for each figure's source.

Raw-mode analysis extracts process-trip and model-domain-exit timing from NPZ
channels and reports whether a fallback was used. Archive-mode checks use the
bundled metadata and tables. Their conclusions must retain that distinction.

## Related records

- [Source provenance](SOURCE_PROVENANCE.md): base snapshot versus study-time source.
- [Manuscript artifact map](../manuscript_verification/MANUSCRIPT_ARTIFACT_MAP.md): table and figure origins.
- [Known limitations](KNOWN_LIMITATIONS.md): limits of public-only verification.
- [Third-party notices](../THIRD_PARTY_NOTICES.md): existing code, data and figure terms.
