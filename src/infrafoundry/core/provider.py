"""Base provider interface for infrastructure plugins."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from infrafoundry.core.types import EnvironmentData
from infrafoundry.core.validation import ValidationReport


class ResourceConfig(BaseModel):
    """Base configuration for infrastructure resources."""

    name: str
    type: str
    provider: str
    config: dict[str, Any]


class ProviderBase(ABC):
    """Base class for infrastructure providers."""

    def __init__(self, name: str, config_dir: Path, output_dir: Path) -> None:
        """Initialize provider.

        Args:
            name: Provider name (e.g., 'proxmox', 'opnsense', 'kubernetes')
            config_dir: Directory containing provider configs
            output_dir: Base directory for generated Terraform/Ansible files
                       (actual paths will be output_dir/{env}/{terraform|ansible}/{provider})
        """
        self.name = name
        self.config_dir = config_dir
        self.base_output_dir = output_dir  # Store base, use set_environment() for actual paths
        self.output_dir = output_dir  # Will be updated by set_environment()
        self.terraform_dir = output_dir / "terraform" / name
        self.ansible_dir = output_dir / "ansible" / name
        self.pyinfra_dir = output_dir / "pyinfra" / name
        self._current_environment: str | None = None

    def set_environment(self, env_name: str) -> None:
        """Set the current environment and update output directories.

        This should be called before generate_terraform(), generate_ansible(),
        or generate_pyinfra() to ensure files are generated in the correct
        environment-specific directory.

        Args:
            env_name: Environment name (e.g., 'dev', 'staging', 'prod')
        """
        self._current_environment = env_name
        self.output_dir = self.base_output_dir / env_name
        self.terraform_dir = self.output_dir / "terraform" / self.name
        self.ansible_dir = self.output_dir / "ansible" / self.name
        self.pyinfra_dir = self.output_dir / "pyinfra" / self.name

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate provider configuration.

        Args:
            config: Configuration dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        pass

    @abstractmethod
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        """Generate Terraform configuration files.

        Args:
            resources: List of resources to generate Terraform for
        """
        pass

    @abstractmethod
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        """Generate Ansible playbooks and roles.

        Args:
            resources: List of resources to generate Ansible for
        """
        pass

    def generate_pyinfra(self, resources: list[ResourceConfig]) -> None:
        """Generate pyinfra deploy scripts and inventory.

        Optional method. Providers can override this to support pyinfra.

        Args:
            resources: List of resources to generate pyinfra for
        """
        return

    def ensure_directories(self) -> None:
        """Create necessary output directories."""
        self.terraform_dir.mkdir(parents=True, exist_ok=True)
        self.ansible_dir.mkdir(parents=True, exist_ok=True)
        self.pyinfra_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def get_resource_types(self) -> list[str]:
        """Get list of resource types supported by this provider.

        Returns:
            List of supported resource type names
        """
        pass

    def get_dependencies(self) -> dict[str, list[str]]:
        """Get resource dependencies for proper ordering.

        Returns:
            Dict mapping resource types to their dependencies
        """
        return {}

    def validate_connectivity(self, env_config: EnvironmentData, report: ValidationReport) -> None:
        """Validate connectivity to provider API.

        Optional method for providers to implement API connectivity checks.
        Should add results to the validation report.

        Args:
            env_config: Environment configuration including credentials
            report: ValidationReport to add results to
        """
        # Default: no connectivity validation
        return None

    def validate_references(
        self, resources: list[ResourceConfig], env_config: EnvironmentData, report: ValidationReport
    ) -> None:
        """Validate that referenced resources exist in the provider.

        Optional method for providers to check that templates, networks,
        aliases, etc. referenced in configs actually exist.

        Args:
            resources: Resources to validate
            env_config: Environment configuration including credentials
            report: ValidationReport to add results to
        """
        # Default: no reference validation
        return None
