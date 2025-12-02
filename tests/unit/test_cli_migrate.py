"""Unit tests for the 'migrate' CLI command."""

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
    mock.migrate_kea_dhcp.return_value = "# Migrated Kea DHCP config\ndhcp: []"
    mock.migrate_isc_to_kea.return_value = "# Migrated ISC to Kea config\ndhcp: []"
    return mock


def test_migrate_kea_dhcp(cli_runner, mock_orchestrator, mock_opnsense_provider, tmp_path):
    """Test migrate command for Kea DHCP."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "migrated-kea-dhcp.yaml"

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea/dhcp",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0
        assert "Migration complete!" in result.output
        assert output_file.exists()
        mock_opnsense_provider.migrate_kea_dhcp.assert_called_once_with("test")


def test_migrate_isc_to_kea(cli_runner, mock_orchestrator, mock_opnsense_provider, tmp_path):
    """Test migrate command for ISC to Kea DHCP."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "migrated-isc-to-kea.yaml"

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "isc-to-kea",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0
        assert "Migration complete!" in result.output
        assert output_file.exists()
        mock_opnsense_provider.migrate_isc_to_kea.assert_called_once_with("test", None)


def test_migrate_with_interfaces(cli_runner, mock_orchestrator, mock_opnsense_provider, tmp_path):
    """Test migrate command with specific interfaces."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "migrated-interfaces.yaml"

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "isc-to-kea",
                "-i",
                "lan",
                "-i",
                "wan",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0
        assert output_file.exists()
        mock_opnsense_provider.migrate_isc_to_kea.assert_called_once_with("test", ["lan", "wan"])


def test_migrate_with_dry_run(cli_runner, mock_orchestrator, mock_opnsense_provider, tmp_path):
    """Test migrate command with dry-run flag."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "dry-run-output.yaml"

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea/dhcp",
                "--output",
                str(output_file),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Dry-run mode" in result.output
        assert "Generated configuration:" in result.output
        assert "Migration complete!" in result.output
        # In dry-run mode, file should not be created
        assert not output_file.exists()


def test_migrate_with_custom_output(
    cli_runner, mock_orchestrator, mock_opnsense_provider, tmp_path
):
    """Test migrate command with custom output path."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "custom-output.yaml"

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea/dhcp",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Configuration written to:" in result.output


def test_migrate_provider_not_found(cli_runner, mock_orchestrator, tmp_path):
    """Test migrate command when provider is not found."""
    output_file = tmp_path / "should-not-exist.yaml"

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea/dhcp",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code != 0
        assert "OPNsense provider not found" in result.output
        assert not output_file.exists()
