"""Tests for the AIQUM initial setup script.

The script ``blueprints/aiqum/scripts/aiqum-initial-setup.py`` is a standalone
Python file (not a package module), so we import it via ``importlib`` using
its filesystem path. Since #644 the script is stdlib-only -- the tests mock
the inline ``AIQUMClient`` (and, at a lower level, ``urllib.request.urlopen``)
instead of ``requests.*``.
"""

from __future__ import annotations

import ast
import base64
import importlib.util
import io
import json
import smtplib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

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
AIQUMClient = aiqum_setup.AIQUMClient
create_alert = aiqum_setup.create_alert
load_config = aiqum_setup.load_config
make_ssl_context = aiqum_setup.make_ssl_context
send_test_email = aiqum_setup.send_test_email
DEFAULT_ALERT_SEVERITIES = aiqum_setup.DEFAULT_ALERT_SEVERITIES
DEFAULT_ALERT_EVENT_TYPES = aiqum_setup.DEFAULT_ALERT_EVENT_TYPES


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------
BASE_URL = "https://192.168.1.50"


def _make_client() -> AIQUMClient:
    """Build a real AIQUMClient instance for unit tests that mock urlopen."""
    return AIQUMClient(BASE_URL, "umadmin", "secret", make_ssl_context())


def _mock_urlopen_response(status: int = 200, body: bytes = b"") -> MagicMock:
    """Build a context-manager mock that mimics urlopen's return value."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=resp)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


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


def _http_error(code: int, body: bytes = b"") -> HTTPError:
    """Build an HTTPError whose .read() returns ``body``."""
    err = HTTPError(
        url=BASE_URL + "/x",
        code=code,
        msg="err",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(body),
    )
    return err


# ---------------------------------------------------------------------------
# Tests: AIQUMClient
# ---------------------------------------------------------------------------
class TestAIQUMClient:
    """Tests for the inline stdlib HTTP client."""

    def test_basic_auth_header_encoded_correctly(self) -> None:
        """Constructor encodes ``user:password`` as Basic auth."""
        client = AIQUMClient(BASE_URL, "bob", "hunter2", make_ssl_context())
        header = client._auth_header
        assert header.startswith("Basic ")
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("ascii")
        assert decoded == "bob:hunter2"

    def test_set_auth_re_encodes_header(self) -> None:
        """set_auth replaces the Authorization header with new credentials."""
        client = AIQUMClient(BASE_URL, "bob", "old", make_ssl_context())
        client.set_auth("bob", "new")
        decoded = base64.b64decode(client._auth_header.split(" ", 1)[1]).decode("ascii")
        assert decoded == "bob:new"

    def test_get_with_params_builds_query_string(self) -> None:
        """GET with params appends ``?key=value`` to the URL."""
        client = _make_client()
        mock_urlopen = MagicMock(return_value=_mock_urlopen_response(200, b"{}"))
        with patch("aiqum_initial_setup.urlopen", mock_urlopen):
            code, body = client.get(
                "/api/management-server/admin/options",
                params={"option": "autosupport.enabled"},
            )

        req = mock_urlopen.call_args.args[0]
        assert code == 200
        assert body == {}
        assert "?option=autosupport.enabled" in req.full_url
        assert req.get_method() == "GET"

    def test_post_serializes_json_body(self) -> None:
        """POST serializes the body to JSON bytes and sets Content-Type."""
        client = _make_client()
        mock_urlopen = MagicMock(return_value=_mock_urlopen_response(201, b'{"ok":true}'))
        with patch("aiqum_initial_setup.urlopen", mock_urlopen):
            code, body = client.post("/api/foo", body={"x": 1})

        req = mock_urlopen.call_args.args[0]
        assert code == 201
        assert body == {"ok": True}
        assert req.data == json.dumps({"x": 1}).encode("utf-8")
        assert req.get_header("Content-type") == "application/json"
        assert req.get_method() == "POST"

    def test_put_uses_put_method_and_custom_content_type(self) -> None:
        """PUT with a custom content type forwards the header."""
        client = _make_client()
        mock_urlopen = MagicMock(return_value=_mock_urlopen_response(204, b""))
        with patch("aiqum_initial_setup.urlopen", mock_urlopen):
            code, body = client.put("/api/foo", body={"k": "v"}, content_type=aiqum_setup.HAL_JSON)

        req = mock_urlopen.call_args.args[0]
        assert code == 204
        assert body == {}
        assert req.get_method() == "PUT"
        assert req.get_header("Content-type") == aiqum_setup.HAL_JSON

    def test_swallows_http_error_returns_status_and_body(self) -> None:
        """HTTPError is captured; code and parsed body are returned."""
        client = _make_client()
        with patch(
            "aiqum_initial_setup.urlopen",
            side_effect=_http_error(401, b'{"error":"nope"}'),
        ):
            code, body = client.get("/api/management-server/admin/options")

        assert code == 401
        assert body == {"error": "nope"}

    def test_non_json_error_body_returned_as_raw(self) -> None:
        """Non-JSON error bodies are returned under ``_raw`` instead of crashing."""
        client = _make_client()
        with patch(
            "aiqum_initial_setup.urlopen",
            side_effect=_http_error(500, b"oops not json"),
        ):
            code, body = client.get("/api/foo")

        assert code == 500
        assert body == {"_raw": "oops not json"}

    def test_empty_response_body_returns_empty_dict(self) -> None:
        """A 204 with no body returns ``(204, {})``."""
        client = _make_client()

        with patch(
            "aiqum_initial_setup.urlopen",
            return_value=_mock_urlopen_response(204, b""),
        ):
            code, body = client.post("/api/foo", body={"x": 1})

        assert code == 204
        assert body == {}

    def test_authorization_header_sent_on_request(self) -> None:
        """Every request carries the Basic auth header."""
        client = _make_client()
        mock_urlopen = MagicMock(return_value=_mock_urlopen_response(200, b"{}"))
        with patch("aiqum_initial_setup.urlopen", mock_urlopen):
            client.get("/api/foo")

        req = mock_urlopen.call_args.args[0]
        auth = req.get_header("Authorization")
        assert auth is not None
        assert auth.startswith("Basic ")


# ---------------------------------------------------------------------------
# Tests: load_config
# ---------------------------------------------------------------------------
class TestLoadConfig:
    """Tests for the env-var-driven config loader."""

    def test_returns_parsed_json_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """INFRAFOUNDRY_PACKAGE_VARS set to JSON returns the parsed dict."""
        monkeypatch.setenv("INFRAFOUNDRY_PACKAGE_VARS", '{"foo": 1, "bar": "baz"}')
        result = load_config()
        assert result == {"foo": 1, "bar": "baz"}

    def test_raises_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing INFRAFOUNDRY_PACKAGE_VARS raises RuntimeError."""
        monkeypatch.delenv("INFRAFOUNDRY_PACKAGE_VARS", raising=False)
        with pytest.raises(RuntimeError, match="INFRAFOUNDRY_PACKAGE_VARS"):
            load_config()

    def test_raises_when_env_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty INFRAFOUNDRY_PACKAGE_VARS raises RuntimeError."""
        monkeypatch.setenv("INFRAFOUNDRY_PACKAGE_VARS", "")
        with pytest.raises(RuntimeError, match="foundry infra apply"):
            load_config()


# ---------------------------------------------------------------------------
# Tests: create_alert function
# ---------------------------------------------------------------------------
class TestCreateAlert:
    """Tests for the ``create_alert`` helper."""

    def test_returns_true_on_201(self) -> None:
        """Successful creation (201) returns True."""
        client = MagicMock()
        client.post.return_value = (201, {})
        assert create_alert(client, "My Alert", "user@example.com") is True
        client.post.assert_called_once()

    def test_returns_true_on_200(self) -> None:
        """Some API versions return 200; should also succeed."""
        client = MagicMock()
        client.post.return_value = (200, {})
        assert create_alert(client, "My Alert", "user@example.com") is True

    def test_returns_true_on_409_already_exists(self, capsys: pytest.CaptureFixture) -> None:
        """409 means the alert already exists -- treated as success."""
        client = MagicMock()
        client.post.return_value = (409, {})
        assert create_alert(client, "My Alert", "user@example.com") is True
        assert "already exists" in capsys.readouterr().out

    def test_returns_false_on_error(self, capsys: pytest.CaptureFixture) -> None:
        """Non-success status codes return False and print a message."""
        client = MagicMock()
        client.post.return_value = (500, {})
        assert create_alert(client, "My Alert", "user@example.com") is False
        assert "Failed to create alert: 500" in capsys.readouterr().out

    def test_payload_structure(self) -> None:
        """The POST payload matches the expected AIQUM alert API structure."""
        client = MagicMock()
        client.post.return_value = (201, {})

        create_alert(client, "Alerts to me@test.com", "me@test.com")

        args, kwargs = client.post.call_args
        # body is passed as a keyword arg in the rewrite
        payload = kwargs.get("body") if "body" in kwargs else args[1]

        assert payload["name"] == "Alerts to me@test.com"
        assert payload["enabled"] is True
        assert payload["action"]["notification"]["emails"] == ["me@test.com"]
        assert payload["action"]["notification"]["send_snmp_trap"] is False
        assert payload["resource"] == [{"type": "cluster", "include_all": True}]
        assert payload["event"]["severities"] == DEFAULT_ALERT_SEVERITIES
        assert payload["event"]["types"] == DEFAULT_ALERT_EVENT_TYPES

    def test_posts_to_correct_url(self) -> None:
        """The request targets the management-server alerts endpoint."""
        client = MagicMock()
        client.post.return_value = (201, {})

        create_alert(client, "My Alert", "user@example.com")

        args, _ = client.post.call_args
        assert args[0] == "/api/management-server/alerts"


# ---------------------------------------------------------------------------
# Tests: send_test_email function
# ---------------------------------------------------------------------------
class TestSendTestEmail:
    """Tests for the ``send_test_email`` helper (unchanged by #644)."""

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


# ---------------------------------------------------------------------------
# Tests: main() integration for Step 7
# ---------------------------------------------------------------------------
def _make_mock_client(
    get_return: tuple = (200, {}),
    post_return: tuple = (201, {}),
    put_return: tuple = (200, {}),
) -> MagicMock:
    """Build a MagicMock that satisfies the AIQUMClient surface used by main()."""
    client = MagicMock()
    client.get.return_value = get_return
    client.post.return_value = post_return
    client.put.return_value = put_return
    return client


class TestMainAlertStep:
    """Tests for Step 7 (alert creation) within ``main()``."""

    @patch("aiqum_initial_setup.send_test_email", return_value=True)
    @patch("aiqum_initial_setup.create_alert", return_value=True)
    @patch("aiqum_initial_setup.load_config")
    @patch("aiqum_initial_setup.AIQUMClient")
    def test_calls_create_alert_when_email_set(
        self,
        mock_client_cls: MagicMock,
        mock_load_config: MagicMock,
        mock_create_alert: MagicMock,
        mock_send_test: MagicMock,
    ) -> None:
        """Step 7 calls create_alert when aiqum_alert_email is configured."""
        mock_load_config.return_value = _make_config("alerts@test.com")
        mock_client_cls.return_value = _make_mock_client()

        result = aiqum_setup.main()

        assert result == 0
        mock_create_alert.assert_called_once()
        args, _ = mock_create_alert.call_args
        # create_alert(client, name, email)
        assert args[1] == "Alerts to alerts@test.com"
        assert args[2] == "alerts@test.com"
        mock_send_test.assert_called_once()

    @patch("aiqum_initial_setup.create_alert")
    @patch("aiqum_initial_setup.load_config")
    @patch("aiqum_initial_setup.AIQUMClient")
    def test_skips_alert_when_email_empty(
        self,
        mock_client_cls: MagicMock,
        mock_load_config: MagicMock,
        mock_create_alert: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Step 7 skips alert creation when aiqum_alert_email is empty."""
        mock_load_config.return_value = _make_config("")
        mock_client_cls.return_value = _make_mock_client()

        result = aiqum_setup.main()

        assert result == 0
        mock_create_alert.assert_not_called()
        assert "Skipping alert setup" in capsys.readouterr().out

    @patch("aiqum_initial_setup.create_alert")
    @patch("aiqum_initial_setup.load_config")
    @patch("aiqum_initial_setup.AIQUMClient")
    def test_skips_alert_when_email_missing(
        self,
        mock_client_cls: MagicMock,
        mock_load_config: MagicMock,
        mock_create_alert: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Step 7 skips alert creation when aiqum_alert_email key is absent."""
        config = _make_config()
        del config["aiqum_alert_email"]
        mock_load_config.return_value = config
        mock_client_cls.return_value = _make_mock_client()

        result = aiqum_setup.main()

        assert result == 0
        mock_create_alert.assert_not_called()
        assert "Skipping alert setup" in capsys.readouterr().out

    @patch("aiqum_initial_setup.send_test_email")
    @patch("aiqum_initial_setup.create_alert", return_value=False)
    @patch("aiqum_initial_setup.load_config")
    @patch("aiqum_initial_setup.AIQUMClient")
    def test_returns_zero_when_alert_fails(
        self,
        mock_client_cls: MagicMock,
        mock_load_config: MagicMock,
        mock_create_alert: MagicMock,
        mock_send_test: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """main() returns 0 even when alert creation fails (non-fatal)."""
        mock_load_config.return_value = _make_config("alerts@test.com")
        mock_client_cls.return_value = _make_mock_client()

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


# ---------------------------------------------------------------------------
# Sanity: script imports only stdlib modules (catches regressions)
# ---------------------------------------------------------------------------
class TestStdlibOnly:
    """Guardrail that blocks regressions to third-party imports."""

    def test_only_stdlib_imports(self) -> None:
        """Every import in the script must be a stdlib module (per #644)."""
        tree = ast.parse(SCRIPT_PATH.read_text())
        stdlib = set(sys.stdlib_module_names)
        offenders: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root not in stdlib:
                        offenders.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                root = node.module.split(".", 1)[0]
                if root not in stdlib:
                    offenders.append(node.module)
        assert offenders == [], f"Non-stdlib imports found: {offenders}"
