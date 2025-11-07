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
        self, env_name: str, provider: str, resource_type: str
    ) -> list[ResourceConfig]:
        """Load resource configurations for a provider.

        Args:
            env_name: Environment name
            provider: Provider name (e.g., 'proxmox')
            resource_type: Resource type (e.g., 'vms', 'networks')

        Returns:
            List of ResourceConfig objects
        """
        resource_file = self.base_dir / env_name / provider / f"{resource_type}.yaml"
        if not resource_file.exists():
            return []

        with open(resource_file) as f:
            data = yaml.safe_load(f)

        if not data:
            return []

        # Get the resource list - handle both dict and direct list formats
        resource_list = data.get(resource_type, []) if isinstance(data, dict) else []

        # Ensure resource_list is actually a list
        if not isinstance(resource_list, list):
            raise ValueError(
                f"Expected list for '{resource_type}' in {resource_file}, "
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

    def get_all_resources(self, env_name: str, provider: str) -> list[ResourceConfig]:
        """Load all resources for a provider in an environment.

        Args:
            env_name: Environment name
            provider: Provider name

        Returns:
            List of all ResourceConfig objects for the provider
        """
        provider_dir = self.base_dir / env_name / provider
        if not provider_dir.exists():
            return []

        all_resources = []
        for config_file in provider_dir.glob("*.yaml"):
            if config_file.name == "environment.yaml":
                continue

            resource_type = config_file.stem
            resources = self.load_resources(env_name, provider, resource_type)
            all_resources.extend(resources)

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
