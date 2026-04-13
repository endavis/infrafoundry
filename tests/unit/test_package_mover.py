"""Unit tests for PackageMover."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from infrafoundry.core.exceptions import (
    ConfigurationError,
    EnvironmentNotFoundError,
    PackageMoveRollbackError,
    PackageNotFoundError,
)
from infrafoundry.core.package_mover import PackageMover


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a config directory structure."""
    envs = tmp_path / "envs"
    envs.mkdir()
    return tmp_path


@pytest.fixture
def generated_dir(tmp_path: Path) -> Path:
    """Create a generated directory."""
    gen = tmp_path / "generated"
    gen.mkdir()
    return gen


@pytest.fixture
def mock_terraform_runner() -> MagicMock:
    """Create a mock terraform runner."""
    return MagicMock()


@pytest.fixture
def mover(config_dir: Path, generated_dir: Path, mock_terraform_runner: MagicMock) -> PackageMover:
    """Create a PackageMover instance."""
    return PackageMover(
        config_dir=config_dir,
        generated_dir=generated_dir,
        terraform_runner=mock_terraform_runner,
    )


def _create_package(
    envs_dir: Path,
    env_name: str,
    package_name: str,
    provider: str | None = None,
    provider_subdir: str | None = None,
    resources: list[str] | None = None,
) -> Path:
    """Create a package directory with manifest.

    Args:
        envs_dir: Path to envs/ directory
        env_name: Environment name
        package_name: Package name
        provider: Provider to set in manifest (None to omit)
        provider_subdir: Provider subdirectory name (None for env root)
        resources: List of resource filenames to list in manifest

    Returns:
        Path to the created package directory
    """
    if provider_subdir:
        pkg_dir = envs_dir / env_name / provider_subdir / package_name
    else:
        pkg_dir = envs_dir / env_name / package_name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {"name": package_name}
    if provider:
        manifest["provider"] = provider
    if resources:
        manifest["resources"] = resources

    (pkg_dir / "infrafoundry.yml").write_text(yaml.dump(manifest))
    return pkg_dir


def _create_resource_file(pkg_dir: Path, filename: str, resources: list[dict]) -> None:
    """Create a resource YAML file with provider-centric format."""
    stem = Path(filename).stem
    data = {stem: resources}
    (pkg_dir / filename).write_text(yaml.dump(data))


class TestFindPackage:
    """Tests for PackageMover.find_package."""

    def test_find_in_provider_subdir(self, mover: PackageMover, config_dir: Path) -> None:
        """find_package locates a package nested under a provider directory."""
        _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        path, provider = mover.find_package("prod", "my-cluster")
        assert path.name == "my-cluster"
        assert provider == "proxmox"

    def test_find_at_env_root(self, mover: PackageMover, config_dir: Path) -> None:
        """find_package locates a package at the environment root."""
        _create_package(config_dir / "envs", "prod", "my-pkg", provider="opnsense")
        path, provider = mover.find_package("prod", "my-pkg")
        assert path.name == "my-pkg"
        assert provider == "opnsense"

    def test_env_root_missing_provider_raises(self, mover: PackageMover, config_dir: Path) -> None:
        """find_package raises when env root package has no provider in manifest."""
        _create_package(config_dir / "envs", "prod", "orphan")
        with pytest.raises(PackageNotFoundError, match="no provider field"):
            mover.find_package("prod", "orphan")

    def test_missing_package_raises(self, mover: PackageMover, config_dir: Path) -> None:
        """find_package raises PackageNotFoundError for non-existent package."""
        (config_dir / "envs" / "prod").mkdir(parents=True)
        with pytest.raises(PackageNotFoundError, match="not found"):
            mover.find_package("prod", "nonexistent")

    def test_missing_env_raises(self, mover: PackageMover) -> None:
        """find_package raises EnvironmentNotFoundError for missing env."""
        with pytest.raises(EnvironmentNotFoundError):
            mover.find_package("missing-env", "pkg")


