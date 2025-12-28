"""Unit tests for the 'diff' CLI command."""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.config.diff import ConfigDiffResult


def _make_result(
    env_a: str,
    env_b: str,
    settings: list[str],
    added: list[str],
    removed: list[str],
    changed: list[str],
    changed_details: dict[str, list[str]] | None = None,
) -> ConfigDiffResult:
    return ConfigDiffResult(
        env_a=env_a,
        env_b=env_b,
        settings_changes=settings,
        resources_added=added,
        resources_removed=removed,
        resources_changed=changed,
        resources_changed_details=changed_details or {},
    )


def test_diff_no_changes():
    """Diff command reports when no differences exist."""
    runner = CliRunner()

    with (
        patch("infrafoundry.cli.commands.config.diff.ConfigManager") as mock_cm,
        patch("infrafoundry.cli.commands.config.diff.diff_environments") as mock_diff,
    ):
        mock_cm.return_value = Mock()
        mock_diff.return_value = _make_result("dev", "prod", [], [], [], [])

        result = runner.invoke(main, ["config", "diff", "--env-a", "dev", "--env-b", "prod"])

        assert result.exit_code == 0
        assert "No differences found." in result.output


def test_diff_with_changes():
    """Diff command outputs settings and resource changes."""
    runner = CliRunner()

    with (
        patch("infrafoundry.cli.commands.config.diff.ConfigManager") as mock_cm,
        patch("infrafoundry.cli.commands.config.diff.diff_environments") as mock_diff,
    ):
        mock_cm.return_value = Mock()
        mock_diff.return_value = _make_result(
            "dev",
            "prod",
            settings=['variables: {"version": "1"} -> {"version": "2"}'],
            added=["proxmox:vm-new"],
            removed=["proxmox:vm-old"],
            changed=["proxmox:vm-changed"],
        )

        result = runner.invoke(main, ["config", "diff", "--env-a", "dev", "--env-b", "prod"])

        assert result.exit_code == 0
        assert "Settings differences" in result.output
        assert "Resources only in prod" in result.output
        assert "Resources only in dev" in result.output
        assert "Resources changed" in result.output


def test_diff_with_nonexistent_environment():
    """Diff command handles nonexistent environment gracefully."""
    from infrafoundry.core.exceptions import EnvironmentNotFoundError

    runner = CliRunner()

    with (
        patch("infrafoundry.cli.commands.config.diff.ConfigManager") as mock_cm,
        patch("infrafoundry.cli.commands.config.diff.diff_environments") as mock_diff,
    ):
        mock_cm.return_value = Mock()
        mock_diff.side_effect = EnvironmentNotFoundError("Environment 'nonexistent' not found")

        result = runner.invoke(
            main, ["config", "diff", "--env-a", "nonexistent", "--env-b", "prod"]
        )

        assert result.exit_code == 1
        assert "Failed to diff configurations" in result.output


def test_diff_with_verbose_mode():
    """Diff command shows detailed changes in verbose mode."""
    runner = CliRunner()

    with (
        patch("infrafoundry.cli.commands.config.diff.ConfigManager") as mock_cm,
        patch("infrafoundry.cli.commands.config.diff.diff_environments") as mock_diff,
    ):
        mock_cm.return_value = Mock()
        mock_diff.return_value = _make_result(
            "dev",
            "prod",
            settings=[],
            added=[],
            removed=[],
            changed=["proxmox:vm-web"],
            changed_details={
                "proxmox:vm-web": [
                    "cpu: 2 -> 4",
                    "memory: 8192 -> 16384",
                ]
            },
        )

        result = runner.invoke(
            main, ["config", "diff", "--env-a", "dev", "--env-b", "prod", "--verbose"]
        )

        assert result.exit_code == 0
        assert "Resources changed" in result.output
        assert "proxmox:vm-web" in result.output
        assert "cpu: 2 -> 4" in result.output
        assert "memory: 8192 -> 16384" in result.output
