from __future__ import annotations

import os
from copy import deepcopy
from importlib.util import find_spec
from pathlib import Path

import pandas as pd
import pytest
import yaml

from boiler_pdm_sim.core.backend_factory import build_core_backend
from boiler_pdm_sim.simulator import Simulator


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_real_fmu_cfg() -> tuple[dict | None, str | None]:
    root = _workspace_root()
    cfg_path = Path(os.environ.get("BOILER_REAL_FMU_CONFIG", root / "configs" / "base_fmpy.yaml")).expanduser()
    if not cfg_path.exists():
        return None, f"real FMU config not found: {cfg_path}"

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        return None, f"real FMU config is not a mapping: {cfg_path}"

    backend = cfg.get("core_backend", {})
    if not isinstance(backend, dict):
        return None, "core_backend must be a mapping"
    raw_path = os.environ.get("BOILER_REAL_FMU_PATH") or backend.get("path") or backend.get("fmu_path")
    if not raw_path:
        return None, "real FMU path is not configured"

    candidate = Path(str(raw_path)).expanduser()
    search = [candidate, cfg_path.parent / candidate, root / candidate]
    resolved = None
    for item in search:
        if item.exists():
            resolved = item.resolve()
            break
    if resolved is None:
        return None, f"real FMU file not found: {raw_path}"

    if find_spec("fmpy") is None and find_spec("pyfmi") is None:
        return None, "real FMU test requires fmpy or pyfmi"

    cfg = deepcopy(cfg)
    cfg.setdefault("core_backend", {})
    cfg["core_backend"]["path"] = str(resolved)
    return cfg, None


def _build_real_e2e_cfgs() -> tuple[dict, dict]:
    cfg, reason = _resolve_real_fmu_cfg()
    if cfg is None:
        pytest.skip(reason or "real FMU config unavailable")

    parity = {}
    if isinstance(cfg.get("phase7"), dict):
        parity = dict(cfg["phase7"].get("parity", {}))

    load_cfg = deepcopy(cfg)
    load_cfg.setdefault("sim", {})
    load_cfg["sim"]["solver"] = "euler"
    load_cfg["sim"]["seed"] = int(parity.get("seed", load_cfg["sim"].get("seed", 31)))
    load_cfg["sim"]["horizon_s"] = float(parity.get("load_follow_horizon_s", 100))
    load_cfg["fault_instances"] = []
    load_cfg.setdefault("randomization", {})
    load_cfg["randomization"]["enable"] = False
    load_cfg.setdefault("calibration", {})
    load_cfg["calibration"]["enabled"] = False
    load_cfg["performance"] = {"enabled": False}
    load_cfg["validation_battery"] = {"enabled": False}
    load_cfg["phase6"] = {"enabled": False}
    load_cfg["scenario"] = {
        "type": "load_follow",
        "seed": 5,
        "load_follow": {"base": 0.6, "noise_std": 0.0, "ramp_limit_per_min": 0.05},
    }

    step_cfg = deepcopy(load_cfg)
    step_cfg["sim"]["horizon_s"] = float(parity.get("step_tests_horizon_s", 90))
    step_cfg["scenario"] = {
        "type": "step_tests",
        "seed": 9,
        "step_tests": {
            "base": 0.6,
            "steps": [{"start_s": 20.0, "duration_s": 300.0, "value": 0.9}],
        },
    }
    return load_cfg, step_cfg


def test_real_fmu_backend_load_follow_and_step_tests() -> None:
    load_cfg, step_cfg = _build_real_e2e_cfgs()

    backend = build_core_backend(load_cfg["boiler"], load_cfg["core_backend"])
    assert backend.state_names == list(load_cfg["core_backend"]["variables"]["state_names"])
    assert backend.algebraic_state_names == list(load_cfg["core_backend"]["variables"].get("algebraic_state_names", []))

    rows_load = Simulator(seed=int(load_cfg["sim"]["seed"])).run(load_cfg)
    assert len(rows_load) > 10

    rows_step = Simulator(seed=int(step_cfg["sim"]["seed"])).run(step_cfg)
    assert len(rows_step) > 10

    df = pd.DataFrame(rows_step)
    flat_events = [str(v) for v in df["label/event_log"].explode().dropna()]
    assert any(evt.startswith("steam_step_") for evt in flat_events)
    assert set(("truth/drum_pressure", "truth/drum_level", "meta/safety_state")).issubset(df.columns)
