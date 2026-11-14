from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from boiler_pdm_sim.schema import SCHEMA_LABEL_KEYS, validate_label_contract_row
from boiler_pdm_sim.simulator import Simulator


def _base_label_row() -> dict[str, object]:
    row: dict[str, object] = {
        "label/fault_type": "none",
        "label/fault_types": [],
        "label/fault_type_count": 0.0,
        "label/fault_severity": 0.0,
        "label/anomaly_flag": 0.0,
        "label/RUL": 100.0,
        "label/RUL_current_mission": 100.0,
        "label/RUL_reference_mission": 100.0,
        "label/censored": 1.0,
        "label/failure_threshold_name": "none",
        "label/fault_onset": -1.0,
        "label/symptom_onset": -1.0,
        "label/anomaly_detectable_onset": -1.0,
        "label/threshold_crossing": -1.0,
        "label/trip_time": -1.0,
        "label/safety_state": "safe",
        "label/safety_active": 0.0,
        "label/alarm_count": 0.0,
        "label/trip_count": 0.0,
        "label/alarm_faults": [],
        "label/trip_faults": [],
        "label/event_log": [],
        "label/event_log_history": [],
        "label/event_log_latest": [],
        "label/fault_names": [],
    }
    return row


def test_label_contract_validator_accepts_and_rejects_expected_rows() -> None:
    row = _base_label_row()
    assert validate_label_contract_row(row, required_keys=SCHEMA_LABEL_KEYS) == []

    broken = _base_label_row()
    broken["label/fault_type"] = ["not", "str"]
    failures = validate_label_contract_row(broken, required_keys=SCHEMA_LABEL_KEYS)
    assert any("label/fault_type must be str" in msg for msg in failures)

    event_row = _base_label_row()
    event_row["label/event_log"] = ["bad_event_token"]
    failures = validate_label_contract_row(event_row, required_keys=SCHEMA_LABEL_KEYS)
    assert any("does not match any schema event pattern" in msg for msg in failures)


def test_schema_strict_mismatch_raises_hard_fail(tmp_path: Path) -> None:
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["schema_version"] = "0.0.0"
    cfg["validation"] = {"schema_strict": True}
    cfg["sim"]["dt"] = 1.0
    cfg["sim"]["horizon_s"] = 1.0

    with pytest.raises(RuntimeError, match="SCHEMA_MISMATCH"):
        Simulator(seed=1).run(cfg)


def test_bottleneck_diagnostics_flags_regression(tmp_path: Path) -> None:
    base_perf = {
        "rows_per_second": 100.0,
        "stage_seconds": {"control_seconds": 1.0, "model_seconds": 2.0, "align_seconds": 1.0, "label_seconds": 1.0, "write_seconds": 1.0},
    }
    base_path = tmp_path / "baseline.perf.jsonl"
    base_path.write_text(json.dumps(base_perf, ensure_ascii=False) + "\n", encoding="utf-8")

    sim = Simulator(seed=7)
    report = sim._evaluate_bottleneck(
        {
            "rows_per_second": 70.0,
            "stage_seconds": {"control_seconds": 1.2, "model_seconds": 3.0, "align_seconds": 1.5, "label_seconds": 1.0, "write_seconds": 1.0},
        },
        {
            "enabled": True,
            "baseline_log_path": str(base_path),
            "throughput_min_ratio": 0.9,
            "stage_share_ratio_max": 1.2,
            "fail_on_regression": True,
        },
    )
    assert report["enabled"] is True
    assert report["ci_fail"] is True
    assert report["failures"]
