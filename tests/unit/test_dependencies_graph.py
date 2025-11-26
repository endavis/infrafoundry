"""Unit tests for dependency graph and algorithms."""

import pytest

from infrafoundry.core.dependencies.dependency_graph import DependencyGraph
from infrafoundry.core.dependencies.graph_algorithms import (
    CircularDependencyError,
    GraphAlgorithms,
)
from infrafoundry.core.dependencies.impact_analyzer import ImpactAnalyzer, ResourceNode


def test_dependency_graph_basic_topology():
    graph = DependencyGraph()
    graph.add_resource("proxmox", "network", "net-1")
    graph.add_resource("proxmox", "vm", "vm-1", dependencies=["net-1"])
    graph.add_resource("proxmox", "vm", "vm-2", dependencies=["net-1"])

    batches = graph.topological_sort()
    assert batches[0] == ["proxmox:net-1"]
    assert set(batches[1]) == {"proxmox:vm-1", "proxmox:vm-2"}
    assert graph.get_dependencies("proxmox:vm-1") == {"proxmox:net-1"}
    assert graph.get_dependents("proxmox:net-1") == {"proxmox:vm-1", "proxmox:vm-2"}
    assert len(graph) == 3
    assert "proxmox:net-1" in graph


def test_dependency_graph_cycle_detection():
    graph = DependencyGraph()
    graph.add_resource("k8s", "svc", "a", dependencies=["c"])
    graph.add_resource("k8s", "svc", "b", dependencies=["a"])
    graph.add_resource("k8s", "svc", "c", dependencies=["b"])

    cycles = graph.detect_cycles()
    assert cycles and set(cycles[0]) == {"k8s:a", "k8s:b", "k8s:c"}
    with pytest.raises(CircularDependencyError):
        graph.topological_sort()


def test_graph_algorithms_transitive_closure_and_batches():
    nodes = {"A", "B", "C", "D"}
    adjacency = {"C": {"A", "B"}, "D": {"B"}}
    closure = GraphAlgorithms.get_transitive_closure("C", adjacency)
    assert closure == {"A", "B"}

    batches = GraphAlgorithms.topological_sort_batched(nodes, adjacency)
    assert [set(batch) for batch in batches] == [{"A", "B"}, {"C", "D"}]


def test_impact_analyzer_paths_and_risk_levels():
    nodes = {
        "p:net": ResourceNode("p", "network", "net", []),
        "p:vm1": ResourceNode("p", "vm", "vm1", ["net"]),
        "p:vm2": ResourceNode("p", "vm", "vm2", ["net"]),
        "p:vm3": ResourceNode("p", "vm", "vm3", ["vm1"]),
    }
    adjacency = {
        "p:vm1": {"p:net"},
        "p:vm2": {"p:net"},
        "p:vm3": {"p:vm1"},
        "p:net": set(),
    }
    reverse = {
        "p:net": {"p:vm1", "p:vm2"},
        "p:vm1": {"p:vm3"},
    }
    analyzer = ImpactAnalyzer(nodes, adjacency, reverse)

    assert analyzer.get_all_dependencies("p:vm3") == {"p:vm1", "p:net"}
    assert analyzer.get_all_dependents("p:net") == {"p:vm1", "p:vm2", "p:vm3"}
    impact = analyzer.get_impact_analysis("p:net")
    assert impact["risk_level"] == "MEDIUM"
    assert "p:vm3" in impact["dependent_resources"]
    assert analyzer.get_dependency_chain("p:vm3", "p:net") == ["p:vm3", "p:vm1", "p:net"]

    # Risk levels boundaries
    assert analyzer._calculate_risk_level(0) == "LOW"
    assert analyzer._calculate_risk_level(3) == "MEDIUM"
    assert analyzer._calculate_risk_level(10) == "HIGH"
    assert analyzer._calculate_risk_level(25) == "CRITICAL"
