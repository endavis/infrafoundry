"""Graph algorithms for dependency resolution.

This module provides reusable graph algorithms (DFS, cycle detection,
topological sorting) that can be applied to any directed graph structure.
"""

from collections import defaultdict, deque


class CircularDependencyError(Exception):
    """Raised when a circular dependency is detected."""

    pass


class GraphAlgorithms:
    """Collection of graph algorithms for dependency analysis.

    This class provides stateless algorithms that operate on adjacency lists.
    All methods are static and can be used with any graph representation.
    """

    @staticmethod
    def detect_cycles(adjacency: dict[str, set[str]]) -> list[list[str]]:
        """Detect circular dependencies using depth-first search.

        Args:
            adjacency: Adjacency list mapping nodes to their dependencies

        Returns:
            List of cycles found (each cycle is a list of node names)

        Example:
            >>> adj = {"A": {"B"}, "B": {"C"}, "C": {"A"}}
            >>> GraphAlgorithms.detect_cycles(adj)
            [['A', 'B', 'C', 'A']]
        """
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: list[str]) -> None:
            """Depth-first search to find cycles."""
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in adjacency.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path.copy())
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])

            rec_stack.remove(node)

        # Check all nodes (graph may not be fully connected)
        all_nodes = set(adjacency.keys())
        for neighbor_set in adjacency.values():
            all_nodes.update(neighbor_set)

        for node in all_nodes:
            if node not in visited:
                dfs(node, [])

        return cycles

    @staticmethod
    def topological_sort_batched(
        nodes: set[str],
        adjacency: dict[str, set[str]],
    ) -> list[list[str]]:
        """Perform topological sort with batching for parallel execution.

        Uses Kahn's algorithm to determine execution order. Groups independent
        nodes into batches that can be executed in parallel.

        Args:
            nodes: Set of all node names in the graph
            adjacency: Adjacency list mapping nodes to their dependencies

        Returns:
            List of batches, where each batch contains nodes that can be
            executed in parallel (no dependencies between them)

        Raises:
            CircularDependencyError: If circular dependencies are detected

        Example:
            >>> nodes = {"A", "B", "C", "D"}
            >>> adj = {"C": {"A", "B"}, "D": {"B"}}  # C depends on A,B; D depends on B
            >>> GraphAlgorithms.topological_sort_batched(nodes, adj)
            [['A', 'B'], ['C', 'D']]  # A,B first (no deps), then C,D
        """
        # Check for cycles first
        cycles = GraphAlgorithms.detect_cycles(adjacency)
        if cycles:
            cycle_str = " -> ".join(cycles[0])
            raise CircularDependencyError(f"Circular dependency detected: {cycle_str}")

        # Build reverse adjacency list (who depends on me?)
        reverse_adjacency: dict[str, set[str]] = defaultdict(set)
        for node, deps in adjacency.items():
            for dep in deps:
                reverse_adjacency[dep].add(node)

        # Calculate in-degree for each node
        in_degree = {node: len(adjacency.get(node, set())) for node in nodes}

        # Find nodes with no dependencies (can execute immediately)
        queue = deque([node for node in nodes if in_degree[node] == 0])
        batches = []

        while queue:
            # All nodes in current queue can be executed in parallel
            current_batch = list(queue)
            batches.append(current_batch)
            queue.clear()

            # Process current batch
            for node in current_batch:
                # Remove edges from this node
                for dependent in reverse_adjacency.get(node, set()):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        # If not all nodes were processed, there's a cycle
        if sum(in_degree.values()) > 0:
            unprocessed = [node for node, degree in in_degree.items() if degree > 0]
            raise CircularDependencyError(
                f"Circular dependency detected involving: {', '.join(unprocessed)}"
            )

        return batches

    @staticmethod
    def get_transitive_closure(
        start_node: str,
        adjacency: dict[str, set[str]],
    ) -> set[str]:
        """Get all nodes reachable from start node (transitive dependencies).

        Uses breadth-first search to find all nodes that can be reached
        by following dependency edges.

        Args:
            start_node: Node to start from
            adjacency: Adjacency list mapping nodes to their dependencies

        Returns:
            Set of all reachable node names (excluding start_node)

        Example:
            >>> adj = {"A": {"B"}, "B": {"C"}, "C": {"D"}}
            >>> GraphAlgorithms.get_transitive_closure("A", adj)
            {'B', 'C', 'D'}
        """
        reachable = set()
        to_visit = deque([start_node])
        visited = set()

        while to_visit:
            current = to_visit.popleft()
            if current in visited:
                continue
            visited.add(current)

            # Add all neighbors to reachable set and visit queue
            neighbors = adjacency.get(current, set())
            for neighbor in neighbors:
                if neighbor != start_node:  # Exclude start node from result
                    reachable.add(neighbor)
                    to_visit.append(neighbor)

        return reachable
