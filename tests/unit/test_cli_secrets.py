"""Unit tests for the 'secrets' CLI command group."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


def test_secrets_init_basic(cli_runner, tmp_path):
    """Test secrets init command."""
    key_file = tmp_path / "age.key"

    # Mock subprocess.run for age-keygen
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = "# public key: age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    with patch("subprocess.run", return_value=mock_result):
        with patch("infrafoundry.cli.commands.secrets.secrets.create_sops_config"):
            result = cli_runner.invoke(main, ["secrets", "init", "--key-file", str(key_file)])

            assert result.exit_code == 0
            assert "Created age key:" in result.output
            assert "Created .sops.yaml" in result.output


def test_secrets_init_key_exists(cli_runner, tmp_path):
    """Test secrets init when key file already exists."""
    key_file = tmp_path / "age.key"
    key_file.touch()

    result = cli_runner.invoke(main, ["secrets", "init", "--key-file", str(key_file)])

    assert result.exit_code == 0
    assert "Key file already exists" in result.output


def test_secrets_init_age_keygen_failure(cli_runner, tmp_path):
    """Test secrets init when age-keygen fails."""
    key_file = tmp_path / "age.key"

    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "age-keygen: command not found"

    with patch("subprocess.run", return_value=mock_result):
        result = cli_runner.invoke(main, ["secrets", "init", "--key-file", str(key_file)])

        assert result.exit_code != 0
        assert "Failed to generate key" in result.output


def test_secrets_encrypt_basic(cli_runner, tmp_path):
    """Test secrets encrypt command."""
    test_file = tmp_path / "test.yaml"
    test_file.write_text("secret: value")

    # Mock subprocess.run for sops
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        result = cli_runner.invoke(main, ["secrets", "encrypt", str(test_file)])

        assert result.exit_code == 0
        assert "Encrypted:" in result.output


def test_secrets_encrypt_file_not_found(cli_runner, tmp_path):
    """Test secrets encrypt when file doesn't exist."""
    nonexistent_file = tmp_path / "nonexistent.yaml"

    result = cli_runner.invoke(main, ["secrets", "encrypt", str(nonexistent_file)])

    assert result.exit_code != 0
    assert "File not found" in result.output


def test_secrets_encrypt_sops_failure(cli_runner, tmp_path):
    """Test secrets encrypt when sops fails."""
    test_file = tmp_path / "test.yaml"
    test_file.write_text("secret: value")

    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "sops: error: no key found"

    with patch("subprocess.run", return_value=mock_result):
        result = cli_runner.invoke(main, ["secrets", "encrypt", str(test_file)])

        assert result.exit_code != 0
        assert "Encryption failed" in result.output


def test_secrets_decrypt_basic(cli_runner, tmp_path):
    """Test secrets decrypt command."""
    test_file = tmp_path / "test.yaml"
    test_file.write_text("encrypted content")

    # Mock subprocess.run for sops
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "secret: value\n"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        result = cli_runner.invoke(main, ["secrets", "decrypt", str(test_file)])

        assert result.exit_code == 0
        assert "secret: value" in result.output


def test_secrets_decrypt_file_not_found(cli_runner, tmp_path):
    """Test secrets decrypt when file doesn't exist."""
    nonexistent_file = tmp_path / "nonexistent.yaml"

    result = cli_runner.invoke(main, ["secrets", "decrypt", str(nonexistent_file)])

    assert result.exit_code != 0
    assert "File not found" in result.output


def test_secrets_decrypt_sops_failure(cli_runner, tmp_path):
    """Test secrets decrypt when sops fails."""
    test_file = tmp_path / "test.yaml"
    test_file.write_text("encrypted content")

    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "sops: error: failed to decrypt"

    with patch("subprocess.run", return_value=mock_result):
        result = cli_runner.invoke(main, ["secrets", "decrypt", str(test_file)])

        assert result.exit_code != 0
        assert "Decryption failed" in result.output
