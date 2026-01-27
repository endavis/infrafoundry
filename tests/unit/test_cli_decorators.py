"""Unit tests for CLI decorators."""

import os
from unittest.mock import patch

from infrafoundry.cli.decorators import _get_error_hint, _is_debug_mode


class TestIsDebugMode:
    """Tests for _is_debug_mode function."""

    def test_returns_true_when_debug_env_set(self):
        """Test returns True when INFRAFOUNDRY_LOG_LEVEL is DEBUG."""
        with patch.dict(os.environ, {"INFRAFOUNDRY_LOG_LEVEL": "DEBUG"}):
            assert _is_debug_mode() is True

    def test_returns_false_when_debug_env_not_set(self):
        """Test returns False when INFRAFOUNDRY_LOG_LEVEL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure the variable is not set
            os.environ.pop("INFRAFOUNDRY_LOG_LEVEL", None)
            assert _is_debug_mode() is False

    def test_returns_false_when_debug_env_is_other_value(self):
        """Test returns False when INFRAFOUNDRY_LOG_LEVEL is not DEBUG."""
        with patch.dict(os.environ, {"INFRAFOUNDRY_LOG_LEVEL": "INFO"}):
            assert _is_debug_mode() is False


class TestGetErrorHint:
    """Tests for _get_error_hint function."""

    def test_file_not_found_with_generated_path(self):
        """Test hint for FileNotFoundError with generated directory."""
        exc = FileNotFoundError("No such file: generated/env/terraform/provider")
        hint = _get_error_hint(exc)
        assert hint is not None
        assert "project root" in hint

    def test_file_not_found_with_terraform_path(self):
        """Test hint for FileNotFoundError with terraform path."""
        exc = FileNotFoundError("terraform directory not found")
        hint = _get_error_hint(exc)
        assert hint is not None
        assert "project root" in hint

    def test_file_not_found_with_kubeconfig(self):
        """Test hint for FileNotFoundError with kubeconfig."""
        exc = FileNotFoundError("kubeconfig file missing")
        hint = _get_error_hint(exc)
        assert hint is not None
        assert "kubeconfig" in hint

    def test_file_not_found_generic(self):
        """Test hint for generic FileNotFoundError."""
        exc = FileNotFoundError("some_file.txt not found")
        hint = _get_error_hint(exc)
        assert hint is not None
        assert "file path" in hint or "file exists" in hint

    def test_permission_error(self):
        """Test hint for PermissionError."""
        exc = PermissionError("Permission denied")
        hint = _get_error_hint(exc)
        assert hint is not None
        assert "permission" in hint.lower()

    def test_connection_error(self):
        """Test hint for connection-related errors."""
        exc = ConnectionError("Connection refused")
        hint = _get_error_hint(exc)
        assert hint is not None
        assert "network" in hint.lower() or "connection" in hint.lower()

    def test_timeout_error(self):
        """Test hint for timeout errors."""
        exc = Exception("Operation timeout exceeded")
        hint = _get_error_hint(exc)
        assert hint is not None
        assert "timeout" in hint.lower()

    def test_authentication_error(self):
        """Test hint for authentication errors."""
        exc = Exception("Authentication failed")
        hint = _get_error_hint(exc)
        assert hint is not None
        assert "credential" in hint.lower() or "authentication" in hint.lower()

    def test_unauthorized_error(self):
        """Test hint for unauthorized errors."""
        exc = Exception("Unauthorized access")
        hint = _get_error_hint(exc)
        assert hint is not None
        assert "credential" in hint.lower() or "authentication" in hint.lower()

    def test_no_hint_for_generic_error(self):
        """Test no hint for errors without known patterns."""
        exc = Exception("Some random error")
        hint = _get_error_hint(exc)
        assert hint is None

    def test_no_hint_for_value_error(self):
        """Test no hint for ValueError."""
        exc = ValueError("Invalid value")
        hint = _get_error_hint(exc)
        assert hint is None
