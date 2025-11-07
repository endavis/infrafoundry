"""Configuration management for InfraFoundry."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from infrafoundry.core.provider import ResourceConfig


class EnvironmentConfig(BaseModel):
    """Environment-specific configuration."""

    name: str
    description: str | None = None
    providers: list[str] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)


class ConfigManager:
    """Manages configuration loading and validation."""

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

    def load_environment(self, env_name: str) -> EnvironmentConfig:
        """Load environment configuration.

        Args:
            env_name: Environment name (e.g., 'dev', 'prod')

        Returns:
            EnvironmentConfig object

        Raises:
            FileNotFoundError: If environment config doesn't exist
        """
        env_file = self.base_dir / env_name / "environment.yaml"
        if not env_file.exists():
            raise FileNotFoundError(f"Environment config not found: {env_file}")

        with open(env_file) as f:
            data = yaml.safe_load(f)

        return EnvironmentConfig(**data)

    def load_resources(
        self, env_name: str, provider: str, resource_file: str
    ) -> list[ResourceConfig]:
        """Load resource configurations for a provider.

        Args:
            env_name: Environment name
            provider: Provider name (e.g., 'proxmox')
            resource_file: Resource filename without extension (e.g., 'vms', 'vms-01')

        Returns:
            List of ResourceConfig objects
        """
        resource_path = self.base_dir / env_name / provider / f"{resource_file}.yaml"
        if not resource_path.exists():
            return []

        with open(resource_path) as f:
            data = yaml.safe_load(f)

        if not data:
            return []

        # Extract resource type from filename
        # Supports:
        #   - vm.yaml -> type: vm
        #   - vm-01.yaml -> type: vm
        #   - vm-webservers.yaml -> type: vm
        resource_type = resource_file.split("-")[0] if "-" in resource_file else resource_file

        # Get the resource list - handle both dict and direct list formats
        # Try singular first, then plural for backwards compatibility
        if isinstance(data, dict):
            resource_list = data.get(resource_type, [])
            # Try plural form if singular not found (backwards compatibility)
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
            )
            for item in resource_list
            if isinstance(item, dict) and "name" in item
        ]

        return resources

    def load_resource_centric_files(self, env_name: str) -> list[ResourceConfig]:
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
            with open(config_file) as f:
                data = yaml.safe_load(f)

            if not data or "resources" not in data:
                continue

            resource_list = data["resources"]
            if not isinstance(resource_list, list):
                raise ValueError(
                    f"Expected list for 'resources' in {config_file}, "
                    f"got {type(resource_list).__name__}"
                )

            for item in resource_list:
                if not isinstance(item, dict):
                    continue

                # Validate required fields
                if "provider" not in item:
                    resource_name = item.get("name", "unnamed")
                    raise ValueError(
                        f"Missing 'provider' field in resource in {config_file}: "
                        f"{resource_name}"
                    )
                if "type" not in item:
                    resource_name = item.get("name", "unnamed")
                    raise ValueError(
                        f"Missing 'type' field in resource in {config_file}: " f"{resource_name}"
                    )
                if "name" not in item:
                    raise ValueError(f"Missing 'name' field in resource in {config_file}")

                # Extract config dict (everything except provider/type/name)
                config = item.get("config", {})
                # Also include name in config for backwards compatibility
                config["name"] = item["name"]

                all_resources.append(
                    ResourceConfig(
                        name=item["name"],
                        type=item["type"],
                        provider=item["provider"],
                        config=config,
                    )
                )

        return all_resources

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

        # Load provider-centric files (original format)
        provider_dir = self.base_dir / env_name / provider
        if provider_dir.exists():
            for config_file in provider_dir.glob("*.yaml"):
                if config_file.name == "environment.yaml":
                    continue

                # Use the filename without extension
                resource_file = config_file.stem
                resources = self.load_resources(env_name, provider, resource_file)
                all_resources.extend(resources)

        # Load resource-centric files (new format)
        resource_centric = self.load_resource_centric_files(env_name)
        # Filter to only resources for this provider
        all_resources.extend([r for r in resource_centric if r.provider == provider])

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
        discovered_providers = set()

        # Discover providers from provider-centric directories
        env_dir = self.base_dir / env_name
        if env_dir.exists():
            for item in env_dir.iterdir():
                if item.is_dir() and item.name not in ("resources", "secrets"):
                    discovered_providers.add(item.name)

        # Load from provider-centric directories (without resource-centric included)
        for provider_name in discovered_providers:
            provider_dir = self.base_dir / env_name / provider_name
            if provider_dir.exists():
                for config_file in provider_dir.glob("*.yaml"):
                    if config_file.name == "environment.yaml":
                        continue
                    resource_file = config_file.stem
                    resources = self.load_resources(env_name, provider_name, resource_file)
                    all_resources.extend(resources)

        # Load from resource-centric files (once)
        resource_centric = self.load_resource_centric_files(env_name)
        all_resources.extend(resource_centric)

        # Check for duplicate resource names
        seen_names: dict[str, str] = {}
        duplicates: list[tuple[str, list[str]]] = []

        for resource in all_resources:
            key = f"{resource.provider}:{resource.name}"
            if key in seen_names:
                # Found duplicate
                if not any(d[0] == key for d in duplicates):
                    duplicates.append((key, [seen_names[key], "current"]))
            else:
                # Track first occurrence (we don't have file info, so use generic label)
                seen_names[key] = "multiple files"

        if duplicates:
            dup_list = [dup[0] for dup in duplicates]
            raise ValueError(
                f"Duplicate resource names found in environment '{env_name}': "
                f"{', '.join(dup_list)}. Each resource name must be unique within its provider."
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

        env_file = env_dir / "environment.yaml"
        return env_file.exists()
