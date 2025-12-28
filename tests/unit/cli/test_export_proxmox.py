"""Unit tests for the 'export-proxmox' CLI command."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.commands.proxmox.export_proxmox import export_proxmox


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager for testing."""
    mock = Mock()
    mock_env = Mock()
    mock_env.model_dump.return_value = {
        "provider_settings": {
            "proxmox": {
                "api_url": "https://proxmox.example.com:8006/api2/json",
                "api_token_id": "user@pam!token",
                "api_token_secret": "secret-value",
            }
        }
    }
    mock.load_environment.return_value = mock_env
    return mock


@pytest.fixture
def mock_exporter():
    """Mock ProxmoxConfigExporter for testing."""
    mock = Mock()
    mock.export.return_value = {
        "pve1-vms.yaml": "vm: content",
        "pve1-networks.yaml": "network: content",
        "storage.yaml": "storage: content",
    }
    return mock


def test_export_proxmox_success(cli_runner, tmp_path, mock_config_manager, mock_exporter):
    """Test successful Proxmox configuration export."""
    output_dir = tmp_path / "output"

    with (
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ConfigManager",
            return_value=mock_config_manager,
        ),
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ProxmoxConfigExporter",
            return_value=mock_exporter,
        ),
    ):
        result = cli_runner.invoke(
            export_proxmox,
            ["--env", "dev", "--output", str(output_dir)],
            obj={"config_dir": Path("/fake/config")},
        )

        assert result.exit_code == 0
        assert "Exported 3 files" in result.output
        assert str(output_dir) in result.output

        # Verify output directory was created and files were written
        assert output_dir.exists()
        assert (output_dir / "pve1-vms.yaml").read_text() == "vm: content"
        assert (output_dir / "pve1-networks.yaml").read_text() == "network: content"
        assert (output_dir / "storage.yaml").read_text() == "storage: content"


def test_export_proxmox_with_node_filter(cli_runner, tmp_path, mock_config_manager, mock_exporter):
    """Test export with node filter."""
    output_dir = tmp_path / "output"

    with (
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ConfigManager",
            return_value=mock_config_manager,
        ),
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ProxmoxConfigExporter",
            return_value=mock_exporter,
        ),
    ):
        result = cli_runner.invoke(
            export_proxmox,
            ["--env", "dev", "--output", str(output_dir), "--node", "pve1"],
            obj={"config_dir": Path("/fake/config")},
        )

        assert result.exit_code == 0
        mock_exporter.export.assert_called_once_with(node_filter="pve1", resource_filter=None)


def test_export_proxmox_with_resource_type_filter(
    cli_runner, tmp_path, mock_config_manager, mock_exporter
):
    """Test export with resource type filter."""
    output_dir = tmp_path / "output"

    with (
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ConfigManager",
            return_value=mock_config_manager,
        ),
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ProxmoxConfigExporter",
            return_value=mock_exporter,
        ),
    ):
        result = cli_runner.invoke(
            export_proxmox,
            ["--env", "dev", "--output", str(output_dir), "--resource-type", "vm"],
            obj={"config_dir": Path("/fake/config")},
        )

        assert result.exit_code == 0
        mock_exporter.export.assert_called_once_with(node_filter=None, resource_filter="vm")


def test_export_proxmox_with_both_filters(cli_runner, tmp_path, mock_config_manager, mock_exporter):
    """Test export with both node and resource type filters."""
    output_dir = tmp_path / "output"

    with (
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ConfigManager",
            return_value=mock_config_manager,
        ),
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ProxmoxConfigExporter",
            return_value=mock_exporter,
        ),
    ):
        result = cli_runner.invoke(
            export_proxmox,
            [
                "--env",
                "dev",
                "--output",
                str(output_dir),
                "--node",
                "pve2",
                "--resource-type",
                "network",
            ],
            obj={"config_dir": Path("/fake/config")},
        )

        assert result.exit_code == 0
        mock_exporter.export.assert_called_once_with(node_filter="pve2", resource_filter="network")


