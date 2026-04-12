"""Tests for the AIQUM initial setup script's alert creation logic.

The script ``blueprints/aiqum/scripts/aiqum-initial-setup.py`` is a standalone
Python file (not a package module), so we import it via ``importlib`` using
its filesystem path.
"""

import importlib.util
import smtplib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the standalone script as a module
# ---------------------------------------------------------------------------
SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "blueprints"
    / "aiqum"
    / "scripts"
    / "aiqum-initial-setup.py"
)

spec = importlib.util.spec_from_file_location("aiqum_initial_setup", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
aiqum_setup = importlib.util.module_from_spec(spec)
sys.modules["aiqum_initial_setup"] = aiqum_setup
spec.loader.exec_module(aiqum_setup)

# Re-export for convenience
create_alert = aiqum_setup.create_alert
send_test_email = aiqum_setup.send_test_email
DEFAULT_ALERT_SEVERITIES = aiqum_setup.DEFAULT_ALERT_SEVERITIES
DEFAULT_ALERT_EVENT_TYPES = aiqum_setup.DEFAULT_ALERT_EVENT_TYPES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
BASE_URL = "https://192.168.1.50"
AUTH = ("umadmin", "secret")


# ---------------------------------------------------------------------------
# Tests: create_alert function
# ---------------------------------------------------------------------------
class TestCreateAlert:
    """Tests for the ``create_alert`` helper."""

    def test_returns_true_on_201(self) -> None:
        """Successful creation (201) returns True."""
        mock_response = MagicMock()
        mock_response.status_code = 201

        with patch("aiqum_initial_setup.requests.post", return_value=mock_response) as mock_post:
            result = create_alert(BASE_URL, "My Alert", "user@example.com", AUTH)

        assert result is True
        mock_post.assert_called_once()

    def test_returns_true_on_200(self) -> None:
        """Some API versions return 200; should also succeed."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("aiqum_initial_setup.requests.post", return_value=mock_response):
            assert create_alert(BASE_URL, "My Alert", "user@example.com", AUTH) is True

    def test_returns_true_on_409_already_exists(self, capsys: pytest.CaptureFixture) -> None:
        """409 means the alert already exists -- treated as success."""
        mock_response = MagicMock()
        mock_response.status_code = 409

        with patch("aiqum_initial_setup.requests.post", return_value=mock_response):
            result = create_alert(BASE_URL, "My Alert", "user@example.com", AUTH)

        assert result is True
        assert "already exists" in capsys.readouterr().out

    def test_returns_false_on_error(self, capsys: pytest.CaptureFixture) -> None:
        """Non-success status codes return False and print a message."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("aiqum_initial_setup.requests.post", return_value=mock_response):
            result = create_alert(BASE_URL, "My Alert", "user@example.com", AUTH)

        assert result is False
        assert "Failed to create alert: 500" in capsys.readouterr().out

    def test_payload_structure(self) -> None:
        """The POST payload matches the expected AIQUM alert API structure."""
        mock_response = MagicMock()
        mock_response.status_code = 201

        with patch("aiqum_initial_setup.requests.post", return_value=mock_response) as mock_post:
            create_alert(BASE_URL, "Alerts to me@test.com", "me@test.com", AUTH)

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]

        assert payload["name"] == "Alerts to me@test.com"
        assert payload["enabled"] is True
        assert payload["action"]["notification"]["emails"] == ["me@test.com"]
        assert payload["action"]["notification"]["send_snmp_trap"] is False
        assert payload["resource"] == [{"type": "cluster", "include_all": True}]
        assert payload["event"]["severities"] == DEFAULT_ALERT_SEVERITIES
        assert payload["event"]["types"] == DEFAULT_ALERT_EVENT_TYPES

    def test_posts_to_correct_url(self) -> None:
        """The request targets the management-server alerts endpoint."""
        mock_response = MagicMock()
        mock_response.status_code = 201

        with patch("aiqum_initial_setup.requests.post", return_value=mock_response) as mock_post:
            create_alert(BASE_URL, "My Alert", "user@example.com", AUTH)

        call_args = mock_post.call_args
        assert call_args[0][0] == f"{BASE_URL}/api/management-server/alerts"
        assert call_args[1]["auth"] == AUTH
        assert call_args[1]["verify"] is False


