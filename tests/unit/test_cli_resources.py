"""Unit tests for the 'resources' CLI command."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.state import ResourceState


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_orchestrator():
    """Mock orchestrator for testing."""
    mock = Mock(spec=Orchestrator)
    mock.state_manager = Mock()
    return mock


@pytest.fixture
def sample_resources():
    """Sample resource data."""
    resource1 = Mock()
    resource1.environment = "test"
    resource1.provider = "proxmox"
    resource1.resource_type = "vm"
    resource1.name = "vm-01"
    resource1.state = ResourceState.ACTIVE
    resource1.terraform_id = "proxmox_vm_qemu.vm-01"
    resource1.updated_at = datetime(2025, 1, 1, 10, 0, 0)

    resource2 = Mock()
    resource2.environment = "prod"
    resource2.provider = "opnsense"
    resource2.resource_type = "firewall_rule"
    resource2.name = "allow-http"
    resource2.state = ResourceState.ACTIVE
    resource2.terraform_id = None
    resource2.updated_at = datetime(2025, 1, 2, 11, 0, 0)

    return [resource1, resource2]


def test_resources_list_all(cli_runner, mock_orchestrator, sample_resources):
    """Test resources command lists all resources."""
    mock_orchestrator.state_manager.get_resources.return_value = sample_resources

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["state", "resources"])

        assert result.exit_code == 0
        assert "Infrastructure Resources" in result.output
        assert "vm-01" in result.output
        # Rich may truncate long names in tables, so check for partial match
        assert "allow" in result.output or "http" in result.output
        assert "Total: 2 resource(s)" in result.output
        mock_orchestrator.state_manager.get_resources.assert_called_once_with(
            environment=None,
            provider=None,
            resource_type=None,
            state=None,
        )


def test_resources_filter_by_environment(cli_runner, mock_orchestrator, sample_resources):
    """Test resources command with environment filter."""
    mock_orchestrator.state_manager.get_resources.return_value = [sample_resources[0]]

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["state", "resources", "--env", "test"])

        assert result.exit_code == 0
        mock_orchestrator.state_manager.get_resources.assert_called_once_with(
            environment="test",
            provider=None,
            resource_type=None,
            state=None,
        )


def test_resources_filter_by_provider(cli_runner, mock_orchestrator, sample_resources):
    """Test resources command with provider filter."""
    mock_orchestrator.state_manager.get_resources.return_value = [sample_resources[0]]

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["state", "resources", "--provider", "proxmox"])

        assert result.exit_code == 0
        mock_orchestrator.state_manager.get_resources.assert_called_once_with(
            environment=None,
            provider="proxmox",
            resource_type=None,
            state=None,
        )


def test_resources_filter_by_type(cli_runner, mock_orchestrator, sample_resources):
    """Test resources command with type filter."""
    mock_orchestrator.state_manager.get_resources.return_value = [sample_resources[0]]

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["state", "resources", "--type", "vm"])

        assert result.exit_code == 0
        mock_orchestrator.state_manager.get_resources.assert_called_once_with(
            environment=None,
            provider=None,
            resource_type="vm",
            state=None,
        )


def test_resources_filter_by_state(cli_runner, mock_orchestrator, sample_resources):
    """Test resources command with state filter."""
    mock_orchestrator.state_manager.get_resources.return_value = sample_resources

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["state", "resources", "--state", "ACTIVE"])

        assert result.exit_code == 0
        # Check that ACTIVE state appears somewhere in the output
        assert "ACTIVE" in result.output
        call_args = mock_orchestrator.state_manager.get_resources.call_args[1]
        assert call_args["state"] == ResourceState.ACTIVE


def test_resources_no_resources_found(cli_runner, mock_orchestrator):
    """Test resources command when no resources are found."""
    mock_orchestrator.state_manager.get_resources.return_value = []

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["state", "resources"])

        assert result.exit_code == 0
        assert "No resources found matching filters" in result.output


def test_resources_invalid_state(cli_runner, mock_orchestrator):
    """Test resources command with invalid state."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["state", "resources", "--state", "INVALID"])

        assert result.exit_code != 0
        assert "Invalid state" in result.output
