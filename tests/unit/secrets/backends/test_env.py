"""Tests for environment variable secret backend."""

import pytest

from infrafoundry.secrets.backends.env import EnvSecretBackend, register
from infrafoundry.secrets.plugin_type import SecretBackendMetadata
from infrafoundry.secrets.protocol import SecretNotFoundError


class TestEnvSecretBackend:
    """Tests for EnvSecretBackend."""

    def test_init_with_prefix(self) -> None:
        """Test initialization with prefix."""
        backend = EnvSecretBackend({"prefix": "TEST_"})
        assert backend.prefix == "TEST_"

    def test_init_without_prefix(self) -> None:
        """Test initialization without prefix."""
        backend = EnvSecretBackend({})
        assert backend.prefix == ""

    def test_key_to_env_with_prefix(self) -> None:
        """Test key to env var conversion with prefix."""
        backend = EnvSecretBackend({"prefix": "APP_"})
        assert backend._key_to_env("db/password") == "APP_DB_PASSWORD"
        assert backend._key_to_env("proxmox/token") == "APP_PROXMOX_TOKEN"

    def test_key_to_env_without_prefix(self) -> None:
        """Test key to env var conversion without prefix."""
        backend = EnvSecretBackend({})
        assert backend._key_to_env("db/password") == "DB_PASSWORD"
        assert backend._key_to_env("api/token") == "API_TOKEN"

    def test_get_secret_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful secret retrieval."""
        monkeypatch.setenv("TEST_DB_PASSWORD", "secret123")
        backend = EnvSecretBackend({"prefix": "TEST_"})

        value = backend.get_secret("db/password")
        assert value == "secret123"

    def test_get_secret_not_found(self) -> None:
        """Test secret not found error."""
        backend = EnvSecretBackend({"prefix": "NONEXISTENT_"})

        with pytest.raises(SecretNotFoundError) as exc_info:
            backend.get_secret("missing/key")

        assert "missing/key" in str(exc_info.value)
        assert "NONEXISTENT_MISSING_KEY" in str(exc_info.value)

    def test_get_secret_without_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test secret retrieval without prefix."""
        monkeypatch.setenv("API_TOKEN", "token456")
        backend = EnvSecretBackend({})

        value = backend.get_secret("api/token")
        assert value == "token456"

    def test_list_secrets_with_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test listing secrets with prefix."""
        monkeypatch.setenv("APP_DB_HOST", "localhost")
        monkeypatch.setenv("APP_DB_PASSWORD", "secret")
        monkeypatch.setenv("APP_API_TOKEN", "token")
        monkeypatch.setenv("OTHER_KEY", "value")  # Should be filtered out

        backend = EnvSecretBackend({"prefix": "APP_"})
        secrets = backend.list_secrets()

        assert "db/host" in secrets
        assert "db/password" in secrets
        assert "api/token" in secrets
        assert "other/key" not in secrets

    def test_list_secrets_with_filter_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test listing secrets with filter prefix."""
        monkeypatch.setenv("APP_DB_HOST", "localhost")
        monkeypatch.setenv("APP_DB_PASSWORD", "secret")
        monkeypatch.setenv("APP_API_TOKEN", "token")

        backend = EnvSecretBackend({"prefix": "APP_"})
        secrets = backend.list_secrets("db/")

        assert "db/host" in secrets
        assert "db/password" in secrets
        assert "api/token" not in secrets

    def test_list_secrets_empty(self) -> None:
        """Test listing when no secrets match."""
        backend = EnvSecretBackend({"prefix": "NONEXISTENT_PREFIX_"})
        secrets = backend.list_secrets()

        assert secrets == []

    def test_health_check(self) -> None:
        """Test health check always returns True."""
        backend = EnvSecretBackend({})
        assert backend.health_check() is True


class TestEnvBackendRegistration:
    """Tests for env backend registration."""

    def test_register_returns_metadata(self) -> None:
        """Test register function returns correct metadata."""
        metadata = register()

        assert isinstance(metadata, SecretBackendMetadata)
        assert metadata.name == "env"
        assert metadata.version == "1.0.0"
        assert metadata.backend_class == EnvSecretBackend
        assert metadata.read_only is True

    def test_register_metadata_has_description(self) -> None:
        """Test metadata includes description."""
        metadata = register()
        assert len(metadata.description) > 0
        assert "environment" in metadata.description.lower()
