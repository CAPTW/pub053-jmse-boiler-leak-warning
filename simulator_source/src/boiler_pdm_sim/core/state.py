"""State helpers for boiler system."""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


DIFFERENTIAL_STATE_NAMES = ["P_d", "M_l", "T_w_d", "m_circ", "m_shrink"]
ALGEBRAIC_STATE_NAMES = ["M_v"]
STATE_NAMES = [*DIFFERENTIAL_STATE_NAMES, *ALGEBRAIC_STATE_NAMES]


@dataclass
class DrumState:
    P_d: float
    M_l: float
    T_w_d: float
    m_circ: float
    m_shrink: float

    def as_array(self) -> np.ndarray:
        return np.array([self.P_d, self.M_l, self.T_w_d, self.m_circ, self.m_shrink], dtype=float)

    @classmethod
    def from_array(cls, arr: np.ndarray) -> "DrumState":
        arr = np.asarray(arr, dtype=float).reshape(-1)
        if arr.size == 6:
            # backward compatible with legacy state ordering that included M_v at index 2
            arr = np.array([arr[0], arr[1], arr[3], arr[4], arr[5]], dtype=float)
        if arr.size != 5:
            raise ValueError("state array must be length 5 (or legacy length 6 including M_v).")
        return cls(*arr.tolist())
