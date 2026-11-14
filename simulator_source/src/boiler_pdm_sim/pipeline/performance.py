"""Performance log helpers and summary rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_last_jsonl_line(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser()
    if not target.exists():
        return {}
    lines = [line.strip() for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return {}
    try:
        payload = json.loads(lines[-1])
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ratio(current: float, baseline: float) -> float:
    if baseline <= 0.0:
        return float("inf") if current > 0 else 0.0
    return float(current) / float(baseline)


def compare_performance_records(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    min_rows_ratio: float = 0.90,
    max_stage_ratio: float = 1.30,
    max_memory_delta: int = 0,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "skipped",
        "issues": [],
        "rows_per_second_ratio": None,
        "stage_ratios": {},
        "memory_delta_bytes": None,
        "dominant_stage": None,
    }
    if not current:
        report["status"] = "failed"
        report["issues"] = ["no current performance record loaded"]
        return report
    if not baseline:
        report["status"] = "skipped"
        report["issues"] = ["no baseline record loaded"]
        return report

    cur_rps = float(current.get("rows_per_second", 0.0))
    base_rps = float(baseline.get("rows_per_second", 0.0))
    rows_ratio = _ratio(cur_rps, base_rps)
    report["rows_per_second_ratio"] = rows_ratio
    if rows_ratio < float(min_rows_ratio):
        report["issues"].append(f"rows_per_second ratio {rows_ratio:.6g} < {float(min_rows_ratio):.6g}")

    cur_stage = current.get("stage_seconds", {})
    base_stage = baseline.get("stage_seconds", {})
    dominant_stage = None
    dominant_value = float("-inf")
    if isinstance(cur_stage, dict) and isinstance(base_stage, dict):
        for stage in set(cur_stage) | set(base_stage):
            c = float(cur_stage.get(stage, 0.0))
            b = float(base_stage.get(stage, 0.0))
            ratio = _ratio(c, b)
            report["stage_ratios"][stage] = ratio
            if c > dominant_value:
                dominant_value = c
                dominant_stage = str(stage)
            if b <= 0.0 < c:
                report["issues"].append(f"{stage}: stage appeared (baseline=0, current={c:.6g})")
            elif ratio > float(max_stage_ratio):
                report["issues"].append(f"{stage}: stage ratio {ratio:.6g} > {float(max_stage_ratio):.6g}")
    report["dominant_stage"] = dominant_stage

    if int(max_memory_delta) > 0:
        cur_mem = current.get("memory_profile", {})
        base_mem = baseline.get("memory_profile", {})
        if isinstance(cur_mem, dict) and isinstance(base_mem, dict):
            cur_peak = int(cur_mem.get("tracemalloc_peak_bytes", 0))
            base_peak = int(base_mem.get("tracemalloc_peak_bytes", 0))
            memory_delta = int(cur_peak - base_peak)
            report["memory_delta_bytes"] = memory_delta
            if memory_delta > int(max_memory_delta):
                report["issues"].append(
                    f"tracemalloc_peak_bytes increase {memory_delta} exceeds policy ({int(max_memory_delta)})"
                )

    report["status"] = "passed" if not report["issues"] else "failed"
    return report


def render_markdown_summary(
    current: dict[str, Any],
    *,
    baseline: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
    current_path: str | None = None,
    baseline_path: str | None = None,
) -> str:
    lines: list[str] = ["# Performance Summary", ""]
    if current_path:
        lines.append(f"- Current: `{current_path}`")
    if baseline_path:
        lines.append(f"- Baseline: `{baseline_path}`")
    lines.append("")
    lines.append("## Current run")
    lines.append("")
    lines.append(f"- Rows per second: `{float(current.get('rows_per_second', 0.0)):.6g}`")
    lines.append(f"- Run seconds: `{float(current.get('run_seconds', 0.0)):.6g}`")
    lines.append(f"- Write seconds: `{float(current.get('write_seconds', 0.0)):.6g}`")
    lines.append(f"- Rows: `{int(current.get('rows', current.get('batch_size', 0)) or 0)}`")
    stage_seconds = current.get("stage_seconds", {})
    if isinstance(stage_seconds, dict) and stage_seconds:
        lines.append("")
        lines.append("## Stage timings")
        lines.append("")
        for stage, value in sorted(stage_seconds.items()):
            lines.append(f"- `{stage}`: `{float(value):.6g}` s")

    if comparison is not None:
        lines.append("")
        lines.append("## Baseline comparison")
        lines.append("")
        lines.append(f"- Status: `{comparison.get('status', 'unknown')}`")
        if comparison.get("rows_per_second_ratio") is not None:
            lines.append(f"- Rows/s ratio: `{float(comparison['rows_per_second_ratio']):.6g}`")
        if comparison.get("dominant_stage"):
            lines.append(f"- Dominant stage: `{comparison['dominant_stage']}`")
        stage_ratios = comparison.get("stage_ratios", {})
        if isinstance(stage_ratios, dict) and stage_ratios:
            lines.append("")
            lines.append("### Stage ratios")
            lines.append("")
            for stage, value in sorted(stage_ratios.items()):
                lines.append(f"- `{stage}`: `{float(value):.6g}`")
        issues = comparison.get("issues", [])
        if issues:
            lines.append("")
            lines.append("### Issues")
            lines.append("")
            for issue in issues:
                lines.append(f"- {issue}")
        else:
            lines.append("")
            lines.append("- No regression issues detected.")
    elif baseline is None:
        lines.append("")
        lines.append("- No baseline comparison available.")

    return "\n".join(lines).rstrip() + "\n"
