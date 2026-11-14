from __future__ import annotations

import numpy as np
import pandas as pd

from boiler_pdm_sim.sensors.sensor_model import SensorModel
from boiler_pdm_sim.validation.level_instrumentation import validate_level_instrumentation


def _truth(level: float, pressure: float) -> dict[str, float]:
    return {
        "drum_level": float(level),
        "drum_pressure": float(pressure),
        "steam_flow": 1.0,
        "feedwater_flow": 1.0,
    }


def test_drum_level_dp_instrument_separates_raw_and_compensated_channels() -> None:
    rng = np.random.default_rng(7)
    model = SensorModel(
        {
            "drum_level": {
                "sample_period_s": 0.5,
                "noise_std": 0.0,
                "tau_s": 0.0,
                "dead_time_s": 0.0,
                "range_min": 0.0,
                "range_max": 6.0,
                "nominal_pressure_bar": 10.0,
                "reference_leg_height_m": 6.0,
                "reference_leg_temp_C": 60.0,
            }
        },
        rng,
    )

    first = model.observe(0.0, _truth(3.1, 10.0))
    second = model.observe(10.0, _truth(3.1, 14.0))

    assert "drum_level_dp_raw" in second
    assert "drum_level_compensated" in second
    assert abs(second["drum_level_dp_raw"] - second["drum_level_compensated"]) > 1e-4
    assert abs(second["drum_level_compensated"] - 3.1) <= abs(second["drum_level_dp_raw"] - 3.1)

    report = validate_level_instrumentation(
        pd.DataFrame(
            [
                {
                    "truth/level_true": 3.1,
                    "obs/drum_level": first["drum_level"],
                    "obs/drum_level_dp_raw": first["drum_level_dp_raw"],
                    "obs/drum_level_compensated": first["drum_level_compensated"],
                },
                {
                    "truth/level_true": 3.1,
                    "obs/drum_level": second["drum_level"],
                    "obs/drum_level_dp_raw": second["drum_level_dp_raw"],
                    "obs/drum_level_compensated": second["drum_level_compensated"],
                },
            ]
        ),
        min_raw_comp_diff=1e-4,
        min_truth_obs_diff=0.0,
    )
    assert report["passed"] is True


def test_drum_level_dp_fault_modes_can_hold_and_degrade_quality() -> None:
    rng = np.random.default_rng(8)
    model = SensorModel(
        {
            "drum_level": {
                "sample_period_s": 0.5,
                "noise_std": 0.0,
                "tau_s": 0.0,
                "dead_time_s": 0.0,
                "range_min": 0.0,
                "range_max": 6.0,
                "nominal_pressure_bar": 10.0,
                "reference_leg_height_m": 6.0,
                "reference_leg_temp_C": 60.0,
            }
        },
        rng,
    )

    first = model.observe(0.0, _truth(3.0, 10.0))
    second = model.observe(
        10.0,
        _truth(3.4, 10.0),
        params={
            "sensors": {
                "drum_level": {
                    "reference_leg_temp_shift_C": 15.0,
                    "wet_leg_density_scale": 1.08,
                    "impulse_line_plugging": 0.95,
                    "freeze_after_s": 5.0,
                }
            }
        },
    )

    assert second["drum_level_dp_raw"] == first["drum_level_dp_raw"]
    assert second["drum_level_compensated"] == first["drum_level_compensated"]
    assert model.last_quality_flags()["drum_level"] == "stale"
