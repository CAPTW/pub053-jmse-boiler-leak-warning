from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import yaml

from boiler_pdm_sim.pipeline.governance import load_governance_policy, validate_dataset_artifact
from boiler_pdm_sim.simulator import Simulator


REPO_ROOT = Path(__file__).resolve().parents[1]


def _base_local_pipeline_config() -> dict:
    cfg = yaml.safe_load((REPO_ROOT / "configs/local_pipeline.yaml").read_text(encoding="utf-8"))
    cfg = deepcopy(cfg)
    cfg["sim"]["horizon_s"] = 20
    cfg["fault_instances"] = []
    cfg["randomization"]["enable"] = False
    cfg["calibration"]["enabled"] = False
    cfg["performance"]["enabled"] = False
    cfg["sim"]["collect_performance"] = False
    cfg["validation_battery"]["enabled"] = False
    cfg["scenario"]["seed"] = 11
    cfg["scenario"]["load_follow"]["noise_std"] = 0.0
    for sensor_cfg in cfg["sensors"].values():
        if "noise_std" in sensor_cfg:
            sensor_cfg["noise_std"] = 0.0
        if "drift_per_hour" in sensor_cfg:
            sensor_cfg["drift_per_hour"] = 0.0
        if "dropout_p" in sensor_cfg:
            sensor_cfg["dropout_p"] = 0.0
        if "spike_p" in sensor_cfg:
            sensor_cfg["spike_p"] = 0.0
        if "spike_std" in sensor_cfg:
            sensor_cfg["spike_std"] = 0.0
    return cfg


def test_simulator_run_to_file_smoke(tmp_path: Path) -> None:
    cfg = _base_local_pipeline_config()
    cfg["governance"]["inline_gate"] = False

    out = tmp_path / "simulator_smoke.parquet"
    out_path = Simulator(seed=42).run_to_file(cfg, str(out), fmt="parquet")

    assert out_path == out
    assert out.exists()
    assert out.with_suffix(".manifest.json").exists()
    manifest = json.loads(out.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert manifest["validation"]["passed"] is True


def test_local_pipeline_config_e2e_writes_locked_manifest(tmp_path: Path) -> None:
    cfg = _base_local_pipeline_config()
    cfg["governance"]["inline_gate"] = True
    cfg["governance"]["policy_path"] = str((REPO_ROOT / "configs/governance_policy.yaml").resolve())

    config_path = tmp_path / "local_pipeline_e2e.yaml"
    config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    out = tmp_path / "local_pipeline_e2e.parquet"
    out_path = Simulator(seed=42).run_to_file(str(config_path), str(out), fmt="parquet")

    assert out_path == out
    assert out.exists()
    manifest_path = out.with_suffix(".manifest.json")
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provenance_locked"] is True
    assert manifest["validation"]["passed"] is True

    policy = load_governance_policy((REPO_ROOT / "configs/governance_policy.yaml").resolve())
    report = validate_dataset_artifact(out_path, policy=policy)
    assert report["passed"] is True
