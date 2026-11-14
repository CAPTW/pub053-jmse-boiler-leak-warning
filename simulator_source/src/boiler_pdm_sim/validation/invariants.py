"""Validation utilities for invariants."""

from __future__ import annotations


def mass_energy_ok(invariants: dict[str, float], mass_tol: float = 1e-4, energy_tol: float = 5e6) -> bool:
    return bool(invariants["mass_balance_residual"] < mass_tol and invariants["energy_balance_residual"] < energy_tol)
