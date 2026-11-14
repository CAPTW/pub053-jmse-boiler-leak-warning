"""Cross-model regression: legacy grey-box vs Phase A ab4 (§7.5, ADR-5).

The grey-box backend is preserved as the fast baseline; this asserts the two
backends both produce schema-valid datasets through the same pipeline while ab4
is the conservation-grade core — its mass/energy balance residuals are orders of
magnitude smaller and its metal temperature tracks saturation instead of the
grey-box's clamped fixed value. This locks in the headline Phase A improvement.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

iapws = pytest.importorskip("iapws")
import yaml

from boiler_pdm_sim.simulator import Simulator

pd = pytest.importorskip("pandas")

_ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path, cfg_name, backend, horizon_s=300):
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load((_ROOT / "configs" / cfg_name).read_text(encoding="utf-8"))
    cfg["sim"]["horizon_s"] = horizon_s
    cfg["sim"]["dt"] = 1.0
    out = str(tmp_path / f"{backend}.parquet")
    Simulator(seed=42).run_to_file(cfg, out, "parquet")
    df = pd.read_parquet(out)
    manifest = json.loads((tmp_path / f"{backend}.manifest.json").read_text(encoding="utf-8"))
    return df, manifest


def test_both_backends_produce_valid_datasets(tmp_path):
    gb, gm = _run(tmp_path / "gb", "base.yaml", "greybox")
    ab, am = _run(tmp_path / "ab", "ab4_marine_aux.yaml", "ab4")
    assert gm["validation"]["passed"] is True
    assert am["validation"]["passed"] is True
    # same frozen schema contract (v1.1) — required channels in both
    for c in ("truth/drum_pressure", "truth/drum_level", "truth/flue_gas_temp", "truth/O2", "truth/h_fw"):
        assert c in gb.columns and c in ab.columns


def test_ab4_conserves_grey_box_does_not(tmp_path):
    gb, _ = _run(tmp_path / "gb", "base.yaml", "greybox")
    ab, _ = _run(tmp_path / "ab", "ab4_marine_aux.yaml", "ab4")
    gb_mass = gb["truth/mass_balance_residual"].abs().max()
    ab_mass = ab["truth/mass_balance_residual"].abs().max()
    gb_energy = gb["truth/energy_balance_residual"].abs().max()
    ab_energy = ab["truth/energy_balance_residual"].abs().max()
    # ab4 conserves to ~machine precision; grey-box residuals are large/diagnostic
    assert ab_mass < 1e-6
    assert ab_energy < 1.0
    assert gb_mass > 1.0
    # the improvement is many orders of magnitude
    assert ab_mass < gb_mass * 1e-6
    assert ab_energy < gb_energy * 1e-6


def test_ab4_metal_tracks_tsat_grey_box_is_clamped(tmp_path):
    gb, _ = _run(tmp_path / "gb", "base.yaml", "greybox")
    ab, _ = _run(tmp_path / "ab", "ab4_marine_aux.yaml", "ab4")
    # grey-box wall temperature is pinned (clamped) and high
    assert gb["truth/wall_temp"].std() < 1.0
    assert gb["truth/wall_temp"].mean() > 250.0
    # ab4 wall temperature follows saturation: lower and time-varying
    assert ab["truth/wall_temp"].mean() < 200.0
    assert ab["truth/wall_temp"].std() > 0.0
    assert (ab["truth/wall_temp"] == ab["truth/drum_temp"]).all()
