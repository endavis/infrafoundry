"""Unit tests for env-root package discovery and integration."""

import warnings

import pytest
import yaml

from infrafoundry.core.config.config_manager import ConfigManager
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.config.provider_centric_loader import ProviderCentricLoader
from infrafoundry.core.exceptions import InvalidConfigurationError, PackageNotFoundError


def _create_env(base_dir, env_name):
    """Create a minimal environment directory with settings.yaml."""
    env_dir = base_dir / env_name
    env_dir.mkdir(parents=True, exist_ok=True)
    settings_path = env_dir / "settings.yaml"
    settings_path.write_text(f"name: {env_name}\n")
    return env_dir


def _create_package(base_dir, env_name, package_name, manifest, resource_files=None, provider=None):
    """Create a package directory structure.

    Args:
        base_dir: Base envs directory
        env_name: Environment name
        package_name: Package subdirectory name
        manifest: Dict for infrafoundry.yml content
        resource_files: Optional dict of filename -> content
        provider: If set, create under provider subdir instead of env root
    """
    if provider:
        package_dir = base_dir / env_name / provider / package_name
    else:
        package_dir = base_dir / env_name / package_name
    package_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = package_dir / "infrafoundry.yml"
    with open(manifest_path, "w") as f:
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


def _create_loose_resources(base_dir, env_name, provider, resource_file, content):
    """Create loose resource files under a provider directory."""
    provider_dir = base_dir / env_name / provider
    provider_dir.mkdir(parents=True, exist_ok=True)
    resource_path = provider_dir / resource_file
    if isinstance(content, str):
        resource_path.write_text(content)
    else:
        with open(resource_path, "w") as f:
            yaml.dump(content, f)
    return resource_path


@pytest.mark.unit
class TestDiscoverEnvRootPackages:
    """Tests for PackageLoader.discover_env_root_packages."""

    def test_discovers_packages_at_env_root(self, temp_dir):
        """Subdirectory of env root with infrafoundry.yml is discovered."""
        loader = PackageLoader(temp_dir)
        _create_env(temp_dir, "dev")
        _create_package(temp_dir, "dev", "my-pkg", {"name": "my-pkg", "provider": "proxmox"})

        packages = loader.discover_env_root_packages("dev")
        assert len(packages) == 1
        assert packages[0].name == "my-pkg"

    def test_discovers_multiple_packages_sorted(self, temp_dir):
        """Multiple packages are returned sorted by name."""
        loader = PackageLoader(temp_dir)
        _create_env(temp_dir, "dev")
        _create_package(temp_dir, "dev", "zeta-pkg", {"name": "zeta", "provider": "proxmox"})
        _create_package(temp_dir, "dev", "alpha-pkg", {"name": "alpha", "provider": "proxmox"})

        packages = loader.discover_env_root_packages("dev")
        names = [p.name for p in packages]
        assert names == ["alpha-pkg", "zeta-pkg"]

    def test_skips_excluded_dirs(self, temp_dir):
        """Directories in EXCLUDED_DIRS and ENV_ROOT_EXCLUDED_DIRS are skipped."""
        loader = PackageLoader(temp_dir)
        _create_env(temp_dir, "dev")

        # Create dirs that should be excluded
        for excluded in ("resources", "secrets", "roles", "scripts"):
            excluded_dir = temp_dir / "dev" / excluded
            excluded_dir.mkdir(parents=True, exist_ok=True)
            (excluded_dir / "infrafoundry.yml").write_text("name: excluded\n")

        # Create valid package
        _create_package(temp_dir, "dev", "valid-pkg", {"name": "valid", "provider": "proxmox"})

        packages = loader.discover_env_root_packages("dev")
        assert len(packages) == 1
        assert packages[0].name == "valid-pkg"

    def test_skips_dirs_without_manifest(self, temp_dir):
        """Subdirectories without infrafoundry.yml are not discovered."""
        loader = PackageLoader(temp_dir)
        _create_env(temp_dir, "dev")
        no_manifest_dir = temp_dir / "dev" / "plain-dir"
        no_manifest_dir.mkdir(parents=True)
        (no_manifest_dir / "some-file.yaml").write_text("key: value\n")

        packages = loader.discover_env_root_packages("dev")
        assert packages == []

    def test_skips_files(self, temp_dir):
        """Files at env root are not treated as packages."""
        loader = PackageLoader(temp_dir)
        _create_env(temp_dir, "dev")
        (temp_dir / "dev" / "extra.yaml").write_text("key: value\n")

        packages = loader.discover_env_root_packages("dev")
        assert packages == []

    def test_nonexistent_env(self, temp_dir):
        """Non-existent environment returns empty list."""
        loader = PackageLoader(temp_dir)
        packages = loader.discover_env_root_packages("nonexistent")
        assert packages == []


