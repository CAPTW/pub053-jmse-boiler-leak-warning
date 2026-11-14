"""Economizer placeholder for v1."""

from __future__ import annotations

from math import exp


def heat_to_fluid(
    q_in: float,
    UA: float,
    T_gas: float,
    T_fw: float,
    m_fw_kg_s: float = 1.0,
    c_p_J_kgK: float = 4200.0,
) -> float:
    """Estimate heat transferred into feedwater and cap with UA or input heat.

    Returns the actual transferred heat in W. This includes a
    first-order approach-to-equilibrium effect through the gas/steam
    temperature gradient.
    """
    q_in = max(0.0, float(q_in))
    if q_in <= 0.0:
        return 0.0
    if m_fw_kg_s <= 1e-9:
        return 0.0

    dT_gas_fw = max(0.0, float(T_gas) - float(T_fw))
    q_limit = max(0.0, float(UA) * dT_gas_fw * max(0.0, (1.0 - exp(-max(q_in, 0.0) / max(UA * max(dT_gas_fw, 1.0), 1.0)))))
    q_transfer = min(q_in, q_limit)
    return float(q_transfer)


def outlet_temperature(
    T_fw: float,
    q_transfer_W: float,
    m_fw_kg_s: float,
    c_p_J_kgK: float = 4200.0,
) -> float:
    """Map transferred heat to outlet temperature with cp closure."""
    T_fw = float(T_fw)
    m_fw = max(1e-9, float(m_fw_kg_s))
    q_transfer_W = max(0.0, float(q_transfer_W))
    c_p = max(1.0, float(c_p_J_kgK))
    return T_fw + q_transfer_W / (m_fw * c_p)
