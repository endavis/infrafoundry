"""Core dependency graph for resource management.

This module provides the main DependencyGraph class that coordinates
graph algorithms and impact analysis for infrastructure resources.
"""

from collections import defaultdict
from typing import Any

from infrafoundry.core.dependencies.graph_algorithms import (
    GraphAlgorithms,
)
from infrafoundry.core.dependencies.impact_analyzer import ImpactAnalyzer, ResourceNode


class DependencyGraph:
    """Manages resource dependencies and execution order.

    Coordinates graph algorithms and impact analysis to determine the correct
    order for creating/updating/destroying infrastructure resources based on
    their dependencies.

    Example:
        >>> graph = DependencyGraph()
        >>> graph.add_resource("proxmox", "network", "vlan-100")
        >>> graph.add_resource("proxmox", "vm", "web-01", dependencies=["vlan-100"])
        >>> batches = graph.topological_sort()
        >>> print(batches)
        [['proxmox:vlan-100'], ['proxmox:web-01']]
    """

    def __init__(self) -> None:
        """Initialize empty dependency graph."""
        self.nodes: dict[str, ResourceNode] = {}
        self._adjacency: dict[str, set[str]] = defaultdict(set)
        self._reverse_adjacency: dict[str, set[str]] = defaultdict(set)

    def add_resource(
        self,
        provider: str,
        resource_type: str,
        name: str,
        dependencies: list[str] | None = None,
    ) -> None:
        """Add a resource to the dependency graph.

        Args:
            provider: Provider name (e.g., 'proxmox', 'opnsense')
            resource_type: Type of resource (e.g., 'vm', 'network')
            name: Resource name
            dependencies: List of resource names this depends on (same provider)
        """
        full_name = f"{provider}:{name}"

        # Create node
        node = ResourceNode(
            provider=provider,
            resource_type=resource_type,
            name=name,
            dependencies=dependencies or [],
        )
        self.nodes[full_name] = node

        # Build adjacency lists for graph algorithms
        for dep in dependencies or []:
            dep_full_name = f"{provider}:{dep}"  # Assume same provider
            self._adjacency[full_name].add(dep_full_name)
            self._reverse_adjacency[dep_full_name].add(full_name)

    def detect_cycles(self) -> list[list[str]]:
        """Detect circular dependencies in the graph.

        Returns:
            List of cycles found (each cycle is a list of resource names)

        Example:
            >>> graph.detect_cycles()
            [['proxmox:vm-01', 'proxmox:vm-02', 'proxmox:vm-01']]
        """
        return GraphAlgorithms.detect_cycles(self._adjacency)

    def topological_sort(self) -> list[list[str]]:
        """Perform topological sort to determine execution order.

        Groups resources into batches where resources in each batch have no
        dependencies on each other and can be executed in parallel.

        Returns:
            List of batches, where each batch contains resources that can be
            executed in parallel

        Raises:
            CircularDependencyError: If circular dependencies are detected

        Example:
            >>> batches = graph.topological_sort()
            >>> for i, batch in enumerate(batches):
            ...     print(f"Batch {i}: {batch}")
            Batch 0: ['proxmox:network-01', 'proxmox:template-01']
            Batch 1: ['proxmox:vm-01', 'proxmox:vm-02']
        """
        node_names = set(self.nodes.keys())
        return GraphAlgorithms.topological_sort_batched(node_names, self._adjacency)

    def get_dependencies(self, resource_name: str) -> set[str]:
        """Get direct dependencies of a resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Set of resource names that this resource directly depends on
        """
        return self._adjacency.get(resource_name, set()).copy()

    def get_dependents(self, resource_name: str) -> set[str]:
        """Get resources that directly depend on this resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Set of resource names that directly depend on this resource
        """
        return self._reverse_adjacency.get(resource_name, set()).copy()

    def get_all_dependencies(self, resource_name: str) -> set[str]:
        """Get all transitive dependencies of a resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Set of all resource names (direct and indirect) this resource depends on
        """
        analyzer = self._get_analyzer()
        return analyzer.get_all_dependencies(resource_name)

    def get_all_dependents(self, resource_name: str) -> set[str]:
        """Get all resources that transitively depend on this resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Set of all resource names that transitively depend on this resource
        """
        analyzer = self._get_analyzer()
        return analyzer.get_all_dependents(resource_name)

    def get_execution_batches(self) -> list[list[str]]:
        """Get batches of resources that can be executed in parallel.

        Alias for topological_sort() for backward compatibility.

        Returns:
            List of batches where each batch contains resources with no
            dependencies between them

        Raises:
            CircularDependencyError: If circular dependencies are detected
        """
        return self.topological_sort()

    def get_impact_analysis(self, resource_name: str) -> dict[str, Any]:
        """Analyze the impact of changing or deleting a resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Dictionary with impact analysis data including risk level
        """
        analyzer = self._get_analyzer()
        return analyzer.get_impact_analysis(resource_name)

    def _get_analyzer(self) -> ImpactAnalyzer:
        """Create an impact analyzer for the current graph state.

        Returns:
            ImpactAnalyzer instance configured with current graph
        """
        return ImpactAnalyzer(
            nodes=self.nodes,
            adjacency=self._adjacency,
            reverse_adjacency=self._reverse_adjacency,
        )

    def __len__(self) -> int:
        """Get number of resources in graph."""
        return len(self.nodes)

    def __contains__(self, resource_name: str) -> bool:
        """Check if resource is in graph."""
        return resource_name in self.nodes
