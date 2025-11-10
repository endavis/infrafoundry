"""Refactored configuration manager - coordinates between loaders."""

import os
from pathlib import Path

import yaml

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.config.provider_centric_loader import ProviderCentricLoader
from infrafoundry.core.config.resource_centric_loader import ResourceCentricLoader
from infrafoundry.core.provider import ResourceConfig


class ConfigManager:
    """Manages configuration loading and validation.

    Coordinates between ProviderCentricLoader and ResourceCentricLoader
    to support both configuration formats.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        """Initialize configuration manager.

        Args:
            base_dir: Base directory for configs
                (defaults to INFRAFOUNDRY_CONFIG_REPO/envs or ./envs)
        """
        if base_dir is None:
            # Check for separate config repo first
            config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
            if config_repo:
                base_dir = Path(config_repo) / "envs"
            else:
                # Fall back to local envs directory
                config_dir = os.getenv("INFRAFOUNDRY_CONFIG_DIR", "envs")
                base_dir = Path.cwd() / config_dir

        self.base_dir = base_dir

        # Initialize loaders
        self.provider_centric = ProviderCentricLoader(base_dir)
        self.resource_centric = ResourceCentricLoader(base_dir)

    def load_environment(self, env_name: str) -> EnvironmentConfig:
        """Load environment configuration.

        Args:
            env_name: Environment name (e.g., 'dev', 'prod')

        Returns:
            EnvironmentConfig object

        Raises:
            FileNotFoundError: If environment config doesn't exist
        """
        settings_file = self.base_dir / env_name / "settings.yaml"

        if not settings_file.exists():
            raise FileNotFoundError(f"Environment config not found: {settings_file}")

        with open(settings_file) as f:
            data = yaml.safe_load(f)

        if not data:
            # Ensure we return an empty but valid EnvironmentConfig if file is empty
            data = {}

        return EnvironmentConfig(**data)

    def load_resources(
        self, env_name: str, provider: str, resource_file: str
    ) -> list[ResourceConfig]:
        """Load resource configurations for a provider from a specific file.

        Delegates to ProviderCentricLoader.

        Args:
            env_name: Environment name
            provider: Provider name (e.g., 'proxmox')
            resource_file: Resource filename without extension (e.g., 'vm', 'vm-01')

        Returns:
            List of ResourceConfig objects
        """
        return self.provider_centric.load_resources(env_name, provider, resource_file)

    def load_resource_centric_files(self, env_name: str) -> list[ResourceConfig]:
        """Load resource-centric configuration files.

        Delegates to ResourceCentricLoader.

        Args:
            env_name: Environment name

        Returns:
            List of ResourceConfig objects from all resource-centric files
        """
        return self.resource_centric.load_resources(env_name)

    def get_all_resources(self, env_name: str, provider: str) -> list[ResourceConfig]:
        """Load all resources for a provider in an environment.

        Supports both provider-centric and resource-centric formats:
        - Provider-centric: envs/{env}/{provider}/*.yaml
        - Resource-centric: envs/{env}/resources/*.yaml

        Args:
            env_name: Environment name
            provider: Provider name

        Returns:
            List of all ResourceConfig objects for the provider
        """
        all_resources = []

        # Load from provider-centric structure
        all_resources.extend(self.provider_centric.get_all_resources(env_name, provider))

        # Load from resource-centric structure
        all_resources.extend(self.resource_centric.get_resources_for_provider(env_name, provider))

        return all_resources

    def get_all_resources_all_providers(self, env_name: str) -> list[ResourceConfig]:
        """Load all resources from all providers in an environment.

        Supports both provider-centric and resource-centric formats.
        Discovers providers dynamically from available resources.

        Args:
            env_name: Environment name

        Returns:
            List of all ResourceConfig objects from all providers

        Raises:
            ValueError: If duplicate resource names are found
        """
        all_resources = []
        resource_locations: dict[str, list[str]] = {}  # Track where each resource is defined

        # Discover and load from provider-centric directories
        discovered_providers = self.provider_centric.discover_providers(env_name)

        for provider_name in discovered_providers:
            provider_dir = self.base_dir / env_name / provider_name
            for config_file in provider_dir.glob("*.yaml"):
                if config_file.name == "settings.yaml":
                    continue

                resource_file = config_file.stem
                resources = self.provider_centric.load_resources(
                    env_name, provider_name, resource_file
                )

                # Track location for each resource
                for resource in resources:
                    key = f"{resource.provider}:{resource.name}"
                    if key not in resource_locations:
                        resource_locations[key] = []
                    resource_locations[key].append(str(config_file))

                all_resources.extend(resources)

        # Load from resource-centric files
        resources_dir = self.base_dir / env_name / "resources"
        if resources_dir.exists():
            for config_file in resources_dir.glob("*.yaml"):
                resources = self.resource_centric._load_single_file(config_file)

                # Track location for each resource
                for resource in resources:
                    key = f"{resource.provider}:{resource.name}"
                    if key not in resource_locations:
                        resource_locations[key] = []
                    resource_locations[key].append(str(config_file))

                all_resources.extend(resources)

        # Check for duplicate resource names
        duplicates = [
            f"{key} found in: {', '.join(locations)}"
            for key, locations in resource_locations.items()
            if len(locations) > 1
        ]

        if duplicates:
            raise ValueError(
                f"Duplicate resource names found in environment '{env_name}':\n  "
                + "\n  ".join(duplicates)
                + "\n\nEach resource name must be unique within its provider."
            )

        return all_resources

    def list_environments(self) -> list[str]:
        """List all available environments.

        Returns:
            List of environment names
        """
        if not self.base_dir.exists():
            return []

        return [d.name for d in self.base_dir.iterdir() if d.is_dir()]

    def validate_environment(self, env_name: str) -> bool:
        """Validate that an environment exists and has proper structure.

        Args:
            env_name: Environment name to validate

        Returns:
            True if valid, False otherwise
        """
        env_dir = self.base_dir / env_name
        if not env_dir.exists():
            return False

        env_file = env_dir / "settings.yaml"
        return env_file.exists()
