"""Slack notifier implementation."""

from typing import Any

import requests

from infrafoundry.core.events import EventType
from infrafoundry.core.notifications.notifiers.base_notifier import Notifier


class SlackNotifier(Notifier):
    """Send notifications to Slack via webhook."""

    def send(self, event_type: str, environment: str, data: dict[str, Any]) -> bool:
        """Send notification to Slack.

        Args:
            event_type: Type of event
            environment: Environment name
            data: Event data

        Returns:
            True if notification sent successfully
        """
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
    ) -> list[dict[Any, Any]]:
        """Format message using Slack Block Kit.

        Args:
            event_type: Type of event
            environment: Environment name
            data: Event data

        Returns:
            List of Slack block objects
        """
        emoji = self._get_event_emoji(event_type)

        blocks: list[dict[Any, Any]] = [
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
        """Get color for event type.

        Args:
            event_type: Type of event

        Returns:
            Hex color code
        """
        if "failed" in event_type.lower():
            return "#FF0000"  # Red
        elif "warning" in event_type.lower() or "drift" in event_type.lower():
            return "#FFA500"  # Orange
        else:
            return "#36A64F"  # Green

    @staticmethod
    def _get_event_emoji(event_type: str) -> str:
        """Get emoji for event type.

        Args:
            event_type: Type of event

        Returns:
            Emoji character
        """
        if "failed" in event_type.lower():
            return "❌"
        elif "completed" in event_type.lower() or "passed" in event_type.lower():
            return "✅"
        elif "drift" in event_type.lower():
            return "⚠️"
        elif "policy" in event_type.lower():
            return "🛡️"
        else:
            return "(i)"
