from __future__ import annotations

import os
from copy import deepcopy
from importlib.util import find_spec
from pathlib import Path

import pandas as pd
import pytest
import yaml

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


def _disable_sensor_noise(cfg: dict) -> None:
    sensors = cfg.get("sensors", {})
    if not isinstance(sensors, dict):
        return
    for sensor_cfg in sensors.values():
        if not isinstance(sensor_cfg, dict):
            continue
        sensor_cfg["noise_std"] = 0.0
        sensor_cfg["bias"] = 0.0
        sensor_cfg["drift_per_hour"] = 0.0
        sensor_cfg["dropout_p"] = 0.0
        sensor_cfg["spike_p"] = 0.0
        sensor_cfg["spike_std"] = 0.0
        sensor_cfg["block_dropout_p"] = 0.0


def _build_real_parity_cfgs() -> tuple[dict, dict, dict]:
    cfg, reason = _resolve_real_fmu_cfg()
    if cfg is None:
        pytest.skip(reason or "real FMU config unavailable")

    parity = {}
    if isinstance(cfg.get("phase7"), dict):
        parity = dict(cfg["phase7"].get("parity", {}))

    base = deepcopy(cfg)
    base.setdefault("sim", {})
    base["sim"]["solver"] = "euler"
    base["sim"]["seed"] = int(parity.get("seed", base["sim"].get("seed", 31)))
    base["sim"]["horizon_s"] = float(parity.get("horizon_s", 180))
    base["fault_instances"] = []
    base.setdefault("randomization", {})
    base["randomization"]["enable"] = False
    base.setdefault("calibration", {})
    base["calibration"]["enabled"] = False
    base["performance"] = {"enabled": False}
    base["validation_battery"] = {"enabled": False}
    base["phase6"] = {"enabled": False}
    _disable_sensor_noise(base)

    python_cfg = deepcopy(base)
    python_cfg["core_backend"] = {"type": "python"}

    fmu_cfg = deepcopy(base)
    return python_cfg, fmu_cfg, parity


def test_python_and_real_fmu_backends_keep_parity_for_core_truth() -> None:
    python_cfg, fmu_cfg, parity = _build_real_parity_cfgs()

    python_rows = Simulator(seed=int(python_cfg["sim"]["seed"])).run(python_cfg)
    fmu_rows = Simulator(seed=int(fmu_cfg["sim"]["seed"])).run(fmu_cfg)

    left = pd.DataFrame(python_rows).reset_index(drop=True)
    right = pd.DataFrame(fmu_rows).reset_index(drop=True)
    columns = parity.get(
        "channels",
        [
            "truth/drum_pressure",
            "truth/drum_level",
            "truth/steam_flow",
            "truth/flue_gas_temp",
            "truth/O2",
            "truth/h_fw",
        ],
    )
    columns = [str(col) for col in columns]
    pd.testing.assert_frame_equal(
        left[columns],
        right[columns],
        check_exact=False,
        atol=float(parity.get("atol", 1e-2)),
        rtol=float(parity.get("rtol", 5e-2)),
    )
