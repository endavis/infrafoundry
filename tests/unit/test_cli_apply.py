"""Unit tests for the 'apply' CLI command."""

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


def test_apply_with_confirmation(cli_runner, mock_orchestrator):
    """Test apply command with user confirmation."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        # User confirms
        result = cli_runner.invoke(main, ["infra", "apply", "--env", "test"], input="y\n")

        assert result.exit_code == 0
        assert "About to apply infrastructure for environment: test" in result.output
        assert "Apply complete!" in result.output
        mock_orchestrator.apply.assert_called_once_with(
            "test",
            auto_approve=True,  # Becomes True after confirmation
            resource_filter=None,
            parallel=False,
            max_workers=4,
            package_filter=None,
            lock_timeout=0,
            lock_ttl=600,
            add_only=False,
            provider_filter=None,
        )


def test_apply_user_cancels(cli_runner, mock_orchestrator):
    """Test apply command when user cancels confirmation."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        # User cancels
        result = cli_runner.invoke(main, ["infra", "apply", "--env", "test"], input="n\n")

        assert result.exit_code == 0
        assert "Apply cancelled." in result.output
        mock_orchestrator.apply.assert_not_called()


def test_apply_with_auto_approve(cli_runner, mock_orchestrator):
    """Test apply command with auto-approve flag."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "apply", "--env", "test", "--auto-approve"])

        assert result.exit_code == 0
        assert "Apply complete!" in result.output
        mock_orchestrator.apply.assert_called_once_with(
            "test",
            auto_approve=True,
            resource_filter=None,
            parallel=False,
            max_workers=4,
            package_filter=None,
            lock_timeout=0,
            lock_ttl=600,
            add_only=False,
            provider_filter=None,
        )


def test_apply_with_resource_filter(cli_runner, mock_orchestrator):
    """Test apply command with resource filter."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "apply", "--env", "test", "--auto-approve", "-r", "vm-01", "-r", "vm-02"],
        )

        assert result.exit_code == 0
        mock_orchestrator.apply.assert_called_once_with(
            "test",
            auto_approve=True,
            resource_filter=["vm-01", "vm-02"],
            parallel=False,
            max_workers=4,
            package_filter=None,
            lock_timeout=0,
            lock_ttl=600,
            add_only=False,
            provider_filter=None,
        )


def test_apply_with_parallel(cli_runner, mock_orchestrator):
    """Test apply command with parallel execution."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "apply",
                "--env",
                "test",
                "--auto-approve",
                "--parallel",
                "--max-workers",
                "8",
            ],
        )

        assert result.exit_code == 0
        mock_orchestrator.apply.assert_called_once_with(
            "test",
            auto_approve=True,
            resource_filter=None,
            parallel=True,
            max_workers=8,
            package_filter=None,
            lock_timeout=0,
            lock_ttl=600,
            add_only=False,
            provider_filter=None,
        )


def test_apply_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test apply command when orchestrator.apply raises an error."""
    mock_orchestrator.apply.side_effect = Exception("Apply failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "apply", "--env", "test", "--auto-approve"])

        assert result.exit_code == 1
        assert "Apply failed" in result.output


def test_apply_with_single_provider_filter(cli_runner, mock_orchestrator):
    """A single --provider value is passed through as a one-element list."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "apply", "--env", "test", "--auto-approve", "--provider", "opnsense"],
        )

        assert result.exit_code == 0
        mock_orchestrator.apply.assert_called_once_with(
            "test",
            auto_approve=True,
            resource_filter=None,
            parallel=False,
            max_workers=4,
            package_filter=None,
            lock_timeout=0,
            lock_ttl=600,
            add_only=False,
            provider_filter=["opnsense"],
        )


def test_apply_with_short_provider_flag(cli_runner, mock_orchestrator):
    """The -P short option is equivalent to --provider."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "apply", "--env", "test", "--auto-approve", "-P", "opnsense"],
        )

        assert result.exit_code == 0
        mock_orchestrator.apply.assert_called_once_with(
            "test",
            auto_approve=True,
            resource_filter=None,
            parallel=False,
            max_workers=4,
            package_filter=None,
            lock_timeout=0,
            lock_ttl=600,
            add_only=False,
            provider_filter=["opnsense"],
        )


def test_apply_with_multiple_provider_filter(cli_runner, mock_orchestrator):
    """Multiple --provider flags accumulate into a list."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "apply",
                "--env",
                "test",
                "--auto-approve",
                "--provider",
                "opnsense",
                "-P",
                "proxmox",
            ],
        )

        assert result.exit_code == 0
        mock_orchestrator.apply.assert_called_once_with(
            "test",
            auto_approve=True,
            resource_filter=None,
            parallel=False,
            max_workers=4,
            package_filter=None,
            lock_timeout=0,
            lock_ttl=600,
            add_only=False,
            provider_filter=["opnsense", "proxmox"],
        )


def test_apply_provider_and_package_mutually_exclusive(cli_runner, mock_orchestrator):
    """--provider with --package raises UsageError; orchestrator is not called."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "apply",
                "--env",
                "test",
                "--auto-approve",
                "-P",
                "opnsense",
                "-p",
                "core",
            ],
        )

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output
        mock_orchestrator.apply.assert_not_called()


def test_apply_provider_and_resource_mutually_exclusive(cli_runner, mock_orchestrator):
    """--provider with --resource raises UsageError; orchestrator is not called."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "apply",
                "--env",
                "test",
                "--auto-approve",
                "-P",
                "opnsense",
                "-r",
                "vm-01",
            ],
        )

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output
        mock_orchestrator.apply.assert_not_called()


def test_apply_three_way_mutex(cli_runner, mock_orchestrator):
    """All three of --provider, --package, --resource together fail."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "apply",
                "--env",
                "test",
                "--auto-approve",
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
        mock_orchestrator.apply.assert_not_called()


def test_apply_unknown_provider_filter_surfaces_error(cli_runner, mock_orchestrator):
    """Unknown provider names surface as ProviderFilterError via the orchestrator."""
    mock_orchestrator.apply.side_effect = ProviderFilterError(
        requested=["nope"], available=["opnsense", "proxmox"]
    )

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "apply", "--env", "test", "--auto-approve", "--provider", "nope"],
        )

        assert result.exit_code != 0
        assert "nope" in result.output
        assert "opnsense" in result.output
        assert "proxmox" in result.output
