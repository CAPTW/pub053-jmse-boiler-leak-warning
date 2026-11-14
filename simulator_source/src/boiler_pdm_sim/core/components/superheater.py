"""Superheater placeholder for v1."""

from __future__ import annotations


def out_temp(
    T_wall: float,
    T_in: float,
    split: float,
    m_s_kg_s: float = 1.0,
    c_p_J_kgK: float = 2200.0,
    ua_super: float = 1.0,
) -> float:
    """Estimate superheater outlet temperature from available heat split.

    `split` is interpreted as the fraction of UA effectively used by
    this section, bounded to [0, 1].
    """
    T_wall = float(T_wall)
    T_in = float(T_in)
    m_s = max(1e-9, float(m_s_kg_s))
    cp = max(1.0, float(c_p_J_kgK))
    split = float(split)
    if split > 1.0:
        delta_q = max(0.0, split)
    else:
        h_eff = max(0.0, min(1.0, split)) * max(0.0, float(ua_super))
        delta_q = h_eff * max(0.0, T_wall - T_in)
    delta_T = delta_q / (m_s * cp)
    return float(T_in + delta_T)
