"""Unit tests for CLI commands."""

from click.testing import CliRunner

from infrafoundry.cli import main as cli


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
        result = runner.invoke(cli, ["list"])

        assert result.exit_code != 0

    def test_plan_command_requires_env(self):
        """Test plan command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["plan"])

        assert result.exit_code != 0

    def test_apply_command_requires_env(self):
        """Test apply command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["apply"])

        assert result.exit_code != 0

    def test_destroy_command_requires_env(self):
        """Test destroy command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["destroy"])

        assert result.exit_code != 0

    def test_status_command_requires_env(self):
        """Test status command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["status"])

        assert result.exit_code != 0

    def test_drift_command_requires_env(self):
        """Test drift command requires --env flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["drift"])

        assert result.exit_code != 0

    def test_rollback_command_requires_deployment_id(self):
        """Test rollback command requires deployment ID."""
        runner = CliRunner()
        result = runner.invoke(cli, ["rollback"])

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
