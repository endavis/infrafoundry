"""Tests for file-based secret backend."""

from pathlib import Path

import pytest

from infrafoundry.secrets.backends.file import FileSecretBackend, register
from infrafoundry.secrets.plugin_type import SecretBackendMetadata
from infrafoundry.secrets.protocol import SecretBackendError, SecretNotFoundError


class TestFileSecretBackend:
    """Tests for FileSecretBackend."""

    def test_init_with_valid_path(self, tmp_path: Path) -> None:
        """Test initialization with valid base path."""
        backend = FileSecretBackend({"base_path": str(tmp_path)})
        assert backend.base_path == tmp_path

    def test_init_without_base_path(self) -> None:
        """Test initialization without base_path raises error."""
        with pytest.raises(SecretBackendError) as exc_info:
            FileSecretBackend({})

        assert "base_path" in str(exc_info.value)

    def test_init_with_file_not_directory(self, tmp_path: Path) -> None:
        """Test initialization with file path instead of directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")

        with pytest.raises(SecretBackendError) as exc_info:
            FileSecretBackend({"base_path": str(file_path)})

        assert "not a directory" in str(exc_info.value)

    def test_init_with_nonexistent_path(self, tmp_path: Path) -> None:
        """Test initialization with non-existent path (should warn but not fail)."""
        nonexistent = tmp_path / "nonexistent"
        backend = FileSecretBackend({"base_path": str(nonexistent)})
        assert backend.base_path == nonexistent

    def test_get_secret_path_normal(self, tmp_path: Path) -> None:
        """Test normal secret path resolution."""
        backend = FileSecretBackend({"base_path": str(tmp_path)})
        path = backend._get_secret_path("db/password")
        assert path == tmp_path / "db/password"

    def test_get_secret_path_prevents_traversal_dotdot(self, tmp_path: Path) -> None:
        """Test path traversal prevention with .."""
        backend = FileSecretBackend({"base_path": str(tmp_path)})

        with pytest.raises(SecretBackendError) as exc_info:
            backend._get_secret_path("../etc/passwd")

        assert "path traversal" in str(exc_info.value).lower()

    def test_get_secret_path_prevents_absolute(self, tmp_path: Path) -> None:
        """Test prevention of absolute paths."""
        backend = FileSecretBackend({"base_path": str(tmp_path)})

        with pytest.raises(SecretBackendError) as exc_info:
            backend._get_secret_path("/etc/passwd")

        assert "path traversal" in str(exc_info.value).lower()

    def test_get_secret_success(self, tmp_path: Path) -> None:
        """Test successful secret retrieval."""
        secret_file = tmp_path / "db" / "password"
        secret_file.parent.mkdir()
        secret_file.write_text("my-secret-password\n")

        backend = FileSecretBackend({"base_path": str(tmp_path)})
        value = backend.get_secret("db/password")

        # Should strip trailing whitespace
        assert value == "my-secret-password"

    def test_get_secret_not_found(self, tmp_path: Path) -> None:
        """Test secret not found error."""
        backend = FileSecretBackend({"base_path": str(tmp_path)})

        with pytest.raises(SecretNotFoundError) as exc_info:
            backend.get_secret("nonexistent/secret")

        assert "nonexistent/secret" in str(exc_info.value)

    def test_get_secret_is_directory(self, tmp_path: Path) -> None:
        """Test error when secret path is a directory."""
        dir_path = tmp_path / "some_dir"
        dir_path.mkdir()

        backend = FileSecretBackend({"base_path": str(tmp_path)})

        with pytest.raises(SecretBackendError) as exc_info:
            backend.get_secret("some_dir")

        assert "not a file" in str(exc_info.value)

    def test_get_secret_strips_whitespace(self, tmp_path: Path) -> None:
        """Test that trailing whitespace is stripped."""
        secret_file = tmp_path / "token"
        secret_file.write_text("my-token  \n\n  ")

        backend = FileSecretBackend({"base_path": str(tmp_path)})
        value = backend.get_secret("token")

        assert value == "my-token"

    def test_list_secrets_empty_directory(self, tmp_path: Path) -> None:
        """Test listing secrets in empty directory."""
        backend = FileSecretBackend({"base_path": str(tmp_path)})
        secrets = backend.list_secrets()

        assert secrets == []

    def test_list_secrets_with_files(self, tmp_path: Path) -> None:
        """Test listing secrets with multiple files."""
        (tmp_path / "db").mkdir()
        (tmp_path / "db" / "host").write_text("localhost")
        (tmp_path / "db" / "password").write_text("secret")
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "token").write_text("token123")

        backend = FileSecretBackend({"base_path": str(tmp_path)})
        secrets = backend.list_secrets()

        assert "db/host" in secrets
        assert "db/password" in secrets
        assert "api/token" in secrets

    def test_list_secrets_with_prefix(self, tmp_path: Path) -> None:
        """Test listing secrets with prefix filter."""
        (tmp_path / "db").mkdir()
        (tmp_path / "db" / "host").write_text("localhost")
        (tmp_path / "db" / "password").write_text("secret")
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "token").write_text("token123")

        backend = FileSecretBackend({"base_path": str(tmp_path)})
        secrets = backend.list_secrets("db/")

        assert "db/host" in secrets
        assert "db/password" in secrets
        assert "api/token" not in secrets

    def test_list_secrets_nonexistent_base(self, tmp_path: Path) -> None:
        """Test listing when base path doesn't exist."""
        nonexistent = tmp_path / "nonexistent"
        backend = FileSecretBackend({"base_path": str(nonexistent)})
        secrets = backend.list_secrets()

        assert secrets == []

    def test_list_secrets_nonexistent_prefix(self, tmp_path: Path) -> None:
        """Test listing with non-existent prefix."""
        backend = FileSecretBackend({"base_path": str(tmp_path)})
        secrets = backend.list_secrets("nonexistent/")

        assert secrets == []

    def test_health_check_healthy(self, tmp_path: Path) -> None:
        """Test health check with accessible directory."""
        backend = FileSecretBackend({"base_path": str(tmp_path)})
        assert backend.health_check() is True

    def test_health_check_nonexistent(self, tmp_path: Path) -> None:
        """Test health check with non-existent directory."""
        nonexistent = tmp_path / "nonexistent"
        backend = FileSecretBackend({"base_path": str(nonexistent)})
        assert backend.health_check() is False


class TestFileBackendRegistration:
    """Tests for file backend registration."""

    def test_register_returns_metadata(self) -> None:
        """Test register function returns correct metadata."""
        metadata = register()

        assert isinstance(metadata, SecretBackendMetadata)
        assert metadata.name == "file"
        assert metadata.version == "1.0.0"
        assert metadata.backend_class == FileSecretBackend
        assert metadata.read_only is True

    def test_register_metadata_has_description(self) -> None:
        """Test metadata includes description."""
        metadata = register()
        assert len(metadata.description) > 0
        assert "file" in metadata.description.lower()
