"""Unit tests for per-package terraform state isolation.

Verifies that ``set_package_context()`` / ``clear_package_context()`` on
``ProviderBase`` correctly switch the ``terraform_dir`` between package-scoped
and provider-scoped paths, and that the orchestrator's package-grouping helpers
correctly split resources by package.
"""

from pathlib import Path
from typing import Any, override

import pytest
import yaml

from infrafoundry.core.config.config_manager import ConfigManager
from infrafoundry.core.deployment_executor import DeploymentExecutor
from infrafoundry.core.orchestrator_workflows import PlanOrchestrator
from infrafoundry.core.provider import ProviderBase, ResourceConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubProvider(ProviderBase):
    """Minimal concrete provider for testing."""

    @override
    def validate_config(self, config: dict[str, Any]) -> bool:
        return True

    @override
    def generate_terraform(self, resources: list[ResourceConfig]) -> None:
        pass

    @override
    def generate_ansible(self, resources: list[ResourceConfig]) -> None:
        pass

    @override
    def get_resource_types(self) -> list[str]:
        return ["vm", "container"]


def _make_resource(name: str, provider: str = "proxmox") -> ResourceConfig:
    return ResourceConfig(name=name, type="vm", provider=provider, config={"name": name})


def _create_env(base_dir: Path, env_name: str) -> Path:
    env_dir = base_dir / env_name
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / "settings.yaml").write_text(f"name: {env_name}\n")
    return env_dir


def _create_package(
    base_dir: Path,
    env_name: str,
    package_name: str,
    manifest: dict[str, Any],
    resource_files: dict[str, Any] | None = None,
    provider: str | None = None,
) -> Path:
    if provider:
        package_dir = base_dir / env_name / provider / package_name
    else:
        package_dir = base_dir / env_name / package_name
    package_dir.mkdir(parents=True, exist_ok=True)
    with open(package_dir / "infrafoundry.yml", "w") as f:
        yaml.dump(manifest, f)
    if resource_files:
        for filename, content in resource_files.items():
            resource_path = package_dir / filename
            resource_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                resource_path.write_text(content)
            else:
                with open(resource_path, "w") as f:
                    yaml.dump(content, f)
    return package_dir


def _create_loose_resources(
    base_dir: Path, env_name: str, provider: str, filename: str, content: Any
) -> Path:
    provider_dir = base_dir / env_name / provider
    provider_dir.mkdir(parents=True, exist_ok=True)
    resource_path = provider_dir / filename
    if isinstance(content, str):
        resource_path.write_text(content)
    else:
        with open(resource_path, "w") as f:
            yaml.dump(content, f)
    return resource_path


