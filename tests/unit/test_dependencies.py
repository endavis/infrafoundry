"""Unit tests for DependencyGraph and dependency resolution."""

import pytest

from infrafoundry.core.dependencies import CircularDependencyError, DependencyGraph, ResourceNode


class TestResourceNode:
    """Tests for ResourceNode dataclass."""

    def test_resource_node_creation(self):
        """Test creating a ResourceNode."""
        node = ResourceNode(
            provider="proxmox",
            resource_type="vm",
            name="web-01",
            dependencies=["network-01"],
        )

        assert node.provider == "proxmox"
        assert node.resource_type == "vm"
        assert node.name == "web-01"
        assert node.dependencies == ["network-01"]

    def test_resource_node_full_name(self):
        """Test full_name property."""
        node = ResourceNode(
            provider="proxmox",
            resource_type="vm",
            name="web-01",
            dependencies=[],
        )

        assert node.full_name == "proxmox:web-01"

    def test_resource_node_no_dependencies(self):
        """Test ResourceNode with no dependencies."""
        node = ResourceNode(
            provider="proxmox",
            resource_type="vm",
            name="standalone",
            dependencies=[],
        )

        assert node.dependencies == []
        assert len(node.dependencies) == 0


class TestDependencyGraph:
    """Tests for DependencyGraph."""

    def test_graph_initialization(self):
        """Test DependencyGraph initialization."""
        graph = DependencyGraph()

        assert len(graph) == 0
        assert len(graph.nodes) == 0

    def test_add_single_resource(self):
        """Test adding a single resource to the graph."""
        graph = DependencyGraph()
        graph.add_resource(
            provider="proxmox",
            resource_type="vm",
            name="web-01",
            dependencies=None,
        )

        assert len(graph) == 1
        assert "proxmox:web-01" in graph
        node = graph.nodes["proxmox:web-01"]
        assert node.provider == "proxmox"
        assert node.resource_type == "vm"
        assert node.name == "web-01"

    def test_add_resource_with_dependencies(self):
        """Test adding a resource with dependencies."""
        graph = DependencyGraph()

        # Add dependency first
        graph.add_resource(
            provider="proxmox",
            resource_type="network",
            name="vlan-100",
            dependencies=None,
        )

        # Add resource that depends on it
        graph.add_resource(
            provider="proxmox",
            resource_type="vm",
            name="web-01",
            dependencies=["vlan-100"],
        )

        assert len(graph) == 2
        assert "proxmox:web-01" in graph
        assert "proxmox:vlan-100" in graph

    def test_contains_operator(self):
        """Test __contains__ operator for graph membership."""
        graph = DependencyGraph()
        graph.add_resource("proxmox", "vm", "web-01")

        assert "proxmox:web-01" in graph
        assert "proxmox:nonexistent" not in graph

    def test_len_operator(self):
        """Test __len__ operator."""
        graph = DependencyGraph()

        assert len(graph) == 0

        graph.add_resource("proxmox", "vm", "web-01")
        assert len(graph) == 1

        graph.add_resource("proxmox", "vm", "web-02")
        assert len(graph) == 2

    def test_get_dependencies_single_level(self):
        """Test getting direct dependencies of a resource."""
        graph = DependencyGraph()
        graph.add_resource("proxmox", "network", "vlan-100")
        graph.add_resource("proxmox", "vm", "web-01", dependencies=["vlan-100"])

        deps = graph.get_dependencies("proxmox:web-01")

        assert len(deps) == 1
        assert "proxmox:vlan-100" in deps

    def test_get_dependencies_no_dependencies(self):
        """Test getting dependencies for resource with none."""
        graph = DependencyGraph()
        graph.add_resource("proxmox", "vm", "standalone")

        deps = graph.get_dependencies("proxmox:standalone")

        assert len(deps) == 0

    def test_get_dependents(self):
        """Test getting resources that depend on a given resource."""
        graph = DependencyGraph()
        graph.add_resource("proxmox", "network", "vlan-100")
        graph.add_resource("proxmox", "vm", "web-01", dependencies=["vlan-100"])
        graph.add_resource("proxmox", "vm", "web-02", dependencies=["vlan-100"])

        dependents = graph.get_dependents("proxmox:vlan-100")

        assert len(dependents) == 2
        assert "proxmox:web-01" in dependents
        assert "proxmox:web-02" in dependents

    def test_get_all_dependencies_transitive(self):
        """Test getting all transitive dependencies."""
        graph = DependencyGraph()

        # Create chain: web-01 -> vlan-100 -> switch-01
        graph.add_resource("proxmox", "switch", "switch-01")
        graph.add_resource("proxmox", "network", "vlan-100", dependencies=["switch-01"])
        graph.add_resource("proxmox", "vm", "web-01", dependencies=["vlan-100"])

        all_deps = graph.get_all_dependencies("proxmox:web-01")

        assert len(all_deps) == 2
        assert "proxmox:vlan-100" in all_deps
        assert "proxmox:switch-01" in all_deps

    def test_get_all_dependents_transitive(self):
        """Test getting all transitive dependents."""
        graph = DependencyGraph()

        # Create chain: switch-01 <- vlan-100 <- web-01
        graph.add_resource("proxmox", "switch", "switch-01")
        graph.add_resource("proxmox", "network", "vlan-100", dependencies=["switch-01"])
        graph.add_resource("proxmox", "vm", "web-01", dependencies=["vlan-100"])

        all_dependents = graph.get_all_dependents("proxmox:switch-01")

        assert len(all_dependents) == 2
        assert "proxmox:vlan-100" in all_dependents
        assert "proxmox:web-01" in all_dependents

    def test_topological_sort_simple(self):
        """Test topological sort with simple linear dependency."""
        graph = DependencyGraph()

        # Linear: A -> B -> C
        graph.add_resource("proxmox", "resource", "A")
        graph.add_resource("proxmox", "resource", "B", dependencies=["A"])
        graph.add_resource("proxmox", "resource", "C", dependencies=["B"])

        batches = graph.topological_sort()

        # Should have 3 batches (one per level)
        assert len(batches) >= 1
        # First batch should include A (no dependencies)
        assert "proxmox:A" in batches[0]

    def test_topological_sort_parallel_resources(self):
        """Test topological sort with resources that can run in parallel."""
        graph = DependencyGraph()

        # Two independent resources
        graph.add_resource("proxmox", "vm", "web-01")
        graph.add_resource("proxmox", "vm", "web-02")

        batches = graph.topological_sort()

        # Both should be in first batch (can run in parallel)
        assert len(batches) == 1
        assert len(batches[0]) == 2
        assert "proxmox:web-01" in batches[0]
        assert "proxmox:web-02" in batches[0]

    def test_topological_sort_diamond_dependency(self):
        """Test topological sort with diamond-shaped dependencies."""
        graph = DependencyGraph()

        # Diamond: D depends on B and C, both depend on A
        #     A
        #    / \
        #   B   C
        #    \ /
        #     D
        graph.add_resource("proxmox", "resource", "A")
        graph.add_resource("proxmox", "resource", "B", dependencies=["A"])
        graph.add_resource("proxmox", "resource", "C", dependencies=["A"])
        graph.add_resource("proxmox", "resource", "D", dependencies=["B", "C"])

        batches = graph.topological_sort()

        # Should have 3 batches
        assert len(batches) == 3
        # A in first batch
        assert "proxmox:A" in batches[0]
        # B and C can run in parallel (second batch)
        assert "proxmox:B" in batches[1]
        assert "proxmox:C" in batches[1]
        # D in third batch
        assert "proxmox:D" in batches[2]

    def test_detect_cycles_no_cycle(self):
        """Test cycle detection with no cycles."""
        graph = DependencyGraph()

        graph.add_resource("proxmox", "resource", "A")
        graph.add_resource("proxmox", "resource", "B", dependencies=["A"])

        cycles = graph.detect_cycles()

        assert len(cycles) == 0

    def test_detect_cycles_self_dependency(self):
        """Test detecting self-referencing cycle."""
        graph = DependencyGraph()

        # A depends on itself
        graph.add_resource("proxmox", "resource", "A", dependencies=["A"])

        cycles = graph.detect_cycles()

        assert len(cycles) > 0

    def test_detect_cycles_simple_cycle(self):
        """Test detecting simple two-node cycle."""
        graph = DependencyGraph()

        # A -> B -> A
        graph.add_resource("proxmox", "resource", "A", dependencies=["B"])
        graph.add_resource("proxmox", "resource", "B", dependencies=["A"])

        cycles = graph.detect_cycles()

        assert len(cycles) > 0

    def test_detect_cycles_complex_cycle(self):
        """Test detecting cycle in larger graph."""
        graph = DependencyGraph()

        # Create cycle: A -> B -> C -> A
        graph.add_resource("proxmox", "resource", "A", dependencies=["C"])
        graph.add_resource("proxmox", "resource", "B", dependencies=["A"])
        graph.add_resource("proxmox", "resource", "C", dependencies=["B"])

        cycles = graph.detect_cycles()

        assert len(cycles) > 0

    def test_topological_sort_raises_on_cycle(self):
        """Test that topological sort raises error on circular dependency."""
        graph = DependencyGraph()

        # Create cycle: A -> B -> A
        graph.add_resource("proxmox", "resource", "A", dependencies=["B"])
        graph.add_resource("proxmox", "resource", "B", dependencies=["A"])

        with pytest.raises(CircularDependencyError):
            graph.topological_sort()

    def test_get_execution_batches(self):
        """Test getting execution batches (alias for topological_sort)."""
        graph = DependencyGraph()

        graph.add_resource("proxmox", "vm", "web-01")
        graph.add_resource("proxmox", "vm", "web-02")

        batches = graph.get_execution_batches()

        assert len(batches) > 0
        assert isinstance(batches, list)

    def test_get_execution_batches_raises_on_cycle(self):
        """Test that get_execution_batches raises on cycle."""
        graph = DependencyGraph()

        graph.add_resource("proxmox", "resource", "A", dependencies=["B"])
        graph.add_resource("proxmox", "resource", "B", dependencies=["A"])

        with pytest.raises(CircularDependencyError):
            graph.get_execution_batches()

    def test_impact_analysis_no_dependents(self):
        """Test impact analysis for resource with no dependents."""
        graph = DependencyGraph()
        graph.add_resource("proxmox", "vm", "standalone")

        analysis = graph.get_impact_analysis("proxmox:standalone")

        assert analysis["resource"] == "proxmox:standalone"
        assert analysis["provider"] == "proxmox"
        assert analysis["type"] == "vm"
        assert analysis["direct_dependents"] == 0
        assert analysis["total_dependents"] == 0
        assert analysis["risk_level"] == "LOW"

    def test_impact_analysis_with_dependents(self):
        """Test impact analysis for resource with dependents."""
        graph = DependencyGraph()

        graph.add_resource("proxmox", "network", "vlan-100")
        graph.add_resource("proxmox", "vm", "web-01", dependencies=["vlan-100"])
        graph.add_resource("proxmox", "vm", "web-02", dependencies=["vlan-100"])

        analysis = graph.get_impact_analysis("proxmox:vlan-100")

        assert analysis["resource"] == "proxmox:vlan-100"
        assert analysis["direct_dependents"] == 2
        assert analysis["total_dependents"] == 2
        assert "proxmox:web-01" in analysis["dependent_resources"]
        assert "proxmox:web-02" in analysis["dependent_resources"]

    def test_impact_analysis_risk_levels(self):
        """Test risk level calculation in impact analysis."""
        graph = DependencyGraph()

        # LOW risk: 0 dependents
        graph.add_resource("proxmox", "vm", "standalone")
        analysis_low = graph.get_impact_analysis("proxmox:standalone")
        assert analysis_low["risk_level"] == "LOW"

        # MEDIUM risk: 1-5 dependents
        graph.add_resource("proxmox", "network", "net1")
        for i in range(3):
            graph.add_resource("proxmox", "vm", f"vm-{i}", dependencies=["net1"])
        analysis_medium = graph.get_impact_analysis("proxmox:net1")
        assert analysis_medium["risk_level"] == "MEDIUM"

    def test_impact_analysis_high_risk(self):
        """Test high risk level (6-20 dependents)."""
        graph = DependencyGraph()

        graph.add_resource("proxmox", "network", "critical-net")
        # Add 10 dependents
        for i in range(10):
            graph.add_resource("proxmox", "vm", f"vm-{i}", dependencies=["critical-net"])

        analysis = graph.get_impact_analysis("proxmox:critical-net")

        assert analysis["direct_dependents"] == 10
        assert analysis["risk_level"] == "HIGH"

    def test_impact_analysis_critical_risk(self):
        """Test critical risk level (>20 dependents)."""
        graph = DependencyGraph()

        graph.add_resource("proxmox", "network", "core-net")
        # Add 25 dependents
        for i in range(25):
            graph.add_resource("proxmox", "vm", f"vm-{i}", dependencies=["core-net"])

        analysis = graph.get_impact_analysis("proxmox:core-net")

        assert analysis["direct_dependents"] == 25
        assert analysis["risk_level"] == "CRITICAL"

    def test_impact_analysis_nonexistent_resource(self):
        """Test impact analysis for resource that doesn't exist."""
        graph = DependencyGraph()

        analysis = graph.get_impact_analysis("proxmox:nonexistent")

        assert "error" in analysis
        assert "not found" in analysis["error"]

    def test_complex_dependency_graph(self):
        """Test complex multi-level dependency graph."""
        graph = DependencyGraph()

        # Build complex graph:
        # Layer 1: infrastructure
        graph.add_resource("proxmox", "storage", "storage-01")
        graph.add_resource("proxmox", "network", "network-01")

        # Layer 2: templates
        graph.add_resource("proxmox", "template", "ubuntu-template", dependencies=["storage-01"])

        # Layer 3: VMs
        graph.add_resource(
            "proxmox",
            "vm",
            "web-01",
            dependencies=["ubuntu-template", "network-01"],
        )
        graph.add_resource(
            "proxmox",
            "vm",
            "web-02",
            dependencies=["ubuntu-template", "network-01"],
        )

        # Layer 4: load balancer
        graph.add_resource("proxmox", "vm", "lb-01", dependencies=["web-01", "web-02"])

        batches = graph.topological_sort()

        # Should have multiple batches
        assert len(batches) >= 3

        # Storage and network should be in first batch
        assert "proxmox:storage-01" in batches[0] or "proxmox:network-01" in batches[0]

        # Load balancer should be in last batch
        assert "proxmox:lb-01" in batches[-1]

    def test_get_all_dependencies_with_shared_dependency(self):
        """Test get_all_dependencies with diamond pattern (shared dependency)."""
        graph = DependencyGraph()

        # Diamond pattern: D depends on B and C, both B and C depend on A
        graph.add_resource("proxmox", "vm", "A")
        graph.add_resource("proxmox", "vm", "B", dependencies=["A"])
        graph.add_resource("proxmox", "vm", "C", dependencies=["A"])
        graph.add_resource("proxmox", "vm", "D", dependencies=["B", "C"])

        # Get all dependencies of D - should visit A only once
        all_deps = graph.get_all_dependencies("proxmox:D")

        assert "proxmox:A" in all_deps
        assert "proxmox:B" in all_deps
        assert "proxmox:C" in all_deps
        assert len(all_deps) == 3  # A, B, C (A counted once despite multiple paths)

    def test_get_all_dependents_with_shared_dependent(self):
        """Test get_all_dependents with inverse diamond pattern."""
        graph = DependencyGraph()

        # Inverse diamond: A is used by B and C, D depends on both B and C
        graph.add_resource("proxmox", "vm", "A")
        graph.add_resource("proxmox", "vm", "B", dependencies=["A"])
        graph.add_resource("proxmox", "vm", "C", dependencies=["A"])
        graph.add_resource("proxmox", "vm", "D", dependencies=["B", "C"])

        # Get all dependents of A - should visit D only once
        all_dependents = graph.get_all_dependents("proxmox:A")

        assert "proxmox:B" in all_dependents
        assert "proxmox:C" in all_dependents
        assert "proxmox:D" in all_dependents
        assert len(all_dependents) == 3  # B, C, D (D counted once despite multiple paths)
