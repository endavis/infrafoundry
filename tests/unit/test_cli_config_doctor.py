"""Unit tests for the config doctor command."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from infrafoundry.cli.main import main

# Patch targets (on the config/doctor module namespace)
_STATE_BACKEND = "infrafoundry.cli.commands.config.doctor._check_state_backend"
_SOPS_KEYS = "infrafoundry.cli.commands.config.doctor._check_sops_keys"
_CONSISTENCY = "infrafoundry.cli.commands.config.doctor._check_consistency"
_BLUEPRINTS = "infrafoundry.cli.commands.config.doctor._check_blueprints"
_STATE_DB_ENVS = "infrafoundry.cli.commands.config.doctor._get_state_db_environments"


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory with two environments."""
    config_dir = tmp_path / "config"
    envs_dir = config_dir / "envs"

    for env_name in ("dev", "prod"):
        env_dir = envs_dir / env_name
        env_dir.mkdir(parents=True)
        settings = {
            "name": env_name,
            "description": f"{env_name} environment",
            "providers": ["proxmox"],
        }
        (env_dir / "settings.yaml").write_text(yaml.safe_dump(settings))

    return config_dir


def _ok(name: str, message: str = "OK") -> MagicMock:
    """Build a mock CheckResult with ok status."""
    from infrafoundry.cli.commands.doctor_utils import CheckResult

    return CheckResult(name=name, status="ok", message=message)


def _error(name: str, message: str = "Failed") -> MagicMock:
    """Build a mock CheckResult with error status."""
    from infrafoundry.cli.commands.doctor_utils import CheckResult

    return CheckResult(name=name, status="error", message=message, suggestion="Fix it")


def _warning(name: str, message: str = "Warn") -> MagicMock:
    """Build a mock CheckResult with warning status."""
    from infrafoundry.cli.commands.doctor_utils import CheckResult

    return CheckResult(name=name, status="warning", message=message)


@pytest.mark.unit
class TestConfigDoctorHelp:
    """Tests for config doctor --help."""

    def test_help(self, cli_runner: CliRunner) -> None:
        """--help exits 0 and shows usage."""
        result = cli_runner.invoke(main, ["config", "doctor", "--help"])
        assert result.exit_code == 0
        assert "configuration repository health" in result.output.lower()

    def test_config_no_check_command(self, cli_runner: CliRunner) -> None:
        """config check is no longer available."""
        result = cli_runner.invoke(main, ["config", "check"])
        assert result.exit_code != 0

    def test_config_no_validate_command(self, cli_runner: CliRunner) -> None:
        """config validate is no longer available."""
        result = cli_runner.invoke(main, ["config", "validate"])
        assert result.exit_code != 0


@pytest.mark.unit
class TestConfigDoctorAllPass:
    """Tests when all checks pass."""

    def test_all_pass_exit_zero(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """All checks passing results in exit code 0."""
        with (
            patch(_STATE_BACKEND, return_value=_ok("State Backend")),
            patch(_SOPS_KEYS, return_value=_ok("SOPS/Age Keys")),
            patch(_CONSISTENCY, return_value=_ok("State Consistency")),
            patch(_BLUEPRINTS, return_value=_ok("Blueprints")),
        ):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "doctor"])
            assert result.exit_code == 0
            assert "All checks passed" in result.output


@pytest.mark.unit
class TestConfigDoctorConfigRepoMissing:
    """Tests when config repo is missing."""

    def test_no_config_repo_warning(self, cli_runner: CliRunner, monkeypatch) -> None:
        """Missing config repo shows warning in output."""
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)
        with (
            patch(_STATE_BACKEND, return_value=_ok("State Backend")),
            patch(_SOPS_KEYS, return_value=_ok("SOPS/Age Keys")),
            patch(_CONSISTENCY, return_value=_ok("State Consistency")),
            patch(_BLUEPRINTS, return_value=_ok("Blueprints")),
        ):
            result = cli_runner.invoke(main, ["config", "doctor"])
            assert result.exit_code == 0
            assert "Not configured" in result.output or "WARN" in result.output


