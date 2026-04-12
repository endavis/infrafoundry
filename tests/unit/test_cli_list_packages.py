"""Unit tests for the 'infra list' CLI command."""

import json
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.models import PackageManifest
from infrafoundry.core.exceptions import EnvironmentNotFoundError


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_config_manager():
    """Mock ConfigManager for testing."""
    mock = Mock(spec=ConfigManager)
    mock.provider_centric = Mock()
    mock._package_loader = Mock()
    return mock


def _make_manifest(
    name: str,
    description: str | None = None,
    provider: str | None = None,
    blueprint: str | None = None,
) -> PackageManifest:
    """Create a PackageManifest for testing."""
    return PackageManifest(
        name=name,
        description=description,
        provider=provider,
        blueprint=blueprint,
    )


def test_list_packages_text(cli_runner, mock_config_manager, tmp_path):
    """Test listing packages in text format."""
    mock_config_manager.provider_centric.discover_providers.return_value = {"proxmox"}

    pkg_dir = tmp_path / "prod" / "proxmox" / "my-cluster"
    pkg_dir.mkdir(parents=True)
    mock_config_manager._package_loader.discover_packages.return_value = [pkg_dir]
    mock_config_manager._package_loader.discover_env_root_packages.return_value = []
    mock_config_manager._package_loader._parse_manifest.return_value = _make_manifest(
        name="my-cluster", description="Test cluster"
    )

    with patch(
        "infrafoundry.cli.commands.infra.list_packages.ConfigManager",
        return_value=mock_config_manager,
    ):
        result = cli_runner.invoke(main, ["infra", "list", "--env", "prod"])

    assert result.exit_code == 0
    assert "Packages in prod:" in result.output
    assert "proxmox/my-cluster" in result.output
    assert "Test cluster" in result.output


