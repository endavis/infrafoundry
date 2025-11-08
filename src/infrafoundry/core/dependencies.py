"""Dependency resolution and resource graph management."""

from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class ResourceNode:
    """Node in the dependency graph."""

    provider: str
    resource_type: str
    name: str
    dependencies: list[str]  # List of resource names this depends on

    @property
    def full_name(self) -> str:
        """Get full resource identifier."""
        return f"{self.provider}:{self.name}"


class CircularDependencyError(Exception):
    """Raised when a circular dependency is detected."""

    pass


class DependencyGraph:
    """Manages resource dependencies and execution order."""

    def __init__(self):
        """Initialize dependency graph."""
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
        """Add a resource to the graph.

        Args:
            provider: Provider name
            resource_type: Resource type
            name: Resource name
            dependencies: List of resource names this depends on
        """
        full_name = f"{provider}:{name}"
        node = ResourceNode(
            provider=provider,
            resource_type=resource_type,
            name=name,
            dependencies=dependencies or [],
        )
        self.nodes[full_name] = node

        # Build adjacency lists
        for dep in dependencies or []:
            dep_full_name = f"{provider}:{dep}"  # Assume same provider for now
            self._adjacency[full_name].add(dep_full_name)
            self._reverse_adjacency[dep_full_name].add(full_name)

    def detect_cycles(self) -> list[list[str]]:
        """Detect circular dependencies in the graph.

        Returns:
            List of cycles found (each cycle is a list of resource names)
        """
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._adjacency[node]:
                if neighbor not in visited:
                    dfs(neighbor, path.copy())
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])

            rec_stack.remove(node)

        for node in self.nodes:
            if node not in visited:
                dfs(node, [])

        return cycles

    def topological_sort(self) -> list[list[str]]:
        """Perform topological sort to determine execution order.

        Returns:
            List of batches, where each batch contains resources that can be
            executed in parallel (no dependencies between them)

        Raises:
            CircularDependencyError: If circular dependencies are detected
        """
        # Check for cycles first
        cycles = self.detect_cycles()
        if cycles:
            cycle_str = " -> ".join(cycles[0])
            raise CircularDependencyError(f"Circular dependency detected: {cycle_str}")

        # Kahn's algorithm for topological sort with batching
        in_degree = {node: 0 for node in self.nodes}
        for node in self.nodes:
            for dep in self._adjacency[node]:
                in_degree[node] += 1

        # Find nodes with no dependencies (can execute immediately)
        queue = deque([node for node in self.nodes if in_degree[node] == 0])
        batches = []

        while queue:
            # All nodes in current queue can be executed in parallel
            current_batch = list(queue)
            batches.append(current_batch)
            queue.clear()

            # Process current batch
            for node in current_batch:
                # Remove edges from this node
                for dependent in self._reverse_adjacency[node]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        # If not all nodes were processed, there's a cycle
        if sum(in_degree.values()) > 0:
            raise CircularDependencyError("Circular dependency detected")

        return batches

    def get_dependencies(self, resource_name: str) -> set[str]:
        """Get direct dependencies of a resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Set of resource names that this resource depends on
        """
        return self._adjacency.get(resource_name, set()).copy()

    def get_dependents(self, resource_name: str) -> set[str]:
        """Get resources that depend on this resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Set of resource names that depend on this resource
        """
        return self._reverse_adjacency.get(resource_name, set()).copy()

    def get_all_dependencies(self, resource_name: str) -> set[str]:
        """Get all transitive dependencies of a resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Set of all resource names (direct and indirect) that this resource depends on
        """
        all_deps = set()
        to_visit = deque([resource_name])
        visited = set()

        while to_visit:
            current = to_visit.popleft()
            if current in visited:
                continue
            visited.add(current)

            deps = self._adjacency.get(current, set())
            all_deps.update(deps)
            to_visit.extend(deps)

        return all_deps

    def get_all_dependents(self, resource_name: str) -> set[str]:
        """Get all resources that transitively depend on this resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Set of all resource names that depend on this resource
        """
        all_deps = set()
        to_visit = deque([resource_name])
        visited = set()

        while to_visit:
            current = to_visit.popleft()
            if current in visited:
                continue
            visited.add(current)

            deps = self._reverse_adjacency.get(current, set())
            all_deps.update(deps)
            to_visit.extend(deps)

        return all_deps

    def get_execution_batches(self) -> list[list[str]]:
        """Get batches of resources that can be executed in parallel.

        Returns:
            List of batches where each batch contains resources with no
            dependencies between them. Batches are ordered so that each
            batch's dependencies are satisfied by previous batches.

        Raises:
            CircularDependencyError: If circular dependencies are detected
        """
        return self.topological_sort()

    def get_impact_analysis(self, resource_name: str) -> dict[str, any]:
        """Analyze the impact of changing/deleting a resource.

        Args:
            resource_name: Full resource name (provider:name)

        Returns:
            Dictionary with impact analysis data
        """
        if resource_name not in self.nodes:
            return {"error": f"Resource {resource_name} not found"}

        dependents = self.get_all_dependents(resource_name)
        node = self.nodes[resource_name]

        return {
            "resource": resource_name,
            "provider": node.provider,
            "type": node.resource_type,
            "direct_dependents": len(self._reverse_adjacency.get(resource_name, set())),
            "total_dependents": len(dependents),
            "dependent_resources": sorted(dependents),
            "risk_level": self._calculate_risk_level(len(dependents)),
        }

    @staticmethod
    def _calculate_risk_level(dependent_count: int) -> str:
        """Calculate risk level based on number of dependents."""
        if dependent_count == 0:
            return "LOW"
        if dependent_count <= 5:
            return "MEDIUM"
        if dependent_count <= 20:
            return "HIGH"
        return "CRITICAL"

    def __len__(self) -> int:
        """Get number of resources in graph."""
        return len(self.nodes)

    def __contains__(self, resource_name: str) -> bool:
        """Check if resource is in graph."""
        return resource_name in self.nodes
