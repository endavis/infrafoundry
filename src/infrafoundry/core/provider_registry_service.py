"""Provider registry service to encapsulate provider lifecycle management."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners import AnsibleRunner, PyInfraRunner, RunnerRegistry, TerraformRunner


class ProviderRegistryService:
    """Manages provider registration and runner registry wiring."""

    def __init__(
        self,
        base_output_dir: Path,
        runner_registry_factory: Callable[[], RunnerRegistry] | None = None,
    ) -> None:
        self.base_output_dir = base_output_dir
        self.runner_registry = (
            runner_registry_factory() if runner_registry_factory else RunnerRegistry()
        )
        self._providers: dict[str, ProviderBase] = {}
        self._register_default_runners()

    @property
    def providers(self) -> dict[str, ProviderBase]:
        """Return registered providers."""
        return self._providers

    def register_provider(self, provider: ProviderBase) -> None:
        """Register a provider instance."""
        self._providers[provider.name] = provider

    def get_runner_priorities(self, env_name: str) -> dict[str, int]:
        """Fetch runner priorities from providers' environment configs if available."""
        # Providers own their config_dir; default to empty priorities.
        priorities: dict[str, int] = {}
        return priorities

    def _register_default_runners(self) -> None:
        """Register built-in runners."""
        self.runner_registry.register(TerraformRunner)
        self.runner_registry.register(AnsibleRunner)
        self.runner_registry.register(PyInfraRunner)
