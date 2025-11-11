"""Impact analysis for resource dependencies.

This module provides tools for analyzing the impact of changes to resources,
calculating risk levels, and understanding dependency relationships.
"""

from collections import deque
from dataclasses import dataclass
from typing import Any

from infrafoundry.core.dependencies.graph_algorithms import GraphAlgorithms


@dataclass
class ResourceNode:
    """Node in the dependency graph representing an infrastructure resource."""

    provider: str
    resource_type: str
    name: str
    dependencies: list[str]  # List of resource names this depends on

    @property
    def full_name(self) -> str:
        """Get full resource identifier (provider:name)."""
        return f"{self.provider}:{self.name}"


class ImpactAnalyzer:
    """Analyzes the impact of resource changes in a dependency graph."""

    def __init__(
        self,
        nodes: dict[str, ResourceNode],
        adjacency: dict[str, set[str]],
        reverse_adjacency: dict[str, set[str]],
    ):
        """Initialize impact analyzer.

        Args:
            nodes: Map of full resource names to ResourceNode objects
            adjacency: Forward adjacency list (resource -> its dependencies)
            reverse_adjacency: Reverse adjacency list (resource -> what depends on it)
        """
        self.nodes = nodes
        self.adjacency = adjacency
        self.reverse_adjacency = reverse_adjacency

    def get_all_dependencies(self, resource_name: str) -> set[str]:
        """Get all transitive dependencies of a resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Set of all resource names (direct and indirect) this resource depends on
        """
        return GraphAlgorithms.get_transitive_closure(resource_name, self.adjacency)

    def get_all_dependents(self, resource_name: str) -> set[str]:
        """Get all resources that transitively depend on this resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Set of all resource names that depend on this resource
        """
        return GraphAlgorithms.get_transitive_closure(resource_name, self.reverse_adjacency)

    def get_impact_analysis(self, resource_name: str) -> dict[str, Any]:
        """Analyze the impact of changing or deleting a resource.

        Calculates what other resources would be affected if this resource
        is modified or removed, and assigns a risk level based on the scope.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Dictionary with impact analysis data including:
            - resource: Full resource name
            - provider: Provider name
            - type: Resource type
            - direct_dependents: Count of direct dependents
            - total_dependents: Count of all transitive dependents
            - dependent_resources: List of affected resource names
            - risk_level: LOW, MEDIUM, HIGH, or CRITICAL

        Example:
            >>> analyzer.get_impact_analysis("proxmox:network-01")
            {
                "resource": "proxmox:network-01",
                "provider": "proxmox",
                "type": "network",
                "direct_dependents": 3,
                "total_dependents": 8,
                "dependent_resources": ["proxmox:vm-01", "proxmox:vm-02", ...],
                "risk_level": "MEDIUM"
            }
        """
        if resource_name not in self.nodes:
            return {"error": f"Resource {resource_name} not found"}

        node = self.nodes[resource_name]
        direct_dependents = self.reverse_adjacency.get(resource_name, set())
        all_dependents = self.get_all_dependents(resource_name)

        return {
            "resource": resource_name,
            "provider": node.provider,
            "type": node.resource_type,
            "direct_dependents": len(direct_dependents),
            "total_dependents": len(all_dependents),
            "dependent_resources": sorted(all_dependents),
            "risk_level": self._calculate_risk_level(len(all_dependents)),
        }

    @staticmethod
    def _calculate_risk_level(dependent_count: int) -> str:
        """Calculate risk level based on number of dependent resources.

        Risk levels:
        - LOW: 0 dependents (safe to change)
        - MEDIUM: 1-5 dependents
        - HIGH: 6-20 dependents
        - CRITICAL: 21+ dependents

        Args:
            dependent_count: Number of resources that depend on this one

        Returns:
            Risk level string: LOW, MEDIUM, HIGH, or CRITICAL
        """
        if dependent_count == 0:
            return "LOW"
        if dependent_count <= 5:
            return "MEDIUM"
        if dependent_count <= 20:
            return "HIGH"
        return "CRITICAL"

    def get_dependency_chain(self, from_resource: str, to_resource: str) -> list[str] | None:
        """Find a dependency path between two resources.

        Uses BFS to find the shortest dependency chain from one resource to another.

        Args:
            from_resource: Starting resource name
            to_resource: Target resource name

        Returns:
            List of resource names forming the dependency chain,
            or None if no path exists

        Example:
            >>> analyzer.get_dependency_chain("proxmox:vm-01", "proxmox:network-01")
            ["proxmox:vm-01", "proxmox:network-01"]
        """
        if from_resource not in self.nodes or to_resource not in self.nodes:
            return None

        # BFS to find shortest path
        queue = deque([(from_resource, [from_resource])])
        visited = {from_resource}

        while queue:
            current, path = queue.popleft()

            # Check if we reached the target
            if current == to_resource:
                return path

            # Explore dependencies
            for dep in self.adjacency.get(current, set()):
                if dep not in visited:
                    visited.add(dep)
                    queue.append((dep, path + [dep]))

        return None  # No path found
