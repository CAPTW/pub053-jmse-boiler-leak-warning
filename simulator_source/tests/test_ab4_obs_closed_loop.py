"""obs-based closed loop verification (§4 / §7.6, DoD 4).

Same-seed truth vs obs runs of the ab4 pipeline: in obs mode the controller
consumes the previous step's noisy observation, so the control trajectory and
plant state differ from truth mode, while safety stays trip-free and the dataset
stays schema-valid. Also guards that the default ('truth') path is unchanged
(opt-in), preserving the grey-box golden parity that the other suites assert.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

iapws = pytest.importorskip("iapws")
import yaml

from boiler_pdm_sim.simulator import Simulator

pd = pytest.importorskip("pandas")

_CFG_PATH = Path(__file__).resolve().parents[1] / "configs" / "ab4_marine_aux.yaml"


def _run(tmp_path, source, horizon_s=600, seed=42):
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(_CFG_PATH.read_text(encoding="utf-8"))
    cfg["sim"]["horizon_s"] = horizon_s
    cfg.setdefault("control", {})["closed_loop_source"] = source
    out = str(tmp_path / f"{source}.parquet")
    Simulator(seed=seed).run_to_file(cfg, out, "parquet")
    import json

    df = pd.read_parquet(out)
    manifest = json.loads((tmp_path / f"{source}.manifest.json").read_text(encoding="utf-8"))
    return df, manifest


def test_obs_mode_runs_valid_and_trip_free(tmp_path):
    df, manifest = _run(tmp_path, "obs")
    assert manifest["validation"]["passed"] is True
    if "label/trip_count" in df.columns:
        assert df["label/trip_count"].max() == 0.0
    assert (df["truth/drum_pressure"].between(5.0, 9.0)).all()


def test_obs_control_reacts_to_sensor_noise(tmp_path):
    """obs-mode control consumes noisy measurements -> trajectory differs from truth."""
    df_t, _ = _run(tmp_path / "t", "truth")
    df_o, _ = _run(tmp_path / "o", "obs")
    # the pressure loop sees noisy obs/drum_pressure -> different fuel command
    fuel_diff = np.linalg.norm(df_o["meta/fuel_cmd"].to_numpy() - df_t["meta/fuel_cmd"].to_numpy())
    assert fuel_diff > 1e-3
    # ... and the closed-loop plant trajectory diverges measurably
    traj_diff = np.linalg.norm(
        df_o["truth/drum_pressure"].to_numpy() - df_t["truth/drum_pressure"].to_numpy()
    )
    assert traj_diff > 1e-3


def test_default_source_is_truth_passthrough(tmp_path):
    """No closed_loop_source (default) == explicit 'truth' (opt-in; parity-preserving)."""
    cfg = yaml.safe_load(_CFG_PATH.read_text(encoding="utf-8"))
    cfg["sim"]["horizon_s"] = 300
    cfg.get("control", {}).pop("closed_loop_source", None)  # ensure unset
    d = Path(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    Simulator(seed=5).run_to_file(cfg, str(d / "default.parquet"), "parquet")
    df_default = pd.read_parquet(d / "default.parquet")

    df_truth, _ = _run(tmp_path / "explicit", "truth", horizon_s=300, seed=5)
    for ch in ("truth/drum_pressure", "truth/drum_level", "meta/fuel_cmd", "meta/fw_cmd"):
        assert (df_default[ch].to_numpy() == df_truth[ch].to_numpy()).all()
