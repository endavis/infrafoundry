"""Unit tests for NotificationManager."""

from unittest.mock import patch

import pytest

from infrafoundry.core.notifications import (NotificationChannel,
                                             NotificationManager,
                                             SlackNotifier, WebhookNotifier)


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

    @patch("requests.post")
    def test_webhook_no_url_configured(self, mock_post, temp_dir):
        """Test webhook notifier with missing URL."""
        import yaml

        config = {
            "channels": [
                {
                    "name": "webhook1",
                    "type": "webhook",
                    "enabled": True,
                    "config": {},  # No URL
                }
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)
        # Should not raise exception, just print error
        manager.notify("AFTER_APPLY", "dev", {"resource": "vm-01"})
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_webhook_request_exception(self, mock_post, temp_dir):
        """Test webhook notifier with request exception."""
        import yaml

        mock_post.side_effect = Exception("Connection error")

        config = {
            "channels": [
                {
                    "name": "webhook1",
                    "type": "webhook",
                    "enabled": True,
                    "config": {"url": "https://webhook.example.com"},
                }
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)
        # Should not raise exception, just print error
        manager.notify("AFTER_APPLY", "dev", {"resource": "vm-01"})

    @patch("requests.post")
    def test_slack_no_webhook_url_configured(self, mock_post, temp_dir):
        """Test Slack notifier with missing webhook URL."""
        import yaml

        config = {
            "channels": [
                {
                    "name": "slack1",
                    "type": "slack",
                    "enabled": True,
                    "config": {},  # No webhook_url
                }
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)
        # Should not raise exception, just print error
        manager.notify("AFTER_APPLY", "dev", {"resource": "vm-01"})
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_slack_request_exception(self, mock_post, temp_dir):
        """Test Slack notifier with request exception."""
        import yaml

        mock_post.side_effect = Exception("Connection error")

        config = {
            "channels": [
                {
                    "name": "slack1",
                    "type": "slack",
                    "enabled": True,
                    "config": {"webhook_url": "https://hooks.slack.com/services/XXX"},
                }
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)
        # Should not raise exception, just print error
        manager.notify("AFTER_APPLY", "dev", {"resource": "vm-01"})

    def test_load_config_invalid_yaml(self, temp_dir):
        """Test loading configuration with invalid YAML."""
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            f.write("invalid: yaml: content:\n  bad indentation")

        # Should not raise exception
        manager = NotificationManager(config_file)
        assert len(manager.channels) == 0

    def test_load_config_empty_file(self, temp_dir):
        """Test loading configuration from empty file."""
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            f.write("")

        manager = NotificationManager(config_file)
        assert len(manager.channels) == 0

    def test_load_config_no_channels_key(self, temp_dir):
        """Test loading configuration without channels key."""
        import yaml

        config = {"some_other_key": "value"}
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)
        assert len(manager.channels) == 0

    @patch("requests.post")
    def test_add_channel_dynamically(self, mock_post, temp_dir):
        """Test adding a channel after initialization."""
        manager = NotificationManager()

        channel = NotificationChannel(
            name="dynamic",
            type="webhook",
            enabled=True,
            config={"url": "https://webhook.example.com"},
        )
        manager.add_channel(channel)

        mock_post.return_value.status_code = 200
        manager.notify("AFTER_APPLY", "dev", {"resource": "vm-01"})

        assert mock_post.call_count == 1

    @patch("requests.post")
    def test_slack_format_apply_failed_event(self, mock_post, temp_dir):
        """Test Slack formatting for APPLY_FAILED event."""
        import yaml

        mock_post.return_value.status_code = 200

        config = {
            "channels": [
                {
                    "name": "slack1",
                    "type": "slack",
                    "enabled": True,
                    "config": {"webhook_url": "https://hooks.slack.com/services/XXX"},
                }
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)
        manager.notify("APPLY_FAILED", "dev", {"error": "Terraform apply failed"})

        # Check that notification was sent
        assert mock_post.call_count == 1
        call_args = mock_post.call_args
        blocks = call_args[1]["json"]["blocks"]
        # Should have header and section with fields at minimum
        assert len(blocks) >= 2
        # Check for error event type in header
        assert "APPLY_FAILED" in str(blocks)

    @patch("requests.post")
    def test_slack_format_drift_detected_event(self, mock_post, temp_dir):
        """Test Slack formatting for DRIFT_DETECTED event."""
        import yaml

        mock_post.return_value.status_code = 200

        config = {
            "channels": [
                {
                    "name": "slack1",
                    "type": "slack",
                    "enabled": True,
                    "config": {"webhook_url": "https://hooks.slack.com/services/XXX"},
                }
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)
        manager.notify("DRIFT_DETECTED", "prod", {"to_add": 2, "to_change": 3, "to_destroy": 1})

        # Check that notification was sent
        assert mock_post.call_count == 1
        call_args = mock_post.call_args
        blocks = call_args[1]["json"]["blocks"]
        # Should have header and section with fields at minimum
        assert len(blocks) >= 2
        # Check for drift event type in header
        assert "DRIFT_DETECTED" in str(blocks)

    @patch("requests.post")
    def test_slack_format_policy_violation_event(self, mock_post, temp_dir):
        """Test Slack formatting for POLICY_VIOLATION event."""
        import yaml

        mock_post.return_value.status_code = 200

        config = {
            "channels": [
                {
                    "name": "slack1",
                    "type": "slack",
                    "enabled": True,
                    "config": {"webhook_url": "https://hooks.slack.com/services/XXX"},
                }
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)
        manager.notify(
            "POLICY_VIOLATION",
            "dev",
            {"policy": "require-tags", "resource": "vm-01", "level": "ERROR"},
        )

        # Check that notification was sent
        assert mock_post.call_count == 1
        call_args = mock_post.call_args
        blocks = call_args[1]["json"]["blocks"]
        # Should have header and section with fields at minimum
        assert len(blocks) >= 2
        # Check for policy event type in header
        assert "POLICY_VIOLATION" in str(blocks)

    @patch("requests.post")
    def test_slack_emoji_for_various_event_types(self, mock_post, temp_dir):
        """Test Slack emoji selection for different event types."""
        import yaml

        mock_post.return_value.status_code = 200

        config = {
            "channels": [
                {
                    "name": "slack1",
                    "type": "slack",
                    "enabled": True,
                    "config": {"webhook_url": "https://hooks.slack.com/services/XXX"},
                }
            ]
        }
        config_file = temp_dir / "notifications.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        manager = NotificationManager(config_file)

        # Test various event types to cover emoji branches
        test_events = [
            ("PLAN_FAILED", "❌"),  # failed
            ("APPLY_COMPLETED", "✅"),  # completed
            ("VALIDATION_PASSED", "✅"),  # passed
            ("DRIFT_DETECTED", "⚠️"),  # drift
            ("POLICY_VIOLATION", "🛡️"),  # policy
            ("CUSTOM_EVENT", "ℹ️"),  # default (else branch)
        ]

        for event_type, expected_emoji in test_events:
            mock_post.reset_mock()
            manager.notify(event_type, "dev", {"data": "test"})

            # Check emoji appears in the notification
            call_args = mock_post.call_args
            blocks = call_args[1]["json"]["blocks"]
            # Emoji should be in the header text
            header_text = str(blocks[0])
            assert expected_emoji in header_text or event_type in header_text

    def test_webhook_missing_url_config(self):
        """Test webhook notifier with missing URL configuration."""
        config = {}  # No URL provided
        notifier = WebhookNotifier(config)
        result = notifier.send("APPLY_COMPLETED", "dev", {"resource": "vm-01"})
        assert result is False

    def test_slack_missing_webhook_url_config(self):
        """Test Slack notifier with missing webhook URL configuration."""
        config = {}  # No webhook_url provided
        notifier = SlackNotifier(config)
        result = notifier.send("APPLY_COMPLETED", "dev", {"resource": "vm-01"})
        assert result is False

    @patch("requests.post")
    def test_slack_network_error(self, mock_post):
        """Test Slack notifier handling network error."""
        import requests

        mock_post.side_effect = requests.RequestException("Network error")
        config = {"webhook_url": "https://hooks.slack.com/test"}
        notifier = SlackNotifier(config)
        result = notifier.send("APPLY_COMPLETED", "dev", {"resource": "vm-01"})
        assert result is False