class TestGetTerraformAddresses:
    """Tests for PackageMover.get_terraform_addresses."""

    def test_matches_resource_names(
        self,
        mover: PackageMover,
        config_dir: Path,
        generated_dir: Path,
        mock_terraform_runner: MagicMock,
    ) -> None:
        """get_terraform_addresses matches resource names to state addresses."""
        pkg = _create_package(
            config_dir / "envs",
            "prod",
            "my-cluster",
            provider_subdir="proxmox",
            resources=["vm.yaml"],
        )
        _create_resource_file(pkg, "vm.yaml", [{"name": "web-01"}, {"name": "db-01"}])

        tf_dir = generated_dir / "prod" / "terraform" / "proxmox"
        tf_dir.mkdir(parents=True)
        (tf_dir / "terraform.tfstate").write_text("{}")

        mock_terraform_runner.state_list.return_value = [
            "proxmox_virtual_environment_vm.web_01",
            "proxmox_virtual_environment_vm.db_01",
            "proxmox_virtual_environment_vm.other_node",
        ]

        addresses = mover.get_terraform_addresses("prod", "proxmox", pkg)
        assert "proxmox" in addresses
        assert "proxmox_virtual_environment_vm.web_01" in addresses["proxmox"]
        assert "proxmox_virtual_environment_vm.db_01" in addresses["proxmox"]
        assert "proxmox_virtual_environment_vm.other_node" not in addresses["proxmox"]

    def test_matches_prefixed_names(
        self,
        mover: PackageMover,
        config_dir: Path,
        generated_dir: Path,
        mock_terraform_runner: MagicMock,
    ) -> None:
        """get_terraform_addresses handles prefixed terraform names."""
        pkg = _create_package(
            config_dir / "envs", "prod", "aiqum", provider_subdir="proxmox", resources=["vm.yaml"]
        )
        _create_resource_file(pkg, "vm.yaml", [{"name": "aiqum"}])

        tf_dir = generated_dir / "prod" / "terraform" / "proxmox"
        tf_dir.mkdir(parents=True)
        (tf_dir / "terraform.tfstate").write_text("{}")

        mock_terraform_runner.state_list.return_value = [
            "proxmox_virtual_environment_vm.ova_vm_aiqum",
        ]

        addresses = mover.get_terraform_addresses("prod", "proxmox", pkg)
        assert "proxmox" in addresses
        assert "proxmox_virtual_environment_vm.ova_vm_aiqum" in addresses["proxmox"]

    def test_no_state_file_returns_empty(self, mover: PackageMover, config_dir: Path) -> None:
        """get_terraform_addresses returns empty list when no state file exists."""
        pkg = _create_package(
            config_dir / "envs",
            "prod",
            "my-cluster",
            provider_subdir="proxmox",
            resources=["vm.yaml"],
        )
        _create_resource_file(pkg, "vm.yaml", [{"name": "web-01"}])

        addresses = mover.get_terraform_addresses("prod", "proxmox", pkg)
        assert addresses == {}