def test_list_packages_json(cli_runner, mock_config_manager, tmp_path):
    """Test listing packages in JSON format."""
    mock_config_manager.provider_centric.discover_providers.return_value = {"proxmox"}

    pkg_dir = tmp_path / "prod" / "proxmox" / "my-cluster"
    pkg_dir.mkdir(parents=True)
    mock_config_manager._package_loader.discover_packages.return_value = [pkg_dir]
    mock_config_manager._package_loader.discover_env_root_packages.return_value = []
    mock_config_manager._package_loader._parse_manifest.return_value = _make_manifest(
        name="my-cluster", description="Test cluster", blueprint="base-vm"
    )

    with patch(
        "infrafoundry.cli.commands.infra.list_packages.ConfigManager",
        return_value=mock_config_manager,
    ):
        result = cli_runner.invoke(main, ["infra", "list", "--env", "prod", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["environment"] == "prod"
    assert len(data["packages"]) == 1
    pkg = data["packages"][0]
    assert pkg["provider"] == "proxmox"
    assert pkg["name"] == "my-cluster"
    assert pkg["description"] == "Test cluster"
    assert pkg["blueprint"] == "base-vm"


def test_list_packages_empty(cli_runner, mock_config_manager):
    """Test listing packages when none exist."""
    mock_config_manager.provider_centric.discover_providers.return_value = set()
    mock_config_manager._package_loader.discover_env_root_packages.return_value = []

    with patch(
        "infrafoundry.cli.commands.infra.list_packages.ConfigManager",
        return_value=mock_config_manager,
    ):
        result = cli_runner.invoke(main, ["infra", "list", "--env", "prod"])

    assert result.exit_code == 0
    assert "No packages found" in result.output


def test_list_packages_empty_json(cli_runner, mock_config_manager):
    """Test listing packages in JSON format when none exist."""
    mock_config_manager.provider_centric.discover_providers.return_value = set()
    mock_config_manager._package_loader.discover_env_root_packages.return_value = []

    with patch(
        "infrafoundry.cli.commands.infra.list_packages.ConfigManager",
        return_value=mock_config_manager,
    ):
        result = cli_runner.invoke(main, ["infra", "list", "--env", "prod", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["environment"] == "prod"
    assert data["packages"] == []


def test_list_packages_invalid_env(cli_runner, mock_config_manager):
    """Test listing packages with an invalid environment name."""
    mock_config_manager.provider_centric.discover_providers.side_effect = EnvironmentNotFoundError(
        "Environment 'nonexistent' not found"
    )

    with patch(
        "infrafoundry.cli.commands.infra.list_packages.ConfigManager",
        return_value=mock_config_manager,
    ):
        result = cli_runner.invoke(main, ["infra", "list", "--env", "nonexistent"])

    assert result.exit_code != 0


def test_list_packages_no_description(cli_runner, mock_config_manager, tmp_path):
    """Test listing a package without a description."""
    mock_config_manager.provider_centric.discover_providers.return_value = {"proxmox"}

    pkg_dir = tmp_path / "prod" / "proxmox" / "bare-pkg"
    pkg_dir.mkdir(parents=True)
    mock_config_manager._package_loader.discover_packages.return_value = [pkg_dir]
    mock_config_manager._package_loader.discover_env_root_packages.return_value = []
    mock_config_manager._package_loader._parse_manifest.return_value = _make_manifest(
        name="bare-pkg"
    )

    with patch(
        "infrafoundry.cli.commands.infra.list_packages.ConfigManager",
        return_value=mock_config_manager,
    ):
        result = cli_runner.invoke(main, ["infra", "list", "--env", "prod"])

    assert result.exit_code == 0
    assert "proxmox/bare-pkg" in result.output
    # Should not show a dash separator when there's no description
    assert "bare-pkg —" not in result.output


def test_list_packages_multiple_providers(cli_runner, mock_config_manager, tmp_path):
    """Test listing packages across multiple providers."""
    mock_config_manager.provider_centric.discover_providers.return_value = {
        "proxmox",
        "opnsense",
    }

    proxmox_pkg = tmp_path / "prod" / "proxmox" / "cluster"
    proxmox_pkg.mkdir(parents=True)
    opnsense_pkg = tmp_path / "prod" / "opnsense" / "firewall"
    opnsense_pkg.mkdir(parents=True)

    def discover_packages(_env_name, provider):
        if provider == "proxmox":
            return [proxmox_pkg]
        if provider == "opnsense":
            return [opnsense_pkg]
        return []

    mock_config_manager._package_loader.discover_packages.side_effect = discover_packages
    mock_config_manager._package_loader.discover_env_root_packages.return_value = []

    manifests = {
        str(proxmox_pkg): _make_manifest(name="cluster", description="VM cluster"),
        str(opnsense_pkg): _make_manifest(name="firewall", description="Firewall rules"),
    }

    def parse_manifest(path):
        # Match on the parent directory
        parent = str(path.parent)
        return manifests[parent]

    mock_config_manager._package_loader._parse_manifest.side_effect = parse_manifest

    with patch(
        "infrafoundry.cli.commands.infra.list_packages.ConfigManager",
        return_value=mock_config_manager,
    ):
        result = cli_runner.invoke(main, ["infra", "list", "--env", "prod"])

    assert result.exit_code == 0
    assert "opnsense/firewall" in result.output
    assert "proxmox/cluster" in result.output


def test_list_packages_env_root_packages(cli_runner, mock_config_manager, tmp_path):
    """Test listing env-root packages (not under a provider directory)."""
    mock_config_manager.provider_centric.discover_providers.return_value = set()

    pkg_dir = tmp_path / "prod" / "shared-pkg"
    pkg_dir.mkdir(parents=True)
    mock_config_manager._package_loader.discover_env_root_packages.return_value = [pkg_dir]
    mock_config_manager._package_loader._parse_manifest.return_value = _make_manifest(
        name="shared-pkg", description="Shared package", provider="custom"
    )

    with patch(
        "infrafoundry.cli.commands.infra.list_packages.ConfigManager",
        return_value=mock_config_manager,
    ):
        result = cli_runner.invoke(main, ["infra", "list", "--env", "prod"])

    assert result.exit_code == 0
    assert "custom/shared-pkg" in result.output
    assert "Shared package" in result.output


def test_list_packages_with_config_dir(cli_runner, mock_config_manager, tmp_path):
    """Test listing packages with a custom config directory."""
    mock_config_manager.provider_centric.discover_providers.return_value = {"proxmox"}

    pkg_dir = tmp_path / "envs" / "prod" / "proxmox" / "my-pkg"
    pkg_dir.mkdir(parents=True)
    mock_config_manager._package_loader.discover_packages.return_value = [pkg_dir]
    mock_config_manager._package_loader.discover_env_root_packages.return_value = []
    mock_config_manager._package_loader._parse_manifest.return_value = _make_manifest(
        name="my-pkg", description="Custom dir pkg"
    )

    with patch(
        "infrafoundry.cli.commands.infra.list_packages.ConfigManager",
        return_value=mock_config_manager,
    ):
        result = cli_runner.invoke(
            main,
            ["--config-dir", str(tmp_path), "infra", "list", "--env", "prod"],
        )

    assert result.exit_code == 0
    assert "proxmox/my-pkg" in result.output
