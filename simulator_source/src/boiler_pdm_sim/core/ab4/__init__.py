"""Phase A ``ab4`` physics core (Åström-Bell 4-state drum boiler, docs/phase_a_design.md §3).

Built incrementally per WP A3. Currently provides the nonlinear drum geometry
(§3.4); the 4-state ODE (§3.1), furnace coupling (§3.3), and feedwater/steam/
blowdown lines (§3.5) land in subsequent A3 steps.
"""

from __future__ import annotations

from .geometry import DrumGeometry

__all__ = ["DrumGeometry"]
