from __future__ import annotations

from boiler_pdm_sim.schema import SCHEMA_LABEL_KEYS, SCHEMA_LOCK, validate_label_contract_row


def _label_row(event: str) -> dict[str, object]:
    return {
        "label/fault_type": "none",
        "label/fault_types": [],
        "label/fault_type_count": 0.0,
        "label/fault_severity": 0.0,
        "label/anomaly_flag": 0.0,
        "label/RUL": 0.0,
        "label/safety_state": "safe",
        "label/safety_active": 0.0,
        "label/alarm_count": 0.0,
        "label/trip_count": 0.0,
        "label/fault_names": [],
        "label/alarm_faults": [],
        "label/trip_faults": [],
        "label/event_log": [event],
        "label/event_log_history": [event],
        "label/event_log_latest": [event],
    }


def test_pid_saturation_literals_are_valid_schema_events() -> None:
    for event in (
        "sat_level_pid_lower",
        "sat_level_pid_upper",
        "sat_pressure_pid_lower",
        "sat_pressure_pid_upper",
    ):
        failures = validate_label_contract_row(
            _label_row(event),
            required_keys=SCHEMA_LABEL_KEYS,
            event_patterns=SCHEMA_LOCK["event_patterns"],
        )
        assert not [failure for failure in failures if "event" in failure]
