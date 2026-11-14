from __future__ import annotations

import numpy as np

from boiler_pdm_sim.safety import ProcessSafetyMonitor
from boiler_pdm_sim.sensors.sensor_model import SensorModel


def test_sensor_model_respects_sample_period_and_quality_flags() -> None:
    rng = np.random.default_rng(1)
    model = SensorModel(
        {
            "drum_level": {
                "sample_period_s": 2.0,
                "tau_s": 0.0,
                "dead_time_s": 0.0,
                "noise_std": 0.0,
                "range_min": 0.0,
                "range_max": 6.0,
            }
        },
        rng,
    )
    first = model.observe(0.0, {"drum_level": 1.0})
    held = model.observe(1.0, {"drum_level": 2.0})
    resampled = model.observe(2.0, {"drum_level": 2.0})

    assert first["drum_level"] == 1.0
    assert held["drum_level"] == 1.0
    assert resampled["drum_level"] == 2.0
    assert model.last_quality_flags()["drum_level"] == "good"


def test_process_safety_monitor_latches_trip_until_reset() -> None:
    monitor = ProcessSafetyMonitor(
        {
            "process": {
                "alarm": {"level_LLL": 1.0, "sensor_bad_quality": True},
                "trip": {
                    "level_LLL": 0.9,
                    "trip_on_sensor_bad_quality": True,
                    "auto_reset": False,
                    "reset_hold_s": 10.0,
                },
            }
        }
    )

    safe = monitor.evaluate(
        t=0.0,
        truth={"drum_level": 3.0, "drum_pressure": 10.0, "feedwater_flow": 1.0, "steam_flow": 1.0},
        controller_snapshot={"level_pid_saturation_s": 0.0, "pressure_pid_saturation_s": 0.0, "flow_pid_saturation_s": 0.0},
        sensor_quality={"drum_level": "good"},
    )
    trip = monitor.evaluate(
        t=5.0,
        truth={"drum_level": 0.8, "drum_pressure": 10.0, "feedwater_flow": 1.0, "steam_flow": 1.0},
        controller_snapshot={"level_pid_saturation_s": 0.0, "pressure_pid_saturation_s": 0.0, "flow_pid_saturation_s": 0.0},
        sensor_quality={"drum_level": "bad"},
    )
    latched = monitor.evaluate(
        t=20.0,
        truth={"drum_level": 3.0, "drum_pressure": 10.0, "feedwater_flow": 1.0, "steam_flow": 1.0},
        controller_snapshot={"level_pid_saturation_s": 0.0, "pressure_pid_saturation_s": 0.0, "flow_pid_saturation_s": 0.0},
        sensor_quality={"drum_level": "good"},
    )

    assert safe.state == "safe"
    assert trip.state == "trip"
    assert trip.trip_latch
    assert "level_LLL" in trip.trip_names or "sensor_bad_quality" in trip.trip_names
    assert latched.state == "trip"
    assert latched.trip_latch
