"""Unit tests for the --package / -p CLI flag and resolve_package_filter."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.config.config_manager import ConfigManager
from infrafoundry.core.exceptions import PackageNotFoundError
from infrafoundry.core.orchestrator import Orchestrator


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_orchestrator():
    """Mock orchestrator for testing."""
    mock = Mock(spec=Orchestrator)
    mock.config_manager = Mock(spec=ConfigManager)
    return mock


# --- resolve_package_filter unit tests ---


class TestResolvePackageFilter:
    """Tests for ConfigManager.resolve_package_filter."""

    def test_known_package_resolves_to_resource_names(self, tmp_path: Path):
        """Known package resolves to correct resource names."""
        # Set up env with a provider-scoped package
        env_dir = tmp_path / "test-env"
        provider_dir = env_dir / "proxmox"
        pkg_dir = provider_dir / "my-cluster"
        pkg_dir.mkdir(parents=True)

        # Create settings.yaml
        (env_dir / "settings.yaml").write_text("iac_tool: terraform\n")

        # Create manifest
        (pkg_dir / "infrafoundry.yml").write_text("name: my-cluster\nresources:\n  - vm.yaml\n")

        # Create resource file
        (pkg_dir / "vm.yaml").write_text(
            "vm:\n  - name: cluster-node1\n    cores: 2\n  - name: cluster-node2\n    cores: 2\n"
        )

        cm = ConfigManager(base_dir=tmp_path)
        result = cm.resolve_package_filter("test-env", "my-cluster")

        assert sorted(result) == ["cluster-node1", "cluster-node2"]

    def test_unknown_package_raises_error(self, tmp_path: Path):
        """Unknown package raises PackageNotFoundError."""
        env_dir = tmp_path / "test-env"
        env_dir.mkdir(parents=True)
        (env_dir / "settings.yaml").write_text("iac_tool: terraform\n")

        cm = ConfigManager(base_dir=tmp_path)

        with pytest.raises(PackageNotFoundError, match="nonexistent"):
            cm.resolve_package_filter("test-env", "nonexistent")

    def test_package_with_multiple_resources(self, tmp_path: Path):
        """Package with multiple resource files resolves all resource names."""
        env_dir = tmp_path / "test-env"
        provider_dir = env_dir / "proxmox"
        pkg_dir = provider_dir / "big-cluster"
        pkg_dir.mkdir(parents=True)

        (env_dir / "settings.yaml").write_text("iac_tool: terraform\n")
        (pkg_dir / "infrafoundry.yml").write_text(
            "name: big-cluster\nresources:\n  - vm.yaml\n  - network.yaml\n"
        )
        (pkg_dir / "vm.yaml").write_text(
            "vm:\n  - name: vm-a\n    cores: 2\n  - name: vm-b\n    cores: 2\n"
        )
        (pkg_dir / "network.yaml").write_text("network:\n  - name: net-a\n    bridge: vmbr0\n")

        cm = ConfigManager(base_dir=tmp_path)
        result = cm.resolve_package_filter("test-env", "big-cluster")

        assert sorted(result) == ["net-a", "vm-a", "vm-b"]

    def test_env_root_package_resolves(self, tmp_path: Path):
        """Env-root package (with provider field) resolves correctly."""
        env_dir = tmp_path / "test-env"
        pkg_dir = env_dir / "standalone-pkg"
        pkg_dir.mkdir(parents=True)

        (env_dir / "settings.yaml").write_text("iac_tool: terraform\n")
        (pkg_dir / "infrafoundry.yml").write_text(
            "name: standalone-pkg\nprovider: proxmox\nresources:\n  - vm.yaml\n"
        )
        (pkg_dir / "vm.yaml").write_text("vm:\n  - name: standalone-vm\n    cores: 4\n")

        cm = ConfigManager(base_dir=tmp_path)
        result = cm.resolve_package_filter("test-env", "standalone-pkg")

        assert result == ["standalone-vm"]


# --- CLI mutual exclusivity tests ---


class TestPackageResourceMutualExclusivity:
    """Tests for --package and --resource mutual exclusivity."""

    def test_plan_package_and_resource_mutually_exclusive(self, cli_runner, mock_orchestrator):
        """Plan rejects --package and --resource together."""
        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            result = cli_runner.invoke(
                main,
                ["infra", "plan", "--env", "test", "-p", "my-pkg", "-r", "vm-01"],
            )

            assert result.exit_code != 0
            assert "mutually exclusive" in result.output

    def test_apply_package_and_resource_mutually_exclusive(self, cli_runner, mock_orchestrator):
        """Apply rejects --package and --resource together."""
        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            result = cli_runner.invoke(
                main,
                [
                    "infra",
                    "apply",
                    "--env",
                    "test",
                    "--auto-approve",
                    "-p",
                    "my-pkg",
                    "-r",
                    "vm-01",
                ],
            )

            assert result.exit_code != 0
            assert "mutually exclusive" in result.output

    def test_destroy_package_and_resource_mutually_exclusive(self, cli_runner, mock_orchestrator):
        """Destroy rejects --package and --resource together."""
        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            result = cli_runner.invoke(
                main,
                [
                    "infra",
                    "destroy",
                    "--env",
                    "test",
                    "--auto-approve",
                    "-p",
                    "my-pkg",
                    "-r",
                    "vm-01",
                ],
            )

            assert result.exit_code != 0
            assert "mutually exclusive" in result.output


# --- CLI --package integration tests ---


class TestPlanWithPackage:
    """Tests for plan --package."""

    def test_plan_with_package_resolves_filter(self, cli_runner, mock_orchestrator):
        """Plan --package resolves package to resource filter."""
        mock_orchestrator.config_manager.resolve_package_filter.return_value = [
            "vm-01",
            "vm-02",
        ]

        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            result = cli_runner.invoke(main, ["infra", "plan", "--env", "test", "-p", "my-cluster"])

            assert result.exit_code == 0
            mock_orchestrator.config_manager.resolve_package_filter.assert_called_once_with(
                "test", "my-cluster"
            )
            mock_orchestrator.plan.assert_called_once_with(
                "test",
                dry_run=False,
                resource_filter=["vm-01", "vm-02"],
                enforce_policies=False,
                package_filter="my-cluster",
            )

    def test_plan_with_unknown_package_fails(self, cli_runner, mock_orchestrator):
        """Plan --package with unknown package raises error."""
        mock_orchestrator.config_manager.resolve_package_filter.side_effect = PackageNotFoundError(
            "Package 'bad-pkg' not found in environment 'test'"
        )

        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            result = cli_runner.invoke(main, ["infra", "plan", "--env", "test", "-p", "bad-pkg"])

            assert result.exit_code == 1
            assert "Package Not Found" in result.output


class TestApplyWithPackage:
    """Tests for apply --package."""

    def test_apply_with_package_resolves_filter(self, cli_runner, mock_orchestrator):
        """Apply --package resolves package to resource filter."""
        mock_orchestrator.config_manager.resolve_package_filter.return_value = [
            "vm-01",
        ]

        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            result = cli_runner.invoke(
                main,
                [
                    "infra",
                    "apply",
                    "--env",
                    "test",
                    "--auto-approve",
                    "-p",
                    "my-cluster",
                ],
            )

            assert result.exit_code == 0
            mock_orchestrator.config_manager.resolve_package_filter.assert_called_once_with(
                "test", "my-cluster"
            )
            mock_orchestrator.apply.assert_called_once_with(
                "test",
                auto_approve=True,
                resource_filter=["vm-01"],
                parallel=False,
                max_workers=4,
                package_filter="my-cluster",
                lock_timeout=0,
                lock_ttl=3600,
            )

    def test_apply_with_package_shows_package_in_prompt(self, cli_runner, mock_orchestrator):
        """Apply --package shows package name in confirmation prompt."""
        mock_orchestrator.config_manager.resolve_package_filter.return_value = [
            "vm-01",
        ]

        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            result = cli_runner.invoke(
                main,
                ["infra", "apply", "--env", "test", "-p", "my-cluster"],
                input="y\n",
            )

            assert result.exit_code == 0
            assert "package: my-cluster" in result.output


class TestDestroyWithPackage:
    """Tests for destroy --package."""

    def test_destroy_with_package_resolves_filter(self, cli_runner, mock_orchestrator):
        """Destroy --package resolves package to resource filter."""
        mock_orchestrator.config_manager.resolve_package_filter.return_value = [
            "vm-01",
            "vm-02",
        ]

        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            result = cli_runner.invoke(
                main,
                [
                    "infra",
                    "destroy",
                    "--env",
                    "test",
                    "--auto-approve",
                    "-p",
                    "my-cluster",
                ],
            )

            assert result.exit_code == 0
            mock_orchestrator.config_manager.resolve_package_filter.assert_called_once_with(
                "test", "my-cluster"
            )
            call_args = mock_orchestrator.destroy.call_args
            assert call_args[1]["resource_filter"] == ["vm-01", "vm-02"]
            assert call_args[1]["package_filter"] == "my-cluster"

    def test_destroy_with_package_shows_package_in_prompt(self, cli_runner, mock_orchestrator):
        """Destroy --package shows package name in confirmation prompt."""
        mock_orchestrator.config_manager.resolve_package_filter.return_value = [
            "vm-01",
        ]

        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            result = cli_runner.invoke(
                main,
                ["infra", "destroy", "--env", "test", "-p", "my-cluster"],
                input="y\n",
            )

            assert result.exit_code == 0
            assert "package: my-cluster" in result.output

    def test_destroy_with_unknown_package_fails(self, cli_runner, mock_orchestrator):
        """Destroy --package with unknown package raises error."""
        mock_orchestrator.config_manager.resolve_package_filter.side_effect = PackageNotFoundError(
            "Package 'bad-pkg' not found in environment 'test'"
        )

        with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
            result = cli_runner.invoke(
                main,
                [
                    "infra",
                    "destroy",
                    "--env",
                    "test",
                    "--auto-approve",
                    "-p",
                    "bad-pkg",
                ],
            )

            assert result.exit_code == 1
            assert "Package Not Found" in result.output
