from __future__ import annotations

import numpy as np


def should_drop(p: float, rng: np.random.Generator) -> bool:
    return bool(rng.uniform(0.0, 1.0) < p)
