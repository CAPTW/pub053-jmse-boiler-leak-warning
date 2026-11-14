from __future__ import annotations

from pathlib import Path


def test_workspace_compatibility_paths_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    for rel_path in (
        "blueprint.md",
        "cli",
        "dataset",
        "validation",
        "safety",
        "calibration",
        "interface",
    ):
        assert (root / rel_path).exists()
