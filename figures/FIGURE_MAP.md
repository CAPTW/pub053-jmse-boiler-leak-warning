# Figures 1–7

[Home](../README.md) · [Quick start](../REPRODUCIBILITY.md) · [Documentation](../docs/README.md)

The images in this directory are preserved manuscript assets. Generate new outputs in a separate directory using [make_figures_r2.py](../code/make_figures_r2.py).

## Figure index

| Figure | Preserved image | Subject |
|---|---|---|
| 1 | [Normal overview](fig1_normal_overview.png) | Conditioned pressure and drum level |
| 2 | [Leak trajectory](fig2_e1_leak_trajectory.png) | Regulated pressure, observed level and feedwater command |
| 3 | [Flow responses](fig3_e1_feature_responses.jpeg) | Observed feedwater and steam flow |
| 4 | [Detector comparison](fig4_method_summary_delay_lead.png) | Confirmed post-onset alarm delay |
| 5 | [Normalized scores](fig5_e1_score_traces.png) | Four detector scores and alarm markers |
| 6 | [Evaluation milestones](fig6_all_eval_leak_panels.jpeg) | Functional and terminal events |
| 7 | [Normal exceedance spans](fig7_normal_score_traces.jpeg) | Persistence behaviour without a leak |

## Generation modes

| Figures | Full raw replay | Archive mode |
|---|---|---|
| 1–2 | Replot from raw inputs | Recompose preserved source images |
| 3, 5–7 | Replot from raw inputs | Copy preserved images |
| 4 | Plot the selected episode-results CSV | Plot the selected episode-results CSV |

Raw replay uses the complete 48-file NPZ input set. Archive mode does not reconstruct the original trajectories. A generated image can be valid without being a numerical-equivalence test; consult the manifest fields described in the [reproduction guide](../docs/REPRODUCTION_GUIDE.md).

## Figure 1: normal operation

**Input:** `E1_normal`, episode time `0–6 h`.

The two panels show conditioned pressure in bar and drum level in metres, with reference lines at `7.0 bar` and `0.85 m`. Monitoring starts at `1,200 s`.

The preserved figure stacks R2 Supplement Figures S2 and S3 with a 30-pixel gap: [pressure asset](raw_source_assets/page1_img3_1261.jpeg) and [level asset](raw_source_assets/page1_img4_1265.jpeg).

## Figure 2: leak trajectory

**Input:** `E1_tube_leak`.

The raw plot interval is `[1200, min(t_end, T_confirm + 300)] s`, or **1,200–11,194 s** for this episode.

- Panel (a): observed pressure, with the `7.0 bar` reference.
- Panel (b): observed level only, with the `0.85 m` setpoint and `0.75 m` oracle criterion.
- Panel (c): `u_fw`, `u_fw_bar` and `u_ref`, with the `0.95` command reference.

Plant-truth level is used to determine the **10,774–10,894 s** endpoint-dwell band. It is not drawn as a separate level curve.

The preserved image comes from [R2 Main Figure 1](raw_source_assets/rId27.png), with a 32-pixel white bottom margin added to protect the x-axis label.

## Figure 3: flow responses

**Input:** `E1_tube_leak` over **1,200–11,194 s**.

The single panel compares observed feedwater `q_f` and observed steam `q_s` in `kg/s`. It marks leak onset at `3,374 s` and the **10,774–10,894 s** endpoint-dwell interval. Default plotting margins can extend the visible x-axis beyond the selected sample interval.

The preserved image is [R2 Supplement Figure S5](raw_source_assets/page1_img5_475.jpeg).

## Figure 4: detector comparison

**Input:** `episode_results.csv` for evaluation blocks `E1–E8`.

The plot shows confirmed post-onset alarm delays in minutes. The `E5*` label identifies endpoint censoring. Figure 4 is rendered from CSV in both execution modes.

Run the analysis step first to use a newly generated table. The renderer uses `episode_results.csv` in the directory selected by `--results`; if that file is missing, it uses the bundled `results/episode_results.csv`.

The preserved image originates from [R2 Main Figure 2](raw_source_assets/rId31.png). Its source analysis used `episode_method_results.csv`; the public renderer uses the corresponding [episode_results.csv](../results/episode_results.csv).

## Figure 5: normalized detector scores

**Input:** `E1_tube_leak` over **1,200–11,194 s**.

The panel plots `B0_state`, `Flow_only`, `Command_only` and `B1_combined` as **score divided by the method's own threshold**. It includes the normalized threshold `1.0`, confirmed post-onset alarm markers, leak onset and endpoint dwell.

The preserved image is [R2 Main Figure 3](raw_source_assets/rId34.png).

## Figure 6: evaluation milestones

**Input:** the eight `E1–E8` tube-leak episodes over **0–6 h**.

The timeline shows functional start, functional confirmation, process trip, model-domain exit and horizon-censoring markers. In raw mode, trip and domain-exit times are extracted from the NPZ safety and feasibility records.

The preserved image is [Supplement Figure S1](raw_source_assets/page1_img1_1103.jpeg), retained from the earlier analysis.

## Figure 7: normal persistence

**Input:** the eight `E1–E8` normal episodes.

The categorical plot compares each detector's longest threshold-exceedance span with the **600 s** required persistence. It is not a set of time-series score curves.

The preserved image is [R2 Supplement Figure S4](raw_source_assets/page1_img2_1217.jpeg).

For table and manuscript assembly links, see the [manuscript artifact map](../manuscript_verification/MANUSCRIPT_ARTIFACT_MAP.md).
