from __future__ import annotations

import json
from pathlib import Path

from boiler_pdm_sim.pipeline.calibration import build_calibration_report_document, build_calibration_report_payload
from boiler_pdm_sim.pipeline.config_types import RuntimeConfig
from boiler_pdm_sim.pipeline.postprocess import write_calibration_sidecar
from boiler_pdm_sim.research.calibration import derive_nominal_offsets_from_rows
from boiler_pdm_sim.schema import (
    CALIBRATION_REPORT_SCHEMA,
    CALIBRATION_REPORT_SCHEMA_VERSION,
    validate_calibration_summary_payload,
    validate_analysis_phase15_config,
)


def test_runtime_calibration_offsets_have_expected_direction() -> None:
    rows = [
        {
            "truth/drum_pressure": 11.0,
            "truth/drum_level": 3.6,
        }
        for _ in range(12)
    ]

    report = derive_nominal_offsets_from_rows(
        rows,
        pressure_key="truth/drum_pressure",
        level_key="truth/drum_level",
        target_pressure=10.0,
        target_level=3.3,
        drum_length_m=6.0,
        warmup_fraction=0.0,
    )

    assert report["status"] == "ok"
    assert report["nominal_pressure_bar_offset"] < 0.0
    assert report["nominal_level_fraction_offset"] < 0.0


def test_analysis_calibration_schema_and_sidecar_contract(tmp_path: Path) -> None:
    valid, errors = validate_analysis_phase15_config(
        {
            "calibration": {
                "enabled": True,
                "report_path": str(tmp_path / "custom.calibration.json"),
                "include_in_analysis": True,
                "include_in_provenance": True,
            }
        }
    )

    assert valid is True
    assert errors == []

    calibration = build_calibration_report_payload(
        {
            "enabled": True,
            "mode": "probe",
            "use_observations": True,
            "pressure_channel": "obs/drum_pressure",
            "level_channel": "obs/drum_level",
            "target_pressure": 10.0,
            "target_level_m": 3.3,
            "pilot_horizon_s": 240,
            "warmup_fraction": 0.25,
            "nominal_pressure_bar_offset": -0.2,
            "nominal_level_fraction_offset": -0.01,
        },
        {
            "mode": "probe",
            "status": "ok",
            "probe_rows": 120,
            "pressure_bias": 0.2,
            "level_bias": 0.06,
            "sample_counts": {"pressure": 100, "level": 100},
        },
    )
    summary_valid, summary_errors = validate_calibration_summary_payload(calibration)
    assert summary_valid is True
    assert summary_errors == []
    report_doc = build_calibration_report_document(
        {
            "order": ["calibration", "phase15_analysis"],
            "calibration": calibration,
            "analysis": {"calibration": calibration},
        },
        {"calibration": {"enabled": True, "report_path": str(tmp_path / "custom.calibration.json")}},
    )
    assert report_doc is not None
    assert report_doc["analysis_summary"]["status"] == "ok"
    out = tmp_path / "dataset.parquet"
    out.write_bytes(b"placeholder")
    sidecar = write_calibration_sidecar(
        out,
        {"order": ["calibration", "phase15_analysis"], "calibration": calibration, "analysis": {"calibration": calibration}},
        {"calibration": {"enabled": True, "report_path": str(tmp_path / "custom.calibration.json"), "include_in_analysis": True}},
    )

    assert sidecar == tmp_path / "custom.calibration.json"
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["schema_name"] == CALIBRATION_REPORT_SCHEMA
    assert payload["schema_version"] == CALIBRATION_REPORT_SCHEMA_VERSION
    assert payload["calibration"]["status"] == "ok"
    assert payload["analysis_summary"]["status"] == "ok"
    assert payload["calibration"]["applied_offsets"]["nominal_pressure_bar_offset"] == -0.2


def test_runtime_config_exposes_control_and_validation_views() -> None:
    runtime_cfg = RuntimeConfig.from_mapping(
        {
            "control": {
                "drum_level_pid": {
                    "kp": 0.9,
                    "ki": 0.03,
                    "kd": 0.0,
                    "umin": 0.0,
                    "umax": 1.0,
                    "setpoint_level_m": 3.3,
                    "out_feedforward": 0.55,
                    "antiwindup_gain": 1.0,
                    "max_step_rate_per_s": 0.9,
                },
                "pressure_pid": {
                    "kp": 0.75,
                    "ki": 0.022,
                    "kd": 0.0,
                    "umin": 0.0,
                    "umax": 1.0,
                    "setpoint_pressure_bar": 10.0,
                    "antiwindup_gain": 1.0,
                    "max_step_rate_per_s": 1.0,
                },
            },
            "validation": {
                "schema_strict": True,
                "dae": {
                    "enabled": True,
                    "residual_tol": 1e-9,
                    "min_feasible_ratio": 0.95,
                },
            },
            "safety": {
                "lockout_on_trip": True,
            },
            "boiler": {
                "nominal": {"pressure_bar": 10.0},
            },
            "sensors": {
                "drum_pressure": {"noise_std": 0.01},
            },
            "randomization": {
                "enable": False,
            },
            "core_backend": {
                "type": "python",
            },
            "fault_instances": [{"fault_type": "tube_leak"}],
            "analysis": {
                "calibration": {
                    "enabled": True,
                    "include_in_analysis": True,
                    "include_in_provenance": True,
                }
            },
        }
    )

    assert runtime_cfg.control.drum_level_pid.kp == 0.9
    assert runtime_cfg.control.drum_level_pid.setpoint == 3.3
    assert runtime_cfg.control.pressure_pid.setpoint == 10.0
    assert runtime_cfg.validation.schema_strict is True
    assert runtime_cfg.validation.dae.enabled is True
    assert runtime_cfg.validation.dae.min_feasible_ratio == 0.95
    assert runtime_cfg.safety.lockout_on_trip is True
    assert runtime_cfg.boiler.raw["nominal"]["pressure_bar"] == 10.0
    assert runtime_cfg.sensors.raw["drum_pressure"]["noise_std"] == 0.01
    assert runtime_cfg.randomization.enabled is False
    assert runtime_cfg.core_backend.raw["type"] == "python"
    assert len(runtime_cfg.faults.instances) == 1
    assert runtime_cfg.analysis.calibration.include_in_analysis is True
    assert runtime_cfg.analysis.calibration.include_in_provenance is True
