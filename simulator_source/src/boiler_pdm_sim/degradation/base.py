"""Degradation base types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FaultTemplate:
    name: str
    type: str
    onset_s: float
    duration_s: float
    severity_kind: str = "linear"
    target: str | None = None
    alpha: float = 1.0
