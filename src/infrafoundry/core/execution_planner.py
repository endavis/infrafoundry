"""Execution planner for infrastructure operations.

This module bridges the dependency graph to actual execution order,
ensuring providers and resources are processed in the correct order
for create, apply, and destroy operations.
"""

from dataclasses import dataclass
from typing import Any, ClassVar

from infrafoundry.core.dependencies import DependencyGraph
from infrafoundry.core.provider import ResourceConfig


@dataclass
class ProviderBatch:
    """A batch of providers that can be processed together.

    Providers in the same batch have no dependencies between them
    and can be executed in parallel.
    """

    providers: list[str]
    resources_by_provider: dict[str, list[ResourceConfig]]

    def __len__(self) -> int:
        return len(self.providers)


class ExecutionPlanner:
    """Plans execution order for infrastructure operations.

    Bridges the dependency graph to actual execution by:
    - Computing provider batches for create/apply operations
    - Computing reverse batches for destroy operations
    - Respecting cross-provider dependencies
    - Falling back to configured or default provider order
    """

    # Default provider execution order when not configured
    DEFAULT_PROVIDER_ORDER: ClassVar[list[str]] = ["opnsense", "proxmox", "oci", "kubernetes"]

    def __init__(
        self,
        provider_order: list[str] | None = None,
        dependency_graph: DependencyGraph | None = None,
    ) -> None:
        """Initialize execution planner.

        Args:
            provider_order: Optional list defining provider execution order.
                           Providers earlier in the list are executed first.
                           Unlisted providers run after listed ones.
            dependency_graph: Optional dependency graph for cross-provider deps.
        """
        self.provider_order = provider_order or self.DEFAULT_PROVIDER_ORDER
        self.dependency_graph = dependency_graph

    def get_provider_order_key(self, provider: str) -> int:
        """Get sort key for a provider based on configured order.

        Args:
            provider: Provider name

        Returns:
            Integer sort key (lower = earlier in execution)
        """
        if provider in self.provider_order:
            return self.provider_order.index(provider)
        # Unlisted providers go after listed ones
        return len(self.provider_order)

    def sort_providers(self, providers: list[str], reverse: bool = False) -> list[str]:
        """Sort providers by configured execution order.

        Args:
            providers: List of provider names to sort
            reverse: If True, sort in reverse order (for destroy)

        Returns:
            Sorted list of provider names
        """
        return sorted(providers, key=self.get_provider_order_key, reverse=reverse)

    def plan_apply(
        self,
        resources_by_provider: dict[str, list[ResourceConfig]],
    ) -> list[ProviderBatch]:
        """Plan execution batches for apply operation.

        For apply, providers are processed in forward order:
        infrastructure providers (opnsense, proxmox) before
        application providers (kubernetes).

        Args:
            resources_by_provider: Dict mapping provider names to resources

        Returns:
            List of ProviderBatch objects in execution order.
            Each batch contains providers that can run in parallel.
        """
        return self._plan_batches(resources_by_provider, reverse=False)

    def plan_destroy(
        self,
        resources_by_provider: dict[str, list[ResourceConfig]],
    ) -> list[ProviderBatch]:
        """Plan execution batches for destroy operation.

        For destroy, providers are processed in REVERSE order:
        application providers (kubernetes) before
        infrastructure providers (proxmox, opnsense).

        Args:
            resources_by_provider: Dict mapping provider names to resources

        Returns:
            List of ProviderBatch objects in execution order.
            Each batch contains providers that can run in parallel.
        """
        return self._plan_batches(resources_by_provider, reverse=True)

    def _plan_batches(
        self,
        resources_by_provider: dict[str, list[ResourceConfig]],
        reverse: bool = False,
    ) -> list[ProviderBatch]:
        """Plan execution batches with optional reverse ordering.

        Args:
            resources_by_provider: Dict mapping provider names to resources
            reverse: If True, use reverse order (for destroy)

        Returns:
            List of ProviderBatch objects in execution order.
        """
        if not resources_by_provider:
            return []

        # If we have a dependency graph with cross-provider deps, use it
        if self.dependency_graph and self._has_cross_provider_deps():
            return self._plan_batches_from_graph(resources_by_provider, reverse)

        # Otherwise, process providers one at a time in order
        sorted_providers = self.sort_providers(list(resources_by_provider.keys()), reverse=reverse)

        batches = []
        for provider in sorted_providers:
            resources = resources_by_provider.get(provider, [])
            if resources:
                batches.append(
                    ProviderBatch(
                        providers=[provider],
                        resources_by_provider={provider: resources},
                    )
                )

        return batches

    def _has_cross_provider_deps(self) -> bool:
        """Check if dependency graph has cross-provider dependencies.

        Returns:
            True if any resources depend on resources from other providers.
        """
        if not self.dependency_graph:
            return False

        for full_name, deps in self.dependency_graph._adjacency.items():
            source_provider = full_name.split(":")[0]
            for dep in deps:
                dep_provider = dep.split(":")[0]
                if source_provider != dep_provider:
                    return True
        return False

    def _plan_batches_from_graph(
        self,
        resources_by_provider: dict[str, list[ResourceConfig]],
        reverse: bool = False,
    ) -> list[ProviderBatch]:
        """Plan batches using dependency graph for cross-provider deps.

        Args:
            resources_by_provider: Dict mapping provider names to resources
            reverse: If True, reverse the batch order (for destroy)

        Returns:
            List of ProviderBatch objects respecting cross-provider deps.
        """
        if not self.dependency_graph:
            return self._plan_batches(resources_by_provider, reverse)

        # Get resource batches from topological sort
        resource_batches = self.dependency_graph.topological_sort()

        if reverse:
            resource_batches = list(reversed(resource_batches))

        # Convert resource batches to provider batches
        provider_batches: list[ProviderBatch] = []

        for resource_batch in resource_batches:
            # Group resources in this batch by provider
            batch_by_provider: dict[str, list[ResourceConfig]] = {}

            for full_name in resource_batch:
                provider, resource_name = full_name.split(":", 1)

                # Find the matching resource config
                provider_resources = resources_by_provider.get(provider, [])
                for resource in provider_resources:
                    if resource.name == resource_name:
                        if provider not in batch_by_provider:
                            batch_by_provider[provider] = []
                        batch_by_provider[provider].append(resource)
                        break

            if batch_by_provider:
                provider_batches.append(
                    ProviderBatch(
                        providers=list(batch_by_provider.keys()),
                        resources_by_provider=batch_by_provider,
                    )
                )

        return provider_batches

    def get_execution_summary(
        self,
        batches: list[ProviderBatch],
    ) -> dict[str, Any]:
        """Get a summary of the execution plan.

        Args:
            batches: List of provider batches

        Returns:
            Dict with execution plan summary
        """
        total_providers = set()
        total_resources = 0

        for batch in batches:
            total_providers.update(batch.providers)
            for resources in batch.resources_by_provider.values():
                total_resources += len(resources)

        return {
            "total_batches": len(batches),
            "total_providers": len(total_providers),
            "total_resources": total_resources,
            "batches": [
                {
                    "providers": batch.providers,
                    "resources": sum(len(r) for r in batch.resources_by_provider.values()),
                }
                for batch in batches
            ],
        }
