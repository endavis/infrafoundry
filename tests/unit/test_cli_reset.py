"""Unit tests for the 'reset' CLI command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.orchestrator import Orchestrator


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_orchestrator():
    """Mock orchestrator for testing."""
    mock = Mock(spec=Orchestrator)
    mock.providers = {}
    return mock


@pytest.fixture
def mock_opnsense_provider():
    """Mock OPNsense provider."""
    from infrafoundry.providers.opnsense import OPNsenseProvider

    mock = Mock(spec=OPNsenseProvider)
    return mock


def test_reset_dhcpv4_with_auto_approve(cli_runner, mock_orchestrator, mock_opnsense_provider):
    """Test reset command for DHCPv4 with auto-approve."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "reset",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea/dhcpv4",
                "--auto-approve",
            ],
        )

        assert result.exit_code == 0
        assert "Reset complete!" in result.output
        mock_opnsense_provider.reset_kea_dhcpv4.assert_called_once_with("test")
        mock_opnsense_provider.reset_kea_dhcpv6.assert_not_called()


def test_reset_dhcpv6_with_auto_approve(cli_runner, mock_orchestrator, mock_opnsense_provider):
    """Test reset command for DHCPv6 with auto-approve."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "reset",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea/dhcpv6",
                "--auto-approve",
            ],
        )

        assert result.exit_code == 0
        assert "Reset complete!" in result.output
        mock_opnsense_provider.reset_kea_dhcpv4.assert_not_called()
        mock_opnsense_provider.reset_kea_dhcpv6.assert_called_once_with("test")


def test_reset_both_dhcp_versions(cli_runner, mock_orchestrator, mock_opnsense_provider):
    """Test reset command for both DHCPv4 and DHCPv6."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "reset",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea/dhcp",
                "--auto-approve",
            ],
        )

        assert result.exit_code == 0
        assert "Reset complete!" in result.output
        mock_opnsense_provider.reset_kea_dhcpv4.assert_called_once_with("test")
        mock_opnsense_provider.reset_kea_dhcpv6.assert_called_once_with("test")


def test_reset_with_confirmation(cli_runner, mock_orchestrator, mock_opnsense_provider):
    """Test reset command with user confirmation."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        # User confirms
        result = cli_runner.invoke(
            main,
            [
                "reset",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea/dhcpv4",
            ],
            input="y\n",
        )

        assert result.exit_code == 0
        assert "Reset complete!" in result.output
        mock_opnsense_provider.reset_kea_dhcpv4.assert_called_once()


def test_reset_user_cancels(cli_runner, mock_orchestrator, mock_opnsense_provider):
    """Test reset command when user cancels."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        # User cancels
        result = cli_runner.invoke(
            main,
            [
                "reset",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea/dhcpv4",
            ],
            input="n\n",
        )

        assert result.exit_code == 0
        assert "Reset cancelled." in result.output
        mock_opnsense_provider.reset_kea_dhcpv4.assert_not_called()


def test_reset_provider_not_found(cli_runner, mock_orchestrator):
    """Test reset command when provider is not found."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "reset",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea/dhcpv4",
                "--auto-approve",
            ],
        )

        assert result.exit_code != 0
        assert "OPNsense provider not found" in result.output
