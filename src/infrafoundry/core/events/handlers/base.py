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
        self._package_resources: list[str] | None = config.get("_package_resources")
        self._package_providers: list[str] | None = config.get("_package_providers")

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
        - Without ``resources``/``requires``, a package-level handler tagged with
          ``_package_resources`` needs an intersection with a non-None
          ``target_resources``.

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
        if handler_resources:
            if target_resources is None:
                return True
            return bool(set(handler_resources) & set(target_resources))

        # Package-level handler without its own filter: scope it to the
        # resources of the package that declared it.
        if self._package_resources is not None and target_resources is not None:
            return bool(set(self._package_resources) & set(target_resources))
        return True

    def matches_providers(self, provider_filter: list[str] | None) -> bool:
        """Check whether this handler should fire for the given provider filter.

        A handler fires if no provider filter is set, it carries no
        ``_package_providers`` (environment-level or older configs), or its
        package's providers intersect the filter.

        Args:
            provider_filter: Provider names from the -P CLI flag, or None.

        Returns:
            True if this handler should execute, False to skip.
        """
        if provider_filter is None:
            return True
        if self._package_providers is None:
            return True
        return bool(set(self._package_providers) & set(provider_filter))

    def matches_scope(self, context: EventContext) -> bool:
        """Check whether this handler is in scope for the event's operation.

        Combines the package (-p), resource (-r) and provider (-P) filters.

        Args:
            context: Event context carrying the operation's filters.

        Returns:
            True if this handler should execute, False to skip.
        """
        return (
            self.matches_package(context.package_filter)
            and self.matches_resources(context.target_resources)
            and self.matches_providers(context.provider_filter)
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
