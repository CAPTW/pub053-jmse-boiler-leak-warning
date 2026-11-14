"""WP A1 contract tests: backend protocol, advance(), additive schema."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import yaml

from boiler_pdm_sim.core.backend_factory import build_core_backend
from boiler_pdm_sim.core.backend_protocol import BackendInputs, CoreBackend, StepReport
from boiler_pdm_sim.core.boiler_system import BoilerSystem
from boiler_pdm_sim.pipeline.runtime import _coerce_scalars
from boiler_pdm_sim.schema import SCHEMA_LABEL_KEYS, SCHEMA_LOCK, validate_label_contract_row
from boiler_pdm_sim.simulator import Simulator


def _base_cfg() -> dict:
    return yaml.safe_load(Path("configs/base.yaml").read_text(encoding="utf-8"))


def _make_system() -> BoilerSystem:
    cfg = _base_cfg()
    return BoilerSystem({"boiler": cfg["boiler"]})


def test_backend_inputs_roundtrip_preserves_control_mapping_exactly():
    control = {"fuel_cmd": 0.41, "fw_cmd": 0.52, "steam_demand": 0.63, "extra_key": 1.5}
    inputs = BackendInputs.from_control(control)
    assert inputs.as_control() == control

    # Keys absent from the original mapping must stay absent so that
    # control.get(key, default) keeps its legacy default semantics.
    partial = {"fuel_cmd": 0.3}
    rebuilt = BackendInputs.from_control(partial).as_control()
    assert rebuilt == partial
    assert "steam_demand" not in rebuilt

    # An empty captured mapping must round-trip as empty, not as
    # synthesized zero-valued commands.
    assert BackendInputs.from_control({}).as_control() == {}


def test_boiler_system_satisfies_core_backend_protocol():
    system = _make_system()
    assert isinstance(system, CoreBackend)


def test_advance_returns_step_report_with_clipped_state_and_legacy_events():
    system = _make_system()
    cfg = _base_cfg()
    params = {"boiler": cfg["boiler"], "control": cfg.get("control", {})}
    inputs = BackendInputs.from_control({"fuel_cmd": 0.4, "fw_cmd": 0.5, "steam_demand": 0.6})

    report = system.advance(0.0, 0.5, inputs, params, method="euler")

    assert isinstance(report, StepReport)
    assert report.x_after.shape == (5,)
    assert np.all(report.x_after >= system.STATE_LOWER - 1e-12)
    assert np.all(report.x_after <= system.STATE_UPPER + 1e-12)
    # Backend internal state must track the advanced state for the
    # outputs/invariants-on-current-state contract.
    assert np.array_equal(np.asarray(system.state, dtype=float), report.x_after)
    assert set(report.solver) >= {"requested_method", "solver_used", "retry_count", "fallback_used"}
    assert set(report.alignment) >= {"iterations", "residual_before_m3", "residual_after_m3", "feasible", "source"}
    # Schema-locked correction-event grammar.
    allowed_prefixes = ("solver_retry_count=", "solver_fallback_euler_t=", "algebraic_", "state_clamp_t=")
    for event in report.events:
        assert event.startswith(allowed_prefixes), event


def test_outputs_via_inputs_matches_legacy_explicit_state_call():
    system = _make_system()
    cfg = _base_cfg()
    params = {"boiler": cfg["boiler"]}
    control = {"fuel_cmd": 0.4, "fw_cmd": 0.5, "steam_demand": 0.6}

    legacy = system.outputs(np.asarray(system.state, dtype=float), control, params)
    via_inputs = system.outputs(BackendInputs.from_control(control), params)
    assert legacy == via_inputs

    legacy_inv = system.invariants(np.asarray(system.state, dtype=float), control, params)
    via_inputs_inv = system.invariants(BackendInputs.from_control(control), params)
    assert legacy_inv == via_inputs_inv


def test_keyword_params_match_positional_and_apply_faults():
    """outputs(inputs, params=...) must not silently drop faulted params."""
    system = _make_system()
    cfg = _base_cfg()
    clean = {"boiler": cfg["boiler"]}
    faulted = {
        "boiler": cfg["boiler"],
        "degradation": {"eta_comb": 0.5, "ua_scale": 0.6, "fouling_severity": 0.8},
    }
    inputs = BackendInputs.from_control({"fuel_cmd": 0.6, "fw_cmd": 0.5, "steam_demand": 0.6})

    positional = system.outputs(inputs, faulted)
    keyword = system.outputs(inputs, params=faulted)
    assert keyword == positional
    assert keyword != system.outputs(inputs, clean)

    assert system.invariants(inputs, params=faulted) == system.invariants(inputs, faulted)

    with pytest.raises(TypeError):
        system.outputs(inputs, faulted, params=faulted)


def test_advance_emits_clamp_and_solver_events_when_triggered(monkeypatch):
    system = _make_system()
    cfg = _base_cfg()
    params = {"boiler": cfg["boiler"]}
    inputs = BackendInputs.from_control({"fuel_cmd": 0.4, "fw_cmd": 0.5, "steam_demand": 0.6})

    def _wild_step(t, x, control, dt, method, p):
        diag = {
            "requested_method": str(method),
            "solver_used": str(method),
            "retry_count": 2,
            "rejected_steps": 1,
            "fallback_used": True,
            "status": "fallback_euler",
        }
        return np.array([200.0, 1e9, 2000.0, 50.0, 30.0]), diag

    monkeypatch.setattr(system, "_integrate_raw", _wild_step)
    report = system.advance(0.0, 0.5, inputs, params, method="euler")

    assert "solver_retry_count=2_t=0.0" in report.events
    assert "solver_fallback_euler_t=0.0" in report.events
    assert "state_clamp_t=0.0" in report.events
    assert any(ev.startswith("algebraic_") for ev in report.events)
    assert np.all(report.x_after >= system.STATE_LOWER - 1e-12)
    assert np.all(report.x_after <= system.STATE_UPPER + 1e-12)


def test_advance_propagates_alignment_failures(monkeypatch):
    """Silent except->projection fallback was removed by design (fail-loud)."""
    system = _make_system()
    cfg = _base_cfg()
    params = {"boiler": cfg["boiler"]}
    inputs = BackendInputs.from_control({"fuel_cmd": 0.4, "fw_cmd": 0.5, "steam_demand": 0.6})

    def _broken_align(x, p, **kwargs):
        raise RuntimeError("alignment blew up")

    monkeypatch.setattr(system, "align_algebraic_state", _broken_align)
    with pytest.raises(RuntimeError, match="alignment blew up"):
        system.advance(0.0, 0.5, inputs, params, method="euler")


def test_step_report_state_is_defensive_copy():
    system = _make_system()
    cfg = _base_cfg()
    params = {"boiler": cfg["boiler"]}
    inputs = BackendInputs.from_control({"fuel_cmd": 0.4, "fw_cmd": 0.5, "steam_demand": 0.6})

    report = system.advance(0.0, 0.5, inputs, params, method="euler")
    before = np.asarray(system.state, dtype=float).copy()
    report.x_after[0] = -999.0
    assert np.array_equal(np.asarray(system.state, dtype=float), before)


class _FlakyEchoFMUSlave:
    """Echo FMU double whose do_step can fail once with a non-FMU exception,
    mimicking fmpy raising FMICallException on fmi2Discard."""

    def __init__(self, boiler_cfg: dict) -> None:
        self._params = {"boiler": _coerce_scalars(deepcopy(boiler_cfg))}
        self._system = BoilerSystem(self._params)
        self._state_names = ["P_d", "M_l", "T_w_d", "m_circ", "m_shrink"]
        self._inputs = {"fuel_cmd": 0.4, "fw_cmd": 0.5, "steam_demand": 0.6}
        self._state = self._system.state.copy()
        self._time = 0.0
        self.fail_next = False

    def initialize(self) -> None:
        self._time = 0.0

    def set(self, name: str, value: float) -> None:
        if name in self._state_names:
            self._state[self._state_names.index(name)] = float(value)
        elif name in self._inputs:
            self._inputs[name] = float(value)
        elif name == "time":
            self._time = float(value)

    def get(self, name: str) -> float:
        if name in self._state_names:
            return float(self._state[self._state_names.index(name)])
        outputs = self._system.outputs(self._state, self._inputs, self._params)
        if name in outputs:
            return float(outputs[name])
        raise KeyError(name)

    def do_step(self, currentCommunicationPoint: float, communicationStepSize: float, *_args) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("transient fmi2Discard")
        dx = self._system.derivatives(self._time, self._state, self._inputs, self._params)
        self._state = self._state + float(communicationStepSize) * dx
        self._time = float(currentCommunicationPoint) + float(communicationStepSize)


def test_fmu_advance_recovers_from_transient_step_failure(monkeypatch):
    cfg = _base_cfg()
    slave = _FlakyEchoFMUSlave(cfg["boiler"])
    monkeypatch.setattr(
        "boiler_pdm_sim.core.fmu_adapter._load_fmu",
        lambda *_args, **_kwargs: slave,
    )
    backend = build_core_backend(
        cfg["boiler"],
        {
            "type": "fmu",
            "path": "unused_model.fmu",
            "variables": {
                "state_names": ["P_d", "M_l", "T_w_d", "m_circ", "m_shrink"],
                "input_names": ["fuel_cmd", "fw_cmd", "steam_demand"],
                "output_map": {"drum_pressure": "drum_pressure", "drum_level": "drum_level"},
            },
        },
    )
    inputs = BackendInputs.from_control({"fuel_cmd": 0.4, "fw_cmd": 0.5, "steam_demand": 0.6})
    params = {"boiler": cfg["boiler"]}

    slave.fail_next = True
    report = backend.advance(0.0, 0.5, inputs, params, method="euler")
    assert bool(report.solver["fallback_used"]) is True
    assert int(report.solver["retry_count"]) >= 1
    assert str(report.solver["status"]).startswith("fmu_step_failed:")
    assert any(ev.startswith("solver_fallback_euler_t=") for ev in report.events)

    clean = backend.advance(0.5, 0.5, inputs, params, method="euler")
    assert clean.solver["status"] == "backend_step"
    assert bool(clean.solver["fallback_used"]) is False


def test_additive_truth_channels_pass_label_contract():
    """ab4 will add truth/* channels; SCHEMA_LOCK keeps truth/* additive-safe."""
    cfg = _base_cfg()
    cfg["sim"]["horizon_s"] = 2.0
    cfg["sim"]["dt"] = 1.0
    cfg["sim"]["solver"] = "euler"
    rows = Simulator(seed=11).run(cfg)
    assert rows

    row = dict(rows[0])
    row["truth/fuel_flow_kg_s"] = 0.09
    row["truth/lambda_excess_air"] = 1.15
    row["truth/boiler_efficiency"] = 0.90

    failures = validate_label_contract_row(
        row,
        required_keys=SCHEMA_LABEL_KEYS,
        event_patterns=SCHEMA_LOCK["event_patterns"],
    )
    assert failures == []
