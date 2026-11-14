"""Dataset split helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .writer import _split_indices


def split_indices(df: pd.DataFrame, split_cfg: dict[str, Any] | None, split_seed: int) -> tuple[dict[str, list[int]], dict[str, Any]]:
    return _split_indices(df, split_cfg, split_seed)


__all__ = ["split_indices"]
