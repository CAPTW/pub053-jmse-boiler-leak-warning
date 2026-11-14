"""Burner degradation fault helpers."""

from __future__ import annotations


def apply_burner_deg(
    params: dict,
    severity: float,
    eta_drop: float,
    qmax_drop: float,
) -> dict:
    p = dict(params)
    p.setdefault("degradation", {})
    sev = float(max(0.0, min(1.0, severity)))
    eta_drop = float(max(0.0, min(1.0, eta_drop)))
    qmax_drop = float(max(0.0, min(1.0, qmax_drop)))

    eta_reduction = eta_drop * (sev ** 1.08)
    qmax_reduction = qmax_drop * (sev ** 1.02)

    base_eta = float(p["boiler"]["parameters"]["combustion"]["eta"])
    p["degradation"]["eta_comb"] = base_eta * float(max(0.65, 1.0 - eta_reduction))
    p["degradation"]["qmax_scale"] = float(max(0.75, 1.0 - qmax_reduction))
    p["degradation"]["burner_deg_severity"] = sev
    return p
