"""Tests for credential loader."""

import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from infrafoundry.core.credential_loader import CredentialLoader


class TestCredentialLoader:
    """Tests for CredentialLoader class."""

    @pytest.fixture
    def temp_config_dir(self, tmp_path):
        """Create temporary config directory structure."""
        config_dir = tmp_path / "config"
        secrets_dir = config_dir / "secrets" / "dev"
        secrets_dir.mkdir(parents=True)
        return config_dir

    @pytest.fixture
    def loader(self, temp_config_dir):
        """Create CredentialLoader instance."""
        return CredentialLoader(config_dir=temp_config_dir)

    def test_init_with_config_dir(self, temp_config_dir):
        """Test initialization with explicit config directory."""
        loader = CredentialLoader(config_dir=temp_config_dir)
        assert loader.config_dir == temp_config_dir

    def test_init_with_env_var(self, tmp_path):
        """Test initialization using INFRAFOUNDRY_CONFIG_REPO env var."""
        config_dir = tmp_path / "from_env"
        config_dir.mkdir(parents=True)

        with patch.dict(os.environ, {"INFRAFOUNDRY_CONFIG_REPO": str(config_dir)}):
            loader = CredentialLoader()
            assert loader.config_dir == config_dir

    def test_init_defaults_to_cwd(self):
        """Test initialization defaults to current working directory."""
        with patch.dict(os.environ, {}, clear=True):
            loader = CredentialLoader()
            assert loader.config_dir == Path.cwd()

    def test_get_secrets_dir(self, loader, temp_config_dir):
        """Test getting secrets directory for environment."""
        secrets_dir = loader.get_secrets_dir("dev")
        assert secrets_dir == temp_config_dir / "envs" / "dev"

    def test_load_no_secrets_dir(self, loader):
        """Test loading when secrets directory doesn't exist."""
        credentials = loader.load("nonexistent")
        assert credentials == {}

    def test_load_proxmox_credentials(self, loader, temp_config_dir):
        """Test loading Proxmox credentials from settings.yaml."""
        env_dir = temp_config_dir / "envs" / "dev"
        env_dir.mkdir(parents=True)

        _mock_data = {
            "provider_settings": {
                "proxmox": {
                    "api_url": "https://pve.example.com:8006",
                    "token_id": "user@pam!token",
                    "token_secret": "secret123",
                }
            }
        }

        # Create proxmox.yaml for backward compatibility (tests still look for it)
        proxmox_yaml = env_dir / "proxmox.yaml"
        proxmox_yaml.write_text("encrypted")

        with patch(
            "infrafoundry.core.credential_loader.base_loader.BaseCredentialLoader._decrypt_sops_file",
            return_value={
                "proxmox_api_url": "https://pve.example.com:8006",
                "proxmox_token_id": "user@pam!token",
                "proxmox_token_secret": "secret123",
            },
        ) as mock_decrypt:
            credentials = loader.load("dev", providers=["proxmox"])

            assert credentials == {
                "PROXMOX_API_URL": "https://pve.example.com:8006",
                "PROXMOX_API_TOKEN_ID": "user@pam!token",
                "PROXMOX_API_TOKEN_SECRET": "secret123",
            }
            mock_decrypt.assert_called_once()

    def test_load_opnsense_credentials(self, loader, temp_config_dir):
        """Test loading OPNsense credentials."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        mock_data = {
            "opnsense_api_url": "https://fw.example.com",
            "opnsense_api_key": "key123",
            "opnsense_api_secret": "secret456",
        }

        with patch(
            "infrafoundry.core.credential_loader.base_loader.BaseCredentialLoader._decrypt_sops_file",
            return_value=mock_data,
        ):
            opnsense_file = secrets_dir / "opnsense.yaml"
            opnsense_file.write_text("encrypted")

            credentials = loader.load("dev", providers=["opnsense"])

            assert credentials == {
                "OPNSENSE_API_URL": "https://fw.example.com",
                "OPNSENSE_API_KEY": "key123",
                "OPNSENSE_API_SECRET": "secret456",
            }

    def test_load_kubernetes_credentials(self, loader, temp_config_dir):
        """Test loading Kubernetes credentials."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        mock_data = {"kubeconfig": "/path/to/kubeconfig"}

        with patch(
            "infrafoundry.core.credential_loader.base_loader.BaseCredentialLoader._decrypt_sops_file",
            return_value=mock_data,
        ):
            k8s_file = secrets_dir / "kubernetes.yaml"
            k8s_file.write_text("encrypted")

            credentials = loader.load("dev", providers=["kubernetes"])

            assert credentials == {"KUBECONFIG": "/path/to/kubeconfig"}

    def test_load_all_providers(self, loader, temp_config_dir):
        """Test loading credentials for all providers."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        # Create all credential files
        (secrets_dir / "proxmox.yaml").write_text("encrypted")
        (secrets_dir / "opnsense.yaml").write_text("encrypted")
        (secrets_dir / "kubernetes.yaml").write_text("encrypted")

        def mock_decrypt(file_path):
            if "proxmox" in str(file_path):
                return {"proxmox_api_url": "https://pve.example.com:8006"}
            elif "opnsense" in str(file_path):
                return {"opnsense_api_url": "https://fw.example.com"}
            elif "kubernetes" in str(file_path):
                return {"kubeconfig": "/path/to/kubeconfig"}
            return {}

        with patch(
            "infrafoundry.core.credential_loader.base_loader.BaseCredentialLoader._decrypt_sops_file",
            side_effect=mock_decrypt,
        ):
            credentials = loader.load("dev")

            assert "PROXMOX_API_URL" in credentials
            assert "OPNSENSE_API_URL" in credentials
            assert "KUBECONFIG" in credentials

    def test_load_partial_credentials(self, loader, temp_config_dir):
        """Test loading when some credential fields are missing."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        # Only some fields present
        mock_data = {"proxmox_api_url": "https://pve.example.com:8006"}

        with patch(
            "infrafoundry.core.credential_loader.base_loader.BaseCredentialLoader._decrypt_sops_file",
            return_value=mock_data,
        ):
            proxmox_file = secrets_dir / "proxmox.yaml"
            proxmox_file.write_text("encrypted")

            credentials = loader.load("dev", providers=["proxmox"])

            # Only the available field is returned
            assert credentials == {"PROXMOX_API_URL": "https://pve.example.com:8006"}
            assert "PROXMOX_API_TOKEN_ID" not in credentials

    def test_load_unknown_provider(self, loader, temp_config_dir):
        """Test loading credentials for unknown provider."""
        # Create secrets dir so it passes exists() check
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        with patch("infrafoundry.core.credential_loader.credential_loader.logger") as mock_logger:
            credentials = loader.load("dev", providers=["unknown_provider"])
            assert credentials == {}
            mock_logger.warning.assert_called_once()

    def test_decrypt_sops_file_success(self, temp_config_dir, tmp_path):
        """Test successful SOPS file decryption."""
        from infrafoundry.core.credential_loader.proxmox_loader import ProxmoxCredentialLoader

        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)
        test_loader = ProxmoxCredentialLoader(secrets_dir, debug_mode=False)

        test_file = tmp_path / "test.yaml"
        test_file.write_text("encrypted: data")

        mock_result = Mock()
        mock_result.stdout = "decrypted_key: decrypted_value\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = test_loader._decrypt_sops_file(test_file)

            assert result == {"decrypted_key": "decrypted_value"}
            mock_run.assert_called_once_with(
                ["sops", "--decrypt", str(test_file)],
                capture_output=True,
                text=True,
                check=True,
            )

    def test_decrypt_sops_file_command_failure(self, temp_config_dir, tmp_path):
        """Test SOPS decryption when command fails."""
        from infrafoundry.core.credential_loader.proxmox_loader import ProxmoxCredentialLoader

        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)
        test_loader = ProxmoxCredentialLoader(secrets_dir, debug_mode=False)

        test_file = tmp_path / "test.yaml"
        test_file.write_text("encrypted: data")

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "sops")):
            result = test_loader._decrypt_sops_file(test_file)
            assert result == {}

    def test_decrypt_sops_file_not_installed(self, temp_config_dir, tmp_path):
        """Test SOPS decryption when sops command not found."""
        from infrafoundry.core.credential_loader.proxmox_loader import ProxmoxCredentialLoader

        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)
        test_loader = ProxmoxCredentialLoader(secrets_dir, debug_mode=False)

        test_file = tmp_path / "test.yaml"
        test_file.write_text("encrypted: data")

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = test_loader._decrypt_sops_file(test_file)
            assert result == {}

    def test_decrypt_sops_file_invalid_yaml(self, temp_config_dir, tmp_path):
        """Test SOPS decryption when output is invalid YAML."""
        from infrafoundry.core.credential_loader.proxmox_loader import ProxmoxCredentialLoader

        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)
        test_loader = ProxmoxCredentialLoader(secrets_dir, debug_mode=False)

        test_file = tmp_path / "test.yaml"
        test_file.write_text("encrypted: data")

        mock_result = Mock()
        mock_result.stdout = "invalid: yaml: data:"

        with patch("subprocess.run", return_value=mock_result):
            result = test_loader._decrypt_sops_file(test_file)
            # Should return empty dict on YAML parse error
            assert result == {}

    def test_set_age_key(self, loader, temp_config_dir):
        """Test setting per-environment age key."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)
        age_key_file = secrets_dir / "age.key"
        age_key_file.write_text("AGE-SECRET-KEY-1...")

        with patch.dict(os.environ, {}, clear=True):
            loader._set_age_key(secrets_dir)
            assert os.environ.get("SOPS_AGE_KEY_FILE") == str(age_key_file)

    def test_set_age_key_not_exists(self, loader, temp_config_dir):
        """Test setting age key when file doesn't exist."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        with patch.dict(os.environ, {}, clear=True):
            loader._set_age_key(secrets_dir)
            assert "SOPS_AGE_KEY_FILE" not in os.environ

    def test_apply_to_environment(self, loader):
        """Test applying credentials to environment."""
        credentials = {
            "TEST_VAR_1": "value1",
            "TEST_VAR_2": "value2",
        }

        with patch.dict(os.environ, {}, clear=True):
            loader.apply_to_environment(credentials)
            assert os.environ["TEST_VAR_1"] == "value1"
            assert os.environ["TEST_VAR_2"] == "value2"

    def test_apply_to_environment_empty(self, loader):
        """Test applying empty credentials dict."""
        with patch.dict(os.environ, {"EXISTING": "value"}, clear=True):
            loader.apply_to_environment({})
            # Existing vars should remain
            assert os.environ["EXISTING"] == "value"

    def test_load_and_apply(self, loader, temp_config_dir):
        """Test convenience method that loads and applies."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        mock_data = {"proxmox_api_url": "https://pve.example.com:8006"}

        with patch(
            "infrafoundry.core.credential_loader.base_loader.BaseCredentialLoader._decrypt_sops_file",
            return_value=mock_data,
        ):
            proxmox_file = secrets_dir / "proxmox.yaml"
            proxmox_file.write_text("encrypted")

            with patch.dict(os.environ, {}, clear=True):
                credentials = loader.load_and_apply("dev", providers=["proxmox"])

                assert credentials == {"PROXMOX_API_URL": "https://pve.example.com:8006"}
                assert os.environ["PROXMOX_API_URL"] == "https://pve.example.com:8006"

    def test_temporary_credentials_context_manager(self, loader, temp_config_dir):
        """Test temporary credentials context manager."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        mock_data = {"proxmox_api_url": "https://pve.example.com:8006"}

        with patch(
            "infrafoundry.core.credential_loader.base_loader.BaseCredentialLoader._decrypt_sops_file",
            return_value=mock_data,
        ):
            proxmox_file = secrets_dir / "proxmox.yaml"
            proxmox_file.write_text("encrypted")

            with patch.dict(os.environ, {"PROXMOX_API_URL": "original"}, clear=True):
                original_value = os.environ["PROXMOX_API_URL"]

                with loader.temporary_credentials("dev", providers=["proxmox"]) as creds:
                    # Inside context, new value is set
                    assert os.environ["PROXMOX_API_URL"] == "https://pve.example.com:8006"
                    assert creds == {"PROXMOX_API_URL": "https://pve.example.com:8006"}

                # Outside context, original value is restored
                assert os.environ["PROXMOX_API_URL"] == original_value

    def test_temporary_credentials_new_vars_removed(self, loader, temp_config_dir):
        """Test that new vars added by context manager are removed after."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        mock_data = {"proxmox_api_url": "https://pve.example.com:8006"}

        with patch(
            "infrafoundry.core.credential_loader.base_loader.BaseCredentialLoader._decrypt_sops_file",
            return_value=mock_data,
        ):
            proxmox_file = secrets_dir / "proxmox.yaml"
            proxmox_file.write_text("encrypted")

            with patch.dict(os.environ, {}, clear=True):
                with loader.temporary_credentials("dev", providers=["proxmox"]):
                    assert "PROXMOX_API_URL" in os.environ

                # After context, var should be removed
                assert "PROXMOX_API_URL" not in os.environ

    def test_register_provider(self, loader):
        """Test registering a custom provider."""
        loader.register_provider(
            "aws",
            "aws.yaml",
            {"access_key": "AWS_ACCESS_KEY_ID", "secret_key": "AWS_SECRET_ACCESS_KEY"},
        )

        assert "aws" in loader.provider_credentials
        assert loader.provider_credentials["aws"]["file"] == "aws.yaml"
        assert loader.provider_credentials["aws"]["fields"]["access_key"] == "AWS_ACCESS_KEY_ID"

    def test_load_custom_provider(self, loader, temp_config_dir):
        """Test loading credentials for a custom registered provider."""
        loader.register_provider("custom", "custom.yaml", {"api_key": "CUSTOM_API_KEY"})

        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)
        custom_file = secrets_dir / "custom.yaml"
        custom_file.write_text("encrypted")

        mock_data = {"api_key": "secret123"}

        with patch(
            "infrafoundry.core.credential_loader.base_loader.BaseCredentialLoader._decrypt_sops_file",
            return_value=mock_data,
        ):
            credentials = loader.load("dev", providers=["custom"])
            assert credentials == {"CUSTOM_API_KEY": "secret123"}

    def test_debug_logging_enabled(self, temp_config_dir):
        """Test debug logging when INFRAFOUNDRY_LOG_LEVEL=DEBUG."""
        with patch.dict(os.environ, {"INFRAFOUNDRY_LOG_LEVEL": "DEBUG"}):
            loader = CredentialLoader(config_dir=temp_config_dir)
            assert loader._debug_mode is True

    def test_debug_logging_disabled(self, temp_config_dir):
        """Test debug logging when not in debug mode."""
        with patch.dict(os.environ, {}, clear=True):
            loader = CredentialLoader(config_dir=temp_config_dir)
            assert loader._debug_mode is False

    def test_load_with_decryption_error(self, loader, temp_config_dir):
        """Test graceful handling of decryption errors."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)
        proxmox_file = secrets_dir / "proxmox.yaml"
        proxmox_file.write_text("encrypted")

        with patch(
            "infrafoundry.core.credential_loader.base_loader.BaseCredentialLoader._decrypt_sops_file",
            side_effect=Exception("Decryption failed"),
        ):
            credentials = loader.load("dev", providers=["proxmox"])
            # Should return empty dict, not raise exception
            assert credentials == {}
