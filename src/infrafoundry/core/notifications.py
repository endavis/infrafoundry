"""Notification system for infrastructure deployment events."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import requests
import yaml

from infrafoundry.core.base_manager import PathBasedManager
from infrafoundry.core.events import EventType


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


class Notifier(ABC):
    """Base class for notification channels."""

    def __init__(self, config: dict[str, Any]):
        """Initialize notifier with configuration."""
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
        """Format a basic text message."""
        return f"[{environment}] {event_type}: {json.dumps(data, indent=2)}"


class WebhookNotifier(Notifier):
    """Send notifications via HTTP webhooks."""

    def send(self, event_type: str, environment: str, data: dict[str, Any]) -> bool:
        """Send notification via webhook."""
        url = self.config.get("url")
        if not url:
            print("Error: Webhook URL not configured")
            return False

        payload = {
            "event_type": event_type,
            "environment": environment,
            "data": data,
            "source": "infrafoundry",
        }

        # Add custom headers if configured
        headers = self.config.get("headers", {})
        headers.setdefault("Content-Type", "application/json")

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            print(f"Failed to send webhook notification: {e}")
            return False


class SlackNotifier(Notifier):
    """Send notifications to Slack via webhook."""

    def send(self, event_type: str, environment: str, data: dict[str, Any]) -> bool:
        """Send notification to Slack."""
        webhook_url = self.config.get("webhook_url")
        if not webhook_url:
            print("Error: Slack webhook URL not configured")
            return False

        # Format message with Slack blocks
        blocks = self._format_slack_message(event_type, environment, data)

        try:
            response = requests.post(
                webhook_url,
                json={"blocks": blocks},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            print(f"Failed to send Slack notification: {e}")
            return False

    def _format_slack_message(
        self, event_type: str, environment: str, data: dict[str, Any]
    ) -> list[dict]:
        """Format message using Slack Block Kit."""
        emoji = self._get_event_emoji(event_type)

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} InfraFoundry: {event_type}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Environment:*\n{environment}"},
                    {"type": "mrkdwn", "text": f"*Event:*\n{event_type}"},
                ],
            },
        ]

        # Add event-specific details
        if event_type in [EventType.APPLY_FAILED, EventType.PLAN_FAILED]:
            error = data.get("error", "Unknown error")
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Error:*\n```{error}```"},
                }
            )
        elif event_type == EventType.DRIFT_DETECTED:
            changes_text = (
                f"*Changes Detected:*\n"
                f"• Add: {data.get('to_add', 0)}\n"
                f"• Change: {data.get('to_change', 0)}\n"
                f"• Destroy: {data.get('to_destroy', 0)}"
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": changes_text},
                }
            )
        elif event_type == EventType.POLICY_VIOLATION:
            blocks.append(
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Policy:*\n{data.get('policy', 'N/A')}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Resource:*\n{data.get('resource', 'N/A')}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Level:*\n{data.get('level', 'N/A')}",
                        },
                    ],
                }
            )

        return blocks

    @staticmethod
    def _get_event_color(event_type: str) -> str:
        """Get color for event type."""
        if "failed" in event_type.lower():
            return "#FF0000"  # Red
        elif "warning" in event_type.lower() or "drift" in event_type.lower():
            return "#FFA500"  # Orange
        else:
            return "#36A64F"  # Green

    @staticmethod
    def _get_event_emoji(event_type: str) -> str:
        """Get emoji for event type."""
        if "failed" in event_type.lower():
            return "❌"
        elif "completed" in event_type.lower() or "passed" in event_type.lower():
            return "✅"
        elif "drift" in event_type.lower():
            return "⚠️"
        elif "policy" in event_type.lower():
            return "🛡️"
        else:
            return "ℹ️"


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
        """Add a notification channel dynamically."""
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