def test_export_proxmox_missing_env(cli_runner, tmp_path):
    """Test export fails when --env is not provided."""
    output_dir = tmp_path / "output"

    result = cli_runner.invoke(
        export_proxmox,
        ["--output", str(output_dir)],
        obj={"config_dir": Path("/fake/config")},
    )

    assert result.exit_code != 0
    assert "Missing option '--env'" in result.output or "Error" in result.output


def test_export_proxmox_missing_output(cli_runner):
    """Test export fails when --output is not provided."""
    result = cli_runner.invoke(
        export_proxmox,
        ["--env", "dev"],
        obj={"config_dir": Path("/fake/config")},
    )

    assert result.exit_code != 0
    assert "Missing option '--output'" in result.output or "Error" in result.output


def test_export_proxmox_creates_output_directory(
    cli_runner, tmp_path, mock_config_manager, mock_exporter
):
    """Test export creates output directory if it doesn't exist."""
    output_dir = tmp_path / "nested" / "output" / "dir"
    assert not output_dir.exists()

    with (
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ConfigManager",
            return_value=mock_config_manager,
        ),
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ProxmoxConfigExporter",
            return_value=mock_exporter,
        ),
    ):
        result = cli_runner.invoke(
            export_proxmox,
            ["--env", "dev", "--output", str(output_dir)],
            obj={"config_dir": Path("/fake/config")},
        )

        assert result.exit_code == 0
        assert output_dir.exists()


def test_export_proxmox_handles_exporter_error(cli_runner, tmp_path, mock_config_manager):
    """Test export handles exporter errors gracefully."""
    output_dir = tmp_path / "output"

    mock_exporter = Mock()
    mock_exporter.export.side_effect = Exception("API connection failed")

    with (
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ConfigManager",
            return_value=mock_config_manager,
        ),
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ProxmoxConfigExporter",
            return_value=mock_exporter,
        ),
    ):
        result = cli_runner.invoke(
            export_proxmox,
            ["--env", "dev", "--output", str(output_dir)],
            obj={"config_dir": Path("/fake/config")},
        )

        assert result.exit_code != 0
        assert "Failed to export Proxmox configuration" in result.output


def test_export_proxmox_handles_config_load_error(cli_runner, tmp_path):
    """Test export handles configuration load errors."""
    output_dir = tmp_path / "output"

    mock_config_manager = Mock()
    mock_config_manager.load_environment.side_effect = Exception("Environment not found")

    with patch(
        "infrafoundry.cli.commands.proxmox.export_proxmox.ConfigManager", return_value=mock_config_manager
    ):
        result = cli_runner.invoke(
            export_proxmox,
            ["--env", "nonexistent", "--output", str(output_dir)],
            obj={"config_dir": Path("/fake/config")},
        )

        assert result.exit_code != 0
        assert "Failed to export Proxmox configuration" in result.output


def test_export_proxmox_without_config_dir(cli_runner, tmp_path, mock_exporter):
    """Test export works without config_dir in context."""
    output_dir = tmp_path / "output"

    mock_config_manager = Mock()
    mock_env = Mock()
    mock_env.model_dump.return_value = {
        "provider_settings": {
            "proxmox": {
                "api_url": "https://proxmox.example.com:8006/api2/json",
                "api_token": "token",
            }
        }
    }
    mock_config_manager.load_environment.return_value = mock_env

    with (
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ConfigManager",
            return_value=mock_config_manager,
        ),
        patch(
            "infrafoundry.cli.commands.proxmox.export_proxmox.ProxmoxConfigExporter",
            return_value=mock_exporter,
        ),
    ):
        result = cli_runner.invoke(
            export_proxmox,
            ["--env", "dev", "--output", str(output_dir)],
            obj={},  # Empty context, no config_dir
        )

        assert result.exit_code == 0


def test_export_proxmox_invalid_resource_type(cli_runner, tmp_path):
    """Test export rejects invalid resource type."""
    output_dir = tmp_path / "output"

    result = cli_runner.invoke(
        export_proxmox,
        ["--env", "dev", "--output", str(output_dir), "--resource-type", "invalid"],
        obj={"config_dir": Path("/fake/config")},
    )

    assert result.exit_code != 0
    assert "Invalid value for '--resource-type'" in result.output or "Error" in result.output
