"""Hot-path execution loop extracted from Simulator."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from .runtime import _merge_event_lists
from ..core.backend_protocol import BackendInputs
from ..dataset.generator import DatasetGenerator
from ..schema import SCHEMA_LABEL_KEYS, SCHEMA_LOCK, validate_label_contract_row


def execute_step_loop(
    simulator: Any,
    *,
    cfg: dict[str, Any],
    system: Any,
    controller: Any,
    scheduler: Any,
    profile: Any,
    sensor_model: Any,
    process_safety: Any,
    params: dict[str, Any],
    safety_cfg: dict[str, Any],
    seed: int,
    dt: float,
    controller_dt: float,
    logger_dt: float,
    horizon: int,
    method: str,
    time_jitter: float,
    strict_schema: bool,
) -> list[dict[str, Any]]:
    generator = DatasetGenerator()
    profile_step_event = getattr(profile, "step_event", None)

    control: dict[str, float] = {"fuel_cmd": 0.4, "fw_cmd": 0.5, "steam_demand": 0.6}
    y = system.outputs(BackendInputs.from_control(control), params)
    # obs-based closed loop (§4, ADR-6): control may consume the previous step's
    # observation (1-step measurement delay); safety stays on truth unless opted in.
    # Default "truth" -> obs_prev is never read, so behaviour is byte-identical.
    control_source = str((cfg.get("control") or {}).get("closed_loop_source", "truth")).strip().lower()
    safety_source = str((cfg.get("safety") or {}).get("evaluation_source", "truth")).strip().lower()
    obs_prev = y  # init = truth at t0 (§4 initialization)
    prev_load_cmd: float | None = None
    safety_lockout = False
    prev_safety_state = "safe"
    next_controller_t = 0.0
    next_logger_t = 0.0
    control_snapshot = controller.snapshot()
    simulator._pipeline_meta["correction_count"] = 0

    for i in range(horizon + 1):
        t = i * dt
        load_cmd = float(profile.value(t))
        params_faulted = scheduler.update(t, params)

        # measurement source for control / safety (truth by default; obs = prior step)
        control_y = obs_prev if control_source == "obs" else y
        safety_y = obs_prev if safety_source == "obs" else y

        control_events: list[str] = []
        degradation = params_faulted.get("degradation", {}) if isinstance(params_faulted, dict) else {}
        if i == 0 or t >= next_controller_t - 1e-9:
            control_start = perf_counter()
            control = controller.step(
                t,
                control_y,
                controller_dt,
                load_cmd,
                degradation=degradation if isinstance(degradation, dict) else None,
            )
            control_snapshot = controller.snapshot()
            control_events.extend(controller.pop_events())
            while next_controller_t <= t + 1e-9:
                next_controller_t += max(controller_dt, dt)
            simulator._last_run_timing["control_seconds"] += perf_counter() - control_start

        if profile_step_event is not None:
            try:
                event = profile_step_event(t, float(load_cmd), prev_load_cmd, dt)
            except Exception:
                event = None
            if event:
                control_events.append(str(event))

        process_eval = process_safety.evaluate(
            t=t,
            truth=safety_y,
            controller_snapshot=control_snapshot,
            sensor_quality=sensor_model.last_quality_flags(),
        )
        inv = system.invariants(BackendInputs.from_control(control), params_faulted)
        labels = scheduler.truth_labels(t, params_faulted, load_cmd=load_cmd)
        labels = simulator._merge_process_safety_labels(labels, process_eval)
        safety_state = str(labels.get("safety_state", "safe"))
        if safety_lockout and safety_cfg.get("lockout_on_trip", True):
            safety_state = "trip"
            labels["safety_state"] = safety_state
            labels["trip_latch"] = 1.0

        control, safety_actions, safety_lockout = simulator._apply_safety_interlocks(
            control,
            safety_state,
            safety_cfg,
            lockout_active=safety_lockout,
        )
        if safety_state != prev_safety_state:
            if safety_state == "alarm":
                control_events.append(f"safety_alarm_enter_t={t:.1f}")
            elif safety_state == "trip":
                control_events.append(f"safety_trip_enter_t={t:.1f}")
        control_events.extend(safety_actions)
        if safety_lockout and "actuator_lockout_active" not in control_events:
            control_events.append("actuator_lockout_active")

        model_start = perf_counter()
        row_time = t + simulator.rng.normal(0.0, time_jitter) if time_jitter > 0.0 else t
        inputs_cmd = BackendInputs.from_control(control)
        y_truth = system.outputs(inputs_cmd, params_faulted)
        obs = sensor_model.observe(t, y_truth, params_faulted)
        obs_prev = obs  # feed the next step's obs-based control/safety (1-step delay)
        control_fuel_cmd = float(control.get("fuel_cmd", 0.0))
        control_fw_cmd = float(control.get("fw_cmd", 0.0))
        control_steam_cmd = float(control.get("steam_demand", load_cmd))
        prev_load_cmd = float(load_cmd)
        prev_safety_state = safety_state

        # Stepping, prev-demand tracking, algebraic alignment, state clipping
        # and the schema-locked correction events are the backend's
        # responsibility (CoreBackend.advance) — the loop stays opaque to the
        # state vector.
        step_report = system.advance(t, dt, inputs_cmd, params_faulted, method=method)
        solver_report = step_report.solver
        alg_report = step_report.alignment
        align_seconds = float(step_report.timings.get("align_seconds", 0.0))
        simulator._last_run_timing["align_seconds"] += align_seconds

        correction_events: list[str] = list(step_report.events)
        solver_retry_count = int(solver_report.get("retry_count", 0))

        next_y = system.outputs(inputs_cmd, params_faulted)
        inv["time_next"] = t + dt
        simulator._last_run_timing["model_seconds"] += max(0.0, perf_counter() - model_start - align_seconds)

        residual_before = float(alg_report.get("residual_before_m3", 0.0))
        residual_after = float(alg_report.get("residual_after_m3", 0.0))
        residual_gap = residual_before - residual_after
        iterations = int(alg_report.get("iterations", 0))
        feasible = bool(alg_report.get("feasible", True))
        simulator._last_algebraic_timing["iterations"] += iterations
        simulator._last_algebraic_timing["residuals"].append(abs(residual_after))
        if feasible:
            simulator._last_algebraic_timing["feasible_count"] += 1
        simulator._pipeline_meta["correction_count"] = int(simulator._pipeline_meta.get("correction_count", 0)) + int(
            solver_retry_count
            + int(iterations)
            + (1 if bool(solver_report.get("fallback_used", False)) else 0)
            + (1 if any(ev.startswith("state_clamp_t=") for ev in correction_events) else 0)
        )

        latest_events = _merge_event_lists(labels.get("event_log_latest", []), control_events, correction_events)
        history_events = _merge_event_lists(labels.get("event_log_history", []), control_events, correction_events)
        labels["event_log"] = _merge_event_lists(labels.get("event_log", []), control_events, correction_events)
        labels["event_log_latest"] = latest_events
        labels["event_log_history"] = history_events

        should_log = bool(i == horizon or t >= next_logger_t - 1e-9)
        if should_log:
            while next_logger_t <= t + 1e-9:
                next_logger_t += max(logger_dt, dt)
            flat = simulator._flatten_row(
                max(0.0, float(row_time)),
                cfg.get("scenario", {}).get("type", "scenario"),
                y_truth,
                obs,
                labels,
                inv,
                {
                    "seed": seed,
                    "step": i,
                    "load_cmd": load_cmd,
                    "fuel_cmd": control_fuel_cmd,
                    "fw_cmd": control_fw_cmd,
                    "steam_demand_cmd": control_steam_cmd,
                    "final_control_fuel_cmd": control_fuel_cmd,
                    "final_control_fw_cmd": control_fw_cmd,
                    "final_control_steam_demand": control_steam_cmd,
                    "safety_state": safety_state,
                    "safety_action": list(safety_actions),
                    "actuator_lockout": float(1.0 if safety_lockout and safety_state == "trip" else 0.0),
                    "algebraic_residual_before_m3": residual_before,
                    "algebraic_residual_m3": residual_after,
                    "algebraic_residual_gap_m3": residual_gap,
                    "algebraic_iterations": iterations,
                    "algebraic_feasible": feasible,
                    "solver_requested": str(solver_report.get("requested_method", method)),
                    "solver_used": str(solver_report.get("solver_used", method)),
                    "solver_retry_count": float(solver_retry_count),
                    "solver_rejected_steps": float(solver_report.get("rejected_steps", 0)),
                    "solver_fallback_used": float(1.0 if bool(solver_report.get("fallback_used", False)) else 0.0),
                    "solver_correction_count": float(
                        solver_retry_count
                        + int(iterations)
                        + (1 if bool(solver_report.get("fallback_used", False)) else 0)
                        + (1 if "state_clamp_t={:.1f}".format(t) in correction_events else 0)
                    ),
                    "plant_dt_s": float(dt),
                    "controller_dt_s": float(controller_dt),
                    "sensor_dt_s": float(min([float(v.get("sample_period_s", dt)) for v in params.get("sensors", {}).values() if isinstance(v, dict)] or [dt])),
                    "logger_dt_s": float(logger_dt),
                    "control_mode": str(control_snapshot.get("mode", "auto")),
                    "control_strategy": str(control_snapshot.get("strategy", "single_element")),
                    "fuel_position_feedback": float(control_snapshot.get("fuel_position", control_fuel_cmd)),
                    "feedwater_position_feedback": float(control_snapshot.get("feedwater_position", control_fw_cmd)),
                    "steam_position_feedback": float(control_snapshot.get("steam_position", control_steam_cmd)),
                },
            )
            if strict_schema:
                row_failures = validate_label_contract_row(
                    flat,
                    required_keys=SCHEMA_LABEL_KEYS,
                    event_patterns=SCHEMA_LOCK["event_patterns"],
                )
                if row_failures:
                    raise RuntimeError(
                        "Label contract validation failed in strict mode at step={step}: {issues}".format(
                            step=i,
                            issues=", ".join(row_failures[:8]),
                        )
                    )
            label_start = perf_counter()
            generator.append(flat)
            simulator._last_run_timing["label_seconds"] += perf_counter() - label_start

        y = next_y

    return generator.rows
