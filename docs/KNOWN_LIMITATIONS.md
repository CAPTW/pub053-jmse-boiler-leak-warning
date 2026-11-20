[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](README.md)

# Known limitations

This page states the limits of the public companion and its recorded evidence.
Use the [reproduction guide](REPRODUCTION_GUIDE.md) for commands and detailed
report interpretation.

## Public data coverage

The public clone contains no original NPZ files. The 48 observation/trace
archives, per-episode applied configurations and study-patched source tree are
external inputs. Public-only checks can verify preserved tables and synthetic
fixtures; they cannot refit or independently regenerate the original trajectories.
See [data provenance](DATA_PROVENANCE.md).

The included simulator is a base snapshot, with different time-step and feedback
settings from the study. It is not a drop-in copy of the complete execution
archive. See [source provenance](SOURCE_PROVENANCE.md).

## Numerical and figure checks

- Use the pinned Python 3.12 environment, including `iapws==1.5.5`, for the
  documented IF97 calculations. The runtime reports backend availability and
  version; it does not enforce version equality by itself.
- An explicit `--allow-approx-density` run is diagnostic. It can produce different
  scores, thresholds and numerical comparisons.
- Figure generation can succeed with the approximate backend. Read the backend
  and override fields; successful plotting does not establish IF97 equivalence.
- Archive figure mode regenerates Figure 4 from CSV, recomposes Figures 1–2 and
  copies Figures 3 and 5–7. It does not regenerate the missing raw curves.
- CSV comparison success is based on numerical, key and display-format rules.
  It does not imply byte identity. Image metadata and rendering can also differ
  across plotting environments.

Without an archive opt-in, missing raw inputs produce an error before
reconstruction and plotting, after backend metadata has been collected.
Archive flags do not force archive mode when all 48 raw files are present. See the
[mode and exit-code table](REPRODUCTION_GUIDE.md#4-read-the-reports-and-exit-codes).

## Synthetic-test scope

The eight companion tests use isolated synthetic fixtures. With `iapws` available,
the forced-fallback test expects 132 array comparisons to pass and 12 to fail.
When it is unavailable, that IF97 comparison branch is skipped. A passing
synthetic suite alone does not prove reproduction of the external study data.

## Simulator-test scope

These are historical results retained with the v1.0.6 release:

| Test selection | Recorded outcome |
|---|---|
| Seven core physics/property/protocol modules, with `iapws==1.5.5` | 88 passed |
| Non-slow suite: `pytest -m "not slow"` | 151 passed, two skipped, one deselected, two failed |
| Seven non-`iapws` contract/smoke modules | 45 passed, one skipped |

The two non-slow failures are
`test_governance_policy_enforces_classification_and_retention` and
`test_workspace_compatibility_paths_exist`. They require excluded upstream
workspace/governance files. The two skipped items are external-FMU tests; the
deselected item is the slow 24 h gate. These results do not establish that the
entire simulator suite passes or that the slow gate was rerun.

Evidence: [fresh-clone log](execution_logs/fresh_clone_reproduction_log.json)
and [non-slow integration log](execution_logs/pytest_ab4_integration_log.txt).

## Manuscript and citation evidence

Formatted manuscript files and the journal template are not distributed here.
Static reports identify their DOCX/PDF inputs by SHA-256. Historical Word COM
logs record citation editing operations but do not contain an input hash or
execution timestamp sufficient to bind those operations to the latest DOCX.

Do not treat a reused dynamic log as a new Word COM execution. The
[manuscript verification report](../manuscript_verification/LATEST_MANUSCRIPT_VERIFICATION_REPORT.md)
separates the evidence. Local Microsoft Word checks require Word and Windows;
static or LibreOffice checks do not substitute for a fresh Word COM run.

## Installation and inherited source examples

The supported companion setup is `python -m pip install -r requirements-lock.txt`
in an isolated Python 3.12 environment. Editable installation of the repository
root is not a supported workflow: the current flat layout contains multiple
top-level packages. Optional manuscript tools can be installed directly as
described in [third-party notices](../THIRD_PARTY_NOTICES.md).

Preserved upstream documents may refer to files excluded from this snapshot.
The current companion guide, rather than those historical workspace examples,
defines the supported reproduction procedure.

## Evidence and publication status

The v1.0.6 tag remains the manuscript's frozen cited version. Later documentation
maintenance on `main` does not modify the tag or create new scientific evidence.
Private development-session details in the [AI disclosure](AI_USAGE_AUDIT.md)
are author-reported history; the underlying private session database is not
published here. This repository does not establish journal acceptance or a
publication DOI.
