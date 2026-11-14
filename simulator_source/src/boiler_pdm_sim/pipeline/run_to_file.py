"""Helpers for Simulator.run_to_file orchestration."""

from __future__ import annotations

import importlib.metadata
import hashlib
import os
import subprocess
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .calibration import attach_calibration_analysis
from .config_types import RuntimeConfig
from .runtime import _coerce_dict_payload, _coerce_list, _safe_hash_config
from ..schema import schema_manifest
from ..validation.phase6 import run_validation_battery


def resolve_split_config(runtime_cfg: RuntimeConfig) -> dict[str, Any] | None:
    split_cfg = dict(runtime_cfg.split.raw)
    return split_cfg if split_cfg else None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _safe_git_hash() -> str:
    for env_key in ("GIT_COMMIT", "GITHUB_SHA", "CI_COMMIT_SHA", "BUILD_VCS_NUMBER"):
        candidate = str(os.environ.get(env_key, "")).strip()
        if candidate:
            return candidate
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
        )
        out = proc.stdout.strip()
        return out or "unknown"
    except Exception:
        return "unknown"


def _source_snapshot_hash() -> str:
    root = _repo_root()
    hasher = hashlib.sha256()
    patterns = (
        "src/boiler_pdm_sim/**/*.py",
        "configs/**/*.yaml",
        "README.md",
        "blueprint.md",
        "docs/**/*.md",
    )
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if rel in seen:
                continue
            seen.add(rel)
            hasher.update(str(rel).replace("\\", "/").encode("utf-8"))
            hasher.update(b"\0")
            try:
                hasher.update(path.read_bytes())
            except Exception:
                hasher.update(b"<unreadable>")
            hasher.update(b"\0")
    return hasher.hexdigest() if seen else "none"


def _property_library_version() -> str:
    try:
        return str(importlib.metadata.version("iapws"))
    except Exception:
        return "fallback"


def run_optional_validation_battery(
    simulator: Any,
    *,
    cfg: dict[str, Any],
    runtime_cfg: RuntimeConfig,
    out: str,
) -> dict[str, Any]:
    phase6_cfg = {k: v for k, v in dict(runtime_cfg.validation_battery.raw).items() if v is not None}
    phase6_enabled = bool(runtime_cfg.validation_battery.enabled)
    phase6_result: dict[str, Any] = {"enabled": phase6_enabled}
    if not phase6_enabled:
        return phase6_result

    perf_cfg = dict(runtime_cfg.performance.raw)
    phase6_log_cfg = _coerce_dict_payload(perf_cfg.get("validation_battery", {}))
    phase6_log_path = str(
        phase6_log_cfg.get("log_path")
        or runtime_cfg.validation_battery.log_path
        or str(Path(out).with_suffix(".validation_battery.jsonl"))
    )
    phase6_result = run_validation_battery(
        simulator.run,
        cfg,
        phase6_cfg=phase6_cfg,
    )
    simulator._pipeline_meta.setdefault("order", []).append("validation_battery")
    simulator._pipeline_meta["validation_battery"] = {
        "status": phase6_result.get("status"),
        "seeds": phase6_result.get("seeds", []),
    }
    if not bool(phase6_result.get("passed", False)):
        failures = phase6_result.get("seed_failures", phase6_result.get("required", {}).get("failures", []))
        raise RuntimeError(f"Phase-6 required KPI validation failed: {', '.join(_coerce_list(failures))}")
    if phase6_result.get("status") == "warning":
        warnings.warn(
            f"[PHASE6_WARNING] validation battery produced warning KPI failures: {phase6_result.get('warning', {}).get('failures', [])}",
            RuntimeWarning,
            stacklevel=2,
        )
    simulator._append_jsonl(
        str(phase6_log_path),
        {
            "run_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": phase6_result.get("status"),
            "seed": simulator.seed,
            "seeds": phase6_result.get("seeds", []),
            "n_runs": phase6_result.get("n_runs", 0),
            "summaries": phase6_result.get("summaries", {}),
            "required": phase6_result.get("required", {}),
            "warning": phase6_result.get("warning", {}),
            "seed_failures": phase6_result.get("seed_failures", []),
            "config_hash": _safe_hash_config(cfg),
        },
    )
    return phase6_result


def record_analysis(
    simulator: Any,
    *,
    rows: list[dict[str, Any]],
    cfg: dict[str, Any],
    runtime_cfg: RuntimeConfig,
) -> dict[str, Any]:
    analysis = simulator._apply_phase15_analysis(rows, cfg)
    calibration_summary = dict(simulator._pipeline_meta.get("calibration", {}))
    include_calibration = bool(
        calibration_summary
        and runtime_cfg.analysis.calibration.include_in_analysis
        and (runtime_cfg.analysis.calibration.enabled or runtime_cfg.calibration.enabled)
    )
    analysis = attach_calibration_analysis(
        analysis,
        calibration_summary,
        include_in_analysis=include_calibration,
    )
    if analysis:
        simulator._pipeline_meta["analysis"] = analysis
    return analysis


def build_provenance(
    simulator: Any,
    *,
    cfg: dict[str, Any],
    runtime_cfg: RuntimeConfig,
    validation: dict[str, Any],
    phase6_result: dict[str, Any],
    split_cfg: dict[str, Any] | None,
) -> dict[str, Any]:
    pipeline_meta = dict(getattr(simulator, "_pipeline_meta", {}))
    analysis_summary = _coerce_dict_payload(pipeline_meta.get("analysis"))
    calibration_summary = _coerce_dict_payload(pipeline_meta.get("calibration"))
    include_calibration = bool(
        calibration_summary
        and runtime_cfg.analysis.calibration.include_in_provenance
        and (runtime_cfg.analysis.calibration.enabled or runtime_cfg.calibration.enabled)
    )
    backend_cfg = dict(runtime_cfg.core_backend.raw)
    backend_type = str(backend_cfg.get("type", "python")).strip().lower() or "python"
    solver_type = str(runtime_cfg.sim.solver).strip().lower()
    solver_tolerance: dict[str, float | None]
    if solver_type in {"euler", "fixed"}:
        solver_tolerance = {"rtol": None, "atol": None}
    else:
        solver_tolerance = {"rtol": 1e-5, "atol": 1e-8}
    return {
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "seed": simulator.seed,
        "git_hash": _safe_git_hash(),
        "source_snapshot_hash": _source_snapshot_hash(),
        "schema": schema_manifest(),
        "analysis": analysis_summary,
        "calibration": calibration_summary if include_calibration else {},
        "pipeline": pipeline_meta,
        "validation": validation,
        "validation_battery": phase6_result,
        "governance": dict(runtime_cfg.governance.raw),
        "split_cfg": split_cfg,
        "config_hash": _safe_hash_config(cfg),
        "property_library_version": _property_library_version(),
        "solver_type": solver_type,
        "solver_tolerance": solver_tolerance,
        "correction_count": int(pipeline_meta.get("correction_count", getattr(simulator, "_last_algebraic_timing", {}).get("iterations", 0))),
        "parameter_draw": str(pipeline_meta.get("parameter_draw_id", "none")),
        "calibration_baseline_id": str(calibration_summary.get("status", "none")) if include_calibration else "none",
        "fmu_backend_id": backend_type,
        "fmu_backend_version": str(backend_cfg.get("library", backend_type)),
    }
