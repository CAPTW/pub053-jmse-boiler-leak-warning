"""Fault observability validation helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd


def validate_fault_observability(
    rows: list[dict[str, Any]] | pd.DataFrame,
    *,
    severity_key: str = "label/fault_severity",
    feature_key: str = "meta/fault_feature_value",
    min_monotonic_ratio: float = 0.95,
) -> dict[str, Any]:
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if severity_key not in df or feature_key not in df:
        return {"passed": False, "reason": "missing_columns"}
    work = df[[severity_key, feature_key]].dropna()
    if work.empty:
        return {"passed": False, "reason": "empty"}
    sev = pd.to_numeric(work[severity_key], errors="coerce").fillna(0.0)
    feat = pd.to_numeric(work[feature_key], errors="coerce").fillna(0.0)
    sev_monotonic = float((sev.diff().fillna(0.0) >= -1e-9).mean())
    feat_monotonic = float((feat.diff().fillna(0.0) >= -1e-9).mean())
    corr = float(sev.corr(feat)) if len(work) > 1 else 1.0
    return {
        "passed": bool(sev_monotonic >= min_monotonic_ratio and feat_monotonic >= min_monotonic_ratio and corr >= 0.9),
        "severity_monotonic_ratio": sev_monotonic,
        "feature_monotonic_ratio": feat_monotonic,
        "correlation": corr,
    }


__all__ = ["validate_fault_observability"]