# ---------------------------------------------------------------------------
# Tests: ProviderBase.set_package_context / clear_package_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSetPackageContext:
    """Tests for ProviderBase.set_package_context and clear_package_context."""

    def test_set_package_context_updates_terraform_dir(self, tmp_path: Path) -> None:
        """set_package_context sets terraform_dir to package-scoped path."""
        provider = _StubProvider("proxmox", tmp_path / "config", tmp_path / "output")
        provider.set_environment("prod")
        provider.set_package_context("ontap-cluster")

        expected = tmp_path / "output" / "prod" / "terraform" / "ontap-cluster"
        assert provider.terraform_dir == expected

    def test_clear_package_context_restores_provider_dir(self, tmp_path: Path) -> None:
        """clear_package_context restores terraform_dir to per-provider path."""
        provider = _StubProvider("proxmox", tmp_path / "config", tmp_path / "output")
        provider.set_environment("prod")
        provider.set_package_context("ontap-cluster")
        provider.clear_package_context()

        expected = tmp_path / "output" / "prod" / "terraform" / "proxmox"
        assert provider.terraform_dir == expected

    def test_without_package_context_uses_provider_dir(self, tmp_path: Path) -> None:
        """Without package context, terraform_dir is the default provider path."""
        provider = _StubProvider("proxmox", tmp_path / "config", tmp_path / "output")
        provider.set_environment("prod")

        expected = tmp_path / "output" / "prod" / "terraform" / "proxmox"
        assert provider.terraform_dir == expected

    def test_package_dir_is_env_scoped(self, tmp_path: Path) -> None:
        """Package terraform dir is under the environment's output directory."""
        provider = _StubProvider("proxmox", tmp_path / "config", tmp_path / "output")
        provider.set_environment("staging")
        provider.set_package_context("k8s-cluster")

        assert "staging" in str(provider.terraform_dir)
        assert "k8s-cluster" in str(provider.terraform_dir)

    def test_set_environment_clears_package_context(self, tmp_path: Path) -> None:
        """Calling set_environment resets any active package context."""
        provider = _StubProvider("proxmox", tmp_path / "config", tmp_path / "output")
        provider.set_environment("prod")
        provider.set_package_context("ontap-cluster")
        provider.set_environment("staging")

        assert provider._current_package is None
        expected = tmp_path / "output" / "staging" / "terraform" / "proxmox"
        assert provider.terraform_dir == expected

    def test_two_packages_get_separate_dirs(self, tmp_path: Path) -> None:
        """Two different packages produce distinct terraform directories."""
        provider = _StubProvider("proxmox", tmp_path / "config", tmp_path / "output")
        provider.set_environment("prod")

        provider.set_package_context("ontap-cluster")
        dir_a = provider.terraform_dir

        provider.set_package_context("k8s-cluster")
        dir_b = provider.terraform_dir

        assert dir_a != dir_b
        assert dir_a.name == "ontap-cluster"
        assert dir_b.name == "k8s-cluster"

    def test_set_package_context_without_environment_raises(self, tmp_path: Path) -> None:
        """set_package_context raises RuntimeError without set_environment first."""
        provider = _StubProvider("proxmox", tmp_path / "config", tmp_path / "output")
        with pytest.raises(RuntimeError, match="set_environment"):
            provider.set_package_context("my-pkg")

    def test_clear_without_prior_set_is_safe(self, tmp_path: Path) -> None:
        """clear_package_context is a no-op when no package context is active."""
        provider = _StubProvider("proxmox", tmp_path / "config", tmp_path / "output")
        provider.set_environment("prod")
        provider.clear_package_context()  # should not raise

        expected = tmp_path / "output" / "prod" / "terraform" / "proxmox"
        assert provider.terraform_dir == expected

    def test_ensure_directories_creates_package_dir(self, tmp_path: Path) -> None:
        """ensure_directories creates the package-scoped terraform directory."""
        provider = _StubProvider("proxmox", tmp_path / "config", tmp_path / "output")
        provider.set_environment("prod")
        provider.set_package_context("my-pkg")
        provider.ensure_directories()

        assert provider.terraform_dir.exists()
        assert provider.terraform_dir == tmp_path / "output" / "prod" / "terraform" / "my-pkg"


# ---------------------------------------------------------------------------
# Tests: _group_by_package helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGroupByPackage:
    """Tests for PlanOrchestrator._group_by_package and DeploymentExecutor._group_by_package."""

    def test_all_loose_resources(self) -> None:
        """When no package map, all resources go to the None group."""
        resources = [_make_resource("vm-1"), _make_resource("vm-2")]
        groups = PlanOrchestrator._group_by_package(resources, {})
        assert len(groups) == 1
        pkg_name, pkg_resources = groups[0]
        assert pkg_name is None
        assert len(pkg_resources) == 2

    def test_all_packaged_resources(self) -> None:
        """When all resources are in packages, no None group is produced."""
        resources = [_make_resource("vm-1"), _make_resource("vm-2")]
        pkg_map = {"vm-1": "pkg-a", "vm-2": "pkg-a"}
        groups = PlanOrchestrator._group_by_package(resources, pkg_map)
        assert len(groups) == 1
        assert groups[0][0] == "pkg-a"
        assert len(groups[0][1]) == 2

    def test_mixed_packages_and_loose(self) -> None:
        """Mixed resources are split into package groups and a loose group."""
        resources = [
            _make_resource("vm-1"),
            _make_resource("vm-2"),
            _make_resource("vm-3"),
        ]
        pkg_map = {"vm-1": "pkg-a", "vm-2": "pkg-b"}
        groups = PlanOrchestrator._group_by_package(resources, pkg_map)

        # Should have 3 groups: pkg-a, pkg-b, None
        assert len(groups) == 3
        names = [g[0] for g in groups]
        assert names == ["pkg-a", "pkg-b", None]

    def test_packages_sorted_deterministically(self) -> None:
        """Package groups are sorted alphabetically for deterministic execution."""
        resources = [
            _make_resource("vm-1"),
            _make_resource("vm-2"),
            _make_resource("vm-3"),
        ]
        pkg_map = {"vm-1": "zzz-pkg", "vm-2": "aaa-pkg", "vm-3": "mmm-pkg"}
        groups = PlanOrchestrator._group_by_package(resources, pkg_map)
        names = [g[0] for g in groups]
        assert names == ["aaa-pkg", "mmm-pkg", "zzz-pkg"]

    def test_deployment_executor_group_matches_plan(self) -> None:
        """DeploymentExecutor._group_by_package produces identical results."""
        resources = [_make_resource("vm-1"), _make_resource("vm-2")]
        pkg_map = {"vm-1": "pkg-a"}
        plan_groups = PlanOrchestrator._group_by_package(resources, pkg_map)
        exec_groups = DeploymentExecutor._group_by_package(resources, pkg_map)
        assert plan_groups == exec_groups

    def test_empty_resources(self) -> None:
        """Empty resource list produces no groups."""
        groups = PlanOrchestrator._group_by_package([], {})
        assert groups == []