# ---------------------------------------------------------------------------
# Tests: main() integration for Step 7
# ---------------------------------------------------------------------------
def _make_config(alert_email: str = "") -> dict:
    """Build a minimal config dict for main()."""
    return {
        "ip_address": "192.168.1.50",
        "aiqum_admin_password": "newpass",
        "aiqum_admin_user": "umadmin",
        "aiqum_admin_email": "admin@example.com",
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "aiqum",
        "smtp_password": "smtppass",
        "ontap_cluster_ip": "192.168.1.220",
        "ontap_admin_user": "admin",
        "ontap_admin_password": "ontappass",
        "aiqum_alert_email": alert_email,
    }


def _mock_requests_get_ok(status_code: int = 200) -> MagicMock:
    """Return a mock response for successful GET requests."""
    resp = MagicMock()
    resp.status_code = status_code
    return resp


def _mock_requests_post_ok(status_code: int = 201) -> MagicMock:
    """Return a mock response for successful POST requests."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {}
    resp.text = ""
    return resp


# ---------------------------------------------------------------------------
# Tests: send_test_email function
# ---------------------------------------------------------------------------
class TestSendTestEmail:
    """Tests for the ``send_test_email`` helper."""

    def test_returns_true_on_success(self) -> None:
        """Successful send returns True."""
        config = _make_config("alerts@test.com")
        with patch("aiqum_initial_setup.smtplib.SMTP") as mock_smtp:
            mock_srv = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_srv)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            result = send_test_email(config, "alerts@test.com")

        assert result is True
        mock_srv.starttls.assert_called_once()
        mock_srv.login.assert_called_once_with("aiqum", "smtppass")
        mock_srv.send_message.assert_called_once()

    def test_returns_false_on_smtp_error(self, capsys: pytest.CaptureFixture) -> None:
        """SMTP failure returns False and prints error."""
        config = _make_config("alerts@test.com")
        with patch("aiqum_initial_setup.smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__ = MagicMock(
                side_effect=smtplib.SMTPException("connection refused")
            )
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            result = send_test_email(config, "alerts@test.com")

        assert result is False
        assert "SMTP error" in capsys.readouterr().out

    def test_uses_correct_smtp_settings(self) -> None:
        """SMTP connection uses server and port from config."""
        config = _make_config("alerts@test.com")
        with patch("aiqum_initial_setup.smtplib.SMTP") as mock_smtp:
            mock_srv = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_srv)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            send_test_email(config, "alerts@test.com")

        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=30)


class TestMainAlertStep:
    """Tests for Step 7 (alert creation) within ``main()``."""

    @patch("aiqum_initial_setup.send_test_email", return_value=True)
    @patch("aiqum_initial_setup.create_alert", return_value=True)
    @patch("aiqum_initial_setup.load_config")
    @patch("aiqum_initial_setup.requests.post")
    @patch("aiqum_initial_setup.requests.get")
    @patch("aiqum_initial_setup.requests.put")
    def test_calls_create_alert_when_email_set(
        self,
        mock_put: MagicMock,
        mock_get: MagicMock,
        mock_post: MagicMock,
        mock_load_config: MagicMock,
        mock_create_alert: MagicMock,
        mock_send_test: MagicMock,
    ) -> None:
        """Step 7 calls create_alert when aiqum_alert_email is configured."""
        mock_load_config.return_value = _make_config("alerts@test.com")
        mock_get.return_value = _mock_requests_get_ok()
        mock_post.return_value = _mock_requests_post_ok()
        mock_put.return_value = _mock_requests_post_ok(200)

        result = aiqum_setup.main()

        assert result == 0
        mock_create_alert.assert_called_once_with(
            BASE_URL,
            "Alerts to alerts@test.com",
            "alerts@test.com",
            ("umadmin", "newpass"),
        )
        mock_send_test.assert_called_once()

    @patch("aiqum_initial_setup.create_alert")
    @patch("aiqum_initial_setup.load_config")
    @patch("aiqum_initial_setup.requests.post")
    @patch("aiqum_initial_setup.requests.get")
    @patch("aiqum_initial_setup.requests.put")
    def test_skips_alert_when_email_empty(
        self,
        mock_put: MagicMock,
        mock_get: MagicMock,
        mock_post: MagicMock,
        mock_load_config: MagicMock,
        mock_create_alert: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Step 7 skips alert creation when aiqum_alert_email is empty."""
        mock_load_config.return_value = _make_config("")
        mock_get.return_value = _mock_requests_get_ok()
        mock_post.return_value = _mock_requests_post_ok()
        mock_put.return_value = _mock_requests_post_ok(200)

        result = aiqum_setup.main()

        assert result == 0
        mock_create_alert.assert_not_called()
        assert "Skipping alert setup" in capsys.readouterr().out

    @patch("aiqum_initial_setup.create_alert")
    @patch("aiqum_initial_setup.load_config")
    @patch("aiqum_initial_setup.requests.post")
    @patch("aiqum_initial_setup.requests.get")
    @patch("aiqum_initial_setup.requests.put")
    def test_skips_alert_when_email_missing(
        self,
        mock_put: MagicMock,
        mock_get: MagicMock,
        mock_post: MagicMock,
        mock_load_config: MagicMock,
        mock_create_alert: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Step 7 skips alert creation when aiqum_alert_email key is absent."""
        config = _make_config()
        del config["aiqum_alert_email"]
        mock_load_config.return_value = config
        mock_get.return_value = _mock_requests_get_ok()
        mock_post.return_value = _mock_requests_post_ok()
        mock_put.return_value = _mock_requests_post_ok(200)

        result = aiqum_setup.main()

        assert result == 0
        mock_create_alert.assert_not_called()
        assert "Skipping alert setup" in capsys.readouterr().out

    @patch("aiqum_initial_setup.send_test_email")
    @patch("aiqum_initial_setup.create_alert", return_value=False)
    @patch("aiqum_initial_setup.load_config")
    @patch("aiqum_initial_setup.requests.post")
    @patch("aiqum_initial_setup.requests.get")
    @patch("aiqum_initial_setup.requests.put")
    def test_returns_zero_when_alert_fails(
        self,
        mock_put: MagicMock,
        mock_get: MagicMock,
        mock_post: MagicMock,
        mock_load_config: MagicMock,
        mock_create_alert: MagicMock,
        mock_send_test: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """main() returns 0 even when alert creation fails (non-fatal)."""
        mock_load_config.return_value = _make_config("alerts@test.com")
        mock_get.return_value = _mock_requests_get_ok()
        mock_post.return_value = _mock_requests_post_ok()
        mock_put.return_value = _mock_requests_post_ok(200)

        result = aiqum_setup.main()

        assert result == 0
        mock_create_alert.assert_called_once()
        mock_send_test.assert_not_called()
        assert "FAILED (non-fatal)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Tests: module-level constants
# ---------------------------------------------------------------------------
class TestAlertConstants:
    """Verify the alert constants are well-formed."""

    def test_severities_are_strings(self) -> None:
        assert all(isinstance(s, str) for s in DEFAULT_ALERT_SEVERITIES)
        assert len(DEFAULT_ALERT_SEVERITIES) == 3

    def test_event_types_are_strings(self) -> None:
        assert all(isinstance(t, str) for t in DEFAULT_ALERT_EVENT_TYPES)

    def test_event_types_count(self) -> None:
        """The curated list should have 62 event types (from prod)."""
        assert len(DEFAULT_ALERT_EVENT_TYPES) == 62
