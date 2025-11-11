"""Notification models and data structures."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class NotificationLevel(Enum):
    """Notification severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class NotificationChannel:
    """Configuration for a notification channel."""

    name: str
    type: str  # webhook, slack, email
    enabled: bool
    config: dict[str, Any]
    events: list[str] | None = None  # None = all events
    levels: list[str] | None = None  # None = all levels
