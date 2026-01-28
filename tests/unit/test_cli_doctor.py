"""Unit tests for the doctor command and welcome message."""

from pathlib import Path
from unittest.mock import Mock, patch

from click.testing import CliRunner

from infrafoundry.cli import main as cli
from infrafoundry.cli.commands.doctor import (
    CheckResult,
    _check_config_repo,
    _check_dependency,
    _check_environments,
    _check_sops_keys,
    _check_state_backend,
)


class TestWelcomeMessage:
    """Tests for the welcome message when no subcommand is invoked."""

    def test_welcome_shown_without_subcommand(self):
        """Test that welcome message is shown when no subcommand is provided."""
        runner = CliRunner()
        result = runner.invoke(cli, [])

        assert result.exit_code == 0
        assert "InfraFoundry" in result.output
        assert "Quick Start" in result.output
        assert "Environment Variables" in result.output

    def test_welcome_shows_config_status(self, tmp_path):
        """Test that welcome message shows configuration status."""
        runner = CliRunner()
        # Create a minimal config structure
        envs_dir = tmp_path / "envs"
        envs_dir.mkdir()
        (envs_dir / "test-env").mkdir()
        (envs_dir / "test-env" / "env.yaml").write_text("description: Test")

        result = runner.invoke(cli, ["--config-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "Status" in result.output

    def test_welcome_not_shown_with_subcommand(self):
        """Test that welcome message is not shown when a subcommand is provided."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        # --help should show help, not welcome
        assert "Usage:" in result.output


class TestDoctorCommand:
    """Tests for the doctor command."""

    def test_doctor_help(self):
        """Test doctor command help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["doctor", "--help"])

        assert result.exit_code == 0
        assert "Check InfraFoundry setup" in result.output

    def test_doctor_runs_successfully(self):
        """Test doctor command runs without errors."""
        runner = CliRunner()
        with patch("infrafoundry.cli.commands.doctor._check_state_backend") as mock_state:
            mock_state.return_value = CheckResult(
                name="State Backend",
                status="ok",
                message="SQLite backend initialized",
            )
            result = runner.invoke(cli, ["doctor"])

        assert result.exit_code == 0
        assert "Health Check Results" in result.output

    def test_doctor_shows_dependency_checks(self):
        """Test doctor command shows dependency checks."""
        runner = CliRunner()
        with patch("infrafoundry.cli.commands.doctor._check_state_backend") as mock_state:
            mock_state.return_value = CheckResult(
                name="State Backend",
                status="ok",
                message="SQLite backend initialized",
            )
            result = runner.invoke(cli, ["doctor"])

        assert result.exit_code == 0
        assert "Terraform" in result.output
        assert "Ansible" in result.output
        assert "SOPS" in result.output
        assert "Age" in result.output


class TestCheckDependency:
    """Tests for dependency checking."""

    def test_check_dependency_found(self):
        """Test dependency check when command is found."""
        # 'python' should exist in any Python environment
        result = _check_dependency("Python", "python", "Install Python")

        assert result.status == "ok"
        assert "Found at" in result.message

    def test_check_dependency_not_found(self):
        """Test dependency check when command is not found."""
        result = _check_dependency(
            "NonExistent",
            "nonexistent-command-12345",
            "Install nonexistent",
        )

        assert result.status == "error"
        assert result.message == "Not found"
        assert result.suggestion == "Install nonexistent"


class TestCheckConfigRepo:
    """Tests for config repository checking."""

    def test_check_config_repo_valid(self, tmp_path):
        """Test config repo check with valid structure."""
        envs_dir = tmp_path / "envs"
        envs_dir.mkdir()

        result = _check_config_repo(tmp_path)

        assert result.status == "ok"
        assert str(tmp_path) in result.message

    def test_check_config_repo_missing_envs(self, tmp_path):
        """Test config repo check with missing envs directory."""
        result = _check_config_repo(tmp_path)

        assert result.status == "warning"
        assert "missing envs/ directory" in result.message

    def test_check_config_repo_not_exists(self, tmp_path):
        """Test config repo check with non-existent path."""
        non_existent = tmp_path / "does-not-exist"

        result = _check_config_repo(non_existent)

        assert result.status == "error"
        assert "does not exist" in result.message

    def test_check_config_repo_not_configured(self, monkeypatch):
        """Test config repo check when not configured."""
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)

        result = _check_config_repo(None)

        assert result.status == "warning"
        assert "Not configured" in result.message


