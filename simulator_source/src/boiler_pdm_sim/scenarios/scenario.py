from __future__ import annotations

from typing import Any

import numpy as np

from .profile import LoadFollowProfile, StepProfile


def build_profile(cfg: dict[str, Any], rng: np.random.Generator):
    stype = str(cfg.get("type", "load_follow"))
    if stype == "step_tests":
        return StepProfile(cfg.get("step_tests", cfg))
    if stype == "load_follow":
        return LoadFollowProfile(cfg.get("load_follow", cfg), rng)
    raise ValueError(f"Unknown scenario type: {stype}")
