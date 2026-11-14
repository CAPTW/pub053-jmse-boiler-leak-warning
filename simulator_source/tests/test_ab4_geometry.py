"""Tests for the Phase A horizontal-cylinder drum geometry (§3.4).

Exact analytic oracles: V(0)=0, V(2r)=pi r^2 L, V(r)=half, symmetry of the
liquid/vapour split, monotonicity, derivative vs finite difference, and
round-trip level_from_volume(volume_from_level(l)) == l.
"""

from __future__ import annotations

import math

import pytest

from boiler_pdm_sim.core.ab4.geometry import DrumGeometry

# marine_aux_boiler.yaml geometry: r=0.75, L=5.0
GEOM = DrumGeometry(radius_m=0.75, length_m=5.0)


def test_endpoints_and_half():
    r, L = GEOM.radius_m, GEOM.length_m
    assert GEOM.volume_from_level(0.0) == pytest.approx(0.0, abs=1e-12)
    assert GEOM.volume_from_level(2 * r) == pytest.approx(GEOM.total_volume_m3, rel=1e-9)
    assert GEOM.volume_from_level(r) == pytest.approx(0.5 * GEOM.total_volume_m3, rel=1e-9)
    assert GEOM.total_volume_m3 == pytest.approx(math.pi * r * r * L, rel=1e-12)


def test_liquid_plus_vapour_equals_total():
    """V(l) + V(2r - l) == total (the vapour space above level l mirrors a liquid of height 2r-l)."""
    r = GEOM.radius_m
    for l in [0.1, 0.3, 0.75, 1.0, 1.4]:
        assert GEOM.volume_from_level(l) + GEOM.volume_from_level(2 * r - l) == pytest.approx(
            GEOM.total_volume_m3, rel=1e-9
        )


def test_monotonic_increasing():
    levels = [i / 100.0 * (2 * GEOM.radius_m) for i in range(101)]
    vols = [GEOM.volume_from_level(l) for l in levels]
    assert all(b >= a for a, b in zip(vols, vols[1:]))


@pytest.mark.parametrize("l", [0.05, 0.2, 0.5, 0.75, 1.0, 1.3, 1.45])
def test_derivative_matches_finite_difference(l):
    eps = 1e-6
    fd = (GEOM.volume_from_level(l + eps) - GEOM.volume_from_level(l - eps)) / (2 * eps)
    assert GEOM.dvolume_dlevel(l) == pytest.approx(fd, rel=1e-4)


@pytest.mark.parametrize("l_true", [1e-3, 0.05, 0.2, 0.5, 0.75, 1.0, 1.3, 1.49, 1.4999])
def test_level_from_volume_roundtrip(l_true):
    v = GEOM.volume_from_level(l_true)
    l_back = GEOM.level_from_volume(v, level_guess_m=GEOM.radius_m)
    assert l_back == pytest.approx(l_true, abs=1e-6)


def test_level_from_volume_clamps_out_of_range():
    assert GEOM.level_from_volume(-5.0) == 0.0
    assert GEOM.level_from_volume(1e6) == pytest.approx(2 * GEOM.radius_m, rel=1e-12)


def test_level_from_volume_converges_from_far_guess():
    """Newton+bisection still converges when the initial guess is at the wrong extreme."""
    l_true = 1.2
    v = GEOM.volume_from_level(l_true)
    assert GEOM.level_from_volume(v, level_guess_m=1e-4) == pytest.approx(l_true, abs=1e-6)
    assert GEOM.level_from_volume(v, level_guess_m=2 * GEOM.radius_m - 1e-4) == pytest.approx(
        l_true, abs=1e-6
    )
