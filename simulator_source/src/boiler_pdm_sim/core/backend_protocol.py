"""Backend contract for simulation cores (Phase A WP A1).

This module defines the opaque-state backend contract described in
``docs/phase_a_design.md`` section 2.1:

- :class:`BackendInputs` — actuator commands plus physical-unit boundary
  conditions handed to the backend each step.
- :class:`StepReport` — everything the orchestration loop needs to know
  about one ``advance`` call (solver diagnostics, algebraic alignment,
  correction events) without inspecting the state vector itself.
- :class:`CoreBackend` / :class:`LegacyStateBackend` — the new contract and
  the legacy extension implemented by the existing grey-box and FMU
  backends (kept so the established tests and the FMU parity harness keep
  working).
- :class:`LegacyAdvanceMixin` — behaviour-preserving ``advance`` for the
  legacy backends: integrate -> set_prev_steam_demand -> algebraic
  alignment -> state clip -> correction events, byte-for-byte identical to
  the sequence the pipeline loop used to perform inline.

The stepping method is named ``advance`` (not ``step``) on purpose: the FMU
adapter already exposes a public ``step(t, x, u, dt)`` with FMI semantics
that external tests call directly, and the old dispatch in the simulator
selected the backend path via ``getattr(system, "step", None)``. Reusing
the name would silently change that dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class BackendInputs:
    """Per-step backend inputs.

    ``fuel_cmd``/``fw_cmd``/``steam_demand`` are the normalized actuator
    commands (0..1). ``boundary`` carries physical-unit boundary conditions
    (reserved keys: ``T_fw_C``, ``T_air_C``, ``P_downstream_bar``,
    ``P_feedtank_bar``, ``lambda_excess_air``; Phase B+: ``exh_gas_T_C``,
    ``exh_gas_mdot_kg_s``, ``list_deg``, ``roll_deg``).

    The original controller mapping is kept verbatim so legacy backends see
    exactly the dict the controller produced — including which keys were
    absent, which matters for ``control.get(key, default)`` semantics.

    Source of truth: legacy backends consume :meth:`as_control` (the verbatim
    mapping, raw values included); new backends (``ab4``) consume the typed
    fields, which are float-coerced at construction. ``_control`` exists only
    to replay the legacy mapping and should not be set directly.

    Instances are not hashable, picklable, or deep-copyable (the captured
    mapping is a ``MappingProxyType``); do not store them in dataset rows or
    ship them across process boundaries.
    """

    fuel_cmd: float
    fw_cmd: float
    steam_demand: float
    boundary: Mapping[str, float] = field(default_factory=dict)
    _control: Mapping[str, Any] | None = field(default=None, repr=False)

    @classmethod
    def from_control(
        cls,
        control: Mapping[str, Any],
        boundary: Mapping[str, float] | None = None,
    ) -> "BackendInputs":
        return cls(
            fuel_cmd=float(control.get("fuel_cmd", 0.0)),
            fw_cmd=float(control.get("fw_cmd", 0.0)),
            steam_demand=float(control.get("steam_demand", 0.0)),
            boundary=MappingProxyType(dict(boundary or {})),
            _control=MappingProxyType(dict(control)),
        )

    def as_control(self) -> dict[str, Any]:
        """Reconstruct the controller mapping exactly as it was captured.

        An *empty* captured mapping is reproduced as an empty dict — absent
        keys must stay absent so ``control.get(key, default)`` keeps its
        legacy defaults. Only instances constructed directly (no captured
        mapping) synthesize the three command keys from the typed fields.
        """
        if self._control is not None:
            return dict(self._control)
        return {
            "fuel_cmd": self.fuel_cmd,
            "fw_cmd": self.fw_cmd,
            "steam_demand": self.steam_demand,
        }


@dataclass
class StepReport:
    """Result of one backend ``advance`` call.

    Row-schema contract (what ``pipeline/step_loop.py`` extracts; every read
    uses ``.get`` defaults, so a minimal ``StepReport(x, {}, {}, [])`` still
    produces schema-valid rows — but the meta columns then fall back to the
    loop's solver name and zeros, so populate what you actually know):

    - ``solver``: ``retry_count`` (meta/solver_retry_count + correction
      count), ``fallback_used`` (meta/solver_fallback_used + correction
      count), ``requested_method``/``solver_used`` (meta/solver_requested,
      meta/solver_used), ``rejected_steps`` (meta/solver_rejected_steps).
    - ``alignment``: ``residual_before_m3``/``residual_after_m3``
      (meta/algebraic_residual_*), ``iterations`` (meta/algebraic_iterations
      + correction count), ``feasible`` (meta/algebraic_feasible).
    - ``events``: appended to the schema-locked correction-event log; the
      exact string ``state_clamp_t={t:.1f}`` is also pattern-matched by the
      loop's correction accounting.
    - ``timings``: ``align_seconds`` feeds the perf-stage accounting.

    ``x_after`` is a defensive copy — mutating it does not touch backend
    state; treat it as read-only logging data.
    """

    x_after: np.ndarray
    solver: dict[str, Any]
    alignment: dict[str, Any]
    events: list[str]
    timings: dict[str, float] = field(default_factory=dict)


@runtime_checkable
class CoreBackend(Protocol):
    """Opaque-state physics backend contract.

    The orchestration layer never inspects or clips the state vector;
    bounds, projection/alignment, and consistency are the backend's
    responsibility and are reported via :class:`StepReport`.

    ``outputs``/``invariants`` evaluate the backend's *current internal
    state* against the given inputs: called before ``advance`` they report
    the pre-step truth, called after they report the post-step truth.
    """

    def reset(self, x0: Any, params: Mapping[str, Any]) -> Any: ...

    def advance(
        self,
        t: float,
        dt: float,
        inputs: BackendInputs,
        params: Mapping[str, Any],
        *,
        method: str = "BDF",
    ) -> StepReport: ...

    def outputs(self, x: Any, u: Any = None, params: Any = None) -> dict[str, float]: ...

    def invariants(self, x: Any, u: Any = None, params: Any = None) -> dict[str, float]: ...

    @property
    def state_names(self) -> list[str]: ...


@runtime_checkable
class LegacyStateBackend(Protocol):
    """Extension contract implemented by the legacy grey-box/FMU backends.

    New backends (``ab4``) implement :class:`CoreBackend` only; the loop
    touches these members solely through :class:`LegacyAdvanceMixin` or
    capability checks.
    """

    state: Any

    def consistent_init(self, x0: Any = None, *, params: Any = None) -> np.ndarray: ...

    def dae_partition(self, params: Any = None) -> dict[str, list[int]]: ...

    @property
    def algebraic_state_names(self) -> list[str]: ...

    def align_algebraic_state(
        self, x: np.ndarray, params: Any = None
    ) -> tuple[np.ndarray, dict[str, Any]]: ...

    def project_to_feasible(self, x: np.ndarray, params: Any = None) -> np.ndarray: ...

    def set_prev_steam_demand(self, steam_demand: float) -> None: ...


class LegacyAdvanceMixin:
    """Behaviour-preserving ``advance`` for the legacy 5-state backends.

    Replicates, in order, what ``simulator._step_system`` plus the inline
    pipeline-loop post-processing used to do: integrate, record the prior
    steam demand, align the algebraic state (with projection fallback),
    clip to the legacy state bounds, and emit the exact correction-event
    strings the dataset schema locks (``solver_retry_count=*``,
    ``solver_fallback_euler_t=*``, ``algebraic_*_t=*``, ``state_clamp_t=*``).

    Unlike the old loop, integration and alignment failures are not
    silently swallowed — they propagate (fail-loud per design ADR).
    """

    # Legacy hardcoded bounds previously applied by pipeline/step_loop.py.
    STATE_LOWER: np.ndarray = np.array([0.2, 1.0, 100.0, 0.01, -5.0], dtype=float)
    STATE_UPPER: np.ndarray = np.array([80.0, 1e8, 1000.0, 30.0, 20.0], dtype=float)

    def _integrate_raw(
        self,
        t: float,
        x: np.ndarray,
        control: Mapping[str, Any],
        dt: float,
        method: str,
        params: Mapping[str, Any],
    ) -> tuple[np.ndarray, dict[str, Any]]:  # pragma: no cover - overridden
        raise NotImplementedError

    def _align_after_step(
        self, x_next: np.ndarray, params: Mapping[str, Any]
    ) -> tuple[np.ndarray, dict[str, Any]]:
        align_fn = getattr(self, "align_algebraic_state", None)
        if callable(align_fn):
            # Malformed return values fall back to projection (legacy
            # semantics); exceptions propagate (fail-loud per design ADR).
            result = align_fn(x_next, params)
            if (
                isinstance(result, tuple)
                and len(result) == 2
                and isinstance(result[0], np.ndarray)
                and isinstance(result[1], dict)
            ):
                return result[0], result[1]
        aligned = self.project_to_feasible(x_next, params)  # type: ignore[attr-defined]
        return aligned, {
            "iterations": 0,
            "residual_before_m3": 0.0,
            "residual_after_m3": 0.0,
            "feasible": True,
            "source": "project_to_feasible",
        }

    def advance(
        self,
        t: float,
        dt: float,
        inputs: BackendInputs,
        params: Mapping[str, Any],
        *,
        method: str = "BDF",
    ) -> StepReport:
        control = inputs.as_control()
        x = np.asarray(self.state, dtype=float)  # type: ignore[attr-defined]
        if x.shape != self.STATE_LOWER.shape:
            raise ValueError(
                "LegacyAdvanceMixin.advance expects a "
                f"{self.STATE_LOWER.shape[0]}-element state vector "
                f"[P_d, M_l, T_w_d, m_circ, m_shrink]; got shape {x.shape!r}. "
                "Backends with a different state layout must implement their "
                "own advance() instead of inheriting the legacy mixin."
            )

        x_next_raw, solver_report = self._integrate_raw(t, x, control, dt, method, params)
        self.set_prev_steam_demand(float(control.get("steam_demand", 0.5)))  # type: ignore[attr-defined]

        align_start = perf_counter()
        x_aligned, alignment = self._align_after_step(x_next_raw, params)
        align_seconds = perf_counter() - align_start

        events: list[str] = []
        retry_count = int(solver_report.get("retry_count", 0))
        if retry_count > 0:
            events.append(f"solver_retry_count={retry_count}_t={t:.1f}")
        if bool(solver_report.get("fallback_used", False)):
            events.append(f"solver_fallback_euler_t={t:.1f}")
        if str(alignment.get("source", "")) in {"projection", "exact_projection"}:
            events.append(f"algebraic_{alignment.get('source')}_t={t:.1f}")

        clipped = np.asarray(np.clip(x_aligned, self.STATE_LOWER, self.STATE_UPPER), dtype=float)
        if not np.allclose(clipped, np.asarray(x_aligned, dtype=float), atol=1e-12, rtol=0.0):
            events.append(f"state_clamp_t={t:.1f}")

        self.state = clipped  # type: ignore[attr-defined]
        return StepReport(
            x_after=clipped.copy(),
            solver=dict(solver_report),
            alignment=dict(alignment),
            events=events,
            timings={"align_seconds": float(align_seconds)},
        )
