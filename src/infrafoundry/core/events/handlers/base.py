"""Base handler protocol for event handlers."""

from abc import ABC, abstractmethod
from typing import Any

from infrafoundry.core.events.context import EventContext, EventResult


class BaseHandler(ABC):
    """Abstract base class for event handlers.

    All handler types (Python, script, webhook) must implement this interface.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize handler with configuration.

        Args:
            config: Handler-specific configuration from event config
        """
        self.config = config
        self._name = config.get("name", self.__class__.__name__)
        self._package: str | None = config.get("_package")
        self._resource_owner: str | None = config.get("_resource_owner")

    @property
    def name(self) -> str:
        """Handler name for logging and identification."""
        return str(self._name)

    @property
    def is_resource_scoped(self) -> bool:
        """Whether this handler is scoped to a specific resource.

        Returns:
            True when ``_resource_owner`` is set, meaning the handler was
            registered for a specific resource (e.g., on_create on a VM).
        """
        return self._resource_owner is not None

    @abstractmethod
    def execute(self, context: EventContext) -> EventResult:
        """Execute the handler for an event.

        Args:
            context: Event context with all relevant information

        Returns:
            EventResult indicating success/failure and whether to continue
        """
        ...

    @abstractmethod
    def validate_config(self) -> list[str]:
        """Validate handler configuration.

        Returns:
            List of validation error messages (empty if valid)
        """
        ...

    def matches_package(self, package_filter: str | None) -> bool:
        """Check whether this handler should fire for the given package filter.

        A handler fires if:
        - No package filter is set (all packages targeted).
        - The handler has no ``_package`` (resource-level or env-level events).
        - The handler's package matches the filter.

        Args:
            package_filter: Package name from the --package CLI flag, or None.

        Returns:
            True if this handler should execute, False to skip.
        """
        if package_filter is None:
            return True
        if self._package is None:
            return True
        return self._package == package_filter

    def matches_resources(self, target_resources: list[str] | None) -> bool:
        """Check whether this handler should fire for the given target resources.

        A handler fires if:
        - Its ``_resource_owner`` is in ``target_resources`` (when set).
        - It has no ``resources`` or ``requires`` filter (fires for all).
        - ``target_resources`` is None (no -r flag, all resources targeted).
        - For ``resources``: intersection between handler and target resources.
        - For ``requires``: ALL required resources must be in target resources.

        Args:
            target_resources: Resource names from the -r CLI filter, or None.

        Returns:
            True if this handler should execute, False to skip.
        """
        # Resource-owner scoping: if the handler was registered for a specific
        # resource (e.g. on_create on a VM), it must only fire when that exact
        # resource is in the target list.  This prevents handlers for resource
        # "web-server" in provider A from firing when resource "web-server" in
        # provider B is created.
        if self._resource_owner is not None:
            if target_resources is None:
                return True
            if self._resource_owner not in target_resources:
                return False

        # Check 'requires' — ALL must be present (group event semantics)
        required_resources = self.config.get("requires")
        if required_resources:
            if target_resources is None:
                return True
            return set(required_resources).issubset(set(target_resources))

        # Check 'resources' — ANY intersection (filter semantics)
        handler_resources = self.config.get("resources")
        if not handler_resources:
            return True
        if target_resources is None:
            return True
        return bool(set(handler_resources) & set(target_resources))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
