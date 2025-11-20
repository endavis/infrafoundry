"""Dependency resolution and resource graph management.

DEPRECATED: This module has been refactored into a package.
Import from infrafoundry.core.dependencies instead.

This file provides backward compatibility for existing imports.
"""

# Re-export everything from the new package structure
from infrafoundry.core.dependencies.dependency_graph import DependencyGraph
from infrafoundry.core.dependencies.graph_algorithms import (
    CircularDependencyError,
)
from infrafoundry.core.dependencies.impact_analyzer import ResourceNode

__all__ = [
    "CircularDependencyError",
    "DependencyGraph",
    "ResourceNode",
]
