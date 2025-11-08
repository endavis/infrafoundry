"""Unit tests for SecretManager."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from infrafoundry.core.secrets import SecretManager


@pytest.fixture
def temp_secrets_dir():
    """Create a temporary secrets directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_sops_age():
    """Mock sops and age availability."""
    with patch("subprocess.run") as mock_run:
        # Default: sops --version succeeds
        mock_run.return_value = MagicMock(returncode=0, stdout="sops 3.7.3")
        yield mock_run


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
        manager = SecretManager()
        assert manager.secrets_dir is not None
        assert "secrets" in str(manager.secrets_dir)

    def test_init_custom_directory(self, mock_sops_age, mock_age_key, temp_secrets_dir):
        """Test initialization with custom secrets directory."""
        manager = SecretManager(secrets_dir=temp_secrets_dir)
        assert manager.secrets_dir == temp_secrets_dir

    def test_init_with_config_repo_env(self, mock_sops_age, mock_age_key, temp_secrets_dir):
        """Test initialization uses INFRAFOUNDRY_CONFIG_REPO environment variable."""
        config_repo = temp_secrets_dir / "config-repo"
        config_repo.mkdir()

        with patch.dict("os.environ", {"INFRAFOUNDRY_CONFIG_REPO": str(config_repo)}):
            manager = SecretManager()
            assert manager.secrets_dir == config_repo / "secrets"

    def test_init_sops_not_installed(self, mock_age_key):
        """Test initialization fails when sops is not installed."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(RuntimeError, match="sops not found"):
                SecretManager()

    def test_init_sops_command_fails(self, mock_age_key):
        """Test initialization fails when sops command fails."""
        import subprocess

        with patch(
            "subprocess.run", side_effect=subprocess.CalledProcessError(1, "sops")
        ):
            with pytest.raises(RuntimeError, match="sops not found"):
                SecretManager()

    def test_init_no_age_key_env(self, mock_sops_age):
        """Test initialization fails when SOPS_AGE_KEY_FILE is not set."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="SOPS_AGE_KEY_FILE not set"):
                SecretManager()

    def test_init_age_key_file_missing(self, mock_sops_age):
        """Test initialization fails when age key file doesn't exist."""
        with patch.dict("os.environ", {"SOPS_AGE_KEY_FILE": "/nonexistent/age.key"}):
            with pytest.raises(FileNotFoundError, match="Age key file not found"):
                SecretManager()

    def test_decrypt_file(
        self, mock_sops_age, mock_age_key, temp_secrets_dir
    ):
        """Test decrypting a SOPS-encrypted file."""
        manager = SecretManager(secrets_dir=temp_secrets_dir)

        # Create encrypted file
        encrypted_file = temp_secrets_dir / "proxmox.yaml"
        encrypted_file.write_text("encrypted content")

        # Mock sops decrypt returning YAML
        decrypted_data = {"api_url": "https://proxmox.example.com", "api_token": "secret123"}
        mock_sops_age.return_value = MagicMock(
            returncode=0, stdout=yaml.dump(decrypted_data)
        )

        result = manager.decrypt_file("proxmox.yaml")

        assert result == decrypted_data
        # Verify sops was called correctly
        mock_sops_age.assert_called_with(
            ["sops", "--decrypt", str(encrypted_file)],
            capture_output=True,
            check=True,
            text=True,
        )

    def test_decrypt_file_not_found(self, mock_sops_age, mock_age_key, temp_secrets_dir):
        """Test decrypting non-existent file raises error."""
        manager = SecretManager(secrets_dir=temp_secrets_dir)

        with pytest.raises(FileNotFoundError, match="Encrypted file not found"):
            manager.decrypt_file("nonexistent.yaml")

    def test_decrypt_file_sops_fails(
        self, mock_sops_age, mock_age_key, temp_secrets_dir
    ):
        """Test decryption failure when sops command fails."""
        import subprocess

        manager = SecretManager(secrets_dir=temp_secrets_dir)

        # Create encrypted file
        encrypted_file = temp_secrets_dir / "proxmox.yaml"
        encrypted_file.write_text("encrypted content")

        # Mock sops decrypt failing
        mock_sops_age.side_effect = subprocess.CalledProcessError(
            1, "sops", stderr="decryption failed"
        )

        with pytest.raises(RuntimeError, match="Failed to decrypt"):
            manager.decrypt_file("proxmox.yaml")

    def test_encrypt_file(self, mock_sops_age, mock_age_key, temp_secrets_dir):
        """Test encrypting data and saving to file."""
        manager = SecretManager(secrets_dir=temp_secrets_dir)

        data = {"api_url": "https://proxmox.example.com", "api_token": "secret123"}

        # Mock sops encrypt succeeding
        def sops_side_effect(*args, **kwargs):
            # On encrypt call, mark temp file as encrypted
            if "--encrypt" in args[0]:
                temp_file = Path(args[0][-1])
                temp_file.write_text("encrypted content")
            return MagicMock(returncode=0)

        mock_sops_age.side_effect = sops_side_effect

        manager.encrypt_file("proxmox.yaml", data)

        encrypted_file = temp_secrets_dir / "proxmox.yaml"
        assert encrypted_file.exists()
        assert encrypted_file.read_text() == "encrypted content"

    def test_encrypt_file_creates_directory(
        self, mock_sops_age, mock_age_key, temp_secrets_dir
    ):
        """Test encrypt_file creates secrets directory if it doesn't exist."""
        secrets_dir = temp_secrets_dir / "nested" / "secrets"
        manager = SecretManager(secrets_dir=secrets_dir)

        data = {"key": "value"}

        # Mock sops encrypt
        def sops_side_effect(*args, **kwargs):
            if "--encrypt" in args[0]:
                temp_file = Path(args[0][-1])
                temp_file.write_text("encrypted")
            return MagicMock(returncode=0)

        mock_sops_age.side_effect = sops_side_effect

        manager.encrypt_file("test.yaml", data)

        assert secrets_dir.exists()
        assert (secrets_dir / "test.yaml").exists()

    def test_encrypt_file_sops_fails(
        self, mock_sops_age, mock_age_key, temp_secrets_dir
    ):
        """Test encryption failure when sops command fails."""
        import subprocess

        manager = SecretManager(secrets_dir=temp_secrets_dir)

        data = {"key": "value"}

        # Mock sops encrypt failing
        mock_sops_age.side_effect = subprocess.CalledProcessError(
            1, "sops", stderr="encryption failed"
        )

        with pytest.raises(RuntimeError, match="Failed to encrypt"):
            manager.encrypt_file("test.yaml", data)

        # Verify temp file was cleaned up
        assert not (temp_secrets_dir / "test.tmp").exists()

    def test_get_secret(self, mock_sops_age, mock_age_key, temp_secrets_dir):
        """Test retrieving a specific secret value."""
        manager = SecretManager(secrets_dir=temp_secrets_dir)

        # Create encrypted file
        encrypted_file = temp_secrets_dir / "config.yaml"
        encrypted_file.write_text("encrypted")

        # Mock sops decrypt
        decrypted_data = {
            "api": {"url": "https://example.com", "token": "secret123"},
            "database": {"password": "dbpass"},
        }
        mock_sops_age.return_value = MagicMock(
            returncode=0, stdout=yaml.dump(decrypted_data)
        )

        # Get nested secret
        token = manager.get_secret("config.yaml", "api.token")
        assert token == "secret123"

        # Get top-level secret
        db_config = manager.get_secret("config.yaml", "database")
        assert db_config == {"password": "dbpass"}

    def test_get_secret_key_not_found(
        self, mock_sops_age, mock_age_key, temp_secrets_dir
    ):
        """Test get_secret raises KeyError when key doesn't exist."""
        manager = SecretManager(secrets_dir=temp_secrets_dir)

        encrypted_file = temp_secrets_dir / "config.yaml"
        encrypted_file.write_text("encrypted")

        decrypted_data = {"api": {"url": "https://example.com"}}
        mock_sops_age.return_value = MagicMock(
            returncode=0, stdout=yaml.dump(decrypted_data)
        )

        with pytest.raises(KeyError):
            manager.get_secret("config.yaml", "nonexistent.key")

    def test_create_sops_config(self, mock_sops_age, mock_age_key, temp_secrets_dir):
        """Test creating .sops.yaml configuration file."""
        manager = SecretManager(secrets_dir=temp_secrets_dir)

        age_public_key = "age1abcdefghijklmnopqrstuvwxyz1234567890"
        manager.create_sops_config(age_public_key)

        sops_config_file = temp_secrets_dir / ".sops.yaml"
        assert sops_config_file.exists()

        config = yaml.safe_load(sops_config_file.read_text())
        assert "creation_rules" in config
        assert config["creation_rules"][0]["age"] == age_public_key

    def test_export_for_terraform(self, mock_sops_age, mock_age_key, temp_secrets_dir):
        """Test exporting secrets as Terraform variables file."""
        manager = SecretManager(secrets_dir=temp_secrets_dir)

        # Create encrypted file
        encrypted_file = temp_secrets_dir / "secrets.yaml"
        encrypted_file.write_text("encrypted")

        # Mock sops decrypt
        decrypted_data = {
            "api_url": "https://example.com",
            "api_token": "secret123",
            "config": {"nested": "value"},
        }
        mock_sops_age.return_value = MagicMock(
            returncode=0, stdout=yaml.dump(decrypted_data)
        )

        output_file = temp_secrets_dir / "secrets.tfvars"
        manager.export_for_terraform("secrets.yaml", output_file)

        assert output_file.exists()
        content = output_file.read_text()
        assert 'api_url = "https://example.com"' in content
        assert 'api_token = "secret123"' in content
        assert 'config = {"nested": "value"}' in content

    def test_export_for_ansible(self, mock_sops_age, mock_age_key, temp_secrets_dir):
        """Test exporting secrets as Ansible vars file."""
        manager = SecretManager(secrets_dir=temp_secrets_dir)

        # Create encrypted file
        encrypted_file = temp_secrets_dir / "secrets.yaml"
        encrypted_file.write_text("encrypted")

        # Mock sops decrypt
        decrypted_data = {
            "api_url": "https://example.com",
            "api_token": "secret123",
            "users": ["alice", "bob"],
        }
        mock_sops_age.return_value = MagicMock(
            returncode=0, stdout=yaml.dump(decrypted_data)
        )

        output_file = temp_secrets_dir / "secrets_vars.yml"
        manager.export_for_ansible("secrets.yaml", output_file)

        assert output_file.exists()
        exported_data = yaml.safe_load(output_file.read_text())
        assert exported_data == decrypted_data
