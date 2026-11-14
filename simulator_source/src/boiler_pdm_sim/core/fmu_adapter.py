"""FMU adapter bridge for optional co-simulation backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
import re
from typing import Any, Mapping
import shutil

import numpy as np

from .backend_protocol import BackendInputs, LegacyAdvanceMixin
from .boiler_system import BoilerSystem
from .solver import integrate_step


class FMUBackendError(RuntimeError):
    """Raised when FMU backend loading or operation fails."""


@dataclass(frozen=True)
class FMUVariableConfig:
    state_names: tuple[str, ...]
    input_names: tuple[str, ...]
    output_map: Mapping[str, str] = field(default_factory=dict)
    derivative_names: tuple[str, ...] = ()
    invariant_map: Mapping[str, str] = field(default_factory=dict)
    algebraic_state_names: tuple[str, ...] = ()
    algebraic_map: Mapping[str, str] = field(default_factory=dict)


class _FMPYSlaveAdapter:
    """Small adapter to normalize fmpy slave APIs to `set`/`get`/`do_step`."""

    def __init__(self, fmu: Any, value_refs: Mapping[str, int], unzip_dir: str, *, mode: str = "co-simulation") -> None:
        self._fmu = fmu
        self._value_refs = dict(value_refs)
        self._unzip_dir = unzip_dir
        self._mode = str(mode).strip().lower() or "co-simulation"

    @staticmethod
    def _mapping_error(code: str, msg: str, *, fmu: Any, missing: str) -> str:
        return _mapping_error_with_help(code, msg, missing=missing, fmu=fmu)

    def has_variable(self, name: str) -> bool:
        return str(name) in self._value_refs

    def initialize(self) -> None:
        instantiate = getattr(self._fmu, "instantiate", None)
        if callable(instantiate):
            try:
                instantiate(visible=False, callbacks=None, loggingOn=False)
            except TypeError:
                try:
                    instantiate()
                except TypeError:
                    pass
        setup = getattr(self._fmu, "setupExperiment", None)
        if callable(setup):
            try:
                setup(startTime=0.0)
            except TypeError:
                try:
                    setup(0.0)
                except TypeError:
                    pass
        setup_snake = getattr(self._fmu, "setup_experiment", None)
        if callable(setup_snake):
            try:
                setup_snake(start_time=0.0)
            except TypeError:
                try:
                    setup_snake(0.0)
                except TypeError:
                    pass

        enter_init = getattr(self._fmu, "enterInitializationMode", None)
        if callable(enter_init):
            try:
                enter_init()
            except TypeError:
                pass
        enter_init_snake = getattr(self._fmu, "enter_initialization_mode", None)
        if callable(enter_init_snake):
            try:
                enter_init_snake()
            except TypeError:
                pass

        exit_init = getattr(self._fmu, "exitInitializationMode", None)
        if callable(exit_init):
            try:
                exit_init()
            except TypeError:
                pass
        exit_init_snake = getattr(self._fmu, "exit_initialization_mode", None)
        if callable(exit_init_snake):
            try:
                exit_init_snake()
            except TypeError:
                pass

        if self._mode == "model-exchange":
            for method_name in ("enterContinuousTimeMode", "enter_continuous_time_mode"):
                method = getattr(self._fmu, method_name, None)
                if callable(method):
                    try:
                        method()
                    except TypeError:
                        pass

    def close(self) -> None:
        for method_name in ("terminate", "freeInstance", "free_instance"):
            method = getattr(self._fmu, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
        if self._unzip_dir:
            shutil.rmtree(self._unzip_dir, ignore_errors=True)

    def __del__(self) -> None:
        self.close()

    def set(self, name: str, value: Any) -> None:
        if hasattr(self._fmu, "set"):
            try:
                self._fmu.set(name, float(value))
                return
            except Exception:
                pass

        vr = self._value_refs.get(name)
        if vr is None:
            # fallback: tolerate valueReference-like aliases in case of minor naming mismatch
            vr = self._value_refs.get(str(name))
            if vr is None:
                raise FMUBackendError(
                    self._mapping_error(
                        "missing_variable",
                        f"state/input/output variable {name!r} missing from FMU variable map",
                        fmu=self,
                        missing=str(name),
                    )
                )
        set_real = getattr(self._fmu, "setReal", None)
        set_real_snake = getattr(self._fmu, "set_real", None)
        if callable(set_real):
            set_real([int(vr)], [float(value)])
            return
        if callable(set_real_snake):
            try:
                set_real_snake([int(vr)], [float(value)])
                return
            except Exception:
                set_real_snake(name, float(value))
                return
        raise FMUBackendError(
            self._mapping_error(
                "backend_api",
                "FMU backend does not expose set/setReal/set_real",
                fmu=self,
                missing=str(name),
            )
        )

    def get(self, name: str) -> float:
        if hasattr(self._fmu, "get"):
            try:
                return float(self._fmu.get(name))
            except Exception:
                pass

        vr = self._value_refs.get(name)
        if vr is None:
            vr = self._value_refs.get(str(name))
            if vr is None:
                raise FMUBackendError(
                    self._mapping_error(
                        "missing_variable",
                        f"state/input/output variable {name!r} missing from FMU variable map",
                        fmu=self,
                        missing=str(name),
                    )
                )
        get_real = getattr(self._fmu, "getReal", None)
        get_real_snake = getattr(self._fmu, "get_real", None)
        if callable(get_real):
            values = get_real([int(vr)])
            if not values:
                raise FMUBackendError(
                    self._mapping_error(
                        "empty_value",
                        f"FMU getReal returned no value for {name!r}",
                        fmu=self,
                        missing=str(name),
                    )
                )
            return float(values[0])
        if callable(get_real_snake):
            try:
                values = get_real_snake([int(vr)])
                if values:
                    return float(values[0])
                value = get_real_snake(name)
                return float(value)
            except Exception:
                value = get_real_snake(name)
                return float(value)
        raise FMUBackendError(
            self._mapping_error(
                "backend_api",
                "FMU backend does not expose get/getReal/get_real",
                fmu=self,
                missing=str(name),
            )
        )

    def do_step(self, t: float, dt: float, *_args: Any) -> None:
        do_step = getattr(self._fmu, "doStep", None)
        if callable(do_step):
            try:
                do_step(currentCommunicationPoint=float(t), communicationStepSize=float(dt))
                return
            except TypeError:
                do_step(float(t), float(dt), True)
                return
        do_step_snake = getattr(self._fmu, "do_step", None)
        if callable(do_step_snake):
            do_step_snake(float(t), float(dt), True)
            return
        raise FMUBackendError(f"FMU backend does not expose doStep/do_step for mode '{self._mode}'.")


def _build_fmpy_value_refs(model_description: Any) -> dict[str, int]:
    value_refs: dict[str, int] = {}
    for var in getattr(model_description, "modelVariables", []):
        name = getattr(var, "name", None)
        ref = getattr(var, "valueReference", None)
        if name is None or ref is None:
            continue
        try:
            value_refs[str(name)] = int(ref)
        except (TypeError, ValueError):
            continue
    return value_refs


def _discover_fmu_variables(fmu: Any) -> list[str]:
    names: list[str] = []
    raw_names = getattr(fmu, "_value_refs", None)
    if isinstance(raw_names, dict):
        names.extend(str(key) for key in raw_names.keys())

    for getter_name in (
        "get_variable_names",
        "getModelVariables",
        "get_model_variables",
    ):
        getter = getattr(fmu, getter_name, None)
        if not callable(getter):
            continue
        try:
            values = getter()
        except Exception:
            continue
        if isinstance(values, dict):
            names.extend(str(key) for key in values.keys())
        elif isinstance(values, (list, tuple, set)):
            names.extend(str(item) for item in values)

    return sorted(set(name for name in names if str(name).strip()))


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _suggest_variable_names(missing: str, available: list[str], *, max_suggestions: int = 3) -> list[str]:
    suggestions = get_close_matches(missing, available, n=max_suggestions, cutoff=0.55)
    if suggestions:
        return suggestions
    normalized = _normalize_name(missing)
    if not normalized:
        return []
    fallback = [name for name in available if _normalize_name(name) == normalized or normalized in _normalize_name(name)]
    if fallback:
        return fallback[:max_suggestions]
    return []


def _mapping_error_with_help(code: str, msg: str, *, missing: str, fmu: Any) -> str:
    available = _discover_fmu_variables(fmu)
    suggestion = _suggest_variable_names(missing, available)
    if suggestion:
        return (
            f"[FMU_MAPPING:{code}] {msg}"
            f" Available nearest matches: {', '.join(suggestion)}"
        )
    if available:
        return f"[FMU_MAPPING:{code}] {msg}"
    return f"[FMU_MAPPING:{code}] {msg}"


def _normalize_fmi_mode(fmi_mode: str | None) -> str:
    mode = str(fmi_mode or "co-simulation").strip().lower() or "co-simulation"
    if mode in {"model-exchange", "model_exchange", "me"}:
        return "model-exchange"
    return "co-simulation"


def _load_fmu_via_fmpy(path: str, *, fmi_mode: str = "co-simulation") -> Any:
    from fmpy import extract, instantiate_fmu, read_model_description

    fmu_path = str(Path(path))
    model_description = read_model_description(fmu_path)
    unzip_dir = extract(fmu_path)
    mode = _normalize_fmi_mode(fmi_mode)
    value_refs = _build_fmpy_value_refs(model_description)
    if not value_refs:
        raise FMUBackendError("FMU model description has no model variables.")

    fmu = None
    try:
        fmu = instantiate_fmu(
            unzip_dir,
            model_description,
            fmi_type="ModelExchange" if mode == "model-exchange" else "CoSimulation",
            visible=False,
            debug_logging=False,
        )
    except Exception as exc:
        # Compile binary variant (Windows/architecture mismatch) and retry once.
        try:
            from fmpy.util import compile_platform_binary

            compile_platform_binary(fmu_path)
            fmu = instantiate_fmu(
                unzip_dir,
                model_description,
                fmi_type="ModelExchange" if mode == "model-exchange" else "CoSimulation",
                visible=False,
                debug_logging=False,
            )
        except Exception as retry_exc:
            shutil.rmtree(unzip_dir, ignore_errors=True)
            raise FMUBackendError(f"fmpy: {exc!r}; retry with compiled binary failed: {retry_exc!r}") from retry_exc

    if fmu is None:
        shutil.rmtree(unzip_dir, ignore_errors=True)
        raise FMUBackendError("fmpy: failed to instantiate FMU slave.")

    return _FMPYSlaveAdapter(fmu, value_refs, unzip_dir, mode=mode)


def _normalize_fmu_path(raw_path: str) -> str:
    candidate = Path(raw_path).expanduser()
    if candidate.exists():
        return str(candidate)
    candidate_bases = [Path.cwd(), Path(__file__).resolve()]
    root = candidate_bases[-1]
    for _ in range(3):
        root = root.parent
        candidate_bases.append(root)
    for base in candidate_bases:
        possible = (base / candidate).resolve()
        if possible.exists():
            return str(possible)
    return str(candidate)


def _coerce_mapping(raw: Any, *, section: str, required: bool = False) -> dict[str, str]:
    if raw is None:
        if required:
            raise FMUBackendError(f"[FMU_MAPPING:missing] required section '{section}' is missing")
        return {}
    if isinstance(raw, Mapping):
        out: dict[str, str] = {}
        for key, value in raw.items():
            if key is None or value is None:
                continue
            out[str(key)] = str(value)
        if required and not out:
            raise FMUBackendError(f"[FMU_MAPPING:empty] required section '{section}' cannot be empty")
        return out
    raise FMUBackendError(f"[FMU_MAPPING:type] section '{section}' must be a mapping")


def _coerce_names(raw: Any, *, section: str, required: bool = False) -> tuple[str, ...]:
    if raw is None:
        if required:
            raise FMUBackendError(f"[FMU_MAPPING:missing] required section '{section}' is missing")
        return ()
    if isinstance(raw, str):
        return (raw,)
    if not isinstance(raw, (list, tuple, set)):
        raise FMUBackendError(f"[FMU_MAPPING:type] section '{section}' must be a list of strings")
    names: list[str] = []
    for value in raw:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            names.append(text)
    if required and not names:
        raise FMUBackendError(f"[FMU_MAPPING:empty] required section '{section}' cannot be empty")
    return tuple(names)


def _ensure_fmu_variables(
    fmu: Any,
    section: str,
    variable_names: tuple[str, ...] | dict[str, str],
) -> None:
    requested: list[str] = []
    if isinstance(variable_names, dict):
        requested.extend(str(v) for v in variable_names.values())
    else:
        requested.extend(str(v) for v in variable_names)
    if not requested:
        return

    if hasattr(fmu, "has_variable") and callable(getattr(fmu, "has_variable")):
        missing = [name for name in requested if not fmu.has_variable(name)]
    else:
        # Fallback: skip strict checks for non-FMPY backends where value-ref maps
        # might not be available at adapter-construction time.
        missing = []
    if missing:
        avail = _discover_fmu_variables(fmu)
        missing_unique = sorted(set(missing))
        suggestion_blocks: list[str] = []
        for name in missing_unique:
            suggestions = _suggest_variable_names(name, avail)
            if suggestions:
                suggestion_blocks.append(f"{name} -> {', '.join(suggestions)}")
        if not suggestion_blocks:
            suggestion_blocks.append("<no close name suggestions>")
        raise FMUBackendError(
            f"[FMU_MAPPING:missing_variable] backend='{section}' requires missing variables: {', '.join(missing_unique)}; "
            f"nearest matches: {'; '.join(suggestion_blocks)}; "
            f"available={len(avail)}"
        )


class FMUCoreAdapter(LegacyAdvanceMixin):
    """Adapter that exposes the simulator core API expected by `Simulator`.

    The implementation is intentionally defensive: it supports optional FMU
    backends where available and documents expected variable mappings.
    """

    def _integrate_raw(
        self,
        t: float,
        x: np.ndarray,
        control: Mapping[str, Any],
        dt: float,
        method: str,
        params: Mapping[str, Any],
    ) -> tuple[np.ndarray, dict[str, Any]]:
        x_arr = np.asarray(x, dtype=float)
        try:
            x_next = self.step(t, x_arr, control, dt)
            arr = np.asarray(x_next, dtype=float)
            if arr.shape != x_arr.shape:
                raise FMUBackendError(
                    "FMU step returned a state of unexpected shape "
                    f"{arr.shape!r} (expected {x_arr.shape!r})."
                )
            return arr, {
                "requested_method": str(method),
                "solver_used": str(type(self).__name__).lower(),
                "retry_count": 0,
                "rejected_steps": 0,
                "fallback_used": False,
                "status": "backend_step",
            }
        except Exception as exc:
            # Transient do_step failures (e.g. fmpy raising on fmi2Discard)
            # used to be recovered by the loop via the derivative-based
            # integrator. Keep that recovery, but promote the failure into
            # the step report so it surfaces as solver_retry/fallback events
            # instead of being silently absorbed. If the derivative fallback
            # also fails, the exception propagates (fail-loud).
            fun = lambda ti, xx: self.derivatives(ti, xx, control, params)
            x_next, diag = integrate_step(fun, t, x_arr, dt, method=method, return_diagnostics=True)
            report = dict(diag)
            report["retry_count"] = int(report.get("retry_count", 0)) + 1
            report["fallback_used"] = True
            report["status"] = f"fmu_step_failed:{type(exc).__name__}"
            return np.asarray(x_next, dtype=float), report

    def __init__(
        self,
        fmu: Any,
        config: FMUVariableConfig,
        *,
        step_size: float = 0.1,
        time_var: str = "time",
        initial_state: np.ndarray | None = None,
        fmi_mode: str = "co-simulation",
    ) -> None:
        self._fmu = fmu
        self._config = config
        self._step_size = float(step_size)
        self._time_var = str(time_var)
        self._fmi_mode = _normalize_fmi_mode(fmi_mode)
        self._prev_steam_demand = None
        if initial_state is None:
            initial_state = np.zeros(len(config.state_names), dtype=float)
        self._initial_state = np.asarray(initial_state, dtype=float).reshape(-1)
        if self._initial_state.size != len(config.state_names):
            raise FMUBackendError("FMU initial state size does not match configured state names.")
        self._state = self._initial_state.copy()
        self._last_time = 0.0

        if hasattr(self._fmu, "initialize"):
            try:
                self._fmu.initialize()
            except Exception:
                # Keep initialization lazy to support read-only inspection.
                pass

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any], boiler_cfg: Mapping[str, Any]) -> "FMUCoreAdapter":
        cfg = dict(cfg or {})
        fmu_path = cfg.get("path") or cfg.get("fmu_path")
        if not fmu_path:
            raise FMUBackendError("FMU backend requires 'path'/'fmu_path'.")

        library = str(cfg.get("library", "auto")).lower()
        fmi_mode = _normalize_fmi_mode(str(cfg.get("fmi_mode", "co-simulation")))
        fmu = _load_fmu(fmu_path, library=library, fmi_mode=fmi_mode)
        variables = dict(cfg.get("variables") or {})

        state_names = _coerce_names(
            variables.get("state_names", variables.get("states", ())),
            section="variables.state_names",
            required=False,
        )
        input_names = _coerce_names(
            variables.get("input_names", variables.get("inputs", ("fuel_cmd", "fw_cmd", "steam_demand"))),
            section="variables.input_names",
            required=False,
        )
        output_map = _coerce_mapping(
            variables.get("output_map", variables.get("outputs")),
            section="variables.output_map",
            required=True,
        )
        derivative_names = _coerce_names(
            variables.get("derivative_names", variables.get("derivatives", ())),
            section="variables.derivative_names",
            required=False,
        )
        invariant_map = _coerce_mapping(
            variables.get("invariants"),
            section="variables.invariants",
            required=False,
        )
        algebraic_map = _coerce_mapping(
            variables.get("algebraics", variables.get("algebraic_residuals")),
            section="variables.algebraics",
            required=False,
        )
        algebraic_state_names = _coerce_names(
            variables.get("algebraic_state_names", variables.get("algebraic_names", ())),
            section="variables.algebraic_state_names",
            required=False,
        )
        if not output_map:
            raise FMUBackendError("FMU adapter requires output variable map to emit simulator truth channels.")
        if not algebraic_state_names and algebraic_map:
            algebraic_state_names = ("M_v",)

        _ensure_fmu_variables(fmu, "state_names", state_names)
        _ensure_fmu_variables(fmu, "input_names", input_names)
        _ensure_fmu_variables(fmu, "variables.output_map", output_map)
        _ensure_fmu_variables(fmu, "variables.derivative_names", derivative_names)
        _ensure_fmu_variables(fmu, "variables.invariants", invariant_map)
        _ensure_fmu_variables(fmu, "variables.algebraics", algebraic_map)

        # Boiler-specific defaults for fallback simulation metadata alignment.
        if not state_names:
            state_names = ("P_d", "M_l", "T_w_d", "m_circ", "m_shrink")
        initial_state = _default_state_from_boiler_config(boiler_cfg, state_names)

        return cls(
            fmu,
            FMUVariableConfig(
                state_names=state_names,
                input_names=input_names,
                output_map=output_map,
                derivative_names=derivative_names,
                invariant_map=invariant_map,
                algebraic_state_names=algebraic_state_names,
                algebraic_map=algebraic_map,
            ),
            step_size=float(cfg.get("step_size", 0.1)),
            time_var=str(cfg.get("time_var", "time")),
            initial_state=initial_state,
            fmi_mode=fmi_mode,
        )

    @property
    def state(self) -> np.ndarray:
        return np.asarray(self._state, dtype=float)

    @state.setter
    def state(self, value: np.ndarray) -> None:
        arr = np.asarray(value, dtype=float)
        if arr.size != len(self._config.state_names):
            raise ValueError("State size does not match configured FMU state dimension.")
        self._state = arr

    @property
    def state_names(self) -> list[str]:
        return list(self._config.state_names)

    @property
    def algebraic_state_names(self) -> list[str]:
        return list(self._config.algebraic_state_names)

    def dae_partition(self, params: Mapping[str, Any] | None = None) -> dict[str, list[int]]:
        del params
        differential = list(range(len(self._config.state_names)))
        algebraic = list(
            range(
                len(self._config.state_names),
                len(self._config.state_names) + len(self._config.algebraic_state_names),
            )
        )
        return {"differential": differential, "algebraic": algebraic}

    @staticmethod
    def _to_float(name: str, value: Any) -> float:
        try:
            return float(value)
        except Exception as exc:
            raise FMUBackendError(f"Unable to convert {name} to float: {value!r}") from exc

    def _set(self, name: str, value: Any) -> None:
        val = self._to_float(name, value)
        if hasattr(self._fmu, "set"):
            self._fmu.set(name, val)
            return
        if hasattr(self._fmu, "set_real"):
            self._fmu.set_real([name], [val])
            return
        raise FMUBackendError("FMU backend does not expose set/set_real.")

    def _get(self, name: str) -> float:
        if hasattr(self._fmu, "get"):
            return self._to_float(name, self._fmu.get(name))
        if hasattr(self._fmu, "get_real"):
            return self._to_float(name, self._fmu.get_real([name])[0])
        raise FMUBackendError("FMU backend does not expose get/get_real.")

    def set_prev_steam_demand(self, steam_demand: float) -> None:
        self._prev_steam_demand = float(np.clip(steam_demand, 0.0, 1.0))

    def _apply_io(self, t: float, x: np.ndarray, u: Mapping[str, float]) -> None:
        for idx, name in enumerate(self._config.state_names):
            self._set(name, x[idx] if idx < len(x) else 0.0)

        for idx, name in enumerate(self._config.input_names):
            source = str(name)
            self._set(name, float(np.clip(float(u.get(source, 0.0)), 0.0, 1.0)))

        # Best-effort time sync for FMUs requiring explicit current time set.
        try:
            self._set(self._time_var, float(t))
        except Exception:
            pass
        self._last_time = float(t)

    def _advance(self, t: float, x: np.ndarray, dt: float) -> None:
        if hasattr(self._fmu, "do_step"):
            try:
                self._fmu.do_step(float(t), float(dt), True)
                return
            except FMUBackendError:
                pass
        if hasattr(self._fmu, "doStep"):
            try:
                self._fmu.doStep(float(t), float(dt), True)
                return
            except Exception:
                pass

        if self._config.derivative_names:
            deriv = np.asarray([self._get(name) for name in self._config.derivative_names], dtype=float)
            next_state = np.asarray(x, dtype=float) + float(dt) * deriv
            if not np.all(np.isfinite(next_state)):
                next_state = np.asarray(x, dtype=float).copy()
            for idx, name in enumerate(self._config.state_names):
                self._set(name, next_state[idx])
            raw_fmu = getattr(self._fmu, "_fmu", self._fmu)
            for method_name in ("setTime", "set_time"):
                method = getattr(raw_fmu, method_name, None)
                if callable(method):
                    try:
                        method(float(t + dt))
                    except TypeError:
                        pass
                    break
            for method_name in ("completedIntegratorStep", "completed_integrator_step"):
                method = getattr(raw_fmu, method_name, None)
                if callable(method):
                    try:
                        method()
                    except TypeError:
                        try:
                            method(1)
                        except Exception:
                            pass
                    break
            for method_name in ("enterContinuousTimeMode", "enter_continuous_time_mode"):
                method = getattr(raw_fmu, method_name, None)
                if callable(method):
                    try:
                        method()
                    except TypeError:
                        pass
                    break
            self._state = next_state
            self._last_time = float(t + dt)
            return

        return

    def step(
        self,
        t: float,
        x: np.ndarray,
        u: Mapping[str, float],
        dt: float,
        params: Mapping[str, Any] | None = None,
    ) -> np.ndarray:
        del params
        x_arr = np.asarray(x, dtype=float)
        if x_arr.size != len(self._config.state_names):
            raise ValueError("State size does not match configured FMU state names.")
        self._apply_io(float(t), x_arr, u)
        self._advance(float(t), x_arr, float(dt))
        try:
            self._state = self._read_state()
        except Exception:
            self._state = x_arr
        return self._state.copy()

    def _read_state(self) -> np.ndarray:
        return np.array([self._get(name) for name in self._config.state_names], dtype=float)

    def reset(self, x0: dict[str, float] | np.ndarray | None, params: Mapping[str, Any]) -> np.ndarray:
        del params
        if x0 is None:
            self.state = self._initial_state.copy()
            return self.state.copy()
        if isinstance(x0, np.ndarray):
            arr = np.asarray(x0, dtype=float)
            if arr.size == len(self._config.state_names):
                self.state = arr
                return arr.copy()
            if arr.size == len(self._config.state_names) + 1:
                self.state = np.array(arr[:-1], dtype=float)
                return self.state.copy()
            raise ValueError("x0 shape incompatible with configured FMU state names.")
        if isinstance(x0, dict):
            arr = np.array([float(x0.get(name, 0.0)) for name in self._config.state_names], dtype=float)
            self.state = arr
            return arr.copy()
        return self.state.copy()

    def consistent_init(self, x0: dict[str, float] | np.ndarray | None = None, *, params: Mapping[str, Any] | None = None) -> np.ndarray:
        del params
        if x0 is None:
            return self.reset(None, {})
        return self.reset(x0, {})

    def project_to_feasible(self, x: np.ndarray, params: Mapping[str, Any] | None = None) -> np.ndarray:
        del params
        arr = np.asarray(x, dtype=float).reshape(-1)
        if arr.size == len(self._config.state_names) + len(self._config.algebraic_state_names):
            arr = arr[: len(self._config.state_names)]
        arr = np.clip(arr, 1e-9, np.inf)
        return arr

    def algebraic_state_error(self, x: np.ndarray, params: Mapping[str, Any] | None = None) -> float:
        residual = self.algebraic_residual(np.asarray(x, dtype=float), None, params)
        values: list[float] = []
        for value in residual.values():
            try:
                values.append(abs(float(value)))
            except Exception:
                continue
        return float(max(values)) if values else 0.0

    def align_algebraic_state(
        self,
        x: np.ndarray,
        params: Mapping[str, Any] | None = None,
        *,
        max_iter: int = 1,
        tol: float = 1e-10,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        del max_iter
        residual_before = self.algebraic_state_error(x, params)
        projected = self.project_to_feasible(x, params)
        residual_after = self.algebraic_state_error(projected, params)
        return projected, {
            "iterations": 0,
            "residual_before_m3": float(residual_before),
            "residual_after_m3": float(residual_after),
            "feasible": bool(residual_after <= tol),
            "source": "fmu_passthrough",
        }

    def algebraic_residual(self, x: np.ndarray, u: Mapping[str, float] | None, params: Mapping[str, Any] | None) -> dict[str, float]:
        del params
        _ = u
        if not self._config.algebraic_map:
            return {}
        residual = {}
        try:
            for key, fmu_name in self._config.algebraic_map.items():
                residual[key] = float(self._get(str(fmu_name)))
        except Exception:
            residual = {}
        return residual

    def derivatives(self, t: float, x: np.ndarray, u: Mapping[str, float], params: Mapping[str, Any]) -> np.ndarray:
        # params is unused for FMU derivative reads but must stay bound: the
        # finite-difference fallback below forwards it to outputs().
        x_arr = np.asarray(x, dtype=float)
        if x_arr.size != len(self._config.state_names):
            raise ValueError("State size does not match configured FMU state names.")
        self._apply_io(t, x_arr, u)
        if self._config.derivative_names:
            return np.asarray([self._get(name) for name in self._config.derivative_names], dtype=float)
        # Fallback: finite-difference proxy on mapped outputs for lack of derivative vars.
        eps = max(1e-4, 1e-4 * max(1.0, np.linalg.norm(x_arr)))
        base = self.outputs(x_arr, u, params)
        grads: list[float] = []
        for idx in range(x_arr.size):
            perturbed = x_arr.copy()
            perturbed[idx] += eps
            self._apply_io(t, perturbed, u)
            after = self.outputs(perturbed, u, params)
            delta = 0.0
            for key in base:
                delta += (float(after.get(key, 0.0)) - float(base.get(key, 0.0)))
            grads.append(delta / eps)
            self._apply_io(t, x_arr, u)
        return np.asarray(grads, dtype=float)

    def invariants(self, x: np.ndarray | BackendInputs, u: Any = None, params: Any = None) -> dict[str, float]:
        if isinstance(x, BackendInputs):
            if u is not None and params is not None:
                raise TypeError("invariants(inputs, params): pass params positionally or as keyword, not both")
            x, u, params = np.asarray(self.state, dtype=float), x.as_control(), (u if u is not None else params)
        del params
        vals = self._get_invariants(x, u, 0.0)
        vals.setdefault("mass_balance_residual", 0.0)
        vals.setdefault("energy_balance_residual", 0.0)
        return vals

    def _get_invariants(self, x: np.ndarray, u: Mapping[str, float], t: float) -> dict[str, float]:
        del u
        del t
        _ = x
        residual = {}
        for key, fmu_name in self._config.invariant_map.items():
            try:
                residual[key] = float(self._get(str(fmu_name)))
            except Exception:
                continue
        return residual

    def outputs(self, x: np.ndarray | BackendInputs, u: Any = None, params: Any = None) -> dict[str, float]:
        preserve_state = isinstance(x, BackendInputs)
        if preserve_state:
            if u is not None and params is not None:
                raise TypeError("outputs(inputs, params): pass params positionally or as keyword, not both")
            x, u, params = np.asarray(self.state, dtype=float), x.as_control(), (u if u is not None else params)
        del params
        x_arr = np.asarray(x, dtype=float)
        if x_arr.size != len(self._config.state_names):
            raise ValueError("State size does not match configured FMU state names.")
        self._apply_io(self._last_time, x_arr, u)
        out: dict[str, float] = {}
        if not preserve_state:
            # Legacy explicit-state call: sync the cached state from the FMU
            # read-back. On the CoreBackend path advance() owns the canonical
            # (aligned + clipped) state — an FMU that transforms written
            # values must not overwrite it between steps.
            self._state = np.array([self._get(name) for name in self._config.state_names], dtype=float)
        for logical, fmu_name in self._config.output_map.items():
            out[str(logical)] = self._get(str(fmu_name))
        return out


def _load_fmu(path: str, library: str = "auto", *, fmi_mode: str = "co-simulation") -> Any:
    fmu_path = _normalize_fmu_path(path)
    errors: list[str] = []
    if not Path(fmu_path).exists():
        raise FMUBackendError(f"FMU file not found at: {fmu_path}")

    if library in {"auto", "fmpy"}:
        try:
            return _load_fmu_via_fmpy(fmu_path, fmi_mode=fmi_mode)
        except Exception as exc:
            errors.append(f"fmpy: {exc}")

    if library in {"auto", "pyfmi"}:
        try:
            from pyfmi import load_fmu  # type: ignore

            return load_fmu(fmu_path)
        except Exception as exc:
            errors.append(f"pyfmi: {exc}")

    if library == "fmpy":
        # If library was explicitly set to `fmpy`, keep only the fmpy failure message if any.
        if not errors:
            errors.append("fmpy: import or runtime error")
    elif library == "auto":
        if not errors:
            errors.append("no backend library was selected")

    raise FMUBackendError("Unable to load FMU backend. " + "; ".join(errors))


def _default_state_from_boiler_config(boiler_cfg: Mapping[str, Any], state_names: tuple[str, ...]) -> np.ndarray:
    payload = dict(boiler_cfg or {})
    nested = payload.get("boiler")
    normalized = dict(nested) if isinstance(nested, Mapping) else payload
    system = BoilerSystem({"boiler": normalized})
    base_state = np.asarray(system.state, dtype=float)
    canonical_names = tuple(system.state_names)
    lookup = {name: float(base_state[idx]) for idx, name in enumerate(canonical_names)}
    return np.array([float(lookup.get(name, 0.0)) for name in state_names], dtype=float)
