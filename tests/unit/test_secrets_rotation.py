"""Unit tests for secrets rotation functionality."""

import subprocess
from unittest.mock import MagicMock, Mock, patch

import pytest
import yaml

from infrafoundry.core.exceptions import SecretError
from infrafoundry.core.secrets.rotation import SecretsRotator


@pytest.fixture
def temp_secrets_dir(tmp_path):
    """Create a temporary secrets directory with test files."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()

    # Create test encrypted files
    test_files = {
        "proxmox.yaml": {"api_token": "test-token-1", "api_url": "https://proxmox.local"},
        "opnsense.yaml": {"api_key": "test-key-1", "api_secret": "test-secret-1"},
        "settings.yaml": {"database": {"password": "db-pass-1"}},
    }

    for filename, data in test_files.items():
        file_path = secrets_dir / filename
        with open(file_path, "w") as f:
            yaml.dump(data, f)

    # Create .sops.yaml
    sops_config = {"creation_rules": [{"path_regex": r".*\.yaml$", "age": "age1oldkey123"}]}
    with open(secrets_dir / ".sops.yaml", "w") as f:
        yaml.dump(sops_config, f)

    return secrets_dir


@pytest.fixture
def mock_provider():
    """Create a mock secret provider."""
    provider = MagicMock()
    provider.load_secret = MagicMock()
    provider.save_secret = MagicMock()
    return provider


@pytest.mark.unit
class TestSecretsRotator:
    """Tests for SecretsRotator class."""

    def test_initialization(self, temp_secrets_dir):
        """Test rotator initialization."""
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)

        assert rotator.secrets_dir == temp_secrets_dir
        assert rotator.backup_dir == temp_secrets_dir.parent / ".secrets_backups"
        assert rotator.current_backup is None

    def test_initialization_custom_backup_dir(self, temp_secrets_dir, tmp_path):
        """Test rotator with custom backup directory."""
        custom_backup = tmp_path / "custom_backups"
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir, backup_dir=custom_backup)

        assert rotator.backup_dir == custom_backup

    @patch("subprocess.run")
    def test_generate_age_key_success(self, mock_run, temp_secrets_dir):
        """Test successful age key generation."""
        mock_run.return_value = Mock(
            stderr="# public key: age1newkey456789",
            returncode=0,
        )

        key_file = temp_secrets_dir / "age.key.new"
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)
        public_key = rotator.generate_age_key(key_file)

        assert public_key == "age1newkey456789"
        mock_run.assert_called_once()
        assert "age-keygen" in mock_run.call_args[0][0]

    def test_generate_age_key_existing_file(self, temp_secrets_dir):
        """Test that generation fails if key file already exists."""
        key_file = temp_secrets_dir / "existing.key"
        key_file.touch()

        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)

        with pytest.raises(SecretError, match="already exists"):
            rotator.generate_age_key(key_file)

    @patch("subprocess.run")
    def test_generate_age_key_command_failure(self, mock_run, temp_secrets_dir):
        """Test handling of age-keygen command failure."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "age-keygen", stderr="error")

        key_file = temp_secrets_dir / "age.key.new"
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)

        with pytest.raises(SecretError, match="Failed to generate age key"):
            rotator.generate_age_key(key_file)

    @patch("subprocess.run")
    def test_generate_age_key_age_not_found(self, mock_run, temp_secrets_dir):
        """Test handling when age-keygen is not installed."""
        mock_run.side_effect = FileNotFoundError()

        key_file = temp_secrets_dir / "age.key.new"
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)

        with pytest.raises(SecretError, match="age-keygen not found"):
            rotator.generate_age_key(key_file)

    def test_create_backup(self, temp_secrets_dir):
        """Test creating backup of encrypted files."""
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)
        backup_path = rotator.create_backup()

        assert backup_path.exists()
        assert backup_path.name.startswith("backup_")

        # Verify all yaml files were backed up
        backup_files = list(backup_path.glob("*.yaml"))
        source_files = list(temp_secrets_dir.glob("*.yaml"))

        assert len(backup_files) == len(source_files)

        # Verify .sops.yaml was backed up
        assert (backup_path / ".sops.yaml").exists()

    def test_restore_backup(self, temp_secrets_dir):
        """Test restoring files from backup."""
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)

        # Create backup
        backup_path = rotator.create_backup()

        # Modify original files
        for yaml_file in temp_secrets_dir.glob("*.yaml"):
            if yaml_file.name != ".sops.yaml":
                with open(yaml_file, "w") as f:
                    yaml.dump({"modified": "data"}, f)

        # Restore backup
        rotator.restore_backup(backup_path)

        # Verify files were restored
        proxmox_file = temp_secrets_dir / "proxmox.yaml"
        with open(proxmox_file) as f:
            data = yaml.safe_load(f)

        assert "api_token" in data  # Original data restored

    def test_restore_backup_not_found(self, temp_secrets_dir):
        """Test that restore fails if backup doesn't exist."""
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)
        fake_backup = temp_secrets_dir.parent / "nonexistent_backup"

        with pytest.raises(SecretError, match="Backup directory not found"):
            rotator.restore_backup(fake_backup)

    def test_update_sops_config(self, temp_secrets_dir):
        """Test updating .sops.yaml with new public key."""
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)
        new_public_key = "age1newkey456789"

        rotator.update_sops_config(new_public_key)

        sops_config_path = temp_secrets_dir / ".sops.yaml"
        with open(sops_config_path) as f:
            config = yaml.safe_load(f)

        assert config["creation_rules"][0]["age"] == new_public_key

    def test_get_encrypted_files_all(self, temp_secrets_dir):
        """Test getting all encrypted files."""
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)
        files = rotator.get_encrypted_files()

        file_names = {f.name for f in files}
        assert "proxmox.yaml" in file_names
        assert "opnsense.yaml" in file_names
        assert "settings.yaml" in file_names
        assert ".sops.yaml" not in file_names  # Should be excluded

    def test_get_encrypted_files_with_patterns(self, temp_secrets_dir):
        """Test getting encrypted files with specific patterns."""
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)
        files = rotator.get_encrypted_files(file_patterns=["proxmox.yaml", "opnsense.yaml"])

        file_names = {f.name for f in files}
        assert len(file_names) == 2
        assert "proxmox.yaml" in file_names
        assert "opnsense.yaml" in file_names
        assert "settings.yaml" not in file_names

    def test_get_encrypted_files_wildcard_pattern(self, temp_secrets_dir):
        """Test getting encrypted files with wildcard pattern."""
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)
        files = rotator.get_encrypted_files(file_patterns=["*sense.yaml"])

        file_names = {f.name for f in files}
        assert len(file_names) == 1
        assert "opnsense.yaml" in file_names

    def test_rotate_missing_parameters(self, temp_secrets_dir):
        """Test that rotate fails without key parameters."""
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)

        with pytest.raises(SecretError, match="Must specify either"):
            rotator.rotate()

    def test_rotate_conflicting_parameters(self, temp_secrets_dir, tmp_path):
        """Test that rotate fails with conflicting parameters."""
        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)
        key_file = tmp_path / "key.txt"
        key_file.touch()

        with pytest.raises(SecretError, match="Cannot specify both"):
            rotator.rotate(new_key_file=key_file, generate_new_key=True)

    @patch("subprocess.run")
    def test_rotate_with_new_key_file(self, mock_run, temp_secrets_dir, mock_provider, tmp_path):
        """Test rotation with a provided new key file."""
        # Create new key file
        new_key_file = tmp_path / "new_age.key"
        new_key_file.write_text("AGE-SECRET-KEY-1NEWKEY")

        # Mock age-keygen -y to extract public key
        mock_run.return_value = Mock(stdout="age1newpublickey789", returncode=0)

        # Mock provider to return test data
        test_data = {
            temp_secrets_dir / "proxmox.yaml": {"api_token": "test-token"},
            temp_secrets_dir / "opnsense.yaml": {"api_key": "test-key"},
        }
        mock_provider.load_secret = lambda path: test_data.get(path, {})

        rotator = SecretsRotator(secrets_dir=temp_secrets_dir, provider=mock_provider)

        result = rotator.rotate(new_key_file=new_key_file, verify=False)

        assert result["success"] is True
        assert result["new_public_key"] == "age1newpublickey789"
        assert len(result["files_rotated"]) > 0

    @patch("subprocess.run")
    @patch.dict("os.environ", {}, clear=True)
    def test_rotate_with_generate_new_key(self, mock_run, temp_secrets_dir, mock_provider):
        """Test rotation with automatic key generation."""
        # Mock age-keygen for key generation
        mock_run.return_value = Mock(
            stderr="# public key: age1generatedkey123",
            stdout="age1generatedkey123",
            returncode=0,
        )

        # Mock provider to return and save test data
        test_data = {
            temp_secrets_dir / "proxmox.yaml": {"api_token": "test-token"},
        }
        mock_provider.load_secret = lambda path: test_data.get(path, {})

        rotator = SecretsRotator(secrets_dir=temp_secrets_dir, provider=mock_provider)

        # Set minimal env for test
        import os

        os.environ["SOPS_AGE_KEY_FILE"] = "/tmp/test_old_key"

        result = rotator.rotate(generate_new_key=True, verify=False)

        assert result["success"] is True
        assert result["new_public_key"] == "age1generatedkey123"

    def test_rotate_no_encrypted_files(self, temp_secrets_dir):
        """Test rotation when no encrypted files exist."""
        # Remove all yaml files
        for yaml_file in temp_secrets_dir.glob("*.yaml"):
            yaml_file.unlink()

        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                stderr="# public key: age1newkey",
                returncode=0,
            )

            result = rotator.rotate(generate_new_key=True)

        assert result["success"] is False
        assert "No encrypted files found" in result["errors"][0]

    @patch("subprocess.run")
    def test_extract_public_key(self, mock_run, temp_secrets_dir, tmp_path):
        """Test extracting public key from private key file."""
        mock_run.return_value = Mock(stdout="age1extractedkey456\n", returncode=0)

        key_file = tmp_path / "test.key"
        key_file.write_text("AGE-SECRET-KEY-123")

        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)
        public_key = rotator._extract_public_key(key_file)

        assert public_key == "age1extractedkey456"
        mock_run.assert_called_once()
        assert "-y" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_extract_public_key_failure(self, mock_run, temp_secrets_dir, tmp_path):
        """Test handling of public key extraction failure."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "age-keygen", stderr="error")

        key_file = tmp_path / "test.key"
        key_file.write_text("AGE-SECRET-KEY-123")

        rotator = SecretsRotator(secrets_dir=temp_secrets_dir)

        with pytest.raises(SecretError, match="Failed to extract public key"):
            rotator._extract_public_key(key_file)

    def test_verify_rotation_success(self, temp_secrets_dir, mock_provider):
        """Test successful rotation verification."""
        test_data = {
            temp_secrets_dir / "test.yaml": {"key": "value"},
        }

        mock_provider.load_secret = lambda path: test_data.get(path, {})

        rotator = SecretsRotator(secrets_dir=temp_secrets_dir, provider=mock_provider)

        # Should not raise
        rotator._verify_rotation(
            encrypted_files=[temp_secrets_dir / "test.yaml"],
            original_data=test_data,
        )

    def test_verify_rotation_data_mismatch(self, temp_secrets_dir, mock_provider):
        """Test rotation verification with mismatched data."""
        original_data = {
            temp_secrets_dir / "test.yaml": {"key": "original_value"},
        }

        # Provider returns different data
        mock_provider.load_secret = lambda path: {"key": "modified_value"}

        rotator = SecretsRotator(secrets_dir=temp_secrets_dir, provider=mock_provider)

        with pytest.raises(SecretError, match="doesn't match original"):
            rotator._verify_rotation(
                encrypted_files=[temp_secrets_dir / "test.yaml"],
                original_data=original_data,
            )

    def test_rotate_rollback_on_failure(self, temp_secrets_dir, mock_provider, tmp_path):
        """Test that rotation rolls back on failure."""
        # Create new key
        new_key_file = tmp_path / "new.key"
        new_key_file.write_text("AGE-SECRET-KEY-NEW")

        # Make provider fail on save
        mock_provider.load_secret = lambda path: {"test": "data"}
        mock_provider.save_secret = MagicMock(side_effect=Exception("Encryption failed"))

        rotator = SecretsRotator(secrets_dir=temp_secrets_dir, provider=mock_provider)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="age1newkey", returncode=0)

            with patch.dict("os.environ", {"SOPS_AGE_KEY_FILE": "/tmp/old_key"}):
                with pytest.raises(SecretError, match="Secrets rotation failed"):
                    rotator.rotate(new_key_file=new_key_file, verify=False)

        # Verify backup was created
        assert rotator.current_backup is not None


@pytest.mark.unit
class TestSecretManagerRotation:
    """Tests for SecretManager.rotate_secrets() method."""

    def test_rotate_secrets_calls_rotator(self, temp_secrets_dir):
        """Test that rotate_secrets properly delegates to SecretsRotator."""
        from infrafoundry.core.secrets import SecretManager

        # Skip SOPS checks during initialization
        with patch.dict("os.environ", {"INFRAFOUNDRY_SKIP_SOPS_CHECK": "1"}):
            manager = SecretManager(env_name="test", secrets_dir=temp_secrets_dir)

        with (
            patch.object(manager, "provider") as mock_provider,
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = Mock(
                stderr="# public key: age1test", stdout="age1test", returncode=0
            )
            mock_provider.load_secret = lambda path: {"test": "data"}

            with patch.dict("os.environ", {"SOPS_AGE_KEY_FILE": "/tmp/test_key"}):
                result = manager.rotate_secrets(generate_new_key=True, verify=False)

            assert "success" in result
            assert "files_rotated" in result
            assert "new_public_key" in result
