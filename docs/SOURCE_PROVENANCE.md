[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](README.md)

# Simulator source provenance

The [simulator_source](../simulator_source/) directory is a preserved source
snapshot containing **156 files**. It provides the boiler model and its tests
for inspection. It is not the exact study-time working tree that generated the
manuscript trajectories.

## Public identity

| Reference | What it identifies |
|---|---|
| Local development base `4fea4646723f04db41583cb682bac8b62c44bc05` | The upstream base recorded during original packaging. |
| [v1.0.6 release](https://github.com/CAPTW/pub053-jmse-boiler-leak-warning/releases/tag/v1.0.6-pub053-r2) | The frozen companion version cited by the manuscript. |
| [Current file manifest](FILE_MANIFEST.json) | Paths, byte counts and SHA-256 hashes for this documentation checkout. |

The upstream development history is private and is not included here. The local
base identifier alone is not a publicly retrievable upstream release. Use the
public companion commit and its file manifest to identify the distributed bytes.
Read the manifest from the same commit or tag as the files you are checking.

## Base settings and study settings

The original simulation archive,
`observable_baseline_study_20260915T215200Z_be142b32.zip`, contains the study-time
`source_copy/`, including pilot and study economizer-leak patches and their
applied configurations.

| Setting | Public base snapshot | Recorded study setup |
|---|---|---|
| Time step | `1.0 s` | `2.0 s` |
| Closed-loop source | `truth` | `obs` |
| Episode horizon | `3,600 s` | `21,600 s` |
| Study patches | Not applied to this snapshot | Preserved in the external study archive |

The public values are in [ab4_marine_aux.yaml](../simulator_source/configs/ab4_marine_aux.yaml).
The recorded study protection policy is
`process_protection_without_schedule_severity_oracle`. It is a study-time
configuration detail, not a claim that the public base YAML reproduces that setup.

Use the separate [R2 archive](DATA_PROVENANCE.md#study-and-archive-lineage) for
reanalysis of frozen observations. To regenerate the original simulation, obtain
the actual study-time source, settings and inputs. Do not apply a patch again to
a study copy that already includes it.

## Historical packaging comparison

The [original v1.0.6 packaging record](https://github.com/CAPTW/pub053-jmse-boiler-leak-warning/blob/v1.0.6-pub053-r2/docs/SOURCE_PROVENANCE.md)
reported the following comparison with the author's local upstream files:

| Files | Recorded relationship at initial packaging |
|---:|---|
| 146 | Matched the local base Git blobs. |
| 8 | Matched workstation files with line-ending differences from the base blobs. |
| 1 | Specification document matched the workstation copy. |
| 1 | License copied from the upstream root. |

These are historical packaging statements, not a fresh comparison with private
upstream history. Earlier workstation byte hashes can differ from normalized
public files. The current [machine-readable manifest](FILE_MANIFEST.json) and
[readable inventory](FILE_MANIFEST.md) are the byte-identity references; a second
independently maintained hash table is intentionally avoided.

## Snapshot exclusions and inherited documentation

The snapshot omits private Git history, environments, bulk research datasets,
external FMUs and upstream workspace/support files that are not part of the
selected source distribution.

The preserved upstream README and design documents describe that larger
development workspace. Some example commands refer to excluded scripts or
directories. In particular, the design document's `../blueprint.md` link points
to an excluded upstream file. Follow this companion's
[reproduction guide](REPRODUCTION_GUIDE.md) for commands supported by the public
layout; the upstream documents remain unchanged as source records.

Two tests in the retained non-slow simulator suite also refer to excluded
workspace/governance files. Their failures are disclosed in
[known limitations](KNOWN_LIMITATIONS.md#simulator-test-scope). This does not
change the identity or scope of the seven core modules' recorded test results.

## License and attribution

The snapshot retains its [upstream MIT license](../simulator_source/LICENSE).
External dependencies have separate terms described in
[third-party notices](../THIRD_PARTY_NOTICES.md). AI-assisted development roles
and the limits of the available session evidence are documented in
[AI usage](AI_USAGE_AUDIT.md).
