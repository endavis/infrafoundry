"""Unit tests for NotificationManager."""

from unittest.mock import patch

import pytest

from infrafoundry.core.notifications import (
    NotificationManager,
    SlackNotifier,
    WebhookNotifier,
)


@pytest.mark.unit
class TestWebhookNotifier:
    """Tests for WebhookNotifier."""

    def test_init(self):
        """Test WebhookNotifier initialization."""
        config = {"url": "https://webhook.example.com", "headers": {"X-Custom": "value"}}
        notifier = WebhookNotifier(config)
        assert notifier.config["url"] == "https://webhook.example.com"

    @patch("requests.post")
    def test_send_success(self, mock_post):
        """Test successful webhook send."""
        mock_post.return_value.status_code = 200
        config = {"url": "https://webhook.example.com"}
        notifier = WebhookNotifier(config)

        result = notifier.send("AFTER_APPLY", "dev", {"resource": "vm-01"})
        assert result is True
        mock_post.assert_called_once()

    def test_send_failure(self):
        """Test webhook send failure."""
        with patch("infrafoundry.core.notifications.requests.post") as mock_post:
            import requests

            mock_post.side_effect = requests.RequestException("Network error")
            config = {"url": "https://webhook.example.com"}
            notifier = WebhookNotifier(config)

            result = notifier.send("AFTER_APPLY", "dev", {})
            assert result is False

    def test_format_message(self):
        """Test message formatting."""
        config = {"url": "https://webhook.example.com"}
        notifier = WebhookNotifier(config)

        message = notifier.format_message("AFTER_APPLY", "dev", {"resource": "vm-01"})
        assert "dev" in message
        assert "AFTER_APPLY" in message
        assert "vm-01" in message


@pytest.mark.unit
class TestSlackNotifier:
    """Tests for SlackNotifier."""

    def test_init(self):
        """Test SlackNotifier initialization."""
        config = {"webhook_url": "https://hooks.slack.com/services/TEST"}
        notifier = SlackNotifier(config)
        assert notifier.config["webhook_url"] == "https://hooks.slack.com/services/TEST"

    @patch("requests.post")
    def test_send_success(self, mock_post):
        """Test successful Slack notification."""
        mock_post.return_value.status_code = 200
        config = {"webhook_url": "https://hooks.slack.com/services/TEST"}
        notifier = SlackNotifier(config)

        result = notifier.send("AFTER_APPLY", "dev", {"resource": "vm-01"})
        assert result is True

    @patch("requests.post")
    def test_send_with_blocks(self, mock_post):
        """Test that Slack sends with block formatting."""
        mock_post.return_value.status_code = 200
        config = {"webhook_url": "https://hooks.slack.com/services/TEST"}
        notifier = SlackNotifier(config)

        notifier.send("POLICY_VIOLATION", "prod", {"policy": "require_tags"})

        # Check that blocks were sent
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert "blocks" in payload
        assert isinstance(payload["blocks"], list)


@pytest.mark.unit
class TestNotificationManager:
    """Tests for NotificationManager."""

    def test_init_no_config(self, temp_dir):
        """Test initialization with no config file."""
        nonexistent = temp_dir / "nonexistent.yaml"
        manager = NotificationManager(nonexistent)
        assert len(manager.channels) == 0

    def test_load_config(self, temp_dir):
        """Test loading configuration."""
        import yaml

        config = {
            "channels": [
                {
                    "name": "test-webhook",
                    "type": "webhook",
                    "enabled": True,
                    "config": {"url": "https://webhook.example.com"},
                    "events": ["AFTER_APPLY"],
                    "levels": ["INFO"],
                }
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)
        assert len(manager.channels) == 1
        assert manager.channels[0].name == "test-webhook"
        assert "test-webhook" in manager.notifiers

    def test_disabled_channel_not_initialized(self, temp_dir):
        """Test that disabled channels don't create notifiers."""
        import yaml

        config = {
            "channels": [
                {
                    "name": "disabled-webhook",
                    "type": "webhook",
                    "enabled": False,
                    "config": {"url": "https://webhook.example.com"},
                }
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)
        assert len(manager.channels) == 1
        assert len(manager.notifiers) == 0

    @patch("requests.post")
    def test_notify_filters_events(self, mock_post, temp_dir):
        """Test that events are filtered per channel."""
        import yaml

        mock_post.return_value.status_code = 200

        config = {
            "channels": [
                {
                    "name": "selective-webhook",
                    "type": "webhook",
                    "enabled": True,
                    "config": {"url": "https://webhook.example.com"},
                    "events": ["AFTER_APPLY"],  # Only this event
                }
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)

        # Should send
        manager.notify("AFTER_APPLY", "dev", {})
        assert mock_post.call_count == 1

        # Should not send (filtered)
        manager.notify("BEFORE_PLAN", "dev", {})
        assert mock_post.call_count == 1  # Still 1

    @patch("requests.post")
    def test_notify_all_channels(self, mock_post, temp_dir):
        """Test notifying multiple channels."""
        import yaml

        mock_post.return_value.status_code = 200

        config = {
            "channels": [
                {
                    "name": "webhook1",
                    "type": "webhook",
                    "enabled": True,
                    "config": {"url": "https://webhook1.example.com"},
                },
                {
                    "name": "webhook2",
                    "type": "webhook",
                    "enabled": True,
                    "config": {"url": "https://webhook2.example.com"},
                },
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)
        manager.notify("AFTER_APPLY", "dev", {"resource": "vm-01"})

        # Both channels should receive notification
        assert mock_post.call_count == 2
