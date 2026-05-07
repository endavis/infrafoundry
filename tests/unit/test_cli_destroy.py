"""Unit tests for the 'destroy' CLI command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.exceptions import ProviderFilterError, TerraformError
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


def test_destroy_confirms_then_auto_approves(cli_runner, mock_orchestrator):
    """Test that confirming at CLI level passes auto_approve=True to orchestrator."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "destroy", "--env", "test"], input="y\n")

        assert result.exit_code == 0
        assert "Destroy complete!" in result.output
        call_args = mock_orchestrator.destroy.call_args
        assert call_args[0] == ("test",)
        assert call_args[1]["auto_approve"] is True
        assert call_args[1]["resource_filter"] is None
        assert "confirm_callback" not in call_args[1]


def test_destroy_cancelled(cli_runner, mock_orchestrator):
    """Test that declining confirmation cancels destroy."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "destroy", "--env", "test"], input="n\n")

        assert result.exit_code == 0
        assert "Destroy cancelled." in result.output
        mock_orchestrator.destroy.assert_not_called()


def test_destroy_with_auto_approve(cli_runner, mock_orchestrator):
    """Test destroy command with auto-approve flag skips confirmation."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "destroy", "--env", "test", "--auto-approve"])

        assert result.exit_code == 0
        assert "Destroy complete!" in result.output
        call_args = mock_orchestrator.destroy.call_args
        assert call_args[1]["auto_approve"] is True


def test_destroy_with_resource_filter(cli_runner, mock_orchestrator):
    """Test destroy command with resource filter."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "destroy", "--env", "test", "--auto-approve", "-r", "vm-01", "-r", "vm-02"],
        )

        assert result.exit_code == 0
        call_args = mock_orchestrator.destroy.call_args
        assert call_args[1]["resource_filter"] == ["vm-01", "vm-02"]


def test_destroy_shows_resource_names_in_prompt(cli_runner, mock_orchestrator):
    """Test that resource names are shown in the confirmation prompt."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "destroy", "--env", "test", "-r", "vm-01", "-r", "vm-02"],
            input="y\n",
        )

        assert result.exit_code == 0
        assert "vm-01" in result.output
        assert "vm-02" in result.output


def test_destroy_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test destroy command when orchestrator.destroy raises an error."""
    mock_orchestrator.destroy.side_effect = Exception("Destroy failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "destroy", "--env", "test", "--auto-approve"])

        assert result.exit_code == 1
        assert "Destroy failed" in result.output


def test_destroy_cli_does_not_print_success_on_orchestrator_failure(cli_runner, mock_orchestrator):
    """Regression for #510: TerraformError from orchestrator must not show 'Destroy complete!'."""
    mock_orchestrator.destroy.side_effect = TerraformError(
        "Terraform destroy failed for provider 'proxmox': Instance cannot be destroyed",
        exit_code=1,
        stderr="Error: Instance cannot be destroyed",
    )

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "destroy", "--env", "test", "--auto-approve"])

    assert result.exit_code != 0
    assert "Destroy complete!" not in result.output
    # Error is reported via the framework's error catalog (IF-RUNNER-001).
    assert "Terraform" in result.output
    assert "Destroy failed" in result.output


def test_destroy_with_single_provider_filter(cli_runner, mock_orchestrator):
    """A single --provider value is passed through as a one-element list."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "destroy", "--env", "test", "--auto-approve", "--provider", "opnsense"],
        )

        assert result.exit_code == 0
        call_args = mock_orchestrator.destroy.call_args
        assert call_args[1]["provider_filter"] == ["opnsense"]
        assert call_args[1]["resource_filter"] is None
        assert call_args[1]["package_filter"] is None


def test_destroy_with_short_provider_flag(cli_runner, mock_orchestrator):
    """The -P short option is equivalent to --provider."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "destroy", "--env", "test", "--auto-approve", "-P", "opnsense"],
        )

        assert result.exit_code == 0
        call_args = mock_orchestrator.destroy.call_args
        assert call_args[1]["provider_filter"] == ["opnsense"]


def test_destroy_with_multiple_provider_filter(cli_runner, mock_orchestrator):
    """Multiple --provider flags accumulate into a list."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "destroy",
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
        call_args = mock_orchestrator.destroy.call_args
        assert call_args[1]["provider_filter"] == ["opnsense", "proxmox"]


def test_destroy_provider_and_package_mutually_exclusive(cli_runner, mock_orchestrator):
    """--provider with --package raises UsageError; orchestrator is not called."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "destroy",
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
        mock_orchestrator.destroy.assert_not_called()


def test_destroy_provider_and_resource_mutually_exclusive(cli_runner, mock_orchestrator):
    """--provider with --resource raises UsageError; orchestrator is not called."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "destroy",
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
        mock_orchestrator.destroy.assert_not_called()


def test_destroy_three_way_mutex(cli_runner, mock_orchestrator):
    """All three of --provider, --package, --resource together fail."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "infra",
                "destroy",
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
        mock_orchestrator.destroy.assert_not_called()


def test_destroy_unknown_provider_filter_surfaces_error(cli_runner, mock_orchestrator):
    """Unknown provider names surface as ProviderFilterError via the orchestrator."""
    mock_orchestrator.destroy.side_effect = ProviderFilterError(
        requested=["nope"], available=["opnsense", "proxmox"]
    )

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            ["infra", "destroy", "--env", "test", "--auto-approve", "--provider", "nope"],
        )

        assert result.exit_code != 0
        assert "nope" in result.output
        assert "opnsense" in result.output
        assert "proxmox" in result.output
