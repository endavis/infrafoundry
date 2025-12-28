"""Unit tests for the 'envs' CLI command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.config import ConfigManager, EnvironmentConfig


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager for testing."""
    mock = Mock(spec=ConfigManager)
    return mock


def test_envs_list_environments(cli_runner, mock_config_manager):
    """Test envs command lists available environments."""
    # Mock environment data
    mock_env1 = Mock(spec=EnvironmentConfig)
    mock_env1.description = "Test environment"
    mock_env1.providers = ["proxmox", "opnsense"]

    mock_env2 = Mock(spec=EnvironmentConfig)
    mock_env2.description = "Production environment"
    mock_env2.providers = ["proxmox", "opnsense", "kubernetes"]

    mock_config_manager.list_environments.return_value = ["test", "prod"]
    mock_config_manager.load_environment.side_effect = [mock_env1, mock_env2]

    with patch(
        "infrafoundry.cli.commands.config.envs.ConfigManager", return_value=mock_config_manager
    ):
        result = cli_runner.invoke(main, ["config", "envs"])

        assert result.exit_code == 0
        assert "Available environments:" in result.output
        assert "test: Test environment" in result.output
        assert "prod: Production environment" in result.output
        assert "proxmox, opnsense" in result.output


def test_envs_no_environments(cli_runner, mock_config_manager):
    """Test envs command when no environments are found."""
    mock_config_manager.list_environments.return_value = []

    with patch(
        "infrafoundry.cli.commands.config.envs.ConfigManager", return_value=mock_config_manager
    ):
        result = cli_runner.invoke(main, ["config", "envs"])

        assert result.exit_code == 0
        assert "No environments found" in result.output


def test_envs_with_config_dir(cli_runner, mock_config_manager, tmp_path):
    """Test envs command with custom config directory."""
    mock_config_manager.list_environments.return_value = ["test"]
    mock_env = Mock(spec=EnvironmentConfig)
    mock_env.description = "Test environment"
    mock_env.providers = ["proxmox"]
    mock_config_manager.load_environment.return_value = mock_env

    with patch(
        "infrafoundry.cli.commands.config.envs.ConfigManager", return_value=mock_config_manager
    ):
        result = cli_runner.invoke(
            main,
            ["--config-dir", str(tmp_path), "config", "envs"],
        )

        assert result.exit_code == 0
        assert "Available environments:" in result.output


def test_envs_no_description(cli_runner, mock_config_manager):
    """Test envs command when environment has no description."""
    mock_env = Mock(spec=EnvironmentConfig)
    mock_env.description = None
    mock_env.providers = ["proxmox"]

    mock_config_manager.list_environments.return_value = ["test"]
    mock_config_manager.load_environment.return_value = mock_env

    with patch(
        "infrafoundry.cli.commands.config.envs.ConfigManager", return_value=mock_config_manager
    ):
        result = cli_runner.invoke(main, ["config", "envs"])

        assert result.exit_code == 0
        assert "test: No description" in result.output
