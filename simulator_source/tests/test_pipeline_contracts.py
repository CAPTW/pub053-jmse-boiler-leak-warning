from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml
import pytest

from boiler_pdm_sim.dataset.writer import write_dataset
from boiler_pdm_sim.simulator import Simulator
from boiler_pdm_sim.validation.level_instrumentation import validate_level_instrumentation


def test_dataset_split_manifest_is_written(tmp_path: Path) -> None:
    rows = []
    for group_id in range(10):
        scenario_id = f"scenario_{group_id}"
        parameter_draw = f"draw_{group_id}"
        fault_instance_id = f"fault_{group_id}"
        for i in range(10):
            rows.append(
                {
                    "time": float(i),
                    "scenario_id": scenario_id,
                    "meta/parameter_draw": parameter_draw,
                    "meta/fault_instance_id": fault_instance_id,
                    "value": float(group_id * 10 + i),
                }
            )
    out = tmp_path / "dataset.parquet"
    manifest_path = tmp_path / "dataset.manifest.json"

    write_dataset(
        rows,
        out,
        fmt="parquet",
        split_cfg={"enabled": True, "train": 0.6, "val": 0.2, "test": 0.2},
        split_seed=2026,
    )

    assert out.exists()
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["split_enabled"] is True
    assert manifest["n_total"] == 100
    assert manifest["counts"] == {"train": 60, "val": 20, "test": 20}
    assert manifest["split_strategy"]["unit"] == "group"

    train = pd.read_parquet(tmp_path / "dataset.train.parquet")
    val = pd.read_parquet(tmp_path / "dataset.val.parquet")
    test = pd.read_parquet(tmp_path / "dataset.test.parquet")
    assert len(train) == 60
    assert len(val) == 20
    assert len(test) == 20
    assert len(train) + len(val) + len(test) == manifest["n_total"]
    train_groups = set(zip(train["scenario_id"], train["meta/parameter_draw"], train["meta/fault_instance_id"], strict=False))
    val_groups = set(zip(val["scenario_id"], val["meta/parameter_draw"], val["meta/fault_instance_id"], strict=False))
    test_groups = set(zip(test["scenario_id"], test["meta/parameter_draw"], test["meta/fault_instance_id"], strict=False))
    assert train_groups.isdisjoint(val_groups)
    assert train_groups.isdisjoint(test_groups)
    assert val_groups.isdisjoint(test_groups)


def _as_list(v: object) -> list[str]:
    return v if isinstance(v, list) else []


def test_output_schema_and_event_log_contract(tmp_path: Path) -> None:
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["dt"] = 0.5
    cfg["sim"]["horizon_s"] = 200
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["seed"] = 31
    cfg["scenario"]["type"] = "step_tests"
    cfg["scenario"]["seed"] = 11
    cfg["scenario"]["step_tests"] = yaml.safe_load(
        Path("configs/scenarios/step_tests.yaml").read_text(encoding="utf-8")
    )

    out = tmp_path / "contract.parquet"
    sim = Simulator(seed=31)
    sim.run_to_file(cfg, out)

    df = pd.read_parquet(out)
    for col in [
        "truth/flue_gas_temp",
        "truth/O2",
        "truth/h_fw",
        "meta/final_control_fuel_cmd",
        "meta/final_control_fw_cmd",
        "meta/final_control_steam_demand",
        "truth/level_true",
        "obs/drum_level_dp_raw",
        "obs/drum_level_compensated",
        "label/RUL_current_mission",
        "label/RUL_reference_mission",
        "label/censored",
        "label/failure_threshold_name",
        "label/fault_onset",
        "label/symptom_onset",
        "label/anomaly_detectable_onset",
        "label/threshold_crossing",
        "label/trip_time",
        "meta/parameter_draw",
        "meta/fault_instance_id",
        "meta/scenario_group_id",
        "label/event_log",
        "label/event_log_history",
        "label/event_log_latest",
    ]:
        assert col in df.columns

    assert df["truth/flue_gas_temp"].between(120.0, 2000.0).all()
    assert df["truth/O2"].between(1.0, 21.0).all()
    assert (df["truth/h_fw"] >= 0).all()
    assert df["meta/final_control_fuel_cmd"].between(0.0, 1.0).all()
    assert df["meta/final_control_fw_cmd"].between(0.0, 1.0).all()

    step_lens = df["label/event_log"].apply(lambda x: len(_as_list(x)))
    hist_lens = df["label/event_log_history"].apply(lambda x: len(_as_list(x)))
    assert (step_lens <= hist_lens).all()
    assert hist_lens.is_monotonic_increasing
    assert (df["truth/level_true"] == df["truth/drum_level"]).all()
    level_report = validate_level_instrumentation(df)
    assert level_report["passed"] is True
    assert (df["label/RUL_current_mission"] <= df["label/RUL_reference_mission"] + 1e-9).all()


