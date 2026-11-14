from __future__ import annotations

import json
from pathlib import Path

from boiler_pdm_sim.dataset.writer import write_dataset
from boiler_pdm_sim.pipeline.governance import load_governance_policy, validate_dataset_artifact


def test_manifest_integrity_block_is_written_and_verifiable(tmp_path: Path) -> None:
    out = tmp_path / "integrity.parquet"
    rows = [{"time": 0.0, "value": 1.0}]

    write_dataset(
        rows,
        out,
        fmt="parquet",
        split_cfg={"enabled": False},
        provenance={
            "created_utc": "2026-03-08T00:00:00Z",
            "config_hash": "abc",
            "schema": {
                "schema_name": "boiler-pdm-sim-schema-v1.1",
                "schema_version": "v1.1.1",
                "freeze_date": "2026-03-08",
            },
            "governance": {
                "approved_by": "local-operator",
                "approved_at": "2026-03-08T00:00:00Z",
                "approval_status": "approved",
                "classification": "internal",
                "retention_days": 365,
            },
        },
        validation={"passed": True},
        validation_battery={"enabled": False},
        lock_provenance=True,
    )

    manifest = json.loads(out.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert "integrity" in manifest
    assert manifest["integrity"]["algorithm"] == "sha256"
    assert "dataset" in manifest["integrity"]["files"]

    policy = load_governance_policy(None)
    report = validate_dataset_artifact(out, policy=policy)
    assert report["passed"] is True


def test_split_manifest_integrity_paths_are_relative_and_verifiable(tmp_path: Path) -> None:
    out = tmp_path / "integrity_split.parquet"
    rows = [{"time": float(i), "value": float(i)} for i in range(12)]

    write_dataset(
        rows,
        out,
        fmt="parquet",
        split_cfg={"enabled": True, "train": 0.5, "val": 0.25, "test": 0.25},
        provenance={
            "created_utc": "2026-03-08T00:00:00Z",
            "config_hash": "abc",
            "schema": {
                "schema_name": "boiler-pdm-sim-schema-v1.1",
                "schema_version": "v1.1.1",
                "freeze_date": "2026-03-08",
            },
            "governance": {
                "approved_by": "local-operator",
                "approved_at": "2026-03-08T00:00:00Z",
                "approval_status": "approved",
                "classification": "internal",
                "retention_days": 365,
            },
        },
        validation={"passed": True},
        validation_battery={"enabled": False},
        lock_provenance=True,
    )

    manifest = json.loads(out.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["train"] == "integrity_split.train.parquet"
    assert manifest["files"]["val"] == "integrity_split.val.parquet"
    assert manifest["files"]["test"] == "integrity_split.test.parquet"

    policy = load_governance_policy(None)
    report = validate_dataset_artifact(out, policy=policy)
    assert report["passed"] is True
