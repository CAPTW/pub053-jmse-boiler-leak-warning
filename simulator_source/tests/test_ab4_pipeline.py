"""End-to-end pipeline integration for the ab4 backend.

Drives the full ``Simulator.run_to_file`` path with ``core_backend.type='ab4'``
(configs/ab4_marine_aux.yaml) and asserts a schema-valid dataset is produced,
the conservation residual channels are tiny (the ab4 win over the grey-box),
the run stays trip-free at the physical operating point, and results are
seed-reproducible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

iapws = pytest.importorskip("iapws")
import yaml

from boiler_pdm_sim.simulator import Simulator

pd = pytest.importorskip("pandas")

_CFG_PATH = Path(__file__).resolve().parents[1] / "configs" / "ab4_marine_aux.yaml"


def _run(tmp_path, horizon_s=300, seed=42):
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(_CFG_PATH.read_text(encoding="utf-8"))
    cfg["sim"]["horizon_s"] = horizon_s
    out = str(tmp_path / "ab4.parquet")
    sim = Simulator(seed=seed)
    sim.run_to_file(cfg, out, "parquet")
    df = pd.read_parquet(out)
    import json

    manifest = json.loads((tmp_path / "ab4.manifest.json").read_text(encoding="utf-8"))
    return df, manifest


def test_ab4_pipeline_produces_valid_dataset(tmp_path):
    df, manifest = _run(tmp_path)
    assert manifest["validation"]["passed"] is True
    assert manifest["validation"].get("failures") in (None, [], ())
    # schema-required channels present
    for c in ("truth/flue_gas_temp", "truth/O2", "truth/h_fw", "truth/drum_pressure", "truth/drum_level"):
        assert c in df.columns
    # ab4 additive physics channels surfaced
    for c in ("truth/alpha_r", "truth/alpha_v_mean", "truth/V_sd", "truth/circulation_flow"):
        assert c in df.columns


def test_ab4_pipeline_conserves_and_metal_follows_tsat(tmp_path):
    df, _ = _run(tmp_path)
    # conservation residuals are ~machine precision (vs grey-box <50 kg/s, <3e7 W)
    assert df["truth/mass_balance_residual"].abs().max() < 1e-6
    assert df["truth/energy_balance_residual"].abs().max() < 1.0
    # metal temperature tracks saturation (no fixed 280 C); ~165 C at 7 bar
    assert 150.0 < df["truth/wall_temp"].max() < 175.0
    assert df["truth/wall_temp"].max() == pytest.approx(df["truth/drum_temp"].max(), rel=1e-6)


def test_ab4_pipeline_stays_physical_and_trip_free(tmp_path):
    df, _ = _run(tmp_path)
    assert (df["truth/drum_pressure"].between(5.0, 9.0)).all()
    assert (df["truth/drum_level"].between(0.0, 1.5)).all()
    if "label/trip_count" in df.columns:
        assert df["label/trip_count"].max() == 0.0


def test_ab4_pipeline_seed_reproducible(tmp_path):
    df1, _ = _run(tmp_path / "a", horizon_s=120, seed=7)
    df2, _ = _run(tmp_path / "b", horizon_s=120, seed=7)
    cols = ["truth/drum_pressure", "truth/drum_level", "obs/drum_pressure"]
    for c in cols:
        assert (df1[c].to_numpy() == df2[c].to_numpy()).all()
