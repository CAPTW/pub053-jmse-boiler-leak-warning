from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from boiler_pdm_sim.simulator import Simulator


def test_reproducible_with_seed():
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["seed"] = 77
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["horizon_s"] = 1000
    a = pd.DataFrame(Simulator(seed=77).run(cfg))
    b = pd.DataFrame(Simulator(seed=77).run(cfg))
    pd.testing.assert_frame_equal(a.sort_index(axis=1), b.sort_index(axis=1))
