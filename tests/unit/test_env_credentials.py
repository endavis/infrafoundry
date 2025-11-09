"""Tests for environment-specific credential loading."""

import os
import subprocess
from unittest.mock import Mock, patch

import pytest
import yaml

from infrafoundry.core.env_credentials import (_decrypt_sops_file,
                                               load_environment_credentials)


class TestLoadEnvironmentCredentials:
    """Tests for load_environment_credentials function."""

    def test_load_credentials_with_all_providers(self, tmp_path):
        """Test loading credentials for all providers."""
        # Setup directory structure
        secrets_dir = tmp_path / "secrets" / "dev"
        secrets_dir.mkdir(parents=True)

        # Create mock encrypted files
        proxmox_file = secrets_dir / "proxmox.yaml"
        opnsense_file = secrets_dir / "opnsense.yaml"
        kubernetes_file = secrets_dir / "kubernetes.yaml"

        proxmox_file.write_text("encrypted")
        opnsense_file.write_text("encrypted")
        kubernetes_file.write_text("encrypted")

        # Mock SOPS decryption
        def mock_decrypt(file_path):
            if "proxmox" in str(file_path):
                return {
                    "proxmox_api_url": "https://proxmox.example.com:8006",
                    "proxmox_token_id": "user@pam!token",
                    "proxmox_token_secret": "secret123",
                }
            elif "opnsense" in str(file_path):
                return {
                    "opnsense_api_url": "https://opnsense.example.com",
                    "opnsense_api_key": "key123",
                    "opnsense_api_secret": "secret456",
                }
            elif "kubernetes" in str(file_path):
                return {"kubeconfig": "/path/to/kubeconfig"}
            return {}

        with patch(
            "infrafoundry.core.env_credentials._decrypt_sops_file", side_effect=mock_decrypt
        ):
            env_vars = load_environment_credentials("dev", config_dir=tmp_path)

        # Verify all credentials loaded
        assert env_vars["PROXMOX_API_URL"] == "https://proxmox.example.com:8006"
        assert env_vars["PROXMOX_API_TOKEN_ID"] == "user@pam!token"
        assert env_vars["PROXMOX_API_TOKEN_SECRET"] == "secret123"
        assert env_vars["OPNSENSE_API_URL"] == "https://opnsense.example.com"
        assert env_vars["OPNSENSE_API_KEY"] == "key123"
        assert env_vars["OPNSENSE_API_SECRET"] == "secret456"
        assert env_vars["KUBECONFIG"] == "/path/to/kubeconfig"

    def test_load_credentials_proxmox_only(self, tmp_path):
        """Test loading credentials with only Proxmox secrets."""
        secrets_dir = tmp_path / "secrets" / "prod"
        secrets_dir.mkdir(parents=True)

        proxmox_file = secrets_dir / "proxmox.yaml"
        proxmox_file.write_text("encrypted")

        def mock_decrypt(file_path):
            if "proxmox" in str(file_path):
                return {
                    "proxmox_api_url": "https://proxmox-prod.example.com:8006",
                    "proxmox_token_id": "prod@pam!token",
                    "proxmox_token_secret": "prod-secret",
                }
            return {}

        with patch(
            "infrafoundry.core.env_credentials._decrypt_sops_file", side_effect=mock_decrypt
        ):
            env_vars = load_environment_credentials("prod", config_dir=tmp_path)

        assert len(env_vars) == 3
        assert env_vars["PROXMOX_API_URL"] == "https://proxmox-prod.example.com:8006"
        assert env_vars["PROXMOX_API_TOKEN_ID"] == "prod@pam!token"
        assert env_vars["PROXMOX_API_TOKEN_SECRET"] == "prod-secret"
        assert "OPNSENSE_API_URL" not in env_vars
        assert "KUBECONFIG" not in env_vars

    def test_load_credentials_no_secrets_dir(self, tmp_path):
        """Test loading credentials when secrets directory doesn't exist."""
        env_vars = load_environment_credentials("nonexistent", config_dir=tmp_path)

        assert env_vars == {}

    def test_load_credentials_empty_secrets_dir(self, tmp_path):
        """Test loading credentials from empty secrets directory."""
        secrets_dir = tmp_path / "secrets" / "staging"
        secrets_dir.mkdir(parents=True)

        env_vars = load_environment_credentials("staging", config_dir=tmp_path)

        assert env_vars == {}

    def test_load_credentials_decryption_failure(self, tmp_path):
        """Test graceful handling of SOPS decryption failures."""
        secrets_dir = tmp_path / "secrets" / "dev"
        secrets_dir.mkdir(parents=True)

        proxmox_file = secrets_dir / "proxmox.yaml"
        proxmox_file.write_text("encrypted")

        # Mock SOPS to raise exception
        with patch(
            "infrafoundry.core.env_credentials._decrypt_sops_file",
            side_effect=subprocess.CalledProcessError(1, "sops"),
        ):
            env_vars = load_environment_credentials("dev", config_dir=tmp_path)

        # Should return empty dict on failure (graceful degradation)
        assert env_vars == {}

    def test_load_credentials_partial_failure(self, tmp_path):
        """Test loading credentials when some providers fail."""
        secrets_dir = tmp_path / "secrets" / "dev"
        secrets_dir.mkdir(parents=True)

        proxmox_file = secrets_dir / "proxmox.yaml"
        opnsense_file = secrets_dir / "opnsense.yaml"
        proxmox_file.write_text("encrypted")
        opnsense_file.write_text("encrypted")

        def mock_decrypt(file_path):
            if "proxmox" in str(file_path):
                return {
                    "proxmox_api_url": "https://proxmox.example.com:8006",
                    "proxmox_token_id": "user@pam!token",
                    "proxmox_token_secret": "secret123",
                }
            # OPNsense fails to decrypt
            raise subprocess.CalledProcessError(1, "sops")

        with patch(
            "infrafoundry.core.env_credentials._decrypt_sops_file", side_effect=mock_decrypt
        ):
            env_vars = load_environment_credentials("dev", config_dir=tmp_path)

        # Proxmox should still load successfully
        assert len(env_vars) == 3
        assert "PROXMOX_API_URL" in env_vars
        assert "OPNSENSE_API_URL" not in env_vars

    def test_load_credentials_missing_fields(self, tmp_path):
        """Test loading credentials with missing fields in YAML."""
        secrets_dir = tmp_path / "secrets" / "dev"
        secrets_dir.mkdir(parents=True)

        proxmox_file = secrets_dir / "proxmox.yaml"
        proxmox_file.write_text("encrypted")

        # Mock SOPS to return incomplete data
        with patch(
            "infrafoundry.core.env_credentials._decrypt_sops_file",
            return_value={"proxmox_api_url": "https://proxmox.example.com:8006"},
        ):
            env_vars = load_environment_credentials("dev", config_dir=tmp_path)

        # Should set available fields and use empty strings for missing ones
        assert env_vars["PROXMOX_API_URL"] == "https://proxmox.example.com:8006"
        assert env_vars["PROXMOX_API_TOKEN_ID"] == ""
        assert env_vars["PROXMOX_API_TOKEN_SECRET"] == ""

    def test_load_credentials_uses_infrafoundry_config_repo_env_var(self, tmp_path):
        """Test that function uses INFRAFOUNDRY_CONFIG_REPO environment variable."""
        secrets_dir = tmp_path / "secrets" / "dev"
        secrets_dir.mkdir(parents=True)

        proxmox_file = secrets_dir / "proxmox.yaml"
        proxmox_file.write_text("encrypted")

        with (
            patch(
                "infrafoundry.core.env_credentials._decrypt_sops_file",
                return_value={
                    "proxmox_api_url": "https://proxmox.example.com:8006",
                    "proxmox_token_id": "user@pam!token",
                    "proxmox_token_secret": "secret123",
                },
            ),
            patch.dict(os.environ, {"INFRAFOUNDRY_CONFIG_REPO": str(tmp_path)}),
        ):
            # Call without config_dir - should use env var
            env_vars = load_environment_credentials("dev")

        assert len(env_vars) == 3
        assert "PROXMOX_API_URL" in env_vars

    def test_load_credentials_defaults_to_cwd(self, tmp_path, monkeypatch):
        """Test that function defaults to current working directory."""
        monkeypatch.chdir(tmp_path)

        secrets_dir = tmp_path / "secrets" / "dev"
        secrets_dir.mkdir(parents=True)

        proxmox_file = secrets_dir / "proxmox.yaml"
        proxmox_file.write_text("encrypted")

        with (
            patch(
                "infrafoundry.core.env_credentials._decrypt_sops_file",
                return_value={
                    "proxmox_api_url": "https://proxmox.example.com:8006",
                    "proxmox_token_id": "user@pam!token",
                    "proxmox_token_secret": "secret123",
                },
            ),
            patch.dict(os.environ, {}, clear=True),
        ):
            # Call without config_dir and no env var
            env_vars = load_environment_credentials("dev")

        assert len(env_vars) == 3
        assert "PROXMOX_API_URL" in env_vars

    def test_load_credentials_multiple_environments(self, tmp_path):
        """Test loading credentials for different environments."""
        # Setup dev environment
        dev_secrets = tmp_path / "secrets" / "dev"
        dev_secrets.mkdir(parents=True)
        (dev_secrets / "proxmox.yaml").write_text("encrypted")

        # Setup prod environment
        prod_secrets = tmp_path / "secrets" / "prod"
        prod_secrets.mkdir(parents=True)
        (prod_secrets / "proxmox.yaml").write_text("encrypted")

        def mock_decrypt(file_path):
            if "dev" in str(file_path):
                return {
                    "proxmox_api_url": "https://proxmox-dev.example.com:8006",
                    "proxmox_token_id": "dev@pam!token",
                    "proxmox_token_secret": "dev-secret",
                }
            elif "prod" in str(file_path):
                return {
                    "proxmox_api_url": "https://proxmox-prod.example.com:8006",
                    "proxmox_token_id": "prod@pam!token",
                    "proxmox_token_secret": "prod-secret",
                }
            return {}

        with patch(
            "infrafoundry.core.env_credentials._decrypt_sops_file", side_effect=mock_decrypt
        ):
            # Load dev credentials
            dev_vars = load_environment_credentials("dev", config_dir=tmp_path)
            assert dev_vars["PROXMOX_API_URL"] == "https://proxmox-dev.example.com:8006"
            assert dev_vars["PROXMOX_API_TOKEN_ID"] == "dev@pam!token"

            # Load prod credentials
            prod_vars = load_environment_credentials("prod", config_dir=tmp_path)
            assert prod_vars["PROXMOX_API_URL"] == "https://proxmox-prod.example.com:8006"
            assert prod_vars["PROXMOX_API_TOKEN_ID"] == "prod@pam!token"


