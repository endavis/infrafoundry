"""Notification system for infrastructure deployment events.

This module has been refactored into a package structure.
All components are now in the notifications/ package.
"""

# Re-export from new package location for convenience
from infrafoundry.core.notifications.manager import NotificationManager
from infrafoundry.core.notifications.models import NotificationChannel, NotificationLevel
from infrafoundry.core.notifications.notifiers import (
    Notifier,
    SlackNotifier,
    WebhookNotifier,
)

__all__ = [
    "NotificationChannel",
    "NotificationLevel",
    "NotificationManager",
    "Notifier",
    "SlackNotifier",
    "WebhookNotifier",
]
