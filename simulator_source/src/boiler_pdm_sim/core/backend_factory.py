"""Backend selection helpers for simulator core engines."""

from __future__ import annotations

from typing import Any, Mapping

from .boiler_system import BoilerSystem
from .fmu_adapter import FMUBackendError, FMUCoreAdapter


def build_core_backend(boiler_cfg: Mapping[str, Any], backend_cfg: Mapping[str, Any] | None = None):
    cfg = dict(backend_cfg or {})
    backend_type = str(cfg.get("type", "python")).strip().lower()

    if backend_type in {"python", "core", "internal", ""}:
        return BoilerSystem({"boiler": boiler_cfg})

    if backend_type in {"fmu", "fmi"}:
        return FMUCoreAdapter.from_config(cfg, {"boiler": boiler_cfg})

    if backend_type == "ab4":
        # Lazy import: props builds its IF97 spline tables at import time, so only
        # pay that cost when the ab4 backend is actually selected.
        from .ab4.backend import Ab4Backend

        return Ab4Backend.from_config(boiler_cfg, cfg)

    raise FMUBackendError(f"Unknown core backend type: {backend_type}")

