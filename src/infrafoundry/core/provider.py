"""Base provider interface for infrastructure plugins."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel


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
            output_dir: Directory for generated Terraform/Ansible files
        """
        self.name = name
        self.config_dir = config_dir
        self.output_dir = output_dir
        self.terraform_dir = output_dir / "terraform" / name
        self.ansible_dir = output_dir / "ansible" / name

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

    def ensure_directories(self) -> None:
        """Create necessary output directories."""
        self.terraform_dir.mkdir(parents=True, exist_ok=True)
        self.ansible_dir.mkdir(parents=True, exist_ok=True)

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