# ---------------------------------------------------------------------------
# Tests: ConfigManager.get_package_for_resource / get_resource_package_map
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigManagerPackageMap:
    """Tests for ConfigManager.get_package_for_resource and get_resource_package_map."""

    def test_get_package_for_resource_in_provider_scoped_package(self, temp_dir: Path) -> None:
        """Resource in a provider-scoped package returns the package name."""
        _create_env(temp_dir, "dev")
        _create_package(
            temp_dir,
            "dev",
            "my-cluster",
            {"name": "my-cluster", "resources": ["vm.yaml"]},
            resource_files={
                "vm.yaml": {"vm": [{"name": "node-01"}]},
            },
            provider="proxmox",
        )
        cm = ConfigManager(temp_dir)
        assert cm.get_package_for_resource("dev", "node-01") == "my-cluster"

    def test_get_package_for_resource_in_env_root_package(self, temp_dir: Path) -> None:
        """Resource in an env-root package returns the package name."""
        _create_env(temp_dir, "dev")
        _create_package(
            temp_dir,
            "dev",
            "my-cluster",
            {"name": "my-cluster", "provider": "proxmox", "resources": ["vm.yaml"]},
            resource_files={
                "vm.yaml": {"vm": [{"name": "node-01"}]},
            },
        )
        cm = ConfigManager(temp_dir)
        assert cm.get_package_for_resource("dev", "node-01") == "my-cluster"

    def test_get_package_for_resource_loose_returns_none(self, temp_dir: Path) -> None:
        """Loose resource not in any package returns None."""
        _create_env(temp_dir, "dev")
        _create_loose_resources(
            temp_dir,
            "dev",
            "proxmox",
            "vm.yaml",
            {"vm": [{"name": "standalone-vm"}]},
        )
        cm = ConfigManager(temp_dir)
        assert cm.get_package_for_resource("dev", "standalone-vm") is None

    def test_get_resource_package_map_includes_all_packages(self, temp_dir: Path) -> None:
        """get_resource_package_map returns all package resources."""
        _create_env(temp_dir, "dev")
        _create_package(
            temp_dir,
            "dev",
            "cluster-a",
            {"name": "cluster-a", "provider": "proxmox", "resources": ["vm.yaml"]},
            resource_files={
                "vm.yaml": {"vm": [{"name": "vm-a1"}, {"name": "vm-a2"}]},
            },
        )
        _create_package(
            temp_dir,
            "dev",
            "cluster-b",
            {"name": "cluster-b", "resources": ["vm.yaml"]},
            resource_files={
                "vm.yaml": {"vm": [{"name": "vm-b1"}]},
            },
            provider="proxmox",
        )
        cm = ConfigManager(temp_dir)
        pkg_map = cm.get_resource_package_map("dev")
        assert pkg_map == {
            "vm-a1": "cluster-a",
            "vm-a2": "cluster-a",
            "vm-b1": "cluster-b",
        }

    def test_get_resource_package_map_excludes_loose_resources(self, temp_dir: Path) -> None:
        """Loose resources are not included in the package map."""
        _create_env(temp_dir, "dev")
        _create_loose_resources(
            temp_dir,
            "dev",
            "proxmox",
            "vm.yaml",
            {"vm": [{"name": "loose-vm"}]},
        )
        cm = ConfigManager(temp_dir)
        pkg_map = cm.get_resource_package_map("dev")
        assert "loose-vm" not in pkg_map
