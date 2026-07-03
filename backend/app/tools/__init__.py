"""Toolkit package. Importing it registers every tool into the REGISTRY."""
from __future__ import annotations

from . import (  # noqa: F401  (imported for side-effect: tool registration)
    comm_tools,
    data_tools,
    integrity_tools,
    maintenance_tools,
    production_tools,
    quality_tools,
)
from .registry import REGISTRY, anthropic_schema, catalog, run_tool

__all__ = ["REGISTRY", "run_tool", "anthropic_schema", "catalog"]
