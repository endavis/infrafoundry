"""Base notifier abstract class."""

import json
from abc import ABC, abstractmethod
from typing import Any


class Notifier(ABC):
    """Base class for notification channels."""

    def __init__(self, config: dict[str, Any]):
        """Initialize notifier with configuration.

        Args:
            config: Notifier-specific configuration
        """
        self.config = config

    @abstractmethod
    def send(self, event_type: str, environment: str, data: dict[str, Any]) -> bool:
        """Send a notification.

        Args:
            event_type: Type of event
            environment: Environment name
            data: Event data

        Returns:
            True if notification sent successfully
        """
        pass

    def format_message(self, event_type: str, environment: str, data: dict[str, Any]) -> str:
        """Format a basic text message.

        Args:
            event_type: Type of event
            environment: Environment name
            data: Event data

        Returns:
            Formatted message string
        """
        return f"[{environment}] {event_type}: {json.dumps(data, indent=2)}"
