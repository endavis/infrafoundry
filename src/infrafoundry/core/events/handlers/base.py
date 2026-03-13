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

    @property
    def name(self) -> str:
        """Handler name for logging and identification."""
        return str(self._name)

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

    def matches_resources(self, target_resources: list[str] | None) -> bool:
        """Check whether this handler should fire for the given target resources.

        A handler fires if:
        - It has no ``resources`` filter in its config (fires for all).
        - ``target_resources`` is None (no -r flag, all resources targeted).
        - There is an intersection between handler resources and target resources.

        Args:
            target_resources: Resource names from the -r CLI filter, or None.

        Returns:
            True if this handler should execute, False to skip.
        """
        handler_resources = self.config.get("resources")
        if not handler_resources:
            return True
        if target_resources is None:
            return True
        return bool(set(handler_resources) & set(target_resources))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
