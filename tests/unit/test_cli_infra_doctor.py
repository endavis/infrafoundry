"""Unit tests for the infra doctor command."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.jumphost_preflight import Check, JumphostReport, Status, Target
from infrafoundry.core.provider import ResourceConfig


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture for invoking CLI commands."""
    return CliRunner()


def _mock_orchestrator(
    validate_results: dict[str, Any] | None = None, has_errors: bool = False
) -> MagicMock:
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
        self, mock_creds: MagicMock, mock_get_orch: MagicMock, cli_runner: CliRunner, tmp_path: Path
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
        self, mock_creds: MagicMock, mock_get_orch: MagicMock, cli_runner: CliRunner, tmp_path: Path
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
        self, mock_creds: MagicMock, mock_get_orch: MagicMock, cli_runner: CliRunner, tmp_path: Path
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
        self, mock_creds: MagicMock, mock_get_orch: MagicMock, cli_runner: CliRunner, tmp_path: Path
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


def _vm(name: str, jumphost: str = "") -> ResourceConfig:
    pkg_vars = {"jumphost": jumphost} if jumphost else {}
    return ResourceConfig(
        name=name, type="vm", provider="proxmox", config={}, package_variables=pkg_vars
    )


def _dhcp(hostname: str, ip: str) -> ResourceConfig:
    return ResourceConfig(
        name=f"{hostname}-dhcp",
        type="kea.dhcp4.reservations",
        provider="opnsense",
        config={"hostname": hostname, "ip_address": ip},
    )


def _report(jumphost: str, status: Status) -> JumphostReport:
    return JumphostReport(jumphost, [Check("SSH to jumphost", status, "detail")])


@pytest.mark.unit
class TestInfraDoctorPackage:
    """Tests for --package and the jumphost preflight (#657)."""

    def _invoke(self, cli_runner: CliRunner, tmp_path: Path, *args: str) -> Any:
        return cli_runner.invoke(
            main, ["-c", str(tmp_path), "infra", "doctor", "--env", "test", *args]
        )

    @patch("infrafoundry.cli.commands.infra.doctor.check_jumphost")
    @patch("infrafoundry.cli.main._get_orchestrator")
    @patch("infrafoundry.cli.main._load_env_credentials")
    def test_package_resolves_filter_and_checks_its_jumphost(
        self,
        mock_creds: MagicMock,
        mock_get_orch: MagicMock,
        mock_check: MagicMock,
        cli_runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """-p checks only the package's jumphost, with its targets and outputs."""
        orch = _mock_orchestrator(has_errors=False)
        orch.config_manager.resolve_package_filter.return_value = ["k3s-server"]
        orch.config_manager.get_all_resources_all_providers.return_value = [
            _vm("k3s-server", jumphost="ansible@jump"),
            _vm("other", jumphost="root@elsewhere"),
            _dhcp("k3s-server", "10.0.1.70"),
            _dhcp("other", "10.0.1.99"),
        ]
        dest = str(tmp_path / "kube" / "k3s.yaml")
        orch.config_manager.get_package_events.return_value = {
            "on_create": [{"requires": ["k3s-server"], "outputs": [{"source": dest, "dest": dest}]}]
        }
        orch.state_manager.get_resources.return_value = []
        mock_get_orch.return_value = orch
        mock_check.return_value = _report("ansible@jump", Status.OK)

        result = self._invoke(cli_runner, tmp_path, "-p", "k3s-cluster")

        assert result.exit_code == 0, result.output
        orch.config_manager.resolve_package_filter.assert_called_once_with("test", "k3s-cluster")
        orch.validate.assert_called_once_with(
            env_name="test", resource_filter=["k3s-server"], verbose=False
        )
        mock_check.assert_called_once_with(
            "ansible@jump", [], [Target("k3s-server", "10.0.1.70", "ansible", False)]
        )
        assert "Jumphost preflight (ansible@jump)" in result.output
        assert "[OK] SSH to jumphost: detail" in result.output
        # Rich wraps the long path at the test console's width.
        assert f"[OK]output{dest}" in "".join(result.output.split())

    @patch("infrafoundry.cli.commands.infra.doctor.check_jumphost")
    @patch("infrafoundry.cli.main._get_orchestrator")
    @patch("infrafoundry.cli.main._load_env_credentials")
    def test_jumphost_failure_exits_one(
        self,
        mock_creds: MagicMock,
        mock_get_orch: MagicMock,
        mock_check: MagicMock,
        cli_runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """A failed jumphost check fails doctor even when provider validation passes."""
        orch = _mock_orchestrator(has_errors=False)
        orch.config_manager.get_all_resources_all_providers.return_value = [
            _vm("vm1", jumphost="ansible@jump")
        ]
        mock_get_orch.return_value = orch
        mock_check.return_value = _report("ansible@jump", Status.FAIL)

        result = self._invoke(cli_runner, tmp_path)

        assert result.exit_code == 1
        assert "[FAIL] SSH to jumphost" in result.output

    @patch("infrafoundry.cli.commands.infra.doctor.check_jumphost")
    @patch("infrafoundry.cli.main._get_orchestrator")
    @patch("infrafoundry.cli.main._load_env_credentials")
    def test_no_jumphost_runs_no_preflight(
        self,
        mock_creds: MagicMock,
        mock_get_orch: MagicMock,
        mock_check: MagicMock,
        cli_runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """Packages without a jumphost get no jumphost section."""
        orch = _mock_orchestrator(has_errors=False)
        orch.config_manager.get_all_resources_all_providers.return_value = [_vm("vm1")]
        mock_get_orch.return_value = orch

        result = self._invoke(cli_runner, tmp_path)

        assert result.exit_code == 0
        mock_check.assert_not_called()
        assert "Jumphost preflight" not in result.output

    @patch("infrafoundry.cli.main._get_orchestrator")
    @patch("infrafoundry.cli.main._load_env_credentials")
    def test_package_and_resource_are_exclusive(
        self, mock_creds: MagicMock, mock_get_orch: MagicMock, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """-p together with -r is a usage error."""
        mock_get_orch.return_value = _mock_orchestrator()

        result = self._invoke(cli_runner, tmp_path, "-p", "pkg", "-r", "vm1")

        assert result.exit_code == 2
        assert "mutually exclusive" in result.output
