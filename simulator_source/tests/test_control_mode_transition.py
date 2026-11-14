from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from boiler_pdm_sim.simulator import Simulator
from boiler_pdm_sim.validation.control_mode_transition import validate_control_mode_transition


def test_control_mode_transitions_are_logged_and_exposed() -> None:
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["dt"] = 0.5
    cfg["sim"]["horizon_s"] = 90.0
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["seed"] = 5
    cfg["fault_instances"] = []
    cfg["control"]["mode"] = "manual"
    cfg["control"]["mode_schedule"] = [
        {"start_s": 0.0, "mode": "manual", "duration_s": 30.0},
        {"start_s": 30.0, "mode": "cascade", "duration_s": 30.0},
        {"start_s": 60.0, "mode": "auto"},
    ]
    rows = Simulator(seed=5).run(cfg)
    df = pd.DataFrame(rows)

    result = validate_control_mode_transition(rows)
    assert result["passed"]
    assert "manual" in set(df["meta/control_mode"])
    assert "cascade" in set(df["meta/control_mode"])
    assert "auto" in set(df["meta/control_mode"])

    events = [str(v) for v in df["label/event_log_latest"].explode().dropna()]
    assert any(event.startswith("control_mode_manual_to_cascade_t=") for event in events)
    assert any(event.startswith("control_mode_cascade_to_auto_t=") for event in events)
    assert {"meta/solver_used", "meta/controller_dt_s", "meta/logger_dt_s"} <= set(df.columns)
