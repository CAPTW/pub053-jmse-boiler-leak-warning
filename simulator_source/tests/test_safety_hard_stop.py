from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from boiler_pdm_sim.simulator import Simulator


def _cfg():
    cfg = yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))
    cfg["sim"]["dt"] = 0.5
    cfg["sim"]["horizon_s"] = 400
    cfg["sim"]["solver"] = "euler"
    cfg["sim"]["seed"] = 22
    cfg["scenario"] = {
        "type": "step_tests",
        "seed": 11,
        "step_tests": {
            "base": 0.6,
            "steps": [{"start_s": 80.0, "duration_s": 320.0, "value": 0.85}],
        },
    }
    cfg["fault_instances"] = [
        {
            "type": "fouling",
            "name": "rapid_trip_test",
            "onset_s": 160.0,
            "duration_s": 40.0,
            "alarm_threshold": 0.20,
            "trip_threshold": 0.30,
            "rul_threshold": 1.0,
        }
    ]
    cfg["safety"] = {
        "enabled": True,
        "alarm": {
            "fuel_cmd_max": 0.40,
            "fw_cmd_max": 0.40,
            "steam_demand_max": 0.40,
        },
        "trip": {
            "fuel_cmd": 0.0,
            "fw_cmd": 0.0,
            "steam_demand": 0.0,
        },
    }
    return cfg


def test_alarm_to_trip_forces_hard_stop_controls():
    cfg = _cfg()
    rows = Simulator(seed=22).run(cfg)
    df = pd.DataFrame(rows)

    safety_events = [str(v) for v in df["label/event_log"].explode().dropna()]
    assert any(item.startswith("safety_alarm_enter_t=") for item in safety_events)
    assert any(item.startswith("safety_trip_enter_t=") for item in safety_events)
    assert "actuator_lockout_active" in safety_events

    trip_rows = df[df["label/safety_state"] == "trip"]
    assert len(trip_rows) > 0
    assert (trip_rows["meta/final_control_fuel_cmd"] == 0.0).all()
    assert (trip_rows["meta/final_control_fw_cmd"] == 0.0).all()
    assert (trip_rows["meta/final_control_steam_demand"] == 0.0).all()
    assert (trip_rows["meta/actuator_lockout"] >= 1.0).all()
    assert (trip_rows["meta/safety_action"].explode().dropna() == "safety_trip_hard_stop").any()

    idx = int(trip_rows.index[0])
    assert (df.loc[idx:, "meta/actuator_lockout"] >= 1.0).all()

    alarm_rows = df[(df["label/safety_state"] == "alarm") & (df["label/safety_state"].shift(1) != "alarm")]
    if len(alarm_rows) > 0:
        assert (alarm_rows["meta/final_control_fuel_cmd"] <= 0.40 + 1e-9).all()
