"""Notification manager for handling multiple notification channels."""

from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.base_manager import PathBasedManager
from infrafoundry.core.notifications.models import NotificationChannel
from infrafoundry.core.notifications.notifiers import SlackNotifier, WebhookNotifier
from infrafoundry.core.notifications.notifiers.base_notifier import Notifier


class NotificationManager(PathBasedManager):
    """Manages notification channels and dispatches events."""

    def __init__(self, config_file: Path | None = None):
        """Initialize notification manager.

        Args:
            config_file: Path to notifications config file (default: ./notifications.yaml)
        """
        # Initialize base manager with logging
        super().__init__()

        self.config_file = config_file or Path("notifications.yaml")
        self.channels: list[NotificationChannel] = []
        self.notifiers: dict[str, Notifier] = {}

        if self.config_file.exists():
            self._log_debug(f"Loading notification config from: {self.config_file}")
            self._load_config()
        else:
            self._log_debug("No notification config file found")

    def _load_config(self) -> None:
        """Load notification configuration from file."""
        try:
            with open(self.config_file) as f:
                config = yaml.safe_load(f)
                if not config or "channels" not in config:
                    self._log_debug("No channels found in config")
                    return

                for channel_config in config["channels"]:
                    channel = NotificationChannel(
                        name=channel_config["name"],
                        type=channel_config["type"],
                        enabled=channel_config.get("enabled", True),
                        config=channel_config.get("config", {}),
                        events=channel_config.get("events"),
                        levels=channel_config.get("levels"),
                    )
                    self.channels.append(channel)

                    # Initialize notifier
                    if channel.enabled:
                        if channel.type == "webhook":
                            self.notifiers[channel.name] = WebhookNotifier(channel.config)
                        elif channel.type == "slack":
                            self.notifiers[channel.name] = SlackNotifier(channel.config)

                self._log_info(f"Loaded {len(self.channels)} notification channels")
        except Exception as e:
            error_msg = "Failed to load notification config"
            self._log_error(error_msg, e)

    def notify(self, event_type: str, environment: str, data: dict[str, Any]) -> None:
        """Send notifications for an event.

        Args:
            event_type: Type of event
            environment: Environment name
            data: Event data
        """
        for channel in self.channels:
            if not channel.enabled:
                continue

            # Check if this event type should be notified
            if channel.events and event_type not in channel.events:
                continue

            # Send notification
            notifier = self.notifiers.get(channel.name)
            if notifier:
                try:
                    self._log_debug(f"Sending notification via {channel.name}")
                    notifier.send(event_type, environment, data)
                except Exception as e:
                    error_msg = f"Error sending notification via {channel.name}"
                    self._log_error(error_msg, e)

    def add_channel(self, channel: NotificationChannel) -> None:
        """Add a notification channel dynamically.

        Args:
            channel: NotificationChannel to add
        """
        self.channels.append(channel)

        if channel.enabled:
            if channel.type == "webhook":
                self.notifiers[channel.name] = WebhookNotifier(channel.config)
            elif channel.type == "slack":
                self.notifiers[channel.name] = SlackNotifier(channel.config)

        self._log_info(f"Added notification channel: {channel.name}")

    def cleanup(self) -> None:
        """Cleanup resources (required by BaseManager).

        No cleanup needed for NotificationManager as it doesn't maintain
        persistent connections.
        """
        self._log_debug("NotificationManager cleanup complete")
