"""Unit tests for the 'infra move-package' CLI command."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.exceptions import PackageNotFoundError


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture for invoking CLI commands."""
    return CliRunner()


def test_required_options(cli_runner: CliRunner) -> None:
    """Required options are enforced."""
    result = cli_runner.invoke(main, ["infra", "move-package"])
    assert result.exit_code != 0
    assert "Missing option" in result.output or "required" in result.output.lower()


def test_requires_config_dir(cli_runner: CliRunner) -> None:
    """Command errors when no config directory is configured."""
    result = cli_runner.invoke(
        main,
        ["infra", "move-package", "--env", "prod", "--package", "foo", "--to-env", "staging"],
    )
    assert result.exit_code != 0
    assert "config" in result.output.lower() or "Error" in result.output


def test_dry_run_shows_actions(cli_runner: CliRunner, tmp_path) -> None:
    """--dry-run shows planned actions via mocked PackageMover."""
    mock_result = {
        "dry_run": True,
        "actions": [
            "Found package 'my-cluster' at /some/path (provider: proxmox)",
            "Move config: /source -> /target",
        ],
        "source_path": "/source",
        "target_path": "/target",
        "provider": "proxmox",
        "state_addresses": [],
    }

    with patch("infrafoundry.cli.commands.infra.move_package.PackageMover") as mock_mover_cls:
        mock_instance = MagicMock()
        mock_instance.execute.return_value = mock_result
        mock_mover_cls.return_value = mock_instance

        result = cli_runner.invoke(
            main,
            [
                "-c",
                str(tmp_path),
                "infra",
                "move-package",
                "--env",
                "prod",
                "--package",
                "my-cluster",
                "--to-env",
                "staging",
                "--dry-run",
            ],
        )

    assert result.exit_code == 0
    assert "dry run" in result.output.lower()


def test_success_with_mocked_mover(cli_runner: CliRunner, tmp_path) -> None:
    """Successful move with mocked PackageMover."""
    mock_result = {
        "dry_run": False,
        "actions": [],
        "source_path": "/source",
        "target_path": "/target",
        "provider": "proxmox",
        "state_addresses": ["proxmox_virtual_environment_vm.web_01"],
        "state_rm_results": [{"address": "proxmox_virtual_environment_vm.web_01", "success": True}],
        "state_db_updated": True,
    }

    with patch("infrafoundry.cli.commands.infra.move_package.PackageMover") as mock_mover_cls:
        mock_instance = MagicMock()
        mock_instance.execute.return_value = mock_result
        mock_mover_cls.return_value = mock_instance

        result = cli_runner.invoke(
            main,
            [
                "-c",
                str(tmp_path),
                "infra",
                "move-package",
                "--env",
                "prod",
                "--package",
                "my-cluster",
                "--to-env",
                "staging",
            ],
        )

    assert result.exit_code == 0
    assert "proxmox" in result.output.lower()


def test_package_not_found_error(cli_runner: CliRunner, tmp_path) -> None:
    """PackageNotFoundError is reported as CLI error."""
    with patch("infrafoundry.cli.commands.infra.move_package.PackageMover") as mock_mover_cls:
        mock_instance = MagicMock()
        mock_instance.execute.side_effect = PackageNotFoundError("Package 'foo' not found")
        mock_mover_cls.return_value = mock_instance

        result = cli_runner.invoke(
            main,
            [
                "-c",
                str(tmp_path),
                "infra",
                "move-package",
                "--env",
                "prod",
                "--package",
                "foo",
                "--to-env",
                "staging",
            ],
        )

    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "Error" in result.output
