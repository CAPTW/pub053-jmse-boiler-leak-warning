"""Label generation helpers."""

from __future__ import annotations


def build_labels(truth_labels: dict, anomaly: float | None = None) -> dict[str, float]:
    raw_fault_type = truth_labels["fault_type"]
    if isinstance(raw_fault_type, str):
        fault_type = raw_fault_type or "none"
    elif isinstance(raw_fault_type, (list, tuple)) and raw_fault_type:
        fault_type = str(raw_fault_type[0]) or "none"
    else:
        fault_type = "none"
    return {
        "fault_type": fault_type,
        "fault_severity": float(truth_labels["fault_severity"]),
        "anomaly_flag": float(anomaly if anomaly is not None else truth_labels["anomaly_flag"]),
        "RUL": float(truth_labels["RUL"]),
        "fault_types": truth_labels.get("fault_types", [fault_type]),
        "event_log": truth_labels["event_log"],
    }
