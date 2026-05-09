"""Provider-centric configuration loader.

Loads resources from envs/{env}/{provider}/*.yaml files.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from infrafoundry.core.config.package_loader import (
    NESTED_PROVIDER_NAMESPACE,
    PackageLoader,
)
from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.secrets.provider import SecretProvider

if TYPE_CHECKING:
    from infrafoundry.core.config.blueprint_resolver import BlueprintResolver


class ProviderCentricLoader:
    """Loads resources from provider-centric directory structure."""

    def __init__(
        self,
        base_dir: Path,
        blueprint_resolver: BlueprintResolver | None = None,
        secret_provider: SecretProvider | None = None,
    ) -> None:
        """Initialize loader.

        Args:
            base_dir: Base directory for environment configs (e.g., ./envs)
            blueprint_resolver: Optional resolver for blueprint references.
            secret_provider: Provider used to load package secrets.
                Forwarded to ``PackageLoader``.
        """
        self.base_dir = base_dir
        self._package_loader = PackageLoader(base_dir, blueprint_resolver, secret_provider)
        self._pending_package_events: dict[str, list[dict[str, Any]]] = {}

    def load_resources(
        self, env_name: str, provider: str, resource_file: str
    ) -> list[ResourceConfig]:
        """Load resource configurations for a provider from a specific file.

        Supports the nested ``opnsense:`` namespace format (#793 Phase 2,
        per ADR-0016) in addition to the existing flat provider-centric
        layout. Detection is by top-level key: a dict-valued ``opnsense:``
        key triggers nested parsing; otherwise the filename-stem path is
        used.

        Args:
            env_name: Environment name
            provider: Provider name (e.g., 'proxmox')
            resource_file: Resource filename without extension (e.g., 'vm', 'vm-01')

        Returns:
            List of ResourceConfig objects

        Raises:
            InvalidConfigurationError: If a nested file mixes formats or
                contains an unknown nested resource path.
        """
        resource_path = self.base_dir / env_name / provider / f"{resource_file}.yaml"
        if not resource_path.exists():
            return []

        with open(resource_path) as f:
            data = yaml.safe_load(f)

        if not data:
            return []

        # Nested provider-namespace format (#793 Phase 2) — branch before
        # the filename-stem path so a top-level ``opnsense:`` key always
        # wins, regardless of filename.
        if isinstance(data, dict):
            nested = data.get(NESTED_PROVIDER_NAMESPACE)
            if isinstance(nested, dict):
                extra_keys = [k for k in data if k != NESTED_PROVIDER_NAMESPACE]
                if extra_keys:
                    raise InvalidConfigurationError(
                        f"{resource_path}: cannot mix nested "
                        f"'{NESTED_PROVIDER_NAMESPACE}:' format with other top-level "
                        f"keys (found: {sorted(extra_keys)!r}). Use one format per file."
                    )
                return self._package_loader._parse_nested_provider_format(
                    nested, NESTED_PROVIDER_NAMESPACE, str(resource_path)
                )

        # Extract resource type from filename
        # Supports:
        #   - vm.yaml -> type: vm
        #   - vm-01.yaml -> type: vm
        #   - vm-webservers.yaml -> type: vm
        resource_type = resource_file.split("-")[0] if "-" in resource_file else resource_file

        # Get the resource list - handle both dict and direct list formats
        # Support both singular and plural forms (e.g., 'vm' or 'vms')
        if isinstance(data, dict):
            resource_list = data.get(resource_type, [])
            # Try plural form if singular not found
            if not resource_list and not resource_type.endswith("s"):
                plural_type = f"{resource_type}s"
                resource_list = data.get(plural_type, [])
        else:
            resource_list = []

        # Ensure resource_list is actually a list
        if not isinstance(resource_list, list):
            raise ValueError(
                f"Expected list for '{resource_type}' in {resource_path}, "
                f"got {type(resource_list).__name__}"
            )

        resources = [
            ResourceConfig(
                name=item["name"],
                type=resource_type,
                provider=provider,
                config=item,
                import_id=item.get("import_id"),
            )
            for item in resource_list
            if isinstance(item, dict) and "name" in item
        ]

        return resources

    def get_all_resources(self, env_name: str, provider: str) -> list[ResourceConfig]:
        """Load all resources for a provider in an environment.

        Args:
            env_name: Environment name
            provider: Provider name

        Returns:
            List of all ResourceConfig objects for the provider
        """
        all_resources = []
        provider_dir = self.base_dir / env_name / provider

        if not provider_dir.exists():
            return []

        for config_file in provider_dir.glob("*.yaml"):
            if config_file.name == "settings.yaml":
                continue

            # Use the filename without extension
            resource_file = config_file.stem
            resources = self.load_resources(env_name, provider, resource_file)
            all_resources.extend(resources)

        # Discover and load packages in provider subdirectories
        for package_dir in self._package_loader.discover_packages(env_name, provider):
            pkg_resources, pkg_events, _pkg_vars = self._package_loader.load_package(
                package_dir, provider, env_name
            )
            all_resources.extend(pkg_resources)
            for event_type, handlers in pkg_events.items():
                self._pending_package_events.setdefault(event_type, []).extend(handlers)

        return all_resources

    def get_package_events(self) -> dict[str, list[dict[str, Any]]]:
        """Return accumulated package events and clear the buffer.

        Events are accumulated during get_all_resources() calls and
        returned once via this method, then cleared.

        Returns:
            Dict mapping event type names to handler configs
        """
        events = self._pending_package_events
        self._pending_package_events = {}
        return events

    def discover_providers(self, env_name: str) -> set[str]:
        """Discover available providers in an environment.

        Args:
            env_name: Environment name

        Returns:
            Set of provider names found in the environment directory
        """
        env_dir = self.base_dir / env_name
        if not env_dir.exists():
            return set()

        providers = set()
        for item in env_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name in ("resources", "secrets"):
                continue
            # Skip directories that are env-root packages (contain infrafoundry.yml)
            if (item / PackageLoader.MANIFEST_FILENAME).exists():
                continue
            providers.add(item.name)

        return providers
