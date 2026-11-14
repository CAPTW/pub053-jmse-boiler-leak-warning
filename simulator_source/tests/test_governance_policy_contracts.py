from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


def test_governance_policy_enforces_classification_and_retention(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.parquet"
    dataset.write_bytes(b"placeholder")

    manifest = {
        "split_enabled": False,
        "split_seed": 42,
        "n_total": 1,
        "n_splits": 0,
        "counts": {},
        "split": {},
        "files": {},
        "fmt": "parquet",
        "validation": {"passed": True},
        "validation_battery": {"enabled": False},
        "provenance": {
            "created_utc": "2026-03-08T00:00:00Z",
            "config_hash": "abc123",
            "schema": {
                "schema_name": "boiler-pdm-sim-schema-v1.1",
                "schema_version": "v1.1.1",
                "freeze_date": "2026-03-08",
            },
            "governance": {
                "approved_by": "ops",
                "approved_at": "2026-03-08T00:00:00Z",
                "approval_status": "approved",
                "classification": "external",
                "retention_days": 30,
            },
        },
    }
    manifest_path = dataset.parent / f"{dataset.stem}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")

    policy = {
        "require_schema_match": True,
        "require_validation_passed": True,
        "require_split_consistency": True,
        "require_dataset_file": True,
        "require_governance_block": True,
        "required_schema_fields": ["schema_name", "schema_version", "freeze_date"],
        "required_manifest_fields": [
            "provenance",
            "provenance.created_utc",
            "provenance.config_hash",
            "validation",
            "validation_battery",
        ],
        "required_governance_fields": [
            "approved_by",
            "approved_at",
            "approval_status",
            "classification",
            "retention_days",
        ],
        "required_governance_status": "approved",
        "required_classification": "internal",
        "min_retention_days": 365,
        "max_manifest_age_days": 365,
    }
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/check_dataset_governance.py",
            "--dataset",
            str(dataset),
            "--policy",
            str(policy_path),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    assert "governance.classification" in proc.stdout
    assert "governance.retention_days" in proc.stdout
