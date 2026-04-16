"""Tests for the shared SOPS decryption utility and SopsSecretProvider."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from infrafoundry.core.config.sops import load_yaml_with_sops, save_yaml_with_sops
from infrafoundry.core.secrets.providers.sops import SopsSecretProvider


class TestLoadYamlWithSops:
    """Tests for load_yaml_with_sops function."""

    def test_plain_yaml_loaded_directly(self, tmp_path: Path) -> None:
        """Plain YAML files are loaded without calling sops."""
        yaml_file = tmp_path / "plain.yaml"
        yaml_file.write_text("key: value\nnested:\n  foo: bar\n")

        result = load_yaml_with_sops(yaml_file)

        assert result == {"key": "value", "nested": {"foo": "bar"}}

    def test_empty_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """Empty YAML file returns empty dict."""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")

        result = load_yaml_with_sops(yaml_file)

        assert result == {}

    def test_sops_encrypted_file_triggers_decrypt(self, tmp_path: Path) -> None:
        """Files with SOPS markers trigger sops --decrypt subprocess call."""
        yaml_file = tmp_path / "encrypted.yaml"
        sops_content = "key: ENC[AES256_GCM,data:abc123]\nsops:\n    version: 3.7.3\n"
        yaml_file.write_text(sops_content)

        decrypted_yaml = "key: decrypted-value\n"
        mock_result = type("Result", (), {"stdout": decrypted_yaml, "returncode": 0})()

        with patch(
            "infrafoundry.core.config.sops.subprocess.run", return_value=mock_result
        ) as mock_run:
            result = load_yaml_with_sops(yaml_file)

        mock_run.assert_called_once_with(
            ["sops", "--decrypt", str(yaml_file)],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result == {"key": "decrypted-value"}

    def test_file_with_only_sops_marker_not_encrypted(self, tmp_path: Path) -> None:
        """File with 'sops:' but no ENC marker is treated as plain YAML."""
        yaml_file = tmp_path / "not-encrypted.yaml"
        yaml_file.write_text("sops:\n  note: 'this is not actually encrypted'\n")

        with patch("infrafoundry.core.config.sops.subprocess.run") as mock_run:
            result = load_yaml_with_sops(yaml_file)

        mock_run.assert_not_called()
        assert result == {"sops": {"note": "this is not actually encrypted"}}

    def test_file_with_only_enc_marker_not_encrypted(self, tmp_path: Path) -> None:
        """File with ENC marker but no 'sops:' key is treated as plain YAML."""
        yaml_file = tmp_path / "not-encrypted.yaml"
        yaml_file.write_text("key: 'ENC[AES256_GCM,data:abc]'\n")

        with patch("infrafoundry.core.config.sops.subprocess.run") as mock_run:
            result = load_yaml_with_sops(yaml_file)

        mock_run.assert_not_called()
        assert result == {"key": "ENC[AES256_GCM,data:abc]"}

    def test_sops_decrypt_returns_empty_yaml(self, tmp_path: Path) -> None:
        """SOPS decryption that returns empty content returns empty dict."""
        yaml_file = tmp_path / "encrypted.yaml"
        yaml_file.write_text("key: ENC[AES256_GCM,data:x]\nsops:\n  v: 1\n")

        mock_result = type("Result", (), {"stdout": "", "returncode": 0})()

        with patch("infrafoundry.core.config.sops.subprocess.run", return_value=mock_result):
            result = load_yaml_with_sops(yaml_file)

        assert result == {}


class TestSaveYamlWithSops:
    """Tests for save_yaml_with_sops function."""

    def test_save_yaml_with_sops_no_encrypt(self, tmp_path: Path) -> None:
        """Plain YAML is written without calling sops when encrypt is False."""
        yaml_file = tmp_path / "output.yaml"
        data = {"name": "staging", "description": "Staging env"}

        with patch("infrafoundry.core.config.sops.subprocess.run") as mock_run:
            save_yaml_with_sops(yaml_file, data)

        mock_run.assert_not_called()
        assert yaml_file.exists()
        content = yaml_file.read_text()
        assert "name: staging" in content
        assert "description: Staging env" in content

    def test_save_yaml_with_sops_with_encrypt(self, tmp_path: Path) -> None:
        """SOPS encrypt is called when encrypt is True."""
        yaml_file = tmp_path / "output.yaml"
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        data = {"name": "staging", "providers": ["proxmox"]}

        mock_result = type("Result", (), {"stdout": "", "returncode": 0})()

        with patch(
            "infrafoundry.core.config.sops.subprocess.run", return_value=mock_result
        ) as mock_run:
            save_yaml_with_sops(yaml_file, data, encrypt=True, config_dir=config_dir)

        mock_run.assert_called_once_with(
            ["sops", "--encrypt", "--in-place", str(yaml_file)],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(config_dir),
        )
        # File should exist (written before encrypt call)
        assert yaml_file.exists()

    def test_save_yaml_with_sops_encrypt_failure(self, tmp_path: Path) -> None:
        """CalledProcessError is raised when sops encryption fails."""
        yaml_file = tmp_path / "output.yaml"
        data = {"name": "staging"}

        with patch(
            "infrafoundry.core.config.sops.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "sops", stderr="encryption failed"),
        ):
            try:
                save_yaml_with_sops(yaml_file, data, encrypt=True)
                raise AssertionError("Expected CalledProcessError")
            except subprocess.CalledProcessError:
                pass

    def test_save_yaml_with_sops_encrypt_no_config_dir(self, tmp_path: Path) -> None:
        """SOPS encrypt passes cwd=None when config_dir is not provided."""
        yaml_file = tmp_path / "output.yaml"
        data = {"name": "staging"}

        mock_result = type("Result", (), {"stdout": "", "returncode": 0})()

        with patch(
            "infrafoundry.core.config.sops.subprocess.run", return_value=mock_result
        ) as mock_run:
            save_yaml_with_sops(yaml_file, data, encrypt=True)

        mock_run.assert_called_once_with(
            ["sops", "--encrypt", "--in-place", str(yaml_file)],
            capture_output=True,
            text=True,
            check=True,
            cwd=None,
        )


class TestSopsSecretProvider:
    """Tests for SopsSecretProvider plaintext detection and load_secret."""

    def test_is_sops_encrypted_both_markers(self) -> None:
        """Content with both sops: and ENC markers is detected as encrypted."""
        content = "key: ENC[AES256_GCM,data:abc]\nsops:\n  version: 3.7.3\n"
        assert SopsSecretProvider._is_sops_encrypted(content) is True

    def test_is_sops_encrypted_only_sops_marker(self) -> None:
        """Content with only sops: marker is not encrypted."""
        content = "sops:\n  note: not encrypted\n"
        assert SopsSecretProvider._is_sops_encrypted(content) is False

    def test_is_sops_encrypted_only_enc_marker(self) -> None:
        """Content with only ENC marker is not encrypted."""
        content = "key: 'ENC[AES256_GCM,data:abc]'\n"
        assert SopsSecretProvider._is_sops_encrypted(content) is False

    def test_is_sops_encrypted_plaintext(self) -> None:
        """Plain YAML content is not encrypted."""
        content = "key: value\nnested:\n  foo: bar\n"
        assert SopsSecretProvider._is_sops_encrypted(content) is False

    def test_load_secret_plaintext_yaml(self, tmp_path: Path) -> None:
        """Plaintext YAML file is loaded directly without subprocess call."""
        yaml_file = tmp_path / "plain.yaml"
        yaml_file.write_text("variables:\n  host: localhost\n")

        provider = SopsSecretProvider()

        with patch("infrafoundry.core.secrets.providers.sops.subprocess.run") as mock_run:
            result = provider.load_secret(yaml_file)

        mock_run.assert_not_called()
        assert result == {"variables": {"host": "localhost"}}

    def test_load_secret_encrypted_yaml(self, tmp_path: Path) -> None:
        """Encrypted YAML file calls sops --decrypt."""
        yaml_file = tmp_path / "encrypted.yaml"
        sops_content = "key: ENC[AES256_GCM,data:abc]\nsops:\n  version: 3.7.3\n"
        yaml_file.write_text(sops_content)

        decrypted_yaml = "key: decrypted-value\n"
        mock_result = type("Result", (), {"stdout": decrypted_yaml, "returncode": 0})()

        provider = SopsSecretProvider()

        with (
            patch("shutil.which", return_value="/usr/bin/sops"),
            patch(
                "infrafoundry.core.secrets.providers.sops.subprocess.run",
                return_value=mock_result,
            ) as mock_run,
        ):
            result = provider.load_secret(yaml_file)

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["/usr/bin/sops", "--decrypt", str(yaml_file)]
        assert result == {"key": "decrypted-value"}

    def test_plaintext_works_without_sops_installed(self, tmp_path: Path) -> None:
        """Plaintext detection skips sops check, so missing sops doesn't matter."""
        yaml_file = tmp_path / "plain.yaml"
        yaml_file.write_text("database:\n  host: db.local\n  port: 5432\n")

        provider = SopsSecretProvider()

        # sops is not installed (shutil.which returns None)
        with patch("shutil.which", return_value=None):
            result = provider.load_secret(yaml_file)

        assert result == {"database": {"host": "db.local", "port": 5432}}
