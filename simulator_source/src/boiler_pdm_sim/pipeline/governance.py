"""Shared governance policy loading and dataset artifact validation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from ..schema import SCHEMA_FREEZE_DATE, SCHEMA_NAME, SCHEMA_VERSION

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


DEFAULT_POLICY: dict[str, Any] = {
    "require_schema_match": True,
    "require_validation_passed": True,
    "require_split_consistency": True,
    "require_dataset_file": True,
    "require_governance_block": False,
    "required_schema_fields": ["schema_name", "schema_version", "freeze_date"],
    "required_manifest_fields": [
        "provenance",
        "provenance.created_utc",
        "provenance.config_hash",
        "validation",
        "validation_battery",
    ],
    "required_governance_fields": [],
    "required_governance_status": None,
    "required_classification": None,
    "allowed_classifications": [],
    "min_retention_days": None,
    "max_retention_days": None,
    "max_manifest_age_days": None,
    "require_integrity": True,
    "verify_integrity": True,
}


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _nested_get(value: Any, path: str, default: Any = None) -> Any:
    current = value
    for key in str(path).split("."):
        if not isinstance(current, dict):
            return default
        if key not in current:
            return default
        current = current[key]
    return current


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"manifest must be an object: {path}")
    return data


def _parse_utc_iso8601(value: str) -> float:
    if not value:
        return 0.0
    normalized = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return 0.0


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_path(value: str, *, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if base is not None and not path.is_absolute():
        if path.exists():
            return path
        path = base / path
    return path


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_content_sha256(manifest: dict[str, Any]) -> str:
    payload = {k: v for k, v in manifest.items() if k != "integrity"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def default_manifest_path(dataset_path: Path) -> Path:
    return dataset_path.parent / f"{dataset_path.stem}.manifest.json"


def load_governance_policy(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        return DEFAULT_POLICY.copy()
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return {**DEFAULT_POLICY, **loaded}
    loaded = _coerce_dict(json.loads(text))
    return {**DEFAULT_POLICY, **loaded}


def _check_integrity(
    manifest: dict[str, Any],
    manifest_path: Path,
    dataset_path: Path,
    policy: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    require_integrity = bool(policy.get("require_integrity", False))
    verify_integrity = bool(policy.get("verify_integrity", True))
    integrity = _coerce_dict(manifest.get("integrity", {}))
    if require_integrity and not integrity:
        return ["manifest missing integrity block"]
    if not integrity:
        return issues

    manifest_info = _coerce_dict(integrity.get("manifest", {}))
    expected_manifest_sha = _manifest_content_sha256(manifest)
    actual_manifest_sha = str(manifest_info.get("content_sha256", "")).strip()
    if not actual_manifest_sha:
        issues.append("integrity.manifest.content_sha256 missing")
    elif verify_integrity and actual_manifest_sha != expected_manifest_sha:
        issues.append("integrity.manifest.content_sha256 mismatch")

    files_info = _coerce_dict(integrity.get("files", {}))
    expected_files: dict[str, Path] = {"dataset": dataset_path}
    base_dir = dataset_path.parent
    for split_name, split_path in _coerce_dict(manifest.get("files", {})).items():
        if isinstance(split_path, str) and split_path.strip():
            expected_files[str(split_name)] = _coerce_path(split_path, base=base_dir)

    for logical_name, path in expected_files.items():
        file_info = _coerce_dict(files_info.get(logical_name, {}))
        if not file_info:
            if require_integrity:
                issues.append(f"integrity missing file record: {logical_name}")
            continue
        if not path.exists():
            issues.append(f"integrity target missing: {path}")
            continue
        declared_path = str(file_info.get("path", "")).strip()
        if declared_path and Path(declared_path).name != path.name:
            issues.append(f"integrity path mismatch for {logical_name}: {declared_path}")
        if verify_integrity:
            declared_size = _coerce_int(file_info.get("size_bytes"), default=-1)
            actual_size = int(path.stat().st_size)
            if declared_size >= 0 and declared_size != actual_size:
                issues.append(f"integrity size mismatch for {logical_name}")
            declared_sha = str(file_info.get("sha256", "")).strip()
            if not declared_sha:
                issues.append(f"integrity sha256 missing for {logical_name}")
            elif declared_sha != _sha256_file(path):
                issues.append(f"integrity sha256 mismatch for {logical_name}")

    return issues


def validate_dataset_artifact(
    dataset_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dataset = Path(dataset_path).expanduser()
    manifest = Path(manifest_path).expanduser() if manifest_path else default_manifest_path(dataset)
    rules = DEFAULT_POLICY.copy() if policy is None else dict(policy)
    issues: list[str] = []

    if rules.get("require_dataset_file", False) and not dataset.exists():
        issues.append(f"dataset file missing: {dataset}")

    if not manifest.exists():
        issues.append(f"manifest missing: {manifest}")
        return {
            "status": "failed",
            "passed": False,
            "dataset": str(dataset),
            "manifest": str(manifest),
            "policy": rules,
            "issues": issues,
            "issue_count": len(issues),
        }

    payload = _read_json(manifest)
    for field in rules.get("required_manifest_fields", []):
        if _nested_get(payload, field, None) is None:
            issues.append(f"manifest missing required field: {field}")

    if bool(rules.get("require_schema_match", False)):
        schema = _coerce_dict(_nested_get(payload, "provenance.schema", {}))
        for field in rules.get("required_schema_fields", []):
            if _nested_get(schema, field, None) is None:
                issues.append(f"provenance.schema missing required field: {field}")
        if schema.get("schema_name") != SCHEMA_NAME:
            issues.append(f"provenance.schema.schema_name mismatch: {schema.get('schema_name')}")
        if schema.get("schema_version") != SCHEMA_VERSION:
            issues.append(f"provenance.schema.schema_version mismatch: {schema.get('schema_version')}")
        if schema.get("freeze_date") != SCHEMA_FREEZE_DATE:
            issues.append(f"provenance.schema.freeze_date mismatch: {schema.get('freeze_date')}")

    if bool(rules.get("require_validation_passed", False)):
        validation = _coerce_dict(payload.get("validation", {}))
        if validation.get("passed") is not True:
            issues.append("dataset validation not passed")

    if bool(rules.get("require_split_consistency", False)):
        counts = _coerce_dict(payload.get("counts", {}))
        n_total = int(payload.get("n_total", 0) or 0)
        split_enabled = bool(payload.get("split_enabled", False))
        if split_enabled:
            split_total = sum(_coerce_int(v) for v in counts.values() if isinstance(v, (int, float)))
            if split_total != n_total:
                issues.append(f"split count mismatch: split_total={split_total}, n_total={n_total}")

    provenance = _coerce_dict(payload.get("provenance", {}))
    governance = _coerce_dict(provenance.get("governance", {}))
    if bool(rules.get("require_governance_block", False)):
        for field in rules.get("required_governance_fields", []):
            if not _nested_get(governance, field, None):
                issues.append(f"governance missing required field: {field}")
        required_status = rules.get("required_governance_status")
        if required_status and governance.get("approval_status") != required_status:
            issues.append(f"governance.approval_status != {required_status!r}")
        required_classification = rules.get("required_classification")
        classification = str(governance.get("classification", "")).strip()
        if required_classification and classification != str(required_classification):
            issues.append(f"governance.classification != {required_classification!r}")
        allowed_classifications = [str(v) for v in rules.get("allowed_classifications", []) if str(v).strip()]
        if allowed_classifications and classification not in allowed_classifications:
            issues.append(
                "governance.classification not in allowed set: "
                + ", ".join(repr(v) for v in allowed_classifications)
            )
        retention_days = governance.get("retention_days")
        min_retention_days = rules.get("min_retention_days")
        max_retention_days = rules.get("max_retention_days")
        if (min_retention_days is not None or max_retention_days is not None) and retention_days is None:
            issues.append("governance.retention_days missing")
        elif retention_days is not None:
            retention_value = _coerce_int(retention_days, default=-1)
            if min_retention_days is not None and retention_value < int(min_retention_days):
                issues.append(
                    f"governance.retention_days {retention_value}d below minimum ({int(min_retention_days)}d)"
                )
            if max_retention_days is not None and retention_value > int(max_retention_days):
                issues.append(
                    f"governance.retention_days {retention_value}d exceeds maximum ({int(max_retention_days)}d)"
                )

    max_age = rules.get("max_manifest_age_days")
    if max_age is not None:
        created = _nested_get(payload, "provenance.created_utc")
        if created:
            age_days = (datetime.now(timezone.utc).timestamp() - _parse_utc_iso8601(str(created))) / 86400.0
            if age_days > float(max_age):
                issues.append(f"manifest age {age_days:.1f}d exceeds policy ({max_age}d)")

    issues.extend(_check_integrity(payload, manifest, dataset, rules))
    issues = list(dict.fromkeys(issues))
    return {
        "status": "passed" if not issues else "failed",
        "passed": not issues,
        "dataset": str(dataset),
        "manifest": str(manifest),
        "policy": rules,
        "issues": issues,
        "issue_count": len(issues),
    }
