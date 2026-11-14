from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from boiler_pdm_sim.simulator import Simulator
from boiler_pdm_sim.validation.step_response import (
    check_shrink_swell_event_consistency,
    has_shrink_swell,
)


def _cfg():
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["scenario"] = yaml.safe_load(Path("configs/scenarios/step_tests.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["horizon_s"] = 2000
    cfg["sim"]["seed"] = 7
    return cfg


def test_shrink_swell_reaction_exists():
    sim = Simulator(seed=7)
    cfg = _cfg()
    rows = sim.run(cfg)
    df = pd.DataFrame(rows)
    assert "obs/drum_level" in df.columns
    assert has_shrink_swell(df["obs/drum_level"].tolist())

    acc = check_shrink_swell_event_consistency(
        df["obs/drum_level"].tolist(),
        df["meta/steam_demand_cmd"].tolist(),
        event_log=df["label/event_log"].tolist(),
        dt=cfg["sim"]["dt"],
        min_excursion=0.0015,
        min_recover=0.0008,
        recovery_ratio=0.0,
        event_window_s=600.0,
    )
    assert acc["passed"]
    assert acc["events_total"] >= 1
    assert acc["events_matched"] >= 1
    assert acc["coverage"] >= 0.8
    assert any(str(v).startswith("steam_step_") for v in df["label/event_log"].explode().dropna())
