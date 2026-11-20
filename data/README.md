# Data and input files

[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](../docs/README.md)

The public repository provides episode metadata, reconstructed table inputs and a base simulator configuration. The original trajectory files and study-specific applied configurations are supplied separately by the corresponding author upon reasonable request.

## Included here

| File or directory | Contents |
|---|---|
| [episode_metadata.csv](episode_metadata.csv) | Names, design fields and event timings for 24 episodes |
| [block_design.json](block_design.json) | Four development blocks, eight evaluation blocks and the recorded seed correction |
| [original_configs/](original_configs/README.md) | Base simulator YAML and its relation to the study configurations |
| [reconstructed_inputs/](reconstructed_inputs/README.md) | Five JSON files covering Tables 1–5 and 7 |

The study has 12 paired blocks: one normal and one tube-leak episode per block. Each episode lasts six hours and has 10,801 samples at two-second intervals, for 259,224 timestamps across 24 episodes.

The reconstructed JSON files preserve table inputs recovered from reference records. They are not replacements for the original observation arrays or the complete study runtime configurations.

## External source packages

| Package | Role | Material not included in this repository |
|---|---|---|
| `PUB053_Manuscript_Package_R2.zip` | Stored-data reanalysis | 24 observation NPZ files, 24 trace NPZ files and per-episode applied configurations |
| `observable_baseline_study_20260915T215200Z_be142b32.zip` | Original simulation execution | Study-patched `source_copy/`, execution configurations, exogenous inputs and run outputs |

The R2 analysis reads stored trajectories. Recreating the original simulation execution additionally requires the study-time source and inputs. The public [simulator snapshot](../docs/SOURCE_PROVENANCE.md) is the development base, not the exact study-patched working tree.

## Raw input layout

For full raw replay, place the original files at these repository-relative paths:

~~~text
data/observations/<episode>.npz
data/traces/<episode>.npz
~~~

Use every episode name in [episode_metadata.csv](episode_metadata.csv): `D1_normal` through `D4_tube_leak` for development and `E1_normal` through `E8_tube_leak` for evaluation. Each of the 24 episode names must have both files, giving **48 required NPZ files**.

Do not rename reconstructed JSON files to stand in for missing raw inputs. The [analysis scripts](../code/README.md) check the required episode paths.

## Run the appropriate checks

Follow the [quick start](../REPRODUCIBILITY.md) for the public clone. It uses explicit archive options because the raw files are not bundled.

When all required NPZ files are supplied, the scripts select raw replay even if an archive option was also passed. A missing or incomplete raw set stops default execution with exit code `1`; explicit archive options permit checks of the public tables and figures.

The [locked dependencies](../requirements-lock.txt) pin `iapws==1.5.5`. The runtime helper checks whether the backend is usable and reports its installed version; it does not enforce a strict version match. Backend metadata is collected before a missing-input error is returned.

For exact commands, report fields and approximate-density limitations, use the [detailed reproduction guide](../docs/REPRODUCTION_GUIDE.md). For the origin of each material, use [data provenance](../docs/DATA_PROVENANCE.md).
