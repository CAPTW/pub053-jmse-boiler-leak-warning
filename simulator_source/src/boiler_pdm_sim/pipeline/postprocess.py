"""Dataset post-processing helpers for Simulator.run_to_file."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .calibration import build_calibration_report_document
from .governance import load_governance_policy, validate_dataset_artifact
from .runtime import _safe_hash_config

def write_calibration_sidecar(
    out_path: Path,
    pipeline_meta: dict[str, Any],
    analysis_cfg: dict[str, Any] | None = None,
) -> Path | None:
    report = build_calibration_report_document(pipeline_meta, analysis_cfg)
    if report is None:
        return None
    calibration_analysis = {}
    if isinstance(analysis_cfg, dict):
        calibration_analysis = dict(analysis_cfg.get("calibration", {})) if isinstance(analysis_cfg.get("calibration", {}), dict) else {}
    report_path = calibration_analysis.get("report_path")
    sidecar_path = Path(str(report_path)).expanduser() if report_path else out_path.with_suffix(".calibration.json")
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_bytes(json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return sidecar_path


def record_performance_outputs(
    simulator: Any,
    *,
    cfg: dict[str, Any],
    perf_cfg: dict[str, Any],
    out: str,
    rows: list[dict[str, Any]],
    validation: dict[str, Any],
    validation_battery: dict[str, Any],
    run_elapsed: float,
    write_elapsed: float,
) -> dict[str, Any]:
    throughput = float(len(rows) / run_elapsed) if run_elapsed > 0 else 0.0
    collect_memory = bool(perf_cfg.get("collect_memory", False))
    mem: dict[str, int] = {}
    if collect_memory:
        import tracemalloc

        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        mem = {
            "tracemalloc_current_bytes": int(current_bytes),
            "tracemalloc_peak_bytes": int(peak_bytes),
        }
        tracemalloc.stop()

    residuals = [float(v) for v in simulator._last_algebraic_timing.get("residuals", []) if isinstance(v, (int, float))]
    residual_p95 = float("nan")
    if residuals:
        residual_p95 = float(np.nanquantile(np.asarray(residuals, dtype=float), 0.95))
    performance_meta = {
        "batch_size": int(len(rows)),
        "run_seconds": float(run_elapsed),
        "write_seconds": float(write_elapsed),
        "elapsed_s": float(run_elapsed + write_elapsed),
        "rows_per_second": throughput,
        "stage_seconds": {
            "control_seconds": float(simulator._last_run_timing.get("control_seconds", 0.0)),
            "model_seconds": float(simulator._last_run_timing.get("model_seconds", 0.0)),
            "align_seconds": float(simulator._last_run_timing.get("align_seconds", 0.0)),
            "label_seconds": float(simulator._last_run_timing.get("label_seconds", 0.0)),
            "write_seconds": float(write_elapsed),
        },
        "rows": int(len(rows)),
        "algebraic_feasible_count": int(simulator._last_algebraic_timing.get("feasible_count", 0)),
        "algebraic_iterations_total": int(simulator._last_algebraic_timing.get("iterations", 0)),
        "algebraic_residual_p95": residual_p95,
        "validation_passed": bool(validation.get("passed", False)),
        "memory_profile": mem,
        **mem,
    }
    simulator._pipeline_meta["performance"] = performance_meta
    bottleneck_report = simulator._evaluate_bottleneck(performance_meta, perf_cfg.get("bottleneck", {}))
    simulator._pipeline_meta["performance"]["bottleneck"] = bottleneck_report
    default_perf_path = Path(out).with_suffix(".perf.jsonl")
    perf_path = Path(str(perf_cfg.get("log_path", str(default_perf_path))))
    simulator._append_performance_log(
        str(perf_path),
        {
            "run_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "seed": simulator.seed,
            "rows": int(len(rows)),
            "batch_size": int(len(rows)),
            "run_seconds": float(run_elapsed),
            "write_seconds": float(write_elapsed),
            "elapsed_s": float(run_elapsed + write_elapsed),
            "stage_seconds": performance_meta["stage_seconds"],
            "rows_per_second": throughput,
            "validation_passed": bool(validation.get("passed", False)),
            "validation": validation,
            "validation_battery": validation_battery,
            "memory_profile": mem,
            "bottleneck": bottleneck_report,
            "config_hash": _safe_hash_config(cfg),
        },
    )
    return bottleneck_report


def enforce_inline_governance(
    *,
    out_path: Path,
    governance_cfg: dict[str, Any],
    pipeline_meta: dict[str, Any],
) -> None:
    if not governance_cfg or not bool(governance_cfg.get("inline_gate", True)):
        return
    policy_path_raw = governance_cfg.get("policy_path", "configs/governance_policy.yaml")
    policy_path = Path(str(policy_path_raw)).expanduser() if policy_path_raw else None
    policy = load_governance_policy(policy_path if policy_path is not None and policy_path.exists() else None)
    governance_report = validate_dataset_artifact(out_path, policy=policy)
    pipeline_meta["governance"] = {
        "inline_gate": True,
        "status": governance_report.get("status"),
        "issue_count": governance_report.get("issue_count", 0),
    }
    if not bool(governance_report.get("passed", False)):
        raise RuntimeError("Inline governance failed: " + ", ".join(governance_report.get("issues", [])))