@pytest.mark.unit
class TestManifestProviderField:
    """Tests for the provider field on PackageManifest."""

    def test_manifest_provider_parsed(self, temp_dir):
        """Provider field is parsed from manifest."""
        loader = PackageLoader(temp_dir)
        pkg_dir = temp_dir / "pkg"
        pkg_dir.mkdir()
        manifest_path = pkg_dir / "infrafoundry.yml"
        manifest_path.write_text("name: my-pkg\nprovider: proxmox\n")

        manifest = loader._parse_manifest(manifest_path)
        assert manifest.provider == "proxmox"

    def test_manifest_provider_defaults_to_none(self, temp_dir):
        """Provider field defaults to None when not specified."""
        loader = PackageLoader(temp_dir)
        pkg_dir = temp_dir / "pkg"
        pkg_dir.mkdir()
        manifest_path = pkg_dir / "infrafoundry.yml"
        manifest_path.write_text("name: my-pkg\n")

        manifest = loader._parse_manifest(manifest_path)
        assert manifest.provider is None

    def test_manifest_provider_overrides_directory_inferred(self, temp_dir):
        """Manifest provider overrides directory-inferred provider in load_package."""
        loader = PackageLoader(temp_dir)
        manifest = {
            "name": "my-pkg",
            "provider": "esxi",
            "resources": ["vm.yaml"],
        }
        resource_content = "vm:\n  - name: test-vm\n    cores: 2\n"
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "my-pkg",
            manifest,
            {"vm.yaml": resource_content},
            provider="proxmox",
        )

        resources, _, _pkg_vars = loader.load_package(pkg_dir, "proxmox", "dev")
        assert len(resources) == 1
        # Should use manifest provider "esxi", not directory-inferred "proxmox"
        assert resources[0].provider == "esxi"

    def test_directory_inferred_provider_used_as_fallback(self, temp_dir):
        """When manifest has no provider, directory-inferred provider is used."""
        loader = PackageLoader(temp_dir)
        manifest = {
            "name": "my-pkg",
            "resources": ["vm.yaml"],
        }
        resource_content = "vm:\n  - name: test-vm\n    cores: 2\n"
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "my-pkg",
            manifest,
            {"vm.yaml": resource_content},
            provider="proxmox",
        )

        resources, _, _pkg_vars = loader.load_package(pkg_dir, "proxmox", "dev")
        assert len(resources) == 1
        assert resources[0].provider == "proxmox"


@pytest.mark.unit
class TestDiscoverProvidersSkipsPackages:
    """Tests for discover_providers() skipping env-root package dirs."""

    def test_skips_directory_with_manifest(self, temp_dir):
        """Directory containing infrafoundry.yml is not treated as a provider."""
        loader = ProviderCentricLoader(temp_dir)
        _create_env(temp_dir, "dev")

        # Create a real provider directory
        provider_dir = temp_dir / "dev" / "proxmox"
        provider_dir.mkdir(parents=True)

        # Create an env-root package (should be skipped)
        _create_package(temp_dir, "dev", "my-pkg", {"name": "my-pkg", "provider": "proxmox"})

        providers = loader.discover_providers("dev")
        assert "proxmox" in providers
        assert "my-pkg" not in providers

    def test_provider_dir_without_manifest_still_discovered(self, temp_dir):
        """Regular directories without infrafoundry.yml are still providers."""
        loader = ProviderCentricLoader(temp_dir)
        _create_env(temp_dir, "dev")

        for name in ("proxmox", "opnsense"):
            (temp_dir / "dev" / name).mkdir(parents=True)

        providers = loader.discover_providers("dev")
        assert providers == {"proxmox", "opnsense"}


