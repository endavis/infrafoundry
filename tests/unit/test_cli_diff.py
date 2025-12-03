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
) -> ConfigDiffResult:
    return ConfigDiffResult(
        env_a=env_a,
        env_b=env_b,
        settings_changes=settings,
        resources_added=added,
        resources_removed=removed,
        resources_changed=changed,
    )


def test_diff_no_changes():
    """Diff command reports when no differences exist."""
    runner = CliRunner()

    with (
        patch("infrafoundry.cli.commands.diff.ConfigManager") as mock_cm,
        patch("infrafoundry.cli.commands.diff.diff_environments") as mock_diff,
    ):
        mock_cm.return_value = Mock()
        mock_diff.return_value = _make_result("dev", "prod", [], [], [], [])

        result = runner.invoke(main, ["diff", "--env-a", "dev", "--env-b", "prod"])

        assert result.exit_code == 0
        assert "No differences found." in result.output


def test_diff_with_changes():
    """Diff command outputs settings and resource changes."""
    runner = CliRunner()

    with (
        patch("infrafoundry.cli.commands.diff.ConfigManager") as mock_cm,
        patch("infrafoundry.cli.commands.diff.diff_environments") as mock_diff,
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

        result = runner.invoke(main, ["diff", "--env-a", "dev", "--env-b", "prod"])

        assert result.exit_code == 0
        assert "Settings differences" in result.output
        assert "Resources only in prod" in result.output
        assert "Resources only in dev" in result.output
        assert "Resources changed" in result.output