class TestExecute:
    """Tests for PackageMover.execute."""

    def test_dry_run_returns_actions(
        self, mover: PackageMover, config_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """execute() with dry_run returns planned actions without modifying filesystem."""
        _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        (config_dir / "envs" / "staging").mkdir(parents=True)
        mock_terraform_runner.state_list.return_value = []

        result = mover.execute("prod", "my-cluster", "staging", dry_run=True)

        assert result["dry_run"] is True
        assert len(result["actions"]) > 0
        # Source should still exist
        assert (config_dir / "envs" / "prod" / "proxmox" / "my-cluster").exists()
        # Target should not exist
        assert not (config_dir / "envs" / "staging" / "my-cluster").exists()

    def test_moves_config_dir(
        self, mover: PackageMover, config_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """execute() moves the config directory to the target environment."""
        pkg = _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        (config_dir / "envs" / "staging").mkdir(parents=True)
        mock_terraform_runner.state_list.return_value = []

        result = mover.execute("prod", "my-cluster", "staging")

        assert result["dry_run"] is False
        assert not pkg.exists()
        assert (config_dir / "envs" / "staging" / "my-cluster" / "infrafoundry.yml").exists()

    def test_adds_provider_field(
        self, mover: PackageMover, config_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """execute() adds provider field to manifest when missing."""
        _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        (config_dir / "envs" / "staging").mkdir(parents=True)
        mock_terraform_runner.state_list.return_value = []

        mover.execute("prod", "my-cluster", "staging")

        manifest_text = (
            config_dir / "envs" / "staging" / "my-cluster" / "infrafoundry.yml"
        ).read_text()
        assert "provider: proxmox" in manifest_text

    def test_skips_provider_field_when_present(
        self, mover: PackageMover, config_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """execute() does not duplicate provider field when already present."""
        _create_package(
            config_dir / "envs", "prod", "my-cluster", provider="proxmox", provider_subdir="proxmox"
        )
        (config_dir / "envs" / "staging").mkdir(parents=True)
        mock_terraform_runner.state_list.return_value = []

        mover.execute("prod", "my-cluster", "staging")

        manifest_text = (
            config_dir / "envs" / "staging" / "my-cluster" / "infrafoundry.yml"
        ).read_text()
        assert manifest_text.count("provider:") == 1

    def test_copies_state_file(
        self,
        mover: PackageMover,
        config_dir: Path,
        generated_dir: Path,
        mock_terraform_runner: MagicMock,
    ) -> None:
        """execute() copies state file when target has none."""
        pkg = _create_package(
            config_dir / "envs",
            "prod",
            "my-cluster",
            provider_subdir="proxmox",
            resources=["vm.yaml"],
        )
        _create_resource_file(pkg, "vm.yaml", [{"name": "web-01"}])
        (config_dir / "envs" / "staging").mkdir(parents=True)

        source_tf = generated_dir / "prod" / "terraform" / "proxmox"
        source_tf.mkdir(parents=True)
        (source_tf / "terraform.tfstate").write_text('{"version": 4}')
        (source_tf / "terraform.tfstate.backup").write_text('{"version": 3}')

        mock_terraform_runner.state_list.return_value = ["proxmox_virtual_environment_vm.web_01"]
        mock_terraform_runner.state_rm.return_value = True

        mover.execute("prod", "my-cluster", "staging")

        target_tf = generated_dir / "staging" / "terraform" / "proxmox"
        assert (target_tf / "terraform.tfstate").exists()
        assert (target_tf / "terraform.tfstate.backup").exists()

    def test_skips_state_copy_when_target_has_state(
        self,
        mover: PackageMover,
        config_dir: Path,
        generated_dir: Path,
        mock_terraform_runner: MagicMock,
    ) -> None:
        """execute() skips state copy when target already has terraform.tfstate."""
        pkg = _create_package(
            config_dir / "envs",
            "prod",
            "my-cluster",
            provider_subdir="proxmox",
            resources=["vm.yaml"],
        )
        _create_resource_file(pkg, "vm.yaml", [{"name": "web-01"}])
        (config_dir / "envs" / "staging").mkdir(parents=True)

        source_tf = generated_dir / "prod" / "terraform" / "proxmox"
        source_tf.mkdir(parents=True)
        (source_tf / "terraform.tfstate").write_text('{"version": 4}')

        target_tf = generated_dir / "staging" / "terraform" / "proxmox"
        target_tf.mkdir(parents=True)
        (target_tf / "terraform.tfstate").write_text('{"version": 99}')

        mock_terraform_runner.state_list.return_value = ["proxmox_virtual_environment_vm.web_01"]
        mock_terraform_runner.state_rm.return_value = True

        mover.execute("prod", "my-cluster", "staging")

        # Target state should be unchanged
        assert (target_tf / "terraform.tfstate").read_text() == '{"version": 99}'

    def test_calls_state_rm_for_resources(
        self,
        mover: PackageMover,
        config_dir: Path,
        generated_dir: Path,
        mock_terraform_runner: MagicMock,
    ) -> None:
        """execute() calls terraform state rm for each matched resource address."""
        pkg = _create_package(
            config_dir / "envs",
            "prod",
            "my-cluster",
            provider_subdir="proxmox",
            resources=["vm.yaml"],
        )
        _create_resource_file(pkg, "vm.yaml", [{"name": "web-01"}, {"name": "db-01"}])
        (config_dir / "envs" / "staging").mkdir(parents=True)

        source_tf = generated_dir / "prod" / "terraform" / "proxmox"
        source_tf.mkdir(parents=True)
        (source_tf / "terraform.tfstate").write_text("{}")

        mock_terraform_runner.state_list.return_value = [
            "proxmox_virtual_environment_vm.web_01",
            "proxmox_virtual_environment_vm.db_01",
        ]
        mock_terraform_runner.state_rm.return_value = True

        mover.execute("prod", "my-cluster", "staging")

        assert mock_terraform_runner.state_rm.call_count == 2
        calls = [c.args for c in mock_terraform_runner.state_rm.call_args_list]
        addresses = [c[1] for c in calls]
        assert "proxmox_virtual_environment_vm.web_01" in addresses
        assert "proxmox_virtual_environment_vm.db_01" in addresses

    def test_removes_source_directory(
        self, mover: PackageMover, config_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """execute() removes the source config directory after move."""
        pkg = _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        (config_dir / "envs" / "staging").mkdir(parents=True)
        mock_terraform_runner.state_list.return_value = []

        mover.execute("prod", "my-cluster", "staging")

        assert not pkg.exists()

    def test_create_env_creates_target(
        self, mover: PackageMover, config_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """execute() with create_env creates the target environment directory."""
        _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        mock_terraform_runner.state_list.return_value = []

        mover.execute("prod", "my-cluster", "new-env", create_env=True)

        assert (config_dir / "envs" / "new-env").exists()
        assert (config_dir / "envs" / "new-env" / "my-cluster" / "infrafoundry.yml").exists()

    def test_missing_target_without_create_env_raises(
        self, mover: PackageMover, config_dir: Path
    ) -> None:
        """execute() raises when target env doesn't exist and create_env is False."""
        _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")

        with pytest.raises(EnvironmentNotFoundError, match="Use --create-env"):
            mover.execute("prod", "my-cluster", "nonexistent")

    def test_target_already_exists_raises(self, mover: PackageMover, config_dir: Path) -> None:
        """execute() raises when target package directory already exists."""
        _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        # Create conflicting target
        target = config_dir / "envs" / "staging" / "my-cluster"
        target.mkdir(parents=True)

        with pytest.raises(ConfigurationError, match="already exists"):
            mover.execute("prod", "my-cluster", "staging")

    def test_no_state_file_config_only_move(
        self, mover: PackageMover, config_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """execute() handles packages with no terraform state (config-only move)."""
        _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        (config_dir / "envs" / "staging").mkdir(parents=True)
        mock_terraform_runner.state_list.return_value = []

        result = mover.execute("prod", "my-cluster", "staging")

        assert result["state_addresses"] == {}
        assert result["state_rm_results"] == []
        assert (config_dir / "envs" / "staging" / "my-cluster" / "infrafoundry.yml").exists()

    def test_state_db_update_called(
        self, mover: PackageMover, config_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """execute() attempts to update the state DB."""
        _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        (config_dir / "envs" / "staging").mkdir(parents=True)
        mock_terraform_runner.state_list.return_value = []

        with patch.object(mover, "_update_state_db", return_value=True) as mock_db:
            mover.execute("prod", "my-cluster", "staging")
            mock_db.assert_called_once_with("prod", "staging", "proxmox", "my-cluster")


class TestAddProviderToManifest:
    """Tests for the _add_provider_to_manifest helper."""

    def test_inserts_after_name(self, tmp_path: Path) -> None:
        """Provider field is inserted after the name line."""
        manifest = tmp_path / "infrafoundry.yml"
        manifest.write_text("name: my-cluster\nvariables:\n  foo: bar\n")

        mover = PackageMover(config_dir=tmp_path, generated_dir=tmp_path)
        mover._add_provider_to_manifest(manifest, "proxmox")

        lines = manifest.read_text().splitlines()
        assert lines[0] == "name: my-cluster"
        assert lines[1] == "provider: proxmox"
        assert lines[2] == "variables:"


class TestExtractResourceNames:
    """Tests for resource name extraction from YAML files."""

    def test_provider_centric_format(self, tmp_path: Path, config_dir: Path) -> None:
        """Extracts names from provider-centric resource format."""
        pkg = _create_package(
            config_dir / "envs",
            "prod",
            "test-pkg",
            provider_subdir="proxmox",
            resources=["vm.yaml"],
        )
        _create_resource_file(pkg, "vm.yaml", [{"name": "web-01"}, {"name": "db-01"}])

        mover = PackageMover(config_dir=config_dir, generated_dir=tmp_path)
        manifest = mover._parse_manifest(pkg / "infrafoundry.yml")
        names = mover._extract_resource_names(pkg, manifest)
        assert "web-01" in names
        assert "db-01" in names

    def test_resource_centric_format(self, tmp_path: Path, config_dir: Path) -> None:
        """Extracts names from resource-centric format."""
        pkg = _create_package(
            config_dir / "envs",
            "prod",
            "test-pkg",
            provider_subdir="proxmox",
            resources=["resources.yaml"],
        )
        data = {
            "resources": [
                {"name": "web-01", "type": "vm", "provider": "proxmox"},
                {"name": "db-01", "type": "vm", "provider": "proxmox"},
            ]
        }
        (pkg / "resources.yaml").write_text(yaml.dump(data))

        mover = PackageMover(config_dir=config_dir, generated_dir=tmp_path)
        manifest = mover._parse_manifest(pkg / "infrafoundry.yml")
        names = mover._extract_resource_names(pkg, manifest)
        assert "web-01" in names
        assert "db-01" in names


class TestExecuteRollback:
    """Tests for PackageMover.execute rollback behaviour."""

    def test_rollback_on_state_db_failure_preserves_source(
        self, mover: PackageMover, config_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """On state DB failure, source directory is preserved and target is cleaned up."""
        pkg = _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        (config_dir / "envs" / "staging").mkdir(parents=True)
        mock_terraform_runner.state_list.return_value = []

        # Make _update_state_db raise
        with (
            patch.object(mover, "_update_state_db", side_effect=RuntimeError("DB connection lost")),
            pytest.raises(RuntimeError, match="DB connection lost"),
        ):
            mover.execute("prod", "my-cluster", "staging")

        # Source should still exist (rollback restored it from target copy)
        assert pkg.exists()
        # Target should be cleaned up
        assert not (config_dir / "envs" / "staging" / "my-cluster").exists()

    def test_rollback_on_terraform_state_rm_failure(
        self,
        mover: PackageMover,
        config_dir: Path,
        generated_dir: Path,
        mock_terraform_runner: MagicMock,
    ) -> None:
        """On terraform state_rm failure (exception), config copy is undone."""
        pkg = _create_package(
            config_dir / "envs",
            "prod",
            "my-cluster",
            provider_subdir="proxmox",
            resources=["vm.yaml"],
        )
        _create_resource_file(pkg, "vm.yaml", [{"name": "web-01"}])
        (config_dir / "envs" / "staging").mkdir(parents=True)

        source_tf = generated_dir / "prod" / "terraform" / "proxmox"
        source_tf.mkdir(parents=True)
        (source_tf / "terraform.tfstate").write_text('{"version": 4}')

        mock_terraform_runner.state_list.return_value = ["proxmox_virtual_environment_vm.web_01"]
        mock_terraform_runner.state_rm.side_effect = RuntimeError("state rm exploded")

        with pytest.raises(RuntimeError, match="state rm exploded"):
            mover.execute("prod", "my-cluster", "staging")

        # Source directory should be preserved
        assert pkg.exists()
        # Target directory should be cleaned up
        assert not (config_dir / "envs" / "staging" / "my-cluster").exists()

    def test_rollback_error_raises_package_move_rollback_error(
        self, mover: PackageMover, config_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """PackageMoveRollbackError raised when undo also fails."""
        _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        (config_dir / "envs" / "staging").mkdir(parents=True)
        mock_terraform_runner.state_list.return_value = []

        # Make _update_state_db raise to trigger rollback
        with patch.object(mover, "_update_state_db", side_effect=RuntimeError("DB fail")):
            # Make shutil.rmtree fail during rollback (target cleanup)
            original_rmtree = shutil.rmtree

            def rmtree_that_fails_on_target(path, *args, **kwargs):
                if "staging" in str(path) and "my-cluster" in str(path):
                    raise OSError("Cannot remove target during rollback")
                return original_rmtree(path, *args, **kwargs)

            with patch(
                "infrafoundry.core.package_mover.shutil.rmtree",
                side_effect=rmtree_that_fails_on_target,
            ):
                with pytest.raises(PackageMoveRollbackError) as exc_info:
                    mover.execute("prod", "my-cluster", "staging")

                assert exc_info.value.original_error is not None
                assert len(exc_info.value.rollback_errors) > 0

    def test_happy_path_unchanged(
        self, mover: PackageMover, config_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """Happy path still works with rollback machinery in place."""
        pkg = _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        (config_dir / "envs" / "staging").mkdir(parents=True)
        mock_terraform_runner.state_list.return_value = []

        with patch.object(mover, "_update_state_db", return_value=True):
            result = mover.execute("prod", "my-cluster", "staging")

        assert result["dry_run"] is False
        assert not pkg.exists()
        assert (config_dir / "envs" / "staging" / "my-cluster" / "infrafoundry.yml").exists()

    def test_state_manager_injection(
        self, config_dir: Path, generated_dir: Path, mock_terraform_runner: MagicMock
    ) -> None:
        """state_manager kwarg is used instead of creating a default."""
        mock_state_mgr = MagicMock()
        mock_state_mgr.get_resources.return_value = []
        mover = PackageMover(
            config_dir=config_dir,
            generated_dir=generated_dir,
            terraform_runner=mock_terraform_runner,
            state_manager=mock_state_mgr,
        )
        _create_package(config_dir / "envs", "prod", "my-cluster", provider_subdir="proxmox")
        (config_dir / "envs" / "staging").mkdir(parents=True)
        mock_terraform_runner.state_list.return_value = []

        mover.execute("prod", "my-cluster", "staging")

        mock_state_mgr.initialize.assert_called()
        mock_state_mgr.get_resources.assert_called_once()
