from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from boiler_pdm_sim.simulator import Simulator
from boiler_pdm_sim.validation.fault_observability import validate_fault_observability


def test_fault_observability_tracks_feature_ordering() -> None:
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["scenario"]["type"] = "step_tests"
    cfg["scenario"]["step_tests"] = yaml.safe_load(Path("configs/scenarios/step_tests.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["horizon_s"] = 1800
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["seed"] = 33
    cfg["fault_instances"] = ["configs/faults/fouling.yaml"]

    rows = Simulator(seed=33).run(cfg)
    report = validate_fault_observability(pd.DataFrame(rows))
    assert report["passed"] is True
