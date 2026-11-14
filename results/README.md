# Preserved R2 Reference Results (`results/`)

This directory holds the immutable preserved reference outputs from the R2 stored-data reanalysis (`24` paired 6 h episodes, `259,224` total samples, `96` episode–detector evaluations), mirrored from `results_archived/`.

- **Do not overwrite `results/` during reproduction runs.**
- When running `code/verify_features.py --out results_reproduced` and `code/reproduce_analysis.py --out results_reproduced`, outputs are written to `results_reproduced/` and numerically diffed against this directory.
- Historical prior-draft QA records (`ce0e9a0e...`) and manuscript-specific table checks live separately under `results_archived/prior_draft_review_ce0e9a0e/` and `results_archived/current_manuscript_verification/`.
