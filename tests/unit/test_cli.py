"""Unit tests for CLI commands."""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from infrafoundry.cli import main as cli
from infrafoundry.core.orchestrator import OrchestratorStrictConfig


class TestCLICommands:
    """Tests for CLI command structure and basic validation."""

    def test_main_help(self):
        """Test main help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "InfraFoundry" in result.output or "infra" in result.output

    def test_main_version(self):
        """Test version flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])

        assert result.exit_code == 0

    def test_main_config_dir_option(self):
        """Test --config-dir option is accepted."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--config-dir", "/tmp/config", "--help"])

        assert result.exit_code == 0

    def test_list_command_requires_env(self):
        """Test list command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["state", "list"])

        assert result.exit_code != 0

    def test_plan_command_requires_env(self):
        """Test plan command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["infra", "plan"])

        assert result.exit_code != 0

    def test_strict_mode_flag_passes_config(self):
        """Test --strict-mode creates strict orchestrator config."""
        runner = CliRunner()
        with (
            patch("infrafoundry.cli.main._get_orchestrator") as mock_get,
            patch("infrafoundry.cli.main._load_env_credentials"),
        ):
            mock_orchestrator = Mock()
            mock_orchestrator.plan.return_value = {}
            mock_get.return_value = mock_orchestrator

            result = runner.invoke(cli, ["--strict-mode", "infra", "plan", "--env", "dev"])

            assert result.exit_code == 0
            call_args, _ = mock_get.call_args
            assert len(call_args) == 2
            strict_config = call_args[1]
            assert isinstance(strict_config, OrchestratorStrictConfig)
            assert strict_config.strict_mode is True

    def test_strict_env_vars_applied_when_no_flags(self, monkeypatch):
        """Test environment variables are respected for strict config."""
        runner = CliRunner()
        with (
            patch("infrafoundry.cli.main._get_orchestrator") as mock_get,
            patch("infrafoundry.cli.main._load_env_credentials"),
        ):
            mock_orchestrator = Mock()
            mock_orchestrator.plan.return_value = {}
            mock_get.return_value = mock_orchestrator

            monkeypatch.setenv("INFRAFOUNDRY_FAIL_ON_MISSING_SECRETS", "1")
            result = runner.invoke(cli, ["infra", "plan", "--env", "dev"])

            assert result.exit_code == 0
            call_args, _ = mock_get.call_args
            strict_config = call_args[1]
            assert isinstance(strict_config, OrchestratorStrictConfig)
            assert strict_config.fail_on_missing_secrets is True

    def test_apply_command_requires_env(self):
        """Test apply command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["infra", "apply"])

        assert result.exit_code != 0

    def test_destroy_command_requires_env(self):
        """Test destroy command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["infra", "destroy"])

        assert result.exit_code != 0

    def test_status_command_requires_env(self):
        """Test status command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["infra", "status"])

        assert result.exit_code != 0

    def test_drift_command_requires_env(self):
        """Test drift command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["infra", "drift"])

        assert result.exit_code != 0

    def test_rollback_command_requires_deployment_id(self):
        """Test rollback command requires deployment ID."""
        runner = CliRunner()
        result = runner.invoke(cli, ["infra", "rollback"])

        assert result.exit_code != 0


class TestSecretsCommands:
    """Tests for secrets subcommands."""

    def test_secrets_help(self):
        """Test secrets command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["secrets", "--help"])

        assert result.exit_code == 0
        assert "init" in result.output or "encrypt" in result.output

    def test_secrets_init_help(self):
        """Test secrets init help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["secrets", "init", "--help"])

        assert result.exit_code == 0

    def test_secrets_encrypt_requires_file(self):
        """Test secrets encrypt requires file argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["secrets", "encrypt"])

        assert result.exit_code != 0

    def test_secrets_decrypt_requires_file(self):
        """Test secrets decrypt requires file argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["secrets", "decrypt"])

        assert result.exit_code != 0

    def test_reset_command_requires_env(self):
        """Test reset command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["infra", "reset"])

        assert result.exit_code != 0

    def test_reset_command_requires_provider(self):
        """Test reset command requires --provider flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["infra", "reset", "--env", "test"])

        assert result.exit_code != 0

    def test_reset_command_requires_component(self):
        """Test reset command requires --component flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["infra", "reset", "--env", "test", "--provider", "opnsense"])

        assert result.exit_code != 0

    def test_reset_command_help(self):
        """Test reset command help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["infra", "reset", "--help"])

        assert result.exit_code == 0
        assert "reset" in result.output.lower()
        assert "kea/dhcp" in result.output

    def test_migrate_command_requires_env(self):
        """Test migrate command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate"])

        assert result.exit_code != 0

    def test_migrate_command_requires_provider(self):
        """Test migrate command requires --provider flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate", "--env", "test"])

        assert result.exit_code != 0

    def test_migrate_command_requires_component(self):
        """Test migrate command requires --component flag."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["config", "migrate", "--env", "test", "--provider", "opnsense"]
        )

        assert result.exit_code != 0

    def test_migrate_command_help(self):
        """Test migrate command help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "migrate", "--help"])

        assert result.exit_code == 0
        assert "migrate" in result.output.lower()
        # After #726 the per-component dispatch lives in the extractor
        # registry; the help string mentions ``kea_dhcp`` as one example
        # of a registered component (the breaking CLI rename replaces
        # ``kea/dhcp`` with ``kea_dhcp``).
        assert "kea_dhcp" in result.output
