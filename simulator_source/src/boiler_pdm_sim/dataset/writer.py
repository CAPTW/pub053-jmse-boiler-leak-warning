"""Persist simulation outputs to parquet or hdf5."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from pathlib import Path

import numpy as np

import pandas as pd


def to_frame(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame.from_records(rows)


def _infer_format(path: Path, fmt: str | None) -> str:
    if fmt:
        return str(fmt).lower()
    suffix = path.suffix.lower()
    if suffix in {".h5", ".hdf", ".hdf5"}:
        return "hdf5"
    return "parquet"


def _coerce_fraction_cfg(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return float(default)


def _coerce_int_cfg(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return int(default)


def _looks_like_counts(value: float) -> bool:
    return value > 1.0


def _split_counts(n_items: int, split_cfg: dict[str, Any]) -> tuple[int, int, int]:
    count_cfg = split_cfg.get("counts", split_cfg)
    n_train = _coerce_int_cfg(count_cfg.get("train_count"), 0)
    n_val = _coerce_int_cfg(count_cfg.get("val_count"), 0)
    n_test = _coerce_int_cfg(count_cfg.get("test_count"), 0)

    # backward-compatible auto-detect where user accidentally passes counts as bare numbers
    if (n_train == 0 and n_val == 0 and n_test == 0) and all(
        key in count_cfg for key in ("train", "val", "test")
    ):
        train_ratio = float(count_cfg.get("train", 0.0))
        val_ratio = float(count_cfg.get("val", 0.0))
        test_ratio = float(count_cfg.get("test", 0.0))
        if _looks_like_counts(train_ratio) or _looks_like_counts(val_ratio) or _looks_like_counts(test_ratio):
            n_train = int(train_ratio)
            n_val = int(val_ratio)
            n_test = int(test_ratio)

    if n_train + n_val + n_test > 0:
        total = n_train + n_val + n_test
        if total > n_items:
            scale = n_items / max(1, total)
            n_train = int(n_train * scale)
            n_val = int(n_val * scale)
            n_test = int(n_test * scale)
        if n_train + n_val + n_test == 0:
            return 0, 0, 0
        if n_train + n_val + n_test < n_items:
            n_test += n_items - (n_train + n_val + n_test)
        if n_test < 0:
            n_test = 0
            n_val = max(0, n_items - n_train)
    else:
        train_ratio = _coerce_fraction_cfg(count_cfg.get("train"), 0.70)
        val_ratio = _coerce_fraction_cfg(count_cfg.get("val"), 0.15)
        test_ratio = _coerce_fraction_cfg(count_cfg.get("test"), 0.15)
        total = train_ratio + val_ratio + test_ratio
        if total <= 0.0:
            return 0, 0, 0
        train_ratio /= total
        val_ratio /= total
        test_ratio /= total
        n_train = int(n_items * train_ratio)
        n_val = int(n_items * val_ratio)
        n_test = n_items - n_train - n_val
        if n_test < 0:
            n_test = 0
            n_val = max(0, n_items - n_train)

    if n_train + n_val + n_test < n_items:
        n_train += n_items - (n_train + n_val + n_test)

    return n_train, n_val, n_test


def _split_indices(df: pd.DataFrame, split_cfg: dict[str, Any] | None, split_seed: int) -> tuple[dict[str, list[int]], dict[str, Any]]:
    n_rows = int(len(df))
    if n_rows <= 0:
        return {}, {"enabled": False, "unit": "none", "reason": "empty_dataset"}
    if not isinstance(split_cfg, dict) or not split_cfg:
        return {}, {"enabled": False, "unit": "none", "reason": "split_not_configured"}
    if split_cfg.get("enabled", True) is False:
        return {}, {"enabled": False, "unit": "none", "reason": "split_disabled"}

    default_group_keys = [
        key for key in ("meta/scenario_group_id", "scenario_id", "meta/parameter_draw", "meta/fault_instance_id") if key in df.columns
    ]
    group_keys_raw = split_cfg.get("group_by")
    if isinstance(group_keys_raw, (list, tuple)):
        group_keys = [str(v) for v in group_keys_raw if str(v) in df.columns]
    else:
        group_keys = default_group_keys

    if group_keys:
        group_labels = (
            df[group_keys]
            .fillna("NA")
            .astype(str)
            .agg("|".join, axis=1)
        )
        group_map: dict[str, list[int]] = {}
        for idx, group_id in enumerate(group_labels.tolist()):
            group_map.setdefault(str(group_id), []).append(int(idx))
        item_ids = list(group_map.keys())
        unit = "group"
    else:
        group_map = {str(idx): [int(idx)] for idx in range(n_rows)}
        item_ids = list(group_map.keys())
        unit = "row"

    n_train, n_val, n_test = _split_counts(len(item_ids), split_cfg)
    if n_train <= 0 and n_val <= 0 and n_test <= 0:
        return {}, {"enabled": False, "unit": unit, "reason": "zero_targets", "group_by": group_keys}
    if unit == "group" and len(item_ids) < 2:
        return {}, {"enabled": False, "unit": unit, "reason": "insufficient_groups", "group_by": group_keys, "n_groups": len(item_ids)}

    indices = np.arange(len(item_ids), dtype=int)
    if split_cfg.get("shuffle", False):
        rng = np.random.default_rng(int(split_seed))
        rng.shuffle(indices)

    out: dict[str, list[int]] = {}
    start = 0
    if n_train > 0:
        train_groups = indices[start : start + n_train].tolist()
        out["train"] = [row_idx for group_idx in train_groups for row_idx in group_map[item_ids[group_idx]]]
        start += n_train
    if n_val > 0:
        val_groups = indices[start : start + n_val].tolist()
        out["val"] = [row_idx for group_idx in val_groups for row_idx in group_map[item_ids[group_idx]]]
        start += n_val
    if n_test > 0:
        test_groups = indices[start : start + n_test].tolist()
        out["test"] = [row_idx for group_idx in test_groups for row_idx in group_map[item_ids[group_idx]]]

    return out, {
        "enabled": True,
        "unit": unit,
        "group_by": group_keys,
        "n_groups": len(item_ids) if unit == "group" else n_rows,
    }


def _write_table(df: pd.DataFrame, path: Path, fmt: str) -> None:
    if fmt == "parquet":
        df.to_parquet(path, index=False)
    elif fmt in {"hdf", "hdf5"}:
        df.to_hdf(path, key="boiler_sim", mode="w")
    else:
        raise ValueError(fmt)


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest_path = path.parent / f"{path.stem}.manifest.json"
    manifest_path.write_bytes(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _describe_file_integrity(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "size_bytes": int(path.stat().st_size),
        "sha256": _sha256_file(path),
    }


def _manifest_content_sha256(manifest: dict[str, Any]) -> str:
    payload = {k: v for k, v in manifest.items() if k != "integrity"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def write_dataset(
    rows: list[dict],
    path: str,
    fmt: str | None = "parquet",
    *,
    split_cfg: dict[str, Any] | None = None,
    split_seed: int = 42,
    provenance: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    validation_battery: dict[str, Any] | None = None,
    lock_provenance: bool = False,
) -> Path:
    df = to_frame(rows)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fmt = _infer_format(p, fmt)
    _write_table(df, p, fmt)

    lock_requested = bool(lock_provenance)
    if lock_requested and validation is not None and not bool(validation.get("passed", False)):
        raise ValueError("Cannot lock provenance until validation passes.")

    split_rows, split_meta = _split_indices(df, split_cfg, split_seed)
    if not split_rows:
        if provenance is None and validation is None and not lock_requested:
            return p

        manifest = {
            "split_enabled": False,
            "split_seed": int(split_seed),
            "n_total": int(len(df)),
            "n_splits": 0,
            "counts": {},
            "split": {},
            "files": {},
            "fmt": fmt,
            "validation": validation,
            "validation_battery": validation_battery,
            "provenance": provenance or {},
            "provenance_locked": lock_requested,
            "split_strategy": split_meta,
        }
        manifest["integrity"] = {
            "algorithm": "sha256",
            "manifest": {
                "content_sha256": _manifest_content_sha256(manifest),
            },
            "files": {
                "dataset": _describe_file_integrity(p),
            },
        }
        _write_manifest(p, manifest)
        return p

    counts: dict[str, int] = {}
    files: dict[str, str] = {}
    split_paths: dict[str, Path] = {}
    suffix = p.suffix or ".parquet"
    if p.suffix:
        stem = p.stem
    else:
        stem = p.name or "boiler_sim"

    for split_name, idx in split_rows.items():
        if not idx:
            continue
        split_df = df.iloc[idx].copy()
        split_path = p.parent / f"{stem}.{split_name}{suffix}"
        _write_table(split_df, split_path, fmt)
        counts[split_name] = len(split_df)
        files[split_name] = str(split_path.relative_to(p.parent))
        split_paths[split_name] = split_path

    manifest = {
        "split_enabled": True,
        "split_seed": int(split_seed),
        "n_total": int(len(df)),
        "n_splits": len(counts),
        "counts": counts,
        "split": {k: v for k, v in split_rows.items() if v},
        "files": files,
        "fmt": fmt,
        "validation": validation,
        "validation_battery": validation_battery,
        "provenance": provenance or {},
        "provenance_locked": lock_requested,
        "split_strategy": split_meta,
    }
    manifest["integrity"] = {
        "algorithm": "sha256",
        "manifest": {
            "content_sha256": _manifest_content_sha256(manifest),
        },
        "files": {
            "dataset": _describe_file_integrity(p),
            **{name: _describe_file_integrity(path) for name, path in split_paths.items()},
        },
    }
    _write_manifest(p, manifest)
    return p
