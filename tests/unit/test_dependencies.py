"""Tests for dependency module re-exports."""

from infrafoundry.core.dependencies import (
    CircularDependencyError,
    DependencyGraph,
    ResourceNode,
)
from infrafoundry.core.dependencies.dependency_graph import DependencyGraph as DGImpl
from infrafoundry.core.dependencies.graph_algorithms import CircularDependencyError as CDEImpl
from infrafoundry.core.dependencies.impact_analyzer import ResourceNode as RNImpl


def test_dependencies_reexports():
    """Ensure backward-compatible re-exports stay wired."""
    assert DependencyGraph is DGImpl
    assert CircularDependencyError is CDEImpl
    assert ResourceNode is RNImpl
