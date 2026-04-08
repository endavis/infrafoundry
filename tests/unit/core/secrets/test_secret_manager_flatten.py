"""Tests for SecretManager.flatten / populate_environment_config.

Phase 1 of issue #212 — secrets→TF_VAR_* bridge. These tests cover the
two new entry points used by the framework to make decrypted secrets
available to provider terraform invocations:

1. ``SecretManager.flatten_dict`` (static helper) and ``flatten`` (instance
   method): converts a nested decrypted secrets tree to a flat dict of
   dotted keys → string values.
2. ``SecretManager.populate_environment_config``: reads the env's encrypted
   ``secrets.yaml`` (if present), decrypts it, and assigns the plaintext
   dict to ``EnvironmentConfig.secrets``. Defensive — missing file is OK.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.secrets.provider import SecretProvider
from infrafoundry.core.secrets.secret_manager import (
    DEFAULT_SECRETS_FILENAME,
    SecretManager,
)


@pytest.fixture
def temp_secrets_dir():
    """Yield an empty temporary directory used as the env secrets root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_provider():
    """Return a MagicMock SecretProvider with no default behavior."""
    return MagicMock(spec=SecretProvider)


def make_manager(secrets_dir: Path, provider: SecretProvider) -> SecretManager:
    """Build a SecretManager bound to ``secrets_dir`` with ``provider`` injected."""
    return SecretManager(env_name="test", secrets_dir=secrets_dir, provider=provider)


# ---------------------------------------------------------------------------
# flatten_dict
# ---------------------------------------------------------------------------


class TestFlattenDict:
    """Static ``SecretManager.flatten_dict`` covers all leaf-shape edge cases."""

    def test_none_returns_empty(self):
        assert SecretManager.flatten_dict(None) == {}

    def test_empty_dict_returns_empty(self):
        assert SecretManager.flatten_dict({}) == {}

    def test_flat_string_values(self):
        data = {"a": "1", "b": "2"}
        assert SecretManager.flatten_dict(data) == {"a": "1", "b": "2"}

    def test_nested_dict_uses_dot_separator(self):
        data = {"tailscale": {"oauth_client_secret": "abc"}}
        assert SecretManager.flatten_dict(data) == {"tailscale.oauth_client_secret": "abc"}

    def test_deeply_nested(self):
        data = {"a": {"b": {"c": {"d": "x"}}}}
        assert SecretManager.flatten_dict(data) == {"a.b.c.d": "x"}

    def test_multiple_nested_keys(self):
        data = {
            "tailscale": {
                "oauth_client_id": "id",
                "oauth_client_secret": "secret",
                "auth_key": "tskey-abc",
            },
            "proxmox": {"api_token": "ptok"},
        }
        result = SecretManager.flatten_dict(data)
        assert result == {
            "tailscale.oauth_client_id": "id",
            "tailscale.oauth_client_secret": "secret",
            "tailscale.auth_key": "tskey-abc",
            "proxmox.api_token": "ptok",
        }

    def test_skips_none_leaves(self):
        data = {"a": None, "b": "x"}
        assert SecretManager.flatten_dict(data) == {"b": "x"}

    def test_skips_empty_nested_dicts(self):
        data = {"a": {}, "b": "x"}
        assert SecretManager.flatten_dict(data) == {"b": "x"}

    def test_int_leaf_stringified(self):
        data = {"port": 22}
        assert SecretManager.flatten_dict(data) == {"port": "22"}

    def test_bool_leaf_stringified(self):
        data = {"enabled": True}
        assert SecretManager.flatten_dict(data) == {"enabled": "True"}

    def test_list_leaf_jsonified(self):
        data = {"tags": ["a", "b"]}
        assert SecretManager.flatten_dict(data) == {"tags": json.dumps(["a", "b"])}

    def test_does_not_mutate_input(self):
        data = {"a": {"b": "x"}}
        snapshot = {"a": {"b": "x"}}
        SecretManager.flatten_dict(data)
        assert data == snapshot


# ---------------------------------------------------------------------------
# flatten (instance method)
# ---------------------------------------------------------------------------


class TestFlattenInstanceMethod:
    """``SecretManager.flatten`` reads the default secrets file and flattens it."""

    def test_returns_empty_when_no_file(self, temp_secrets_dir, mock_provider):
        manager = make_manager(temp_secrets_dir, mock_provider)
        assert manager.flatten() == {}
        # Provider was never called because the file doesn't exist.
        mock_provider.load_secret.assert_not_called()

    def test_returns_flat_dict_when_file_exists(self, temp_secrets_dir, mock_provider):
        # Touch the file so .exists() is True; provider mock supplies the data.
        secrets_file = temp_secrets_dir / DEFAULT_SECRETS_FILENAME
        secrets_file.write_text("# placeholder")
        mock_provider.load_secret.return_value = {"tailscale": {"oauth_client_secret": "abc"}}

        manager = make_manager(temp_secrets_dir, mock_provider)
        result = manager.flatten()

        assert result == {"tailscale.oauth_client_secret": "abc"}
        mock_provider.load_secret.assert_called_once_with(secrets_file)


# ---------------------------------------------------------------------------
# populate_environment_config
# ---------------------------------------------------------------------------


class TestPopulateEnvironmentConfig:
    """``populate_environment_config`` mutates the env config in place."""

    def test_no_file_leaves_secrets_none(self, temp_secrets_dir, mock_provider):
        manager = make_manager(temp_secrets_dir, mock_provider)
        env_config = EnvironmentConfig(name="test")

        manager.populate_environment_config(env_config)

        assert env_config.secrets is None
        mock_provider.load_secret.assert_not_called()

    def test_decrypted_secrets_assigned(self, temp_secrets_dir, mock_provider):
        secrets_file = temp_secrets_dir / DEFAULT_SECRETS_FILENAME
        secrets_file.write_text("# placeholder")
        mock_provider.load_secret.return_value = {
            "tailscale": {
                "oauth_client_id": "id",
                "oauth_client_secret": "secret",
            }
        }

        manager = make_manager(temp_secrets_dir, mock_provider)
        env_config = EnvironmentConfig(name="test")
        manager.populate_environment_config(env_config)

        assert env_config.secrets == {
            "tailscale": {
                "oauth_client_id": "id",
                "oauth_client_secret": "secret",
            }
        }

    def test_decryption_failure_propagates(self, temp_secrets_dir, mock_provider):
        secrets_file = temp_secrets_dir / DEFAULT_SECRETS_FILENAME
        secrets_file.write_text("# placeholder")
        mock_provider.load_secret.side_effect = RuntimeError("sops boom")

        manager = make_manager(temp_secrets_dir, mock_provider)
        env_config = EnvironmentConfig(name="test")

        with pytest.raises(RuntimeError, match="sops boom"):
            manager.populate_environment_config(env_config)
