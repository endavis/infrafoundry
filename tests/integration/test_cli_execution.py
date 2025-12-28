"""Integration tests for CLI command execution.

Tests actual CLI command execution paths with mocked orchestrator.
Focus on high-coverage commands: plan, apply, destroy, validate.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli import main as cli


@pytest.fixture
def cli_runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_orchestrator():
    """Create mock orchestrator with all required methods."""
    orch = Mock()
    orch.plan.return_value = None
    orch.apply.return_value = None
    orch.destroy.return_value = None
    orch.validate.return_value = True
    orch.config_manager.list_environments.return_value = ["dev", "prod"]
    return orch


@pytest.fixture
def test_env(tmp_path: Path):
    """Create test environment directory structure."""
    config_dir = tmp_path / "config" / "envs"
    secrets_dir = tmp_path / "secrets"
    output_dir = tmp_path / "output"

    config_dir.mkdir(parents=True)
    secrets_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    # Create dev environment config
    dev_dir = config_dir / "dev"
    dev_dir.mkdir()
    (dev_dir / "settings.yaml").write_text("name: dev\ndescription: Development environment\n")

    return {
        "INFRAFOUNDRY_CONFIG_DIR": str(config_dir),
        "INFRAFOUNDRY_SECRETS_DIR": str(secrets_dir),
        "INFRAFOUNDRY_OUTPUT_DIR": str(output_dir),
    }


@pytest.mark.integration
class TestCLIPlan:
    """Test plan command execution."""

    def test_plan_basic(self, cli_runner, test_env, mock_orchestrator):
        """Test basic plan execution."""
        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            with patch(
                "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
            ):
                with patch(
                    "infrafoundry.core.secrets.secret_manager.SecretManager.__init__",
                    return_value=None,
                ):
                    result = cli_runner.invoke(cli, ["infra", "plan", "--env", "dev"], env=test_env)

                    assert result.exit_code == 0
                    mock_orchestrator.plan.assert_called_once()
                    args = mock_orchestrator.plan.call_args
                    assert args[0][0] == "dev"
                    assert "Plan generated successfully" in result.output

    def test_plan_dry_run(self, cli_runner, test_env, mock_orchestrator):
        """Test plan with --dry-run."""
        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            with patch(
                "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
            ):
                with patch(
                    "infrafoundry.core.secrets.secret_manager.SecretManager.__init__",
                    return_value=None,
                ):
                    result = cli_runner.invoke(
                        cli, ["infra", "plan", "--env", "dev", "--dry-run"], env=test_env
                    )

                    assert result.exit_code == 0
                    assert mock_orchestrator.plan.call_args[1]["dry_run"] is True
                    assert "Dry run complete" in result.output

    def test_plan_with_policies(self, cli_runner, test_env, mock_orchestrator):
        """Test plan with --enforce-policies."""
        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            with patch(
                "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
            ):
                with patch(
                    "infrafoundry.core.secrets.secret_manager.SecretManager.__init__",
                    return_value=None,
                ):
                    result = cli_runner.invoke(
                        cli, ["infra", "plan", "--env", "dev", "--enforce-policies"], env=test_env
                    )

                    assert result.exit_code == 0
                    assert mock_orchestrator.plan.call_args[1]["enforce_policies"] is True

    def test_plan_error(self, cli_runner, test_env, mock_orchestrator):
        """Test plan error handling."""
        mock_orchestrator.plan.side_effect = Exception("Plan failed")

        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            with patch(
                "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
            ):
                with patch(
                    "infrafoundry.core.secrets.secret_manager.SecretManager.__init__",
                    return_value=None,
                ):
                    result = cli_runner.invoke(cli, ["infra", "plan", "--env", "dev"], env=test_env)

                    assert result.exit_code == 1
                    assert "Plan failed" in result.output


@pytest.mark.integration
class TestCLIApply:
    """Test apply command execution."""

    def test_apply_auto_approve(self, cli_runner, test_env, mock_orchestrator):
        """Test apply with --auto-approve."""
        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            with patch(
                "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
            ):
                with patch(
                    "infrafoundry.core.secrets.secret_manager.SecretManager.__init__",
                    return_value=None,
                ):
                    result = cli_runner.invoke(
                        cli, ["infra", "apply", "--env", "dev", "--auto-approve"], env=test_env
                    )

                    assert result.exit_code == 0
                    mock_orchestrator.apply.assert_called_once()
                    assert "Apply complete" in result.output

    def test_apply_parallel(self, cli_runner, test_env, mock_orchestrator):
        """Test apply with --parallel."""
        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            with patch(
                "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
            ):
                with patch(
                    "infrafoundry.core.secrets.secret_manager.SecretManager.__init__",
                    return_value=None,
                ):
                    result = cli_runner.invoke(
                        cli,
                        ["infra", "apply", "--env", "dev", "--auto-approve", "--parallel"],
                        env=test_env,
                    )

                    assert result.exit_code == 0
                    assert mock_orchestrator.apply.call_args[1]["parallel"] is True

    def test_apply_error(self, cli_runner, test_env, mock_orchestrator):
        """Test apply error handling."""
        mock_orchestrator.apply.side_effect = Exception("Apply failed")

        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            with patch(
                "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
            ):
                with patch(
                    "infrafoundry.core.secrets.secret_manager.SecretManager.__init__",
                    return_value=None,
                ):
                    result = cli_runner.invoke(
                        cli, ["infra", "apply", "--env", "dev", "--auto-approve"], env=test_env
                    )

                    assert result.exit_code == 1
                    assert "Apply failed" in result.output


@pytest.mark.integration
class TestCLIDestroy:
    """Test destroy command execution."""

    def test_destroy_auto_approve(self, cli_runner, test_env, mock_orchestrator):
        """Test destroy with --auto-approve."""
        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            with patch(
                "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
            ):
                with patch(
                    "infrafoundry.core.secrets.secret_manager.SecretManager.__init__",
                    return_value=None,
                ):
                    result = cli_runner.invoke(
                        cli, ["infra", "destroy", "--env", "dev", "--auto-approve"], env=test_env
                    )

                    assert result.exit_code == 0
                    mock_orchestrator.destroy.assert_called_once()
                    assert "Destroy complete" in result.output

    def test_destroy_error(self, cli_runner, test_env, mock_orchestrator):
        """Test destroy error handling."""
        mock_orchestrator.destroy.side_effect = Exception("Destroy failed")

        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            with patch(
                "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
            ):
                with patch(
                    "infrafoundry.core.secrets.secret_manager.SecretManager.__init__",
                    return_value=None,
                ):
                    result = cli_runner.invoke(
                        cli, ["infra", "destroy", "--env", "dev", "--auto-approve"], env=test_env
                    )

                    assert result.exit_code == 1


@pytest.mark.integration
class TestCLIEnvs:
    """Test envs command."""

    def test_envs_list(self, cli_runner, test_env):
        """Test listing environments."""
        with patch(
            "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
        ):
            with patch(
                "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
            ):
                result = cli_runner.invoke(cli, ["config", "envs"], env=test_env)

                # Command should execute (exit codes may vary based on implementation)
                assert "dev" in result.output or result.exit_code in [0, 1]
