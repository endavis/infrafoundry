"""Unit tests for the foundry doctor command (system-level checks only)."""

from click.testing import CliRunner

from infrafoundry.cli import main as cli
from infrafoundry.cli.commands import doctor as doctor_module
from infrafoundry.cli.commands.doctor_utils import CheckResult, check_dependency


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
        assert "Usage:" in result.output


class TestDoctorCommand:
    """Tests for the foundry doctor command (system dependencies only)."""

    def test_doctor_help(self):
        """Test doctor command help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["doctor", "--help"])

        assert result.exit_code == 0
        assert "system dependencies" in result.output.lower()

    def test_doctor_runs_successfully(self):
        """Test doctor command runs without errors."""
        runner = CliRunner()
        result = runner.invoke(cli, ["doctor"])

        assert result.exit_code == 0
        assert "Health Check Results" in result.output

    def test_doctor_shows_only_dependency_checks(self):
        """Test doctor only shows binary dependency checks, not config checks."""
        runner = CliRunner()
        result = runner.invoke(cli, ["doctor"])

        assert result.exit_code == 0
        assert "Terraform" in result.output
        assert "Ansible" in result.output
        assert "SOPS" in result.output
        assert "Age" in result.output
        # Config-level checks should NOT be present
        assert "Config Repository" not in result.output
        assert "Environments" not in result.output
        assert "State Backend" not in result.output
        assert "SOPS/Age Keys" not in result.output

    def test_doctor_json_format(self):
        """Test doctor JSON output contains only system checks."""
        runner = CliRunner()
        result = runner.invoke(cli, ["doctor", "--format", "json"])

        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "checks" in data
        assert "summary" in data
        check_names = {c["name"] for c in data["checks"]}
        assert "Terraform" in check_names
        assert "Ansible" in check_names
        # Config-level checks should not be in system doctor
        assert "Config Repository" not in check_names
        assert "Environments" not in check_names

    def test_doctor_no_blueprint_reference(self):
        """Test that foundry --help no longer shows blueprint command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "blueprint" not in result.output


class TestCheckDependency:
    """Tests for the shared dependency checking utility."""

    def test_check_dependency_found(self):
        """Test dependency check when command is found."""
        result = check_dependency("Python", "python", "Install Python")

        assert result.status == "ok"
        assert "Found at" in result.message

    def test_check_dependency_not_found(self):
        """Test dependency check when command is not found."""
        result = check_dependency(
            "NonExistent",
            "nonexistent-command-12345",
            "Install nonexistent",
        )

        assert result.status == "error"
        assert result.message == "Not found"
        assert result.suggestion == "Install nonexistent"


class TestIacToolAlternatives:
    """Tests that Terraform and OpenTofu are treated as alternatives."""

    def _which_stub(self, installed: set[str]):
        def _which(cmd: str) -> str | None:
            return f"/usr/bin/{cmd}" if cmd in installed else None

        return _which

    def test_both_installed_both_ok(self, monkeypatch):
        monkeypatch.setattr(doctor_module.shutil, "which", self._which_stub({"terraform", "tofu"}))
        results = {r.name: r for r in doctor_module._check_iac_tools()}
        assert results["Terraform"].status == "ok"
        assert results["OpenTofu"].status == "ok"

    def test_only_terraform_opentofu_is_warning(self, monkeypatch):
        monkeypatch.setattr(doctor_module.shutil, "which", self._which_stub({"terraform"}))
        results = {r.name: r for r in doctor_module._check_iac_tools()}
        assert results["Terraform"].status == "ok"
        assert results["OpenTofu"].status == "warning"
        assert "optional" in results["OpenTofu"].message.lower()

    def test_only_opentofu_terraform_is_warning(self, monkeypatch):
        monkeypatch.setattr(doctor_module.shutil, "which", self._which_stub({"tofu"}))
        results = {r.name: r for r in doctor_module._check_iac_tools()}
        assert results["OpenTofu"].status == "ok"
        assert results["Terraform"].status == "warning"
        assert "optional" in results["Terraform"].message.lower()

    def test_neither_installed_both_error(self, monkeypatch):
        monkeypatch.setattr(doctor_module.shutil, "which", self._which_stub(set()))
        results = {r.name: r for r in doctor_module._check_iac_tools()}
        assert results["Terraform"].status == "error"
        assert results["OpenTofu"].status == "error"

    def test_doctor_exits_zero_when_only_terraform_installed(self, monkeypatch):
        """Doctor should exit 0 when a supported IaC tool is installed."""
        installed = {"terraform", "ansible", "sops", "age"}
        monkeypatch.setattr(
            doctor_module.shutil,
            "which",
            lambda cmd: f"/usr/bin/{cmd}" if cmd in installed else None,
        )
        # doctor_utils.check_dependency also calls shutil.which directly
        from infrafoundry.cli.commands import doctor_utils

        monkeypatch.setattr(
            doctor_utils.shutil,
            "which",
            lambda cmd: f"/usr/bin/{cmd}" if cmd in installed else None,
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "OpenTofu" in result.output


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
