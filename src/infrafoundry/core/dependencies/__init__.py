"""Dependency resolution and resource graph management.

This package provides tools for managing infrastructure resource dependencies,
determining execution order, and analyzing the impact of changes.

Main classes:
    - DependencyGraph: Core graph for managing resource dependencies
    - ResourceNode: Represents a resource in the dependency graph
    - CircularDependencyError: Raised when circular dependencies are detected
    - GraphAlgorithms: Reusable graph algorithms (DFS, topological sort, etc.)
    - ImpactAnalyzer: Analyzes impact of resource changes

Example:
    >>> from infrafoundry.core.dependencies import DependencyGraph
    >>> graph = DependencyGraph()
    >>> graph.add_resource("proxmox", "network", "vlan-100")
    >>> graph.add_resource("proxmox", "vm", "web-01", dependencies=["vlan-100"])
    >>> batches = graph.topological_sort()
    >>> print(batches)
    [['proxmox:vlan-100'], ['proxmox:web-01']]
"""

from infrafoundry.core.dependencies.dependency_graph import DependencyGraph
from infrafoundry.core.dependencies.graph_algorithms import (
    CircularDependencyError,
    GraphAlgorithms,
)
from infrafoundry.core.dependencies.impact_analyzer import ImpactAnalyzer, ResourceNode

__all__ = [
    "CircularDependencyError",
    "DependencyGraph",
    "GraphAlgorithms",
    "ImpactAnalyzer",
    "ResourceNode",
]