def test_selected_outputs_are_seed_reproducible(tmp_path: Path) -> None:
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["dt"] = 1.0
    cfg["sim"]["horizon_s"] = 120
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["seed"] = 2026
    cfg["fault_instances"] = ["configs/faults/fouling.yaml"]

    a = pd.DataFrame(Simulator(seed=2026).run(cfg))
    b = pd.DataFrame(Simulator(seed=2026).run(cfg))

    selected_cols = ["truth/flue_gas_temp", "truth/O2", "truth/h_fw", "meta/final_control_fuel_cmd"]
    pd.testing.assert_frame_equal(
        a[selected_cols].sort_index(axis=1),
        b[selected_cols].sort_index(axis=1),
    )


def test_pipeline_meta_is_recorded_in_provenance(tmp_path: Path) -> None:
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["dt"] = 1.0
    cfg["sim"]["horizon_s"] = 60
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["seed"] = 13
    cfg["fault_instances"] = []
    cfg["calibration"] = {"enabled": True, "nominal": {"pressure_bar": 10.0}}
    cfg["identifiability"] = {"enabled": True, "freeze_level_chain": True}
    cfg["randomization"] = {"enable": False}

    out = tmp_path / "pipeline.parquet"
    sim = Simulator(seed=13)
    sim.run_to_file(cfg, out)

    manifest_path = out.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    pipeline = manifest["provenance"]["pipeline"]
    assert pipeline["order"] == ["calibration", "identifiability", "randomization"]
    assert pipeline["calibration_applied"] is True
    assert pipeline["identifiability_applied"] is True
    assert pipeline["randomization_enabled"] is False
    assert manifest["provenance_locked"] is True
    assert manifest["provenance"]["validation"]["passed"] is True
    assert manifest["provenance"]["git_hash"]
    assert manifest["provenance"]["source_snapshot_hash"]
    assert manifest["provenance"]["property_library_version"]
    assert manifest["provenance"]["solver_type"] == "euler"
    assert "parameter_draw" in manifest["provenance"]
    assert "fmu_backend_id" in manifest["provenance"]
    assert manifest["provenance"]["pipeline"]["identifiability"]["enabled"] is True


def test_lock_prevents_write_when_validation_fails(tmp_path: Path) -> None:
    rows = [{"time": 0.0, "value": 1.0}]
    out = tmp_path / "lock_fail.parquet"

    with pytest.raises(ValueError, match="Cannot lock provenance until validation passes"):
        write_dataset(
            rows,
            out,
            fmt="parquet",
            validation={"passed": False, "failures": ["dummy"]},
            split_cfg={"enabled": False},
            lock_provenance=True,
        )


def test_manifest_written_when_split_disabled(tmp_path: Path) -> None:
    rows = [{"time": 0.0, "value": 1.0}]
    out = tmp_path / "nosplit.parquet"
    provenance = {"pipeline": {"order": ["calibration"]}, "validation": {"passed": True}}
    validation = {"passed": True, "failures": []}

    write_dataset(
        rows,
        out,
        fmt="parquet",
        split_cfg={"enabled": False},
        split_seed=111,
        provenance=provenance,
        validation=validation,
        lock_provenance=True,
    )

    manifest_path = out.with_suffix(".manifest.json")
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["split_enabled"] is False
    assert manifest["provenance_locked"] is True
    assert manifest["provenance"] == provenance
    assert manifest["validation"] == validation


def test_run_to_file_does_not_split_without_explicit_split_cfg(tmp_path: Path) -> None:
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["dt"] = 1.0
    cfg["sim"]["horizon_s"] = 30
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["seed"] = 17
    cfg["fault_instances"] = []

    out = tmp_path / "nosplit_default.parquet"
    Simulator(seed=17).run_to_file(cfg, out)

    manifest = json.loads(out.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert manifest["split_enabled"] is False
    assert not (tmp_path / "nosplit_default.train.parquet").exists()
