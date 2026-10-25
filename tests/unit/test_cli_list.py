"""Unit tests for the 'list' CLI command."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.config import ConfigManager


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_config_manager() -> Mock:
    """Mock ConfigManager for testing."""
    mock = Mock(spec=ConfigManager)
    return mock


@pytest.fixture
def sample_resources() -> list[Any]:
    """Sample resource data."""
    # Create mock resources
    vm1 = Mock()
    vm1.name = "vm-01"
    vm1.provider = "proxmox"
    vm1.type = "vms"

    vm2 = Mock()
    vm2.name = "vm-02"
    vm2.provider = "proxmox"
    vm2.type = "vms"

    firewall = Mock()
    firewall.name = "firewall-01"
    firewall.provider = "opnsense"
    firewall.type = "firewall.rules"

    return [vm1, vm2, firewall]


def test_list_all_resources(
    cli_runner: CliRunner, mock_config_manager: Mock, sample_resources: list[Any]
) -> None:
    """Test list command shows all resources."""
    mock_config_manager.get_all_resources_all_providers.return_value = sample_resources

    with patch(
        "infrafoundry.cli.commands.state.list.ConfigManager", return_value=mock_config_manager
    ):
        result = cli_runner.invoke(main, ["state", "list", "--env", "test"])

        assert result.exit_code == 0
        assert "Resources in test:" in result.output
        assert "vm-01" in result.output
        assert "vm-02" in result.output
        assert "firewall-01" in result.output
        assert "Total: 3 resources" in result.output


def test_list_filter_by_provider(
    cli_runner: CliRunner, mock_config_manager: Mock, sample_resources: list[Any]
) -> None:
    """Test list command with provider filter."""
    mock_config_manager.get_all_resources_all_providers.return_value = sample_resources

    with patch(
        "infrafoundry.cli.commands.state.list.ConfigManager", return_value=mock_config_manager
    ):
        result = cli_runner.invoke(
            main, ["state", "list", "--env", "test", "--provider", "proxmox"]
        )

        assert result.exit_code == 0
        assert "vm-01" in result.output
        assert "vm-02" in result.output
        assert "firewall-01" not in result.output
        assert "Total: 2 resources" in result.output


def test_list_filter_by_type(
    cli_runner: CliRunner, mock_config_manager: Mock, sample_resources: list[Any]
) -> None:
    """Test list command with type filter."""
    mock_config_manager.get_all_resources_all_providers.return_value = sample_resources

    with patch(
        "infrafoundry.cli.commands.state.list.ConfigManager", return_value=mock_config_manager
    ):
        result = cli_runner.invoke(main, ["state", "list", "--env", "test", "--type", "vms"])

        assert result.exit_code == 0
        assert "vm-01" in result.output
        assert "vm-02" in result.output
        assert "firewall-01" not in result.output
        assert "Total: 2 resources" in result.output


def test_list_filter_by_both(
    cli_runner: CliRunner, mock_config_manager: Mock, sample_resources: list[Any]
) -> None:
    """Test list command with both provider and type filters."""
    mock_config_manager.get_all_resources_all_providers.return_value = sample_resources

    with patch(
        "infrafoundry.cli.commands.state.list.ConfigManager", return_value=mock_config_manager
    ):
        result = cli_runner.invoke(
            main, ["state", "list", "--env", "test", "--provider", "proxmox", "--type", "vms"]
        )

        assert result.exit_code == 0
        assert "vm-01" in result.output
        assert "vm-02" in result.output
        assert "Total: 2 resources" in result.output


def test_list_no_resources_found(cli_runner: CliRunner, mock_config_manager: Mock) -> None:
    """Test list command when no resources are found."""
    mock_config_manager.get_all_resources_all_providers.return_value = []

    with patch(
        "infrafoundry.cli.commands.state.list.ConfigManager", return_value=mock_config_manager
    ):
        result = cli_runner.invoke(main, ["state", "list", "--env", "test"])

        assert result.exit_code == 0
        assert "No resources found" in result.output


def test_list_no_matching_provider(
    cli_runner: CliRunner, mock_config_manager: Mock, sample_resources: list[Any]
) -> None:
    """Test list command when provider filter matches nothing."""
    mock_config_manager.get_all_resources_all_providers.return_value = sample_resources

    with patch(
        "infrafoundry.cli.commands.state.list.ConfigManager", return_value=mock_config_manager
    ):
        result = cli_runner.invoke(
            main, ["state", "list", "--env", "test", "--provider", "nonexistent"]
        )

        assert result.exit_code == 0
        assert "No resources found with provider 'nonexistent'" in result.output