@pytest.mark.unit
class TestEnvRootPackageIntegration:
    """Tests for env-root packages in get_all_resources_all_providers."""

    def test_env_root_packages_loaded(self, temp_dir):
        """Env-root packages are loaded alongside provider-scoped resources."""
        _create_env(temp_dir, "dev")

        # Create provider-scoped loose resource
        _create_loose_resources(
            temp_dir,
            "dev",
            "proxmox",
            "vm.yaml",
            {"vm": [{"name": "loose-vm", "cores": 2}]},
        )

        # Create env-root package
        _create_package(
            temp_dir,
            "dev",
            "my-pkg",
            {"name": "my-pkg", "provider": "proxmox", "resources": ["vm.yaml"]},
            {"vm.yaml": "vm:\n  - name: pkg-vm\n    cores: 4\n"},
        )

        manager = ConfigManager(base_dir=temp_dir)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            resources = manager.get_all_resources_all_providers("dev")

        names = {r.name for r in resources}
        assert "loose-vm" in names
        assert "pkg-vm" in names

    def test_env_root_package_without_provider_raises(self, temp_dir):
        """Env-root package without provider field raises InvalidConfigurationError."""
        _create_env(temp_dir, "dev")
        _create_package(
            temp_dir,
            "dev",
            "bad-pkg",
            {"name": "bad-pkg", "resources": ["vm.yaml"]},
            {"vm.yaml": "vm:\n  - name: test-vm\n"},
        )

        manager = ConfigManager(base_dir=temp_dir)
        with pytest.raises(InvalidConfigurationError, match="must declare a 'provider' field"):
            manager.get_all_resources_all_providers("dev")

    def test_env_root_package_events_accumulated(self, temp_dir):
        """Events from env-root packages are accumulated in package events."""
        _create_env(temp_dir, "dev")
        _create_package(
            temp_dir,
            "dev",
            "my-pkg",
            {
                "name": "my-pkg",
                "provider": "proxmox",
                "events": {
                    "AFTER_APPLY": [{"type": "script", "script": "scripts/setup.sh"}],
                },
            },
        )

        manager = ConfigManager(base_dir=temp_dir)
        manager.get_all_resources_all_providers("dev")
        events = manager.get_package_events()
        assert "AFTER_APPLY" in events

    def test_env_root_package_duplicate_name_detected(self, temp_dir):
        """Duplicate resource names between env-root package and loose resources raise."""
        _create_env(temp_dir, "dev")

        # Create loose resource
        _create_loose_resources(
            temp_dir,
            "dev",
            "proxmox",
            "vm.yaml",
            {"vm": [{"name": "dupe-vm", "cores": 2}]},
        )

        # Create env-root package with same resource name
        _create_package(
            temp_dir,
            "dev",
            "my-pkg",
            {"name": "my-pkg", "provider": "proxmox", "resources": ["vm.yaml"]},
            {"vm.yaml": "vm:\n  - name: dupe-vm\n    cores: 4\n"},
        )

        manager = ConfigManager(base_dir=temp_dir)
        with pytest.raises(ValueError, match="Duplicate resource names"), warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            manager.get_all_resources_all_providers("dev")


@pytest.mark.unit
class TestLooseResourceDeprecationWarning:
    """Tests for deprecation warnings on loose resources."""

    def test_loose_resources_emit_deprecation_warning(self, temp_dir):
        """Loose resource files trigger a DeprecationWarning."""
        _create_env(temp_dir, "dev")
        _create_loose_resources(
            temp_dir,
            "dev",
            "proxmox",
            "vm.yaml",
            {"vm": [{"name": "loose-vm", "cores": 2}]},
        )

        manager = ConfigManager(base_dir=temp_dir)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            manager.get_all_resources_all_providers("dev")

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) == 1
        assert "Loose resources" in str(deprecation_warnings[0].message)
        assert "deprecated" in str(deprecation_warnings[0].message)

    def test_no_warning_when_only_packages(self, temp_dir):
        """No deprecation warning when all resources are in packages."""
        _create_env(temp_dir, "dev")
        _create_package(
            temp_dir,
            "dev",
            "my-pkg",
            {"name": "my-pkg", "provider": "proxmox", "resources": ["vm.yaml"]},
            {"vm.yaml": "vm:\n  - name: pkg-vm\n    cores: 4\n"},
        )

        manager = ConfigManager(base_dir=temp_dir)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            manager.get_all_resources_all_providers("dev")

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) == 0

    def test_resource_centric_loose_files_emit_warning(self, temp_dir):
        """Resource-centric loose files also trigger deprecation warning."""
        _create_env(temp_dir, "dev")

        # Create resource-centric file
        resources_dir = temp_dir / "dev" / "resources"
        resources_dir.mkdir(parents=True)
        resource_file = resources_dir / "infra.yaml"
        resource_file.write_text(
            "resources:\n  - name: rc-vm\n    type: vm\n    provider: proxmox\n"
        )

        manager = ConfigManager(base_dir=temp_dir)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            manager.get_all_resources_all_providers("dev")

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) == 1

    def test_no_warning_when_no_resources(self, temp_dir):
        """No deprecation warning when environment has no resources at all."""
        _create_env(temp_dir, "dev")

        manager = ConfigManager(base_dir=temp_dir)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            manager.get_all_resources_all_providers("dev")

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) == 0


@pytest.mark.unit
class TestPackageNotFoundError:
    """Tests for PackageNotFoundError exception."""

    def test_exception_exists_and_inherits(self):
        """PackageNotFoundError exists and inherits from InfraFoundryError."""
        from infrafoundry.core.exceptions import InfraFoundryError

        error = PackageNotFoundError("test package not found")
        assert isinstance(error, InfraFoundryError)
        assert str(error) == "test package not found"

    def test_exception_with_context(self):
        """PackageNotFoundError accepts context dict."""
        error = PackageNotFoundError(
            "Package 'my-pkg' not found",
            context={"env": "dev", "package": "my-pkg"},
        )
        assert error.context["env"] == "dev"
        assert "my-pkg" in str(error)