class TestDecryptSopsFile:
    """Tests for _decrypt_sops_file helper function."""

    def test_decrypt_valid_file(self, tmp_path):
        """Test decrypting a valid SOPS file."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("encrypted")

        decrypted_data = {"key1": "value1", "key2": "value2"}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=yaml.dump(decrypted_data), stderr="")

            result = _decrypt_sops_file(test_file)

        assert result == decrypted_data
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["sops", "--decrypt", str(test_file)]
        assert call_args[1]["capture_output"] is True
        assert call_args[1]["text"] is True
        assert call_args[1]["check"] is True

    def test_decrypt_sops_command_failure(self, tmp_path):
        """Test handling of SOPS command failure."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("encrypted")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "sops", stderr="Failed")

            result = _decrypt_sops_file(test_file)

        # Should return empty dict on failure
        assert result == {}

    def test_decrypt_sops_not_installed(self, tmp_path):
        """Test handling when SOPS is not installed."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("encrypted")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("sops command not found")

            result = _decrypt_sops_file(test_file)

        # Should return empty dict when SOPS not found
        assert result == {}

    def test_decrypt_invalid_yaml(self, tmp_path):
        """Test handling of invalid YAML output from SOPS."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("encrypted")

        with patch("subprocess.run") as mock_run:
            # SOPS returns invalid YAML
            mock_run.return_value = Mock(returncode=0, stdout="invalid: yaml: content:", stderr="")

            # yaml.safe_load should handle this
            with pytest.raises(yaml.YAMLError):
                _decrypt_sops_file(test_file)

    def test_decrypt_empty_file(self, tmp_path):
        """Test decrypting an empty file."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("encrypted")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            result = _decrypt_sops_file(test_file)

        # Empty YAML should return None from yaml.safe_load
        assert result is None

    def test_decrypt_complex_yaml_structure(self, tmp_path):
        """Test decrypting file with complex YAML structure."""
        test_file = tmp_path / "test.yaml"
        test_file.write_text("encrypted")

        complex_data = {
            "proxmox_api_url": "https://proxmox.example.com:8006",
            "proxmox_token_id": "user@pam!token",
            "proxmox_token_secret": "secret123",
            "nested": {"key": "value", "list": [1, 2, 3]},
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=yaml.dump(complex_data), stderr="")

            result = _decrypt_sops_file(test_file)

        assert result == complex_data
        assert result["nested"]["key"] == "value"
        assert result["nested"]["list"] == [1, 2, 3]


class TestIntegration:
    """Integration tests for credential loading."""

    def test_end_to_end_credential_flow(self, tmp_path):
        """Test complete flow of loading and using credentials."""
        # Setup environment
        secrets_dir = tmp_path / "secrets" / "staging"
        secrets_dir.mkdir(parents=True)

        # Create credential files
        (secrets_dir / "proxmox.yaml").write_text("encrypted")
        (secrets_dir / "opnsense.yaml").write_text("encrypted")

        # Mock decryption
        def mock_decrypt(file_path):
            if "proxmox" in str(file_path):
                return {
                    "proxmox_api_url": "https://staging-proxmox.example.com:8006",
                    "proxmox_token_id": "staging@pam!token",
                    "proxmox_token_secret": "staging-secret",
                }
            elif "opnsense" in str(file_path):
                return {
                    "opnsense_api_url": "https://staging-opnsense.example.com",
                    "opnsense_api_key": "staging-key",
                    "opnsense_api_secret": "staging-secret",
                }
            return {}

        with patch(
            "infrafoundry.core.env_credentials._decrypt_sops_file", side_effect=mock_decrypt
        ):
            # Load credentials
            env_vars = load_environment_credentials("staging", config_dir=tmp_path)

            # Simulate setting environment variables
            original_env = os.environ.copy()
            try:
                os.environ.update(env_vars)

                # Verify environment variables are set
                assert os.environ["PROXMOX_API_URL"] == "https://staging-proxmox.example.com:8006"
                assert os.environ["PROXMOX_API_TOKEN_ID"] == "staging@pam!token"
                assert os.environ["OPNSENSE_API_URL"] == "https://staging-opnsense.example.com"
                assert os.environ["OPNSENSE_API_KEY"] == "staging-key"
            finally:
                # Restore original environment
                os.environ.clear()
                os.environ.update(original_env)

    def test_fallback_to_existing_env_vars(self, tmp_path):
        """Test that existing environment variables work when secrets not available."""
        # No secrets directory exists
        original_env = os.environ.copy()
        try:
            # Set existing env vars
            os.environ["PROXMOX_API_URL"] = "https://existing.example.com:8006"
            os.environ["PROXMOX_API_TOKEN_ID"] = "existing@pam!token"

            # Try to load non-existent secrets
            env_vars = load_environment_credentials("nonexistent", config_dir=tmp_path)

            # Should return empty (falling back to existing env vars)
            assert env_vars == {}

            # Existing env vars should still be available
            assert os.environ["PROXMOX_API_URL"] == "https://existing.example.com:8006"
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    def test_per_environment_age_key(self, tmp_path):
        """Test that SOPS_AGE_KEY_FILE is set per environment."""
        # Setup directory structure with age keys
        dev_secrets = tmp_path / "secrets" / "dev"
        prod_secrets = tmp_path / "secrets" / "prod"
        dev_secrets.mkdir(parents=True)
        prod_secrets.mkdir(parents=True)

        # Create age keys
        dev_age_key = dev_secrets / "age.key"
        prod_age_key = prod_secrets / "age.key"
        dev_age_key.write_text("dev-key-content")
        prod_age_key.write_text("prod-key-content")

        # Create encrypted credential files
        proxmox_dev = dev_secrets / "proxmox.yaml"
        proxmox_prod = prod_secrets / "proxmox.yaml"
        proxmox_dev.write_text("encrypted-dev")
        proxmox_prod.write_text("encrypted-prod")

        original_env = os.environ.copy()
        try:
            # Clear SOPS_AGE_KEY_FILE
            os.environ.pop("SOPS_AGE_KEY_FILE", None)

            with patch("infrafoundry.core.env_credentials._decrypt_sops_file") as mock_decrypt:
                mock_decrypt.return_value = {
                    "proxmox": {
                        "api_url": "https://proxmox-dev.example.com",
                        "api_token_id": "dev@pam!token",
                        "api_token_secret": "dev-secret",
                    }
                }

                # Load dev credentials
                load_environment_credentials("dev", config_dir=tmp_path)

                # Verify SOPS_AGE_KEY_FILE was set to dev key
                assert os.environ.get("SOPS_AGE_KEY_FILE") == str(dev_age_key)

            # Clear again
            os.environ.pop("SOPS_AGE_KEY_FILE", None)

            with patch("infrafoundry.core.env_credentials._decrypt_sops_file") as mock_decrypt:
                mock_decrypt.return_value = {
                    "proxmox": {
                        "api_url": "https://proxmox-prod.example.com",
                        "api_token_id": "prod@pam!token",
                        "api_token_secret": "prod-secret",
                    }
                }

                # Load prod credentials
                load_environment_credentials("prod", config_dir=tmp_path)

                # Verify SOPS_AGE_KEY_FILE was set to prod key
                assert os.environ.get("SOPS_AGE_KEY_FILE") == str(prod_age_key)

        finally:
            os.environ.clear()
            os.environ.update(original_env)

    def test_missing_age_key_does_not_set_env_var(self, tmp_path):
        """Test that SOPS_AGE_KEY_FILE is not set if age.key doesn't exist."""
        # Setup directory without age key
        secrets_dir = tmp_path / "secrets" / "dev"
        secrets_dir.mkdir(parents=True)

        # Create encrypted file but no age key
        proxmox_file = secrets_dir / "proxmox.yaml"
        proxmox_file.write_text("encrypted")

        original_env = os.environ.copy()
        try:
            # Set a different SOPS key
            os.environ["SOPS_AGE_KEY_FILE"] = "/some/other/path/age.key"

            with patch("infrafoundry.core.env_credentials._decrypt_sops_file") as mock_decrypt:
                mock_decrypt.return_value = {}

                # Load credentials
                load_environment_credentials("dev", config_dir=tmp_path)

                # SOPS_AGE_KEY_FILE should not have been changed
                assert os.environ.get("SOPS_AGE_KEY_FILE") == "/some/other/path/age.key"

        finally:
            os.environ.clear()
            os.environ.update(original_env)
