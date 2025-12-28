"""Tests for secret resolver."""

from pathlib import Path

import pytest

from infrafoundry.secrets.backends.env import EnvSecretBackend
from infrafoundry.secrets.backends.file import FileSecretBackend
from infrafoundry.secrets.resolver import (
    SECRET_URI_PATTERN,
    SecretResolutionError,
    SecretResolver,
    _reset_resolver,
    get_resolver,
)


class TestSecretURIPattern:
    """Tests for secret URI pattern matching."""

    def test_valid_uri(self) -> None:
        """Test valid secret URIs."""
        assert SECRET_URI_PATTERN.match("secret://env/db/password")
        assert SECRET_URI_PATTERN.match("secret://file/api/token")
        assert SECRET_URI_PATTERN.match("secret://vault/secret/key")

    def test_invalid_uri(self) -> None:
        """Test invalid URIs."""
        assert not SECRET_URI_PATTERN.match("not-a-secret")
        assert not SECRET_URI_PATTERN.match("secret://")
        assert not SECRET_URI_PATTERN.match("secret://backend")
        assert not SECRET_URI_PATTERN.match("http://example.com")


class TestSecretResolver:
    """Tests for SecretResolver."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        """Reset global resolver and registry before each test."""
        from infrafoundry.core.plugin_system.registry import _reset_registry

        _reset_resolver()
        _reset_registry()

    def test_init(self) -> None:
        """Test resolver initialization."""
        resolver = SecretResolver()
        assert resolver._backends == {}
        assert resolver._backend_configs == {}

    def test_configure_backend(self) -> None:
        """Test backend configuration."""
        resolver = SecretResolver()
        resolver.configure_backend("env", {"prefix": "TEST_"})

        assert "env" in resolver._backend_configs
        assert resolver._backend_configs["env"]["prefix"] == "TEST_"

    def test_configure_backend_clears_cached_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test reconfiguring backend clears cached instance."""
        # Mock the registry to return our backend
        from infrafoundry.core.plugin_system import get_registry
        from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

        registry = get_registry()
        registry.register(
            PluginMetadata(
                name="env",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretBackend,
            )
        )

        monkeypatch.setenv("TEST_KEY", "value1")

        resolver = SecretResolver()
        resolver.configure_backend("env", {"prefix": "TEST_"})

        # Load backend (gets cached)
        _ = resolver._get_backend("env")
        assert "env" in resolver._backends

        # Reconfigure
        resolver.configure_backend("env", {"prefix": "NEW_"})

        # Should have cleared cache
        assert "env" not in resolver._backends

    def test_is_secret_uri(self) -> None:
        """Test secret URI detection."""
        resolver = SecretResolver()

        assert resolver.is_secret_uri("secret://env/key") is True
        assert resolver.is_secret_uri("secret://file/db/password") is True
        assert resolver.is_secret_uri("plain-value") is False
        assert resolver.is_secret_uri(123) is False  # type: ignore[arg-type]
        assert resolver.is_secret_uri(None) is False  # type: ignore[arg-type]

    def test_parse_secret_uri_valid(self) -> None:
        """Test parsing valid secret URIs."""
        resolver = SecretResolver()

        backend, key = resolver.parse_secret_uri("secret://env/db/password")
        assert backend == "env"
        assert key == "db/password"

        backend, key = resolver.parse_secret_uri("secret://file/api/token")
        assert backend == "file"
        assert key == "api/token"

    def test_parse_secret_uri_invalid(self) -> None:
        """Test parsing invalid URIs."""
        resolver = SecretResolver()

        with pytest.raises(SecretResolutionError) as exc_info:
            resolver.parse_secret_uri("not-a-secret")

        assert "Invalid secret URI format" in str(exc_info.value)

    def test_get_backend_not_configured(self) -> None:
        """Test error when backend not configured."""
        resolver = SecretResolver()

        with pytest.raises(SecretResolutionError) as exc_info:
            resolver._get_backend("env")

        assert "not configured" in str(exc_info.value)

    def test_get_backend_loads_and_caches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test backend loading and caching."""
        # Mock the registry
        from infrafoundry.core.plugin_system import get_registry
        from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

        registry = get_registry()
        registry.register(
            PluginMetadata(
                name="env",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretBackend,
            )
        )

        resolver = SecretResolver()
        resolver.configure_backend("env", {"prefix": "TEST_"})

        # First call should load
        backend1 = resolver._get_backend("env")
        assert isinstance(backend1, EnvSecretBackend)
        assert "env" in resolver._backends

        # Second call should return cached
        backend2 = resolver._get_backend("env")
        assert backend2 is backend1

    def test_resolve_env_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test resolving secret from env backend."""
        # Mock the registry
        from infrafoundry.core.plugin_system import get_registry
        from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

        registry = get_registry()
        registry.register(
            PluginMetadata(
                name="env",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretBackend,
            )
        )

        monkeypatch.setenv("TEST_DB_PASSWORD", "secret123")

        resolver = SecretResolver()
        resolver.configure_backend("env", {"prefix": "TEST_"})

        value = resolver.resolve("secret://env/db/password")
        assert value == "secret123"

    def test_resolve_file_backend(self, tmp_path: Path) -> None:
        """Test resolving secret from file backend."""
        # Mock the registry
        from infrafoundry.core.plugin_system import get_registry
        from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

        registry = get_registry()
        registry.register(
            PluginMetadata(
                name="file",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=FileSecretBackend,
            )
        )

        secret_file = tmp_path / "token"
        secret_file.write_text("my-token\n")

        resolver = SecretResolver()
        resolver.configure_backend("file", {"base_path": str(tmp_path)})

        value = resolver.resolve("secret://file/token")
        assert value == "my-token"

    def test_resolve_backend_error(self) -> None:
        """Test error when backend fails."""
        # Mock the registry
        from infrafoundry.core.plugin_system import get_registry
        from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

        registry = get_registry()
        registry.register(
            PluginMetadata(
                name="env",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretBackend,
            )
        )

        resolver = SecretResolver()
        resolver.configure_backend("env", {"prefix": "TEST_"})

        with pytest.raises(SecretResolutionError):
            resolver.resolve("secret://env/nonexistent/key")

    def test_resolve_config_simple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test resolving config with simple values."""
        # Mock the registry
        from infrafoundry.core.plugin_system import get_registry
        from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

        registry = get_registry()
        registry.register(
            PluginMetadata(
                name="env",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretBackend,
            )
        )

        monkeypatch.setenv("TEST_TOKEN", "token123")

        resolver = SecretResolver()
        resolver.configure_backend("env", {"prefix": "TEST_"})

        config = {
            "api_url": "https://example.com",
            "api_token": "secret://env/token",
        }

        resolved = resolver.resolve_config(config)

        assert resolved["api_url"] == "https://example.com"
        assert resolved["api_token"] == "token123"

    def test_resolve_config_nested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test resolving config with nested dicts."""
        # Mock the registry
        from infrafoundry.core.plugin_system import get_registry
        from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

        registry = get_registry()
        registry.register(
            PluginMetadata(
                name="env",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretBackend,
            )
        )

        monkeypatch.setenv("TEST_DB_PASSWORD", "dbpass")
        monkeypatch.setenv("TEST_API_TOKEN", "apitoken")

        resolver = SecretResolver()
        resolver.configure_backend("env", {"prefix": "TEST_"})

        config = {
            "database": {
                "host": "localhost",
                "password": "secret://env/db/password",
            },
            "api": {"token": "secret://env/api/token"},
        }

        resolved = resolver.resolve_config(config)

        assert resolved["database"]["host"] == "localhost"
        assert resolved["database"]["password"] == "dbpass"
        assert resolved["api"]["token"] == "apitoken"

    def test_resolve_config_with_lists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test resolving config with lists."""
        # Mock the registry
        from infrafoundry.core.plugin_system import get_registry
        from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

        registry = get_registry()
        registry.register(
            PluginMetadata(
                name="env",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretBackend,
            )
        )

        monkeypatch.setenv("TEST_TOKEN1", "token1")
        monkeypatch.setenv("TEST_TOKEN2", "token2")

        resolver = SecretResolver()
        resolver.configure_backend("env", {"prefix": "TEST_"})

        config = {
            "tokens": ["secret://env/token1", "secret://env/token2"],
        }

        resolved = resolver.resolve_config(config)

        assert resolved["tokens"] == ["token1", "token2"]

    def test_close(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test closing resolver cleans up backends."""
        # Mock the registry
        from infrafoundry.core.plugin_system import get_registry
        from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

        registry = get_registry()
        registry.register(
            PluginMetadata(
                name="env",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretBackend,
            )
        )

        monkeypatch.setenv("TEST_KEY", "value")

        resolver = SecretResolver()
        resolver.configure_backend("env", {"prefix": "TEST_"})

        # Load backend
        resolver._get_backend("env")
        assert "env" in resolver._backends

        # Close
        resolver.close()
        assert resolver._backends == {}

    def test_context_manager(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test resolver as context manager."""
        # Mock the registry
        from infrafoundry.core.plugin_system import get_registry
        from infrafoundry.core.plugin_system.plugin_type import PluginMetadata

        registry = get_registry()
        registry.register(
            PluginMetadata(
                name="env",
                version="1.0.0",
                plugin_type="secret_backend",
                description="Test",
                implementation=EnvSecretBackend,
            )
        )

        monkeypatch.setenv("TEST_KEY", "value")

        with SecretResolver() as resolver:
            resolver.configure_backend("env", {"prefix": "TEST_"})
            value = resolver.resolve("secret://env/key")
            assert value == "value"
            assert "env" in resolver._backends

        # Should be closed after context
        assert resolver._backends == {}


class TestGlobalResolver:
    """Tests for global resolver instance."""

    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        """Reset global resolver before each test."""
        _reset_resolver()

    def test_get_resolver_singleton(self) -> None:
        """Test get_resolver returns singleton."""
        resolver1 = get_resolver()
        resolver2 = get_resolver()

        assert resolver1 is resolver2

    def test_reset_resolver(self) -> None:
        """Test reset clears global instance."""
        resolver1 = get_resolver()
        _reset_resolver()
        resolver2 = get_resolver()

        assert resolver1 is not resolver2
