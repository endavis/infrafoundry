"""Unit tests for SecretManager."""

import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from infrafoundry.core.exceptions import (
    SecretDecryptionError,
    SecretError,
    SecretNotFoundError,
)
from infrafoundry.core.secrets.provider import SecretProvider
from infrafoundry.core.secrets.secret_manager import SecretManager


@pytest.fixture
def temp_secrets_dir():
    """Create a temporary secrets directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_sops_age():
    """Mock sops and age availability via subprocess."""
    with patch("subprocess.run") as mock_run:
        # Default: sops --version succeeds
        mock_run.return_value = MagicMock(returncode=0, stdout="sops 3.7.3")
        yield mock_run


@pytest.fixture
def mock_provider():
    """Create a mock SecretProvider."""
    provider = MagicMock(spec=SecretProvider)
    return provider


@pytest.fixture
def mock_age_key(temp_secrets_dir):
    """Mock age key file."""
    age_key_file = temp_secrets_dir / "age.key"
    age_key_file.write_text("AGE-SECRET-KEY-1234567890ABCDEF")
    with patch.dict("os.environ", {"SOPS_AGE_KEY_FILE": str(age_key_file)}):
        yield age_key_file


class TestSecretManager:
    """Tests for SecretManager."""

    def test_init_default_location(self, mock_sops_age, mock_age_key):
        """Test initialization with default secrets directory."""
        manager = SecretManager(env_name="dev")
        assert manager.secrets_dir is not None
        assert "envs" in str(manager.secrets_dir) and "dev" in str(manager.secrets_dir)

    def test_init_custom_directory(self, mock_sops_age, mock_age_key, temp_secrets_dir):
        """Test initialization with custom secrets directory."""
        manager = SecretManager(env_name="dev", secrets_dir=temp_secrets_dir)
        assert manager.secrets_dir == temp_secrets_dir

    def test_init_with_provider(self, temp_secrets_dir, mock_provider):
        """Test initialization with injected provider."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )
        assert manager.provider == mock_provider

    def test_init_with_config_repo_env(self, mock_sops_age, mock_age_key, temp_secrets_dir):
        """Test initialization uses INFRAFOUNDRY_CONFIG_REPO environment variable."""
        config_repo = temp_secrets_dir / "config-repo"
        config_repo.mkdir()
        (config_repo / "envs" / "dev").mkdir(parents=True)

        with patch.dict("os.environ", {"INFRAFOUNDRY_CONFIG_REPO": str(config_repo)}):
            manager = SecretManager(env_name="dev")
            assert manager.secrets_dir == config_repo / "envs" / "dev"

    def test_init_no_age_key_env(self, mock_sops_age, temp_secrets_dir, monkeypatch):
        """Test initialization fails when SOPS_AGE_KEY_FILE is not set."""
        monkeypatch.setenv("INFRAFOUNDRY_CONFIG_REPO", str(temp_secrets_dir))
        monkeypatch.delenv("SOPS_AGE_KEY_FILE", raising=False)
        monkeypatch.delenv("INFRAFOUNDRY_SKIP_SOPS_CHECK", raising=False)
        monkeypatch.setenv("INFRAFOUNDRY_FORCE_SOPS_CHECK", "1")
        with pytest.raises(ValueError, match="SOPS_AGE_KEY_FILE not set"):
            SecretManager(env_name="dev")

    def test_init_age_key_file_missing(self, mock_sops_age):
        """Test initialization fails when age key file doesn't exist."""
        with (
            patch.dict(
                "os.environ",
                {
                    "SOPS_AGE_KEY_FILE": "/nonexistent/age.key",
                    "INFRAFOUNDRY_FORCE_SOPS_CHECK": "1",
                },
            ),
            pytest.raises(FileNotFoundError, match="Age key file not found"),
        ):
            SecretManager(env_name="dev")

    def test_decrypt_file(self, temp_secrets_dir, mock_provider):
        """Test decrypting a file using injected provider."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )

        decrypted_data = {
            "api_url": "https://proxmox.example.com",
            "api_token": "secret123",
        }
        mock_provider.load_secret.return_value = decrypted_data

        result = manager.decrypt_file("proxmox.yaml")

        assert result == decrypted_data
        mock_provider.load_secret.assert_called_with(temp_secrets_dir / "proxmox.yaml")

    def test_decrypt_file_not_found(self, temp_secrets_dir, mock_provider):
        """Test decrypting non-existent file raises error."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )

        mock_provider.load_secret.side_effect = SecretNotFoundError("File not found")

        with pytest.raises(SecretNotFoundError):
            manager.decrypt_file("nonexistent.yaml")

    def test_decrypt_file_provider_fails(self, temp_secrets_dir, mock_provider):
        """Test decryption failure when provider fails."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )

        mock_provider.load_secret.side_effect = SecretDecryptionError("Decryption failed")

        with pytest.raises(SecretDecryptionError, match="Decryption failed"):
            manager.decrypt_file("proxmox.yaml")

    def test_encrypt_file(self, temp_secrets_dir, mock_provider):
        """Test encrypting data using injected provider."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )

        data = {"api_url": "https://proxmox.example.com", "api_token": "secret123"}

        manager.encrypt_file("proxmox.yaml", data)

        mock_provider.save_secret.assert_called_with(temp_secrets_dir / "proxmox.yaml", data)

    def test_encrypt_file_creates_directory(self, temp_secrets_dir, mock_provider):
        """Test encrypt_file creates secrets directory if it doesn't exist."""
        secrets_dir = temp_secrets_dir / "nested" / "secrets"
        manager = SecretManager(env_name="dev", secrets_dir=secrets_dir, provider=mock_provider)

        data = {"key": "value"}
        manager.encrypt_file("test.yaml", data)

        assert secrets_dir.exists()
        mock_provider.save_secret.assert_called()

    def test_encrypt_file_provider_fails(self, temp_secrets_dir, mock_provider):
        """Test encryption failure when provider fails."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )

        data = {"key": "value"}
        mock_provider.save_secret.side_effect = SecretError("Encryption failed")

        with pytest.raises(SecretError, match="Encryption failed"):
            manager.encrypt_file("test.yaml", data)

    def test_get_secret(self, temp_secrets_dir, mock_provider):
        """Test retrieving a specific secret value."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )

        decrypted_data = {
            "api": {"url": "https://example.com", "token": "secret123"},
            "database": {"password": "dbpass"},
        }
        mock_provider.load_secret.return_value = decrypted_data

        # Get nested secret
        token = manager.get_secret("config.yaml", "api.token")
        assert token == "secret123"

        # Get top-level secret
        db_config = manager.get_secret("config.yaml", "database")
        assert db_config == {"password": "dbpass"}

    def test_get_secret_key_not_found(self, temp_secrets_dir, mock_provider):
        """Test get_secret raises KeyError when key doesn't exist."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )

        decrypted_data = {"api": {"url": "https://example.com"}}
        mock_provider.load_secret.return_value = decrypted_data

        with pytest.raises(KeyError):
            manager.get_secret("config.yaml", "nonexistent.key")

    def test_create_sops_config(self, mock_sops_age, mock_age_key, temp_secrets_dir):
        """Test creating .sops.yaml configuration file."""
        # This still uses legacy method in SecretManager
        # which calls create_sops_config from age_key_manager
        manager = SecretManager(env_name="dev", secrets_dir=temp_secrets_dir)

        age_public_key = "age1abcdefghijklmnopqrstuvwxyz1234567890"
        manager.create_sops_config(age_public_key)

        sops_config_file = temp_secrets_dir / ".sops.yaml"
        assert sops_config_file.exists()

        config = yaml.safe_load(sops_config_file.read_text())
        assert "creation_rules" in config
        assert config["creation_rules"][0]["age"] == age_public_key

    def test_export_for_terraform(self, temp_secrets_dir, mock_provider):
        """Test exporting secrets as Terraform variables file."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )

        decrypted_data = {
            "api_url": "https://example.com",
            "api_token": "secret123",
            "config": {"nested": "value"},
        }
        mock_provider.load_secret.return_value = decrypted_data

        output_file = temp_secrets_dir / "secrets.tfvars"
        manager.export_for_terraform("secrets.yaml", output_file)

        assert output_file.exists()
        content = output_file.read_text()
        assert 'api_url = "https://example.com"' in content
        assert 'api_token = "secret123"' in content
        assert 'config = {"nested": "value"}' in content

    def test_export_for_ansible(self, temp_secrets_dir, mock_provider):
        """Test exporting secrets as Ansible vars file."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )

        decrypted_data = {
            "api_url": "https://example.com",
            "api_token": "secret123",
            "users": ["alice", "bob"],
        }
        mock_provider.load_secret.return_value = decrypted_data

        output_file = temp_secrets_dir / "secrets_vars.yml"
        manager.export_for_ansible("secrets.yaml", output_file)

        assert output_file.exists()
        exported_data = yaml.safe_load(output_file.read_text())
        assert exported_data == decrypted_data

    def test_export_for_terraform_sets_restrictive_permissions(
        self, temp_secrets_dir, mock_provider
    ):
        """Test that export_for_terraform creates files with 0o600 permissions."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )
        mock_provider.load_secret.return_value = {"api_token": "secret123"}

        output_file = temp_secrets_dir / "secrets.tfvars"
        manager.export_for_terraform("secrets.yaml", output_file)

        assert stat.S_IMODE(os.stat(output_file).st_mode) == 0o600

    def test_export_for_ansible_sets_restrictive_permissions(self, temp_secrets_dir, mock_provider):
        """Test that export_for_ansible creates files with 0o600 permissions."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )
        mock_provider.load_secret.return_value = {"api_token": "secret123"}

        output_file = temp_secrets_dir / "secrets_vars.yml"
        manager.export_for_ansible("secrets.yaml", output_file)

        assert stat.S_IMODE(os.stat(output_file).st_mode) == 0o600

    def test_temporary_export_cleans_up_file(self, temp_secrets_dir, mock_provider):
        """Test that temporary_export removes the file after context manager exits."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )
        mock_provider.load_secret.return_value = {"api_token": "secret123"}

        output_file = temp_secrets_dir / "temp_secrets.tfvars"
        with manager.temporary_export("secrets.yaml", output_file, fmt="terraform") as path:
            assert path.exists()
            assert path == output_file

        assert not output_file.exists()

    def test_temporary_export_cleans_up_on_exception(self, temp_secrets_dir, mock_provider):
        """Test that temporary_export cleans up even when an exception occurs."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )
        mock_provider.load_secret.return_value = {"api_token": "secret123"}

        output_file = temp_secrets_dir / "temp_secrets.tfvars"
        with (
            pytest.raises(RuntimeError, match="test error"),
            manager.temporary_export("secrets.yaml", output_file, fmt="terraform") as path,
        ):
            assert path.exists()
            raise RuntimeError("test error")

        assert not output_file.exists()

    def test_temporary_export_ansible_format(self, temp_secrets_dir, mock_provider):
        """Test that temporary_export works with ansible format."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )
        mock_provider.load_secret.return_value = {"api_token": "secret123"}

        output_file = temp_secrets_dir / "temp_vars.yml"
        with manager.temporary_export("secrets.yaml", output_file, fmt="ansible") as path:
            assert path.exists()
            data = yaml.safe_load(path.read_text())
            assert data == {"api_token": "secret123"}

        assert not output_file.exists()

    def test_temporary_export_invalid_format(self, temp_secrets_dir, mock_provider):
        """Test that temporary_export raises ValueError for unsupported format."""
        manager = SecretManager(
            env_name="dev", secrets_dir=temp_secrets_dir, provider=mock_provider
        )

        output_file = temp_secrets_dir / "temp.txt"
        with (
            pytest.raises(ValueError, match="Unsupported export format"),
            manager.temporary_export("secrets.yaml", output_file, fmt="invalid"),
        ):
            pass  # pragma: no cover

    def test_cleanup_secret_files(self, temp_secrets_dir):
        """Test that cleanup_secret_files removes specified files."""
        file1 = temp_secrets_dir / "secret1.tfvars"
        file2 = temp_secrets_dir / "secret2.yml"
        file1.write_text("secret")
        file2.write_text("secret")

        SecretManager.cleanup_secret_files(file1, file2)

        assert not file1.exists()
        assert not file2.exists()

    def test_cleanup_secret_files_missing_file(self, temp_secrets_dir):
        """Test that cleanup_secret_files handles already-deleted files gracefully."""
        missing_file = temp_secrets_dir / "nonexistent.tfvars"
        # Should not raise
        SecretManager.cleanup_secret_files(missing_file)
