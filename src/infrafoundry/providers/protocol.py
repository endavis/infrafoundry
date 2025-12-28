"""Provider plugin protocol.

This module defines the protocol that all provider plugins must implement.
Providers handle infrastructure resource management through CRUD operations.

Example:
    >>> class MyProvider:
    ...     def __init__(self, config: dict[str, Any]) -> None:
    ...         self.config = config
    ...
    ...     def create(self, resource_type: str, resource_config: dict[str, Any]) -> ResourceResult:
    ...         # Create resource implementation
    ...         pass
"""

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol

from infrafoundry.core.plugin_system.plugin_type import ValidationResult


@dataclass
class ResourceResult:
    """Result of a resource operation.

    Args:
        success: Whether the operation succeeded
        resource_id: ID of the resource
        resource_type: Type of the resource
        state: Current state of the resource
        message: Optional message about the operation
    """

    success: bool
    resource_id: str
    resource_type: str
    state: dict[str, Any]
    message: str | None = None

    def __str__(self) -> str:
        """Return formatted resource result string."""
        status = "SUCCESS" if self.success else "FAILURE"
        return f"{status}: {self.resource_type}/{self.resource_id}"


@dataclass
class ResourceSummary:
    """Summary information about a resource.

    Args:
        resource_id: ID of the resource
        resource_type: Type of the resource
        name: Human-readable name
        status: Current status (e.g., "running", "stopped")
        metadata: Additional metadata about the resource
    """

    resource_id: str
    resource_type: str
    name: str
    status: str
    metadata: dict[str, Any]

    def __str__(self) -> str:
        """Return formatted resource summary string."""
        return f"{self.resource_type}/{self.name} ({self.status})"


class BaseProvider(Protocol):
    """Protocol that all provider plugins must implement.

    This protocol defines the interface for infrastructure provider plugins.
    Providers manage resources through CRUD operations and support
    configuration validation.

    Example:
        >>> class ProxmoxProvider:
        ...     def __init__(self, config: dict[str, Any]) -> None:
        ...         self.api_url = config["api_url"]
        ...         self.api_token = config["api_token"]
        ...
        ...     def create(
        ...         self,
        ...         resource_type: str,
        ...         resource_config: dict[str, Any]
        ...     ) -> ResourceResult:
        ...         # Implementation
        ...         pass
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize provider with configuration.

        Args:
            config: Provider configuration dictionary

        Example:
            >>> config = {
            ...     "api_url": "https://proxmox.example.com:8006",
            ...     "api_token": "secret://vault/proxmox/api_token"
            ... }
            >>> provider = ProxmoxProvider(config)
        """

    @abstractmethod
    def create(self, resource_type: str, resource_config: dict[str, Any]) -> ResourceResult:
        """Create a new resource.

        Args:
            resource_type: Type of resource to create (e.g., "vm", "container")
            resource_config: Configuration for the resource

        Returns:
            ResourceResult with creation status and resource state

        Example:
            >>> result = provider.create("vm", {
            ...     "name": "web-server-01",
            ...     "memory": 4096,
            ...     "cpu": 2,
            ...     "template": "ubuntu-22.04"
            ... })
            >>> print(result.resource_id)
            'vm-101'
        """

    @abstractmethod
    def read(self, resource_type: str, resource_id: str) -> ResourceResult:
        """Read the current state of a resource.

        Args:
            resource_type: Type of resource (e.g., "vm", "container")
            resource_id: ID of the resource

        Returns:
            ResourceResult with current resource state

        Example:
            >>> result = provider.read("vm", "vm-101")
            >>> print(result.state["status"])
            'running'
        """

    @abstractmethod
    def update(
        self, resource_type: str, resource_id: str, desired_config: dict[str, Any]
    ) -> ResourceResult:
        """Update an existing resource.

        Args:
            resource_type: Type of resource (e.g., "vm", "container")
            resource_id: ID of the resource to update
            desired_config: Desired configuration changes

        Returns:
            ResourceResult with updated resource state

        Example:
            >>> result = provider.update("vm", "vm-101", {
            ...     "memory": 8192,  # Increase memory
            ...     "cpu": 4          # Increase CPU
            ... })
        """

    @abstractmethod
    def delete(self, resource_type: str, resource_id: str) -> None:
        """Delete a resource.

        Args:
            resource_type: Type of resource (e.g., "vm", "container")
            resource_id: ID of the resource to delete

        Example:
            >>> provider.delete("vm", "vm-101")
        """

    @abstractmethod
    def list_resources(self, resource_type: str) -> list[ResourceSummary]:
        """List all resources of a specific type.

        Args:
            resource_type: Type of resources to list (e.g., "vm", "container")

        Returns:
            List of resource summaries

        Example:
            >>> vms = provider.list_resources("vm")
            >>> for vm in vms:
            ...     print(f"{vm.name}: {vm.status}")
        """

    @abstractmethod
    def validate_config(
        self, resource_type: str, resource_config: dict[str, Any]
    ) -> ValidationResult:
        """Validate resource configuration.

        Args:
            resource_type: Type of resource (e.g., "vm", "container")
            resource_config: Configuration to validate

        Returns:
            ValidationResult indicating if config is valid

        Example:
            >>> result = provider.validate_config("vm", {
            ...     "name": "web-server-01",
            ...     "memory": 4096,
            ...     "cpu": 2
            ... })
            >>> if not result.valid:
            ...     print(f"Errors: {result.errors}")
        """
