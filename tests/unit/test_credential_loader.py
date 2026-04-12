"""Tests for credential loader."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.credential_loader import CredentialLoader
from infrafoundry.core.secrets.provider import SecretProvider


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
    def mock_provider(self):
        """Create a mock SecretProvider."""
        return MagicMock(spec=SecretProvider)

    @pytest.fixture
    def loader(self, temp_config_dir, mock_provider):
        """Create CredentialLoader instance."""
        return CredentialLoader(config_dir=temp_config_dir, secret_provider=mock_provider)

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

    def test_init_defaults_to_cwd(self, monkeypatch):
        """Test initialization defaults to current working directory."""
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)
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

    def test_load_kubernetes_credentials(self, loader, mock_provider, temp_config_dir):
        """Test loading Kubernetes credentials."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        mock_data = {"kubeconfig": "/path/to/kubeconfig"}
        mock_provider.load_secret.return_value = mock_data

        k8s_file = secrets_dir / "kubernetes.yaml"
        k8s_file.write_text("encrypted")

        credentials = loader.load("dev", providers=["kubernetes"])

        assert credentials == {"KUBECONFIG": "/path/to/kubeconfig"}

    def test_load_all_providers(self, loader, mock_provider, temp_config_dir):
        """Test loading credentials for all providers."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        # Create credential files
        (secrets_dir / "kubernetes.yaml").write_text("encrypted")

        mock_provider.load_secret.return_value = {"kubeconfig": "/path/to/kubeconfig"}

        credentials = loader.load("dev")

        assert "KUBECONFIG" in credentials

    def test_load_partial_credentials(self, loader, mock_provider, temp_config_dir):
        """Test loading when some credential fields are missing."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        # Only some fields present
        mock_data = {"kubeconfig": "/path/to/kubeconfig"}
        mock_provider.load_secret.return_value = mock_data

        k8s_file = secrets_dir / "kubernetes.yaml"
        k8s_file.write_text("encrypted")

        credentials = loader.load("dev", providers=["kubernetes"])

        # Only the available field is returned
        assert credentials == {"KUBECONFIG": "/path/to/kubeconfig"}

    def test_load_unknown_provider(self, loader, temp_config_dir):
        """Test loading credentials for unknown provider."""
        # Create secrets dir so it passes exists() check
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        with patch("infrafoundry.core.credential_loader.credential_loader.logger") as mock_logger:
            credentials = loader.load("dev", providers=["unknown_provider"])
            assert credentials == {}
            mock_logger.warning.assert_called_once()

    def test_set_age_key(self, loader, temp_config_dir, monkeypatch):
        """Test setting per-environment age key."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)
        age_key_file = secrets_dir / "age.key"
        age_key_file.write_text("AGE-SECRET-KEY-1...")

        monkeypatch.delenv("SOPS_AGE_KEY_FILE", raising=False)
        loader._set_age_key(secrets_dir)
        assert os.environ.get("SOPS_AGE_KEY_FILE") == str(age_key_file)

    def test_set_age_key_not_exists(self, loader, temp_config_dir, monkeypatch):
        """Test setting age key when file doesn't exist."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        monkeypatch.delenv("SOPS_AGE_KEY_FILE", raising=False)
        loader._set_age_key(secrets_dir)
        assert "SOPS_AGE_KEY_FILE" not in os.environ

    def test_apply_to_environment(self, loader, monkeypatch):
        """Test applying credentials to environment."""
        credentials = {
            "TEST_VAR_1": "value1",
            "TEST_VAR_2": "value2",
        }

        monkeypatch.delenv("TEST_VAR_1", raising=False)
        monkeypatch.delenv("TEST_VAR_2", raising=False)
        loader.apply_to_environment(credentials)
        assert os.environ["TEST_VAR_1"] == "value1"
        assert os.environ["TEST_VAR_2"] == "value2"

    def test_apply_to_environment_empty(self, loader, monkeypatch):
        """Test applying empty credentials dict."""
        monkeypatch.setenv("EXISTING", "value")
        loader.apply_to_environment({})
        # Existing vars should remain
        assert os.environ["EXISTING"] == "value"

    def test_load_and_apply(self, loader, mock_provider, temp_config_dir, monkeypatch):
        """Test convenience method that loads and applies."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        mock_data = {"kubeconfig": "/path/to/kubeconfig"}
        mock_provider.load_secret.return_value = mock_data

        k8s_file = secrets_dir / "kubernetes.yaml"
        k8s_file.write_text("encrypted")

        monkeypatch.delenv("KUBECONFIG", raising=False)
        credentials = loader.load_and_apply("dev", providers=["kubernetes"])

        assert credentials == {"KUBECONFIG": "/path/to/kubeconfig"}
        assert os.environ["KUBECONFIG"] == "/path/to/kubeconfig"

    def test_temporary_credentials_context_manager(
        self, loader, mock_provider, temp_config_dir, monkeypatch
    ):
        """Test temporary credentials context manager."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        mock_data = {"kubeconfig": "/path/to/kubeconfig"}
        mock_provider.load_secret.return_value = mock_data

        k8s_file = secrets_dir / "kubernetes.yaml"
        k8s_file.write_text("encrypted")

        monkeypatch.setenv("KUBECONFIG", "original")

        with loader.temporary_credentials("dev", providers=["kubernetes"]) as creds:
            # Inside context, new value is set
            assert os.environ["KUBECONFIG"] == "/path/to/kubeconfig"
            assert creds == {"KUBECONFIG": "/path/to/kubeconfig"}

        # Outside context, original value is restored
        assert os.environ["KUBECONFIG"] == "original"

    def test_temporary_credentials_new_vars_removed(
        self, loader, mock_provider, temp_config_dir, monkeypatch
    ):
        """Test that new vars added by context manager are removed after."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)

        mock_data = {"kubeconfig": "/path/to/kubeconfig"}
        mock_provider.load_secret.return_value = mock_data

        k8s_file = secrets_dir / "kubernetes.yaml"
        k8s_file.write_text("encrypted")

        monkeypatch.delenv("KUBECONFIG", raising=False)

        with loader.temporary_credentials("dev", providers=["kubernetes"]):
            assert "KUBECONFIG" in os.environ

        # After context, var should be removed
        assert "KUBECONFIG" not in os.environ

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

    def test_load_custom_provider(self, loader, mock_provider, temp_config_dir):
        """Test loading credentials for a custom registered provider."""
        loader.register_provider("custom", "custom.yaml", {"api_key": "CUSTOM_API_KEY"})

        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)
        custom_file = secrets_dir / "custom.yaml"
        custom_file.write_text("encrypted")

        mock_data = {"api_key": "secret123"}
        mock_provider.load_secret.return_value = mock_data

        credentials = loader.load("dev", providers=["custom"])
        assert credentials == {"CUSTOM_API_KEY": "secret123"}

    def test_debug_logging_enabled(self, temp_config_dir):
        """Test debug logging when INFRAFOUNDRY_LOG_LEVEL=DEBUG."""
        with patch.dict(os.environ, {"INFRAFOUNDRY_LOG_LEVEL": "DEBUG"}):
            loader = CredentialLoader(config_dir=temp_config_dir)
            assert loader._debug_mode is True

    def test_debug_logging_disabled(self, temp_config_dir, monkeypatch):
        """Test debug logging when not in debug mode."""
        monkeypatch.delenv("INFRAFOUNDRY_LOG_LEVEL", raising=False)
        loader = CredentialLoader(config_dir=temp_config_dir)
        assert loader._debug_mode is False

    def test_load_with_decryption_error(self, loader, mock_provider, temp_config_dir):
        """Test graceful handling of decryption errors."""
        secrets_dir = temp_config_dir / "envs" / "dev"
        secrets_dir.mkdir(parents=True)
        k8s_file = secrets_dir / "kubernetes.yaml"
        k8s_file.write_text("encrypted")

        mock_provider.load_secret.side_effect = Exception("Decryption failed")

        credentials = loader.load("dev", providers=["kubernetes"])
        # Should return empty dict, not raise exception
        assert credentials == {}
