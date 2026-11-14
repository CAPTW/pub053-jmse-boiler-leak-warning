"""Validation helpers for control mode and strategy transitions."""

from __future__ import annotations

from typing import Any


def validate_control_mode_transition(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"passed": False, "failures": ["empty_rows"], "transitions": []}

    transitions: list[str] = []
    prev_mode = None
    prev_strategy = None
    for row in rows:
        mode = str(row.get("meta/control_mode", ""))
        strategy = str(row.get("meta/control_strategy", ""))
        if prev_mode is not None and mode and mode != prev_mode:
            transitions.append(f"mode:{prev_mode}->{mode}")
        if prev_strategy is not None and strategy and strategy != prev_strategy:
            transitions.append(f"strategy:{prev_strategy}->{strategy}")
        prev_mode = mode or prev_mode
        prev_strategy = strategy or prev_strategy

    return {
        "passed": bool(transitions),
        "failures": [] if transitions else ["no_control_mode_transition_detected"],
        "transitions": transitions,
    }
