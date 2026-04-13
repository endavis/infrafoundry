"""Unit tests for the infra doctor command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


def _mock_orchestrator(validate_results: dict | None = None, has_errors: bool = False):
    """Build a mock orchestrator with configurable validate results.

    Args:
        validate_results: Dict of provider -> result dicts.
        has_errors: Whether any provider result has errors > 0.

    Returns:
        A mock orchestrator instance.
    """
    mock = MagicMock()
    if validate_results is None:
        validate_results = {"proxmox": {"errors": 1 if has_errors else 0, "warnings": 0}}
    mock.validate.return_value = validate_results
    return mock


@pytest.mark.unit
class TestInfraDoctorHelp:
    """Tests for infra doctor --help."""

    def test_help(self, cli_runner: CliRunner) -> None:
        """--help exits 0 and shows --env is required."""
        result = cli_runner.invoke(main, ["infra", "doctor", "--help"])
        assert result.exit_code == 0
        assert "--env" in result.output
        assert "provider APIs" in result.output.lower() or "Validate" in result.output

    def test_requires_env(self, cli_runner: CliRunner) -> None:
        """Running without --env produces an error."""
        result = cli_runner.invoke(main, ["infra", "doctor"])
        assert result.exit_code != 0


@pytest.mark.unit
class TestInfraDoctorSuccess:
    """Tests for successful validation."""

    @patch("infrafoundry.cli.main._get_orchestrator")
    @patch("infrafoundry.cli.main._load_env_credentials")
    def test_clean_validation_exit_zero(
        self, mock_creds, mock_get_orch, cli_runner: CliRunner, tmp_path
    ) -> None:
        """Clean validation exits with code 0."""
        orch = _mock_orchestrator(has_errors=False)
        mock_get_orch.return_value = orch

        result = cli_runner.invoke(main, ["-c", str(tmp_path), "infra", "doctor", "--env", "test"])
        assert result.exit_code == 0
        orch.validate.assert_called_once()


@pytest.mark.unit
class TestInfraDoctorFailure:
    """Tests for validation errors."""

    @patch("infrafoundry.cli.main._get_orchestrator")
    @patch("infrafoundry.cli.main._load_env_credentials")
    def test_validation_errors_exit_one(
        self, mock_creds, mock_get_orch, cli_runner: CliRunner, tmp_path
    ) -> None:
        """Validation errors result in exit code 1."""
        orch = _mock_orchestrator(has_errors=True)
        mock_get_orch.return_value = orch

        result = cli_runner.invoke(main, ["-c", str(tmp_path), "infra", "doctor", "--env", "test"])
        assert result.exit_code == 1


@pytest.mark.unit
class TestInfraDoctorResourceFilter:
    """Tests for --resource filter option."""

    @patch("infrafoundry.cli.main._get_orchestrator")
    @patch("infrafoundry.cli.main._load_env_credentials")
    def test_resource_filter_passed(
        self, mock_creds, mock_get_orch, cli_runner: CliRunner, tmp_path
    ) -> None:
        """--resource values are passed to orchestrator.validate()."""
        orch = _mock_orchestrator(has_errors=False)
        mock_get_orch.return_value = orch

        result = cli_runner.invoke(
            main,
            [
                "-c",
                str(tmp_path),
                "infra",
                "doctor",
                "--env",
                "test",
                "-r",
                "vm-01",
                "-r",
                "vm-02",
            ],
        )
        assert result.exit_code == 0
        orch.validate.assert_called_once_with(
            env_name="test",
            resource_filter=["vm-01", "vm-02"],
            verbose=False,
        )


@pytest.mark.unit
class TestInfraDoctorVerbose:
    """Tests for --verbose flag."""

    @patch("infrafoundry.cli.main._get_orchestrator")
    @patch("infrafoundry.cli.main._load_env_credentials")
    def test_verbose_flag_passed(
        self, mock_creds, mock_get_orch, cli_runner: CliRunner, tmp_path
    ) -> None:
        """--verbose flag is forwarded to orchestrator.validate()."""
        orch = _mock_orchestrator(has_errors=False)
        mock_get_orch.return_value = orch

        result = cli_runner.invoke(
            main,
            [
                "-c",
                str(tmp_path),
                "infra",
                "doctor",
                "--env",
                "test",
                "--verbose",
            ],
        )
        assert result.exit_code == 0
        orch.validate.assert_called_once_with(
            env_name="test",
            resource_filter=None,
            verbose=True,
        )
