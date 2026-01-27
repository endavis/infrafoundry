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

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