@pytest.mark.unit
class TestConfigDoctorConsistencyError:
    """Tests when state/filesystem consistency fails."""

    def test_consistency_error_exit_one(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """Consistency error results in exit code 1."""
        with (
            patch(_STATE_BACKEND, return_value=_ok("State Backend")),
            patch(_SOPS_KEYS, return_value=_ok("SOPS/Age Keys")),
            patch(
                _CONSISTENCY,
                return_value=_error("State Consistency", "Mismatch found"),
            ),
            patch(_BLUEPRINTS, return_value=_ok("Blueprints")),
        ):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "doctor"])
            assert result.exit_code == 1
            assert "FAIL" in result.output


@pytest.mark.unit
class TestConfigDoctorBlueprintError:
    """Tests when blueprint validation fails."""

    def test_blueprint_error_exit_one(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """Blueprint validation errors result in exit code 1."""
        with (
            patch(_STATE_BACKEND, return_value=_ok("State Backend")),
            patch(_SOPS_KEYS, return_value=_ok("SOPS/Age Keys")),
            patch(_CONSISTENCY, return_value=_ok("State Consistency")),
            patch(
                _BLUEPRINTS,
                return_value=_error("Blueprints", "2 error(s)"),
            ),
        ):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "doctor"])
            assert result.exit_code == 1
            assert "FAIL" in result.output


@pytest.mark.unit
class TestConfigDoctorSopsWarning:
    """Tests when SOPS keys are missing."""

    def test_sops_warning(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """Missing SOPS keys show warning but exit 0."""
        with (
            patch(_STATE_BACKEND, return_value=_ok("State Backend")),
            patch(
                _SOPS_KEYS,
                return_value=_warning("SOPS/Age Keys", "Not found"),
            ),
            patch(_CONSISTENCY, return_value=_ok("State Consistency")),
            patch(_BLUEPRINTS, return_value=_ok("Blueprints")),
        ):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "doctor"])
            assert result.exit_code == 0
            assert "WARN" in result.output


@pytest.mark.unit
class TestConfigDoctorDeep:
    """Tests for --deep flag."""

    def test_deep_flag_accepted(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """--deep flag is accepted without error."""
        with (
            patch(_STATE_BACKEND, return_value=_ok("State Backend")),
            patch(_SOPS_KEYS, return_value=_ok("SOPS/Age Keys")),
            patch(
                _CONSISTENCY,
                return_value=_ok(
                    "State Consistency",
                    "All environments consistent (resource counts: dev: 5, prod: 12)",
                ),
            ),
            patch(_BLUEPRINTS, return_value=_ok("Blueprints")),
        ):
            result = cli_runner.invoke(
                main,
                ["-c", str(temp_config_dir), "config", "doctor", "--deep"],
            )
            assert result.exit_code == 0


@pytest.mark.unit
class TestConfigDoctorJsonFormat:
    """Tests for --format json output."""

    def test_json_output_structure(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """JSON output has expected structure."""
        with (
            patch(_STATE_BACKEND, return_value=_ok("State Backend")),
            patch(_SOPS_KEYS, return_value=_ok("SOPS/Age Keys")),
            patch(_CONSISTENCY, return_value=_ok("State Consistency")),
            patch(_BLUEPRINTS, return_value=_ok("Blueprints")),
        ):
            result = cli_runner.invoke(
                main,
                [
                    "-c",
                    str(temp_config_dir),
                    "config",
                    "doctor",
                    "--format",
                    "json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "checks" in data
            assert "summary" in data
            assert data["summary"]["total"] == 6
            check_names = {c["name"] for c in data["checks"]}
            assert "Config Repository" in check_names
            assert "Blueprints" in check_names


@pytest.mark.unit
class TestConfigDoctorStateDbUnavailable:
    """Tests when state database is unavailable."""

    def test_state_db_unavailable_graceful(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """State DB unavailable produces warning, not crash."""
        with (
            patch(
                _STATE_BACKEND,
                return_value=_warning("State Backend", "Not initialized"),
            ),
            patch(_SOPS_KEYS, return_value=_ok("SOPS/Age Keys")),
            patch(
                _CONSISTENCY,
                return_value=_warning(
                    "State Consistency",
                    "State database unavailable",
                ),
            ),
            patch(_BLUEPRINTS, return_value=_ok("Blueprints")),
        ):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "doctor"])
            assert result.exit_code == 0
            assert "WARN" in result.output
