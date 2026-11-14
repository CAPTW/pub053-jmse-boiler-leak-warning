# AI Tooling & Provenance Audit (`PUB-053`)

This document provides an evidence-backed audit of generative AI / coding-agent tooling used across the `boiler_pdm_sim` upstream simulator repository and preparation of the JMSE manuscript (`PUB-053`), matching **Section 2.4** and **Acknowledgments**.

## 1. Upstream Simulator Development (`boiler_pdm_sim` & `ab4` Core)
- **Upstream Git Repository**: `https://github.com/CAPTW/boiler-pdm-sim.git` (`HEAD commit 4fea4646723f04db41583cb682bac8b62c44bc05`).
- **Principal AI Coding Tool**: **OpenAI Codex** assisted with software engineering, boilerplate module structuring, spline IAPWS-IF97 refactoring, closed-loop wiring, and pytest authoring under author physical specification and verification.
- **Verified Local Codex CLI Records (`state_5.sqlite`)**:
  - `2026-03-07` to `2026-04-16`: 46 Codex CLI threads using `cli_version` `0.104.0` through `0.119.0-alpha.28` with logged models `gpt-5.3-codex-spark` and `gpt-5.4` across earlier `Boiler` scaffolding and compatibility tracks.
  - `2026-06-29`: Codex CLI `0.142.3` (`gpt-5.5` default profile `xhigh`) recorded workspace migration preparation prior to final Phase A commits.
- **Recorded Phase A Git Commits (`2026-06-11` to `2026-06-30`)**:
  - `bb0c2d54`..`e9414e01` (`2026-06-11`–`2026-06-12`): Baseline snapshot, opaque backend contract (`WP A1`), review hardening.
  - `4ac933b1` (`2026-06-30 15:56`): `WP A2` (`props/if97.py`, `props/fuels.py`, `props/gas.py`).
  - `228d927c`, `83687240`, `25cc6379`, `5c25dcca` (`2026-06-30 16:05`–`16:42`): `WP A3` (`core/ab4/drum_model.py`, `geometry.py`, `feedwater.py`, `steam_line.py`, hydraulics, configs, pipeline tests).
  - `0ac3e249`, `3f14b0d0` (`2026-06-30 17:26`–`17:44`): `WP A4` (`core/ab4/furnace.py`, combustion/flue-gas modules).
  - `e2fc455d`, `4fea4646` (`2026-06-30 18:27`–`20:23`): `WP A5` (`pipeline/step_loop.py` closed-loop `obs` wiring, 24 h conservation & cross-model gates).
- **Verified Database Boundary (Unconfirmed / External Records)**: Per-session Codex CLI model logs for the separate-workstation `2026-06-30` commits are not stored in the local CLI SQLite database and therefore only the locally recorded versions/models (`0.104.0`–`0.142.3`; `gpt-5.3-codex-spark`, `gpt-5.4`, `gpt-5.5`) are claimed. Upstream `PR_BODY.md` also carries a Claude Code PR-summary footer dated `2026-06-30`.

## 2. Boundary Between Simulation Generation, R2 Reanalysis, and Manuscript Assembly
- **Original Deterministic Simulation**: The 24 paired 6 h episode trajectories (`observable_baseline_study_20260915T215200Z_be142b32.zip`) were generated once by the deterministic `boiler_pdm_sim` / `ab4` simulator.
- **R2 Stored-Data Reanalysis**: Preserved R2 scripts (`code/reproduce_analysis.py`, `code/verify_features.py`, `code/test_analysis.py`, `code/make_figures_r2.py`) read frozen `.npz` trajectories only; they **did not generate new simulation trajectories or alter physical states**.
- **JMSE Template Assembly, `<w:sdt>` + Live `REF` Citation Automation & Verification**: Google Antigravity and deterministic Python scripts (`build_full_paper.py`, `combine_normal_figs.py`, `create_automated_citation_docx.py`, `sync_citations_and_references.py`, `word_update_export_and_test.py`, `verify_revised_manuscript.py`, `verify_tables_from_archived_results.py`, `verify_citations_and_manuscript.py`, `check_cutoff_leads.py`, `check_delay_window.py`, `independent_numeric_review.py`) assembled the JMSE template, built structured Word citation controls, and cross-checked Tables 1–8 without modifying underlying numerical results.
- **Author Supervision & Verification Scope**: Authors specified physical equations, scenarios, detector rules, and verification gates, inspected `ab4` unit/integration tests and multi-scenario Word citation reordering tests, and take full scientific responsibility.
