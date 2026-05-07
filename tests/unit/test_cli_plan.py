"""Unit tests for the 'plan' CLI command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.exceptions import ProviderFilterError
from infrafoundry.core.orchestrator import Orchestrator


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_orchestrator():
    """Mock orchestrator for testing."""
    mock = Mock(spec=Orchestrator)
    return mock


def test_plan_basic(cli_runner, mock_orchestrator):
    """Test basic plan command."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "plan", "--env", "test"])

        assert result.exit_code == 0
        assert "Plan generated successfully!" in result.output
        assert "Generated files are in: generated/" in result.output
        mock_orchestrator.plan.assert_called_once_with(
            "test",
            dry_run=False,
            resource_filter=None,
            enforce_policies=False,
            package_filter=None,
            add_only=False,
            provider_filter=None,
        )


def test_plan_with_dry_run(cli_runner, mock_orchestrator):
    """Test plan command with dry-run flag."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "plan", "--env", "test", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run complete. No files generated." in result.output
        mock_orchestrator.plan.assert_called_once_with(
            "test",
            dry_run=True,
            resource_filter=None,
            enforce_policies=False,
            package_filter=None,
            add_only=False,
            provider_filter=None,
        )


def test_plan_with_resource_filter(cli_runner, mock_orchestrator):
    """Test plan command with resource filter."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "plan", "--env", "test", "-r", "vm-01", "-r", "vm-02"],
        )

        assert result.exit_code == 0
        mock_orchestrator.plan.assert_called_once_with(
            "test",
            dry_run=False,
            resource_filter=["vm-01", "vm-02"],
            enforce_policies=False,
            package_filter=None,
            add_only=False,
            provider_filter=None,
        )


def test_plan_with_enforce_policies(cli_runner, mock_orchestrator):
    """Test plan command with enforce policies flag."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "plan", "--env", "test", "--enforce-policies"],
        )

        assert result.exit_code == 0
        mock_orchestrator.plan.assert_called_once_with(
            "test",
            dry_run=False,
            resource_filter=None,
            enforce_policies=True,
            package_filter=None,
            add_only=False,
            provider_filter=None,
        )


def test_plan_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test plan command when orchestrator.plan raises an error."""
    mock_orchestrator.plan.side_effect = Exception("Plan failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "plan", "--env", "test"])

        assert result.exit_code == 1
        assert "Plan failed" in result.output


def test_plan_with_single_provider_filter(cli_runner, mock_orchestrator):
    """A single --provider value is passed through as a one-element list."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "plan", "--env", "test", "--provider", "opnsense"],
        )

        assert result.exit_code == 0
        mock_orchestrator.plan.assert_called_once_with(
            "test",
            dry_run=False,
            resource_filter=None,
            enforce_policies=False,
            package_filter=None,
            add_only=False,
            provider_filter=["opnsense"],
        )


def test_plan_with_short_provider_flag(cli_runner, mock_orchestrator):
    """The -P short option is equivalent to --provider."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "plan", "--env", "test", "-P", "opnsense"],
        )

        assert result.exit_code == 0
        mock_orchestrator.plan.assert_called_once_with(
            "test",
            dry_run=False,
            resource_filter=None,
            enforce_policies=False,
            package_filter=None,
            add_only=False,
            provider_filter=["opnsense"],
        )


def test_plan_with_multiple_provider_filter(cli_runner, mock_orchestrator):
    """Multiple --provider flags accumulate into a list."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "plan",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "-P",
                "proxmox",
            ],
        )

        assert result.exit_code == 0
        mock_orchestrator.plan.assert_called_once_with(
            "test",
            dry_run=False,
            resource_filter=None,
            enforce_policies=False,
            package_filter=None,
            add_only=False,
            provider_filter=["opnsense", "proxmox"],
        )


def test_plan_provider_and_package_mutually_exclusive(cli_runner, mock_orchestrator):
    """--provider with --package raises UsageError; orchestrator is not called."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "plan", "--env", "test", "-P", "opnsense", "-p", "core"],
        )

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output
        mock_orchestrator.plan.assert_not_called()


def test_plan_provider_and_resource_mutually_exclusive(cli_runner, mock_orchestrator):
    """--provider with --resource raises UsageError; orchestrator is not called."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "plan", "--env", "test", "-P", "opnsense", "-r", "vm-01"],
        )

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output
        mock_orchestrator.plan.assert_not_called()


def test_plan_three_way_mutex(cli_runner, mock_orchestrator):
    """All three of --provider, --package, --resource together fail."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "plan",
                "--env",
                "test",
                "-P",
                "opnsense",
                "-p",
                "core",
                "-r",
                "vm-01",
            ],
        )

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output
        mock_orchestrator.plan.assert_not_called()


def test_plan_unknown_provider_filter_surfaces_error(cli_runner, mock_orchestrator):
    """Unknown provider names surface as ProviderFilterError via the orchestrator."""
    mock_orchestrator.plan.side_effect = ProviderFilterError(
        requested=["nope"], available=["opnsense", "proxmox"]
    )

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "plan", "--env", "test", "--provider", "nope"],
        )

        assert result.exit_code != 0
        assert "nope" in result.output
        assert "opnsense" in result.output
        assert "proxmox" in result.output
