"""Tests for the ExecutionPlanner service."""

from infrafoundry.core.dependencies import DependencyGraph
from infrafoundry.core.execution_planner import ExecutionPlanner, ProviderBatch
from infrafoundry.core.provider import ResourceConfig


def make_resource(provider: str, name: str, rtype: str = "vm") -> ResourceConfig:
    """Create a test ResourceConfig."""
    return ResourceConfig(
        provider=provider,
        type=rtype,
        name=name,
        config={},
    )


class TestExecutionPlannerInit:
    """Test ExecutionPlanner initialization."""

    def test_default_provider_order(self) -> None:
        """Test that default provider order is set correctly."""
        planner = ExecutionPlanner()
        assert planner.provider_order == ["opnsense", "proxmox", "oci", "kubernetes"]

    def test_custom_provider_order(self) -> None:
        """Test custom provider order is used."""
        order = ["kubernetes", "oci", "proxmox"]
        planner = ExecutionPlanner(provider_order=order)
        assert planner.provider_order == order

    def test_with_dependency_graph(self) -> None:
        """Test initialization with dependency graph."""
        graph = DependencyGraph()
        planner = ExecutionPlanner(dependency_graph=graph)
        assert planner.dependency_graph is graph


class TestExecutionPlannerSorting:
    """Test provider sorting functionality."""

    def test_sort_providers_forward(self) -> None:
        """Test forward sorting respects provider order."""
        planner = ExecutionPlanner(provider_order=["a", "b", "c"])
        providers = ["c", "a", "b"]
        sorted_providers = planner.sort_providers(providers, reverse=False)
        assert sorted_providers == ["a", "b", "c"]

    def test_sort_providers_reverse(self) -> None:
        """Test reverse sorting for destroy operations."""
        planner = ExecutionPlanner(provider_order=["a", "b", "c"])
        providers = ["a", "c", "b"]
        sorted_providers = planner.sort_providers(providers, reverse=True)
        assert sorted_providers == ["c", "b", "a"]

    def test_sort_providers_unlisted_go_last(self) -> None:
        """Test that unlisted providers are placed at the end."""
        planner = ExecutionPlanner(provider_order=["a", "b"])
        providers = ["z", "a", "y", "b"]
        sorted_providers = planner.sort_providers(providers, reverse=False)
        # a, b first (in order), then z, y (unlisted, in original order due to stable sort)
        assert sorted_providers[:2] == ["a", "b"]
        assert set(sorted_providers[2:]) == {"y", "z"}

    def test_sort_providers_unlisted_reverse(self) -> None:
        """Test reverse sorting with unlisted providers."""
        planner = ExecutionPlanner(provider_order=["a", "b"])
        providers = ["z", "a", "b"]
        sorted_providers = planner.sort_providers(providers, reverse=True)
        # In reverse: unlisted (z) first, then b, a
        assert sorted_providers == ["z", "b", "a"]


class TestExecutionPlannerPlanApply:
    """Test plan_apply functionality."""

    def test_plan_apply_empty(self) -> None:
        """Test plan_apply with empty resources."""
        planner = ExecutionPlanner()
        batches = planner.plan_apply({})
        assert batches == []

    def test_plan_apply_single_provider(self) -> None:
        """Test plan_apply with single provider."""
        planner = ExecutionPlanner()
        resources = {"proxmox": [make_resource("proxmox", "vm1")]}
        batches = planner.plan_apply(resources)

        assert len(batches) == 1
        assert batches[0].providers == ["proxmox"]
        assert "proxmox" in batches[0].resources_by_provider

    def test_plan_apply_multiple_providers(self) -> None:
        """Test plan_apply with multiple providers in correct order."""
        planner = ExecutionPlanner(provider_order=["opnsense", "proxmox", "kubernetes"])
        resources = {
            "kubernetes": [make_resource("kubernetes", "deploy1")],
            "opnsense": [make_resource("opnsense", "rule1")],
            "proxmox": [make_resource("proxmox", "vm1")],
        }
        batches = planner.plan_apply(resources)

        # Each provider should be in its own batch, in order
        assert len(batches) == 3
        assert batches[0].providers == ["opnsense"]
        assert batches[1].providers == ["proxmox"]
        assert batches[2].providers == ["kubernetes"]


class TestExecutionPlannerPlanDestroy:
    """Test plan_destroy functionality."""

    def test_plan_destroy_reverse_order(self) -> None:
        """Test plan_destroy uses reverse provider order."""
        planner = ExecutionPlanner(provider_order=["opnsense", "proxmox", "kubernetes"])
        resources = {
            "kubernetes": [make_resource("kubernetes", "deploy1")],
            "opnsense": [make_resource("opnsense", "rule1")],
            "proxmox": [make_resource("proxmox", "vm1")],
        }
        batches = planner.plan_destroy(resources)

        # Destroy should be in REVERSE order
        assert len(batches) == 3
        assert batches[0].providers == ["kubernetes"]
        assert batches[1].providers == ["proxmox"]
        assert batches[2].providers == ["opnsense"]


class TestExecutionPlannerWithGraph:
    """Test ExecutionPlanner with dependency graph for cross-provider deps."""

    def test_cross_provider_deps_detected(self) -> None:
        """Test that cross-provider dependencies are detected."""
        graph = DependencyGraph()
        # kubernetes depends on proxmox VM
        graph.add_resource("proxmox", "vm", "vm1")
        # Manually add cross-provider dependency
        graph._adjacency["kubernetes:deploy1"].add("proxmox:vm1")
        graph._reverse_adjacency["proxmox:vm1"].add("kubernetes:deploy1")

        planner = ExecutionPlanner(dependency_graph=graph)
        assert planner._has_cross_provider_deps()

    def test_no_cross_provider_deps(self) -> None:
        """Test when there are no cross-provider dependencies."""
        graph = DependencyGraph()
        graph.add_resource("proxmox", "vm", "vm1")
        graph.add_resource("proxmox", "vm", "vm2", dependencies=["vm1"])

        planner = ExecutionPlanner(dependency_graph=graph)
        assert not planner._has_cross_provider_deps()


class TestExecutionPlannerSummary:
    """Test execution summary functionality."""

    def test_execution_summary(self) -> None:
        """Test get_execution_summary returns correct data."""
        planner = ExecutionPlanner()
        resources = {
            "proxmox": [make_resource("proxmox", "vm1"), make_resource("proxmox", "vm2")],
            "kubernetes": [make_resource("kubernetes", "deploy1")],
        }
        batches = planner.plan_apply(resources)
        summary = planner.get_execution_summary(batches)

        assert summary["total_batches"] == 2
        assert summary["total_providers"] == 2
        assert summary["total_resources"] == 3


class TestProviderBatch:
    """Test ProviderBatch dataclass."""

    def test_provider_batch_len(self) -> None:
        """Test ProviderBatch length."""
        batch = ProviderBatch(
            providers=["a", "b", "c"],
            resources_by_provider={},
        )
        assert len(batch) == 3
