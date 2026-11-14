from __future__ import annotations

import numpy as np


def apply_gaussian(v: float, std: float, rng: np.random.Generator) -> float:
    return float(v + rng.normal(0.0, std))
