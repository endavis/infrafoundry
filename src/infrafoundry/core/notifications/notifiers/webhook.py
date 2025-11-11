"""Webhook notifier implementation."""

from typing import Any

import requests

from infrafoundry.core.notifications.notifiers.base_notifier import Notifier


class WebhookNotifier(Notifier):
    """Send notifications via HTTP webhooks."""

    def send(self, event_type: str, environment: str, data: dict[str, Any]) -> bool:
        """Send notification via webhook.

        Args:
            event_type: Type of event
            environment: Environment name
            data: Event data

        Returns:
            True if notification sent successfully
        """
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
