from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from boiler_pdm_sim.simulator import Simulator


def test_fault_severity_monotonic_increases():
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["scenario"]["type"] = "step_tests"
    cfg["scenario"]["step_tests"] = yaml.safe_load(Path("configs/scenarios/step_tests.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["horizon_s"] = 2500
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["seed"] = 12

    cfg["fault_instances"] = ["configs/faults/fouling.yaml"]
    sim = Simulator(seed=12)
    rows = sim.run(cfg)
    df = pd.DataFrame(rows)
    sev = df["label/fault_severity"]
    assert (sev.diff().fillna(0.0) >= -1e-9).all()
    feature_value = pd.to_numeric(df["meta/fault_feature_value"], errors="coerce").fillna(0.0)
    feature_ref = pd.to_numeric(df["meta/fault_feature_reference"], errors="coerce").replace(0.0, np.nan)
    expected = (feature_value / feature_ref).fillna(0.0).clip(lower=0.0, upper=1.0)
    assert np.allclose(sev.to_numpy(dtype=float), expected.to_numpy(dtype=float), atol=1e-6)
    active = df[df["label/fault_type"] != "none"]
    assert len(active) > 10
    assert set(active["meta/fault_feature_name"]) == {"ua_loss_ratio"}
    assert (active["label/RUL_current_mission"] <= active["label/RUL_reference_mission"] + 1e-9).all()
    sh = pd.to_numeric(df["obs/drum_temp_sh"], errors="coerce").dropna()
    assert len(sh) > 10
    assert sh.iloc[-1] < sh.iloc[0] + 1.0
