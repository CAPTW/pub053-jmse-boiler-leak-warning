"""FMU interface contract helpers."""

from __future__ import annotations

from typing import Any


def build_fmu_contract(core_backend_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = core_backend_cfg if isinstance(core_backend_cfg, dict) else {}
    backend_type = str(raw.get("type", "python")).strip().lower() or "python"
    mode = str(raw.get("fmi_mode", "co-simulation")).strip().lower() or "co-simulation"
    if mode not in {"co-simulation", "model-exchange"}:
        mode = "co-simulation"
    return {
        "backend_type": backend_type,
        "mode": mode,
        "public_inputs": ["fuel_cmd", "fw_cmd", "steam_demand"],
        "public_outputs": [
            "drum_pressure",
            "drum_level",
            "steam_flow",
            "feedwater_flow",
            "drum_temp_sh",
        ],
        "event_handling": "python_core_alignment_and_projection",
        "communication_step": "fixed_to_plant_dt",
        "input_interpolation": "zero_order_hold",
        "reset_reinit": True,
        "bad_status_handling": "retry_then_fallback",
        "canonical_reference": "python_grey_box_core",
    }
