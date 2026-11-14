"""Core simulation modules."""

from .backend_factory import build_core_backend
from .fmu_adapter import FMUCoreAdapter

__all__ = ["build_core_backend", "FMUCoreAdapter"]
