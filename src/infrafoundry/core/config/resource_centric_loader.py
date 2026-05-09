"""Resource-centric configuration loader.

Loads resources from envs/{env}/resources/*.yaml files.
"""

from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.config.package_loader import (
    NESTED_PROVIDER_NAMESPACE,
    PackageLoader,
)
from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig


class ResourceCentricLoader:
    """Loads resources from resource-centric directory structure."""

    def __init__(self, base_dir: Path) -> None:
        """Initialize loader.

        Args:
            base_dir: Base directory for environment configs (e.g., ./envs)
        """
        self.base_dir = base_dir
        # Lazily-instantiated helper for the nested-format walk; the loader
        # delegates to ``PackageLoader._parse_nested_provider_format`` so the
        # nested-format logic lives in a single module (#793 Phase 2).
        self._package_loader = PackageLoader(base_dir)

    def load_resources(self, env_name: str) -> list[ResourceConfig]:
        """Load resource-centric configuration files.

        Resource-centric files have format:
        ```yaml
        resources:
          - provider: proxmox
            type: vm
            name: web-01
            config:
              cores: 4
              memory: 8192
        ```

        Files under the nested ``opnsense:`` namespace (#793 Phase 2, per
        ADR-0016) are also accepted; detection is by top-level key.

        Args:
            env_name: Environment name

        Returns:
            List of ResourceConfig objects from all resource-centric files
        """
        resources_dir = self.base_dir / env_name / "resources"
        if not resources_dir.exists():
            return []

        all_resources = []
        for config_file in resources_dir.glob("*.yaml"):
            resources = self._load_single_file(config_file)
            all_resources.extend(resources)

        return all_resources

    def _load_single_file(self, config_file: Path) -> list[ResourceConfig]:
        """Load resources from a single resource-centric config file.

        Args:
            config_file: Path to YAML config file

        Returns:
            List of ResourceConfig objects from the file

        Raises:
            InvalidConfigurationError: If a nested-format file mixes
                ``opnsense:`` with other top-level keys.
        """
        with open(config_file) as f:
            data = yaml.safe_load(f)

        if not data:
            return []

        # Nested provider-namespace format (#793 Phase 2) — branch before
        # the existing ``resources:``-key path so a top-level ``opnsense:``
        # key always wins.
        if isinstance(data, dict):
            nested = data.get(NESTED_PROVIDER_NAMESPACE)
            if isinstance(nested, dict):
                extra_keys = [k for k in data if k != NESTED_PROVIDER_NAMESPACE]
                if extra_keys:
                    raise InvalidConfigurationError(
                        f"{config_file}: cannot mix nested "
                        f"'{NESTED_PROVIDER_NAMESPACE}:' format with other top-level "
                        f"keys (found: {sorted(extra_keys)!r}). Use one format per file."
                    )
                return self._package_loader._parse_nested_provider_format(
                    nested, NESTED_PROVIDER_NAMESPACE, str(config_file)
                )

        if "resources" not in data:
            return []

        resource_list = data["resources"]
        if not isinstance(resource_list, list):
            raise ValueError(
                f"Expected list for 'resources' in {config_file}, "
                f"got {type(resource_list).__name__}"
            )

        resources = []
        for item in resource_list:
            if not isinstance(item, dict):
                continue

            # Validate required fields
            self._validate_resource_item(item, config_file)

            # Extract config dict (everything except provider/type/name)
            config = item.get("config", {})
            # Include name in config for template convenience
            config["name"] = item["name"]

            resources.append(
                ResourceConfig(
                    name=item["name"],
                    type=str(item["type"]),
                    provider=item["provider"],
                    config=config,
                    import_id=item.get("import_id"),
                )
            )

        return resources

    def _validate_resource_item(self, item: dict[str, Any], config_file: Path) -> None:
        """Validate required fields in a resource item.

        Args:
            item: Resource item dictionary
            config_file: Config file path for error messages

        Raises:
            ValueError: If required fields are missing
        """
        resource_name = item.get("name", "unnamed")

        if "provider" not in item:
            raise ValueError(
                f"Missing 'provider' field in resource in {config_file}: {resource_name}"
            )
        if "type" not in item:
            raise ValueError(f"Missing 'type' field in resource in {config_file}: {resource_name}")
        if "name" not in item:
            raise ValueError(f"Missing 'name' field in resource in {config_file}")

    def get_resources_for_provider(self, env_name: str, provider: str) -> list[ResourceConfig]:
        """Load resources for a specific provider from resource-centric files.

        Args:
            env_name: Environment name
            provider: Provider name to filter by

        Returns:
            List of ResourceConfig objects for the specified provider
        """
        all_resources = self.load_resources(env_name)
        return [r for r in all_resources if r.provider == provider]
