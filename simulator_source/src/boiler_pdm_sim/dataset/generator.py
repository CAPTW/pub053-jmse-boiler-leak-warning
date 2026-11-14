"""Simulation dataset container."""

from __future__ import annotations


class DatasetGenerator:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def append(self, row: dict) -> None:
        self.rows.append(row)

    def clear(self) -> None:
        self.rows = []