class TestCheckEnvironments:
    """Tests for environment checking."""

    def test_check_environments_found(self, tmp_path):
        """Test environment check with environments present."""
        envs_dir = tmp_path / "envs"
        envs_dir.mkdir()
        test_env = envs_dir / "test-env"
        test_env.mkdir()
        (test_env / "env.yaml").write_text("description: Test environment")

        result = _check_environments(tmp_path)

        assert result.status == "ok"
        assert "1 found" in result.message
        assert "test-env" in result.message

    def test_check_environments_none_found(self, tmp_path):
        """Test environment check with no environments."""
        envs_dir = tmp_path / "envs"
        envs_dir.mkdir()

        result = _check_environments(tmp_path)

        assert result.status == "warning"
        assert "No environments found" in result.message

    def test_check_environments_no_config(self, monkeypatch):
        """Test environment check when config not set."""
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)

        result = _check_environments(None)

        assert result.status == "warning"
        assert "config repo not set" in result.message


class TestCheckStateBackend:
    """Tests for state backend checking."""

    def test_check_state_backend_ok(self):
        """Test state backend check when initialization succeeds."""
        with patch("infrafoundry.core.state.state_manager.StateManager") as mock_state_manager:
            mock_state_manager.return_value = Mock()

            result = _check_state_backend()

        assert result.status == "ok"
        assert "initialized" in result.message

    def test_check_state_backend_error(self):
        """Test state backend check when initialization fails."""
        with patch("infrafoundry.core.state.state_manager.StateManager") as mock_state_manager:
            mock_state_manager.side_effect = Exception("Connection failed")

            result = _check_state_backend()

        assert result.status == "warning"
        assert "Not initialized" in result.message


class TestCheckSopsKeys:
    """Tests for SOPS/age key checking."""

    def test_check_sops_keys_found_default_location(self, tmp_path, monkeypatch):
        """Test SOPS key check when key exists at default location."""
        # Create the expected directory structure
        sops_dir = tmp_path / ".config" / "sops" / "age"
        sops_dir.mkdir(parents=True)
        keys_file = sops_dir / "keys.txt"
        keys_file.write_text("AGE-SECRET-KEY-...")

        # Patch Path.home() to return our tmp_path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = _check_sops_keys()

        assert result.status == "ok"
        assert "Found at" in result.message

    def test_check_sops_keys_found_env_var(self, tmp_path, monkeypatch):
        """Test SOPS key check when key is set via environment variable."""
        keys_file = tmp_path / "age-keys.txt"
        keys_file.write_text("AGE-SECRET-KEY-...")

        monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(keys_file))
        # Make sure default location doesn't exist
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "nonexistent")

        result = _check_sops_keys()

        assert result.status == "ok"
        assert "SOPS_AGE_KEY_FILE" in result.message

    def test_check_sops_keys_not_found(self, tmp_path, monkeypatch):
        """Test SOPS key check when no keys are configured."""
        monkeypatch.delenv("SOPS_AGE_KEY_FILE", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = _check_sops_keys()

        assert result.status == "warning"
        assert "Not found" in result.message
        assert "age-keygen" in result.suggestion


class TestCheckResultDataclass:
    """Tests for the CheckResult dataclass."""

    def test_check_result_creation(self):
        """Test CheckResult creation with all fields."""
        result = CheckResult(
            name="Test Check",
            status="ok",
            message="All good",
            suggestion="No action needed",
        )

        assert result.name == "Test Check"
        assert result.status == "ok"
        assert result.message == "All good"
        assert result.suggestion == "No action needed"

    def test_check_result_default_suggestion(self):
        """Test CheckResult creation with default suggestion."""
        result = CheckResult(
            name="Test Check",
            status="warning",
            message="Something minor",
        )

        assert result.suggestion == ""
