"""Tests for PackageLoader resource parsing."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.provider import ResourceConfig


@pytest.fixture
def loader(tmp_path: Path) -> PackageLoader:
    """Create a PackageLoader with a temporary base directory."""
    return PackageLoader(tmp_path)


class TestParseResourceCentric:
    """Tests for _parse_resource_centric parsing logic."""

    def _parse(
        self,
        loader: PackageLoader,
        resources: list[dict[str, Any]],
        resource_file: str = "resources.yaml",
        default_provider: str = "proxmox",
    ) -> list[ResourceConfig]:
        """Helper to call _parse_resource_centric."""
        return loader._parse_resource_centric(resources, resource_file, default_provider)

    def test_explicit_config_key_injects_name(self, loader: PackageLoader) -> None:
        """When a resource has an explicit config key, name is injected into config."""
        resources = [
            {
                "provider": "proxmox",
                "type": "storage",
                "name": "infra",
                "config": {
                    "backend": "nfs",
                    "server": "192.168.10.50",
                },
            }
        ]
        result = self._parse(loader, resources)
        assert len(result) == 1
        assert result[0].name == "infra"
        assert result[0].config["name"] == "infra"
        assert result[0].config["backend"] == "nfs"

    def test_explicit_config_key_does_not_override_existing_name(
        self, loader: PackageLoader
    ) -> None:
        """If config already contains name, it is not overridden."""
        resources = [
            {
                "provider": "proxmox",
                "type": "storage",
                "name": "infra",
                "config": {
                    "name": "custom-name",
                    "backend": "nfs",
                },
            }
        ]
        result = self._parse(loader, resources)
        assert result[0].config["name"] == "custom-name"

    def test_no_config_key_uses_full_item(self, loader: PackageLoader) -> None:
        """Without explicit config key, the full item dict is used as config."""
        resources = [
            {
                "provider": "proxmox",
                "type": "vm",
                "name": "test-vm",
                "cores": 4,
                "memory": 8192,
            }
        ]
        result = self._parse(loader, resources)
        assert len(result) == 1
        assert result[0].config["name"] == "test-vm"
        assert result[0].config["cores"] == 4
        assert result[0].config["memory"] == 8192

    def test_default_provider_used_when_not_specified(self, loader: PackageLoader) -> None:
        """Resources without provider field use the default provider."""
        resources = [
            {
                "type": "vm",
                "name": "test-vm",
            }
        ]
        result = self._parse(loader, resources, default_provider="esxi")
        assert result[0].provider == "esxi"

    def test_explicit_provider_overrides_default(self, loader: PackageLoader) -> None:
        """Resources with provider field override the default."""
        resources = [
            {
                "provider": "kubernetes",
                "type": "namespace",
                "name": "test-ns",
            }
        ]
        result = self._parse(loader, resources, default_provider="proxmox")
        assert result[0].provider == "kubernetes"

    def test_missing_type_raises_error(self, loader: PackageLoader) -> None:
        """Resources without type field raise InvalidConfigurationError."""
        from infrafoundry.core.exceptions import InvalidConfigurationError

        resources = [{"name": "test"}]
        with pytest.raises(InvalidConfigurationError, match="missing 'type'"):
            self._parse(loader, resources)

    def test_items_without_name_are_skipped(self, loader: PackageLoader) -> None:
        """Items without a name field are silently skipped."""
        resources = [
            {"type": "vm"},  # no name
            {"type": "vm", "name": "valid"},
        ]
        result = self._parse(loader, resources)
        assert len(result) == 1
        assert result[0].name == "valid"

    def test_non_dict_items_are_skipped(self, loader: PackageLoader) -> None:
        """Non-dict items in the resources list are skipped."""
        resources = ["not-a-dict", {"type": "vm", "name": "valid"}]  # type: ignore[list-item]
        result = self._parse(loader, resources)
        assert len(result) == 1


class TestParseResourcesFromData:
    """Tests for _parse_resources_from_data covering both formats."""

    def test_resource_centric_format(self, loader: PackageLoader) -> None:
        """Data with 'resources' key uses resource-centric parsing."""
        data = {
            "resources": [
                {
                    "provider": "proxmox",
                    "type": "storage",
                    "name": "infra",
                    "config": {"backend": "nfs"},
                }
            ]
        }
        result = loader._parse_resources_from_data(data, "resources.yaml", "proxmox")
        assert len(result) == 1
        assert result[0].config["name"] == "infra"

    def test_provider_centric_format(self, loader: PackageLoader) -> None:
        """Data with type-named key uses provider-centric parsing."""
        data = {
            "vm": [
                {"name": "test-vm", "cores": 4},
            ]
        }
        result = loader._parse_resources_from_data(data, "vm.yaml", "proxmox")
        assert len(result) == 1
        assert result[0].type == "vm"
        assert result[0].config["name"] == "test-vm"

    def test_empty_data_returns_empty(self, loader: PackageLoader) -> None:
        """Empty data returns empty list."""
        result = loader._parse_resources_from_data({}, "vm.yaml", "proxmox")
        assert result == []


def _create_package(
    tmp_path: Path,
    manifest_data: dict[str, Any],
    resource_data: dict[str, Any] | None = None,
    secrets_data: dict[str, Any] | None = None,
) -> Path:
    """Helper to create a package directory with manifest, resource, and optional secrets.

    Args:
        tmp_path: Temporary directory root (used as base_dir/env/provider/).
        manifest_data: Data for infrafoundry.yml.
        resource_data: Data for the resource file (vm.yaml by default).
        secrets_data: If provided, written to secrets.yaml.

    Returns:
        Path to the package directory.
    """
    env_dir = tmp_path / "test-env"
    provider_dir = env_dir / "proxmox"
    package_dir = provider_dir / manifest_data.get("name", "test-pkg")
    package_dir.mkdir(parents=True, exist_ok=True)

    # Write manifest
    manifest_path = package_dir / "infrafoundry.yml"
    manifest_path.write_text(yaml.dump(manifest_data))

    # Write resource file
    if resource_data is not None:
        for res_file in manifest_data.get("resources", []):
            (package_dir / res_file).write_text(yaml.dump(resource_data))

    # Write secrets file
    if secrets_data is not None:
        secrets_path = package_dir / "secrets.yaml"
        secrets_path.write_text(yaml.dump(secrets_data))

    return package_dir


class TestPackageSecrets:
    """Tests for per-package secrets.yaml loading and merging."""

    def test_secrets_merged_into_manifest_variables(self, tmp_path: Path) -> None:
        """Secret variables from secrets.yaml are merged into manifest variables."""
        manifest = {
            "name": "test-pkg",
            "variables": {"public_var": "public-value", "db_host": "localhost"},
            "resources": ["vm.yaml"],
        }
        resource = {"vm": [{"name": "test-vm", "host": "{{ db_host }}"}]}
        secrets = {"variables": {"db_password": "secret123"}}

        package_dir = _create_package(tmp_path, manifest, resource, secrets)
        loader = PackageLoader(tmp_path)

        resources, _, _pkg_vars = loader.load_package(package_dir, "proxmox", "test-env")

        assert len(resources) == 1
        # The secret variable was available during rendering (no UndefinedError)

    def test_secrets_override_manifest_variables(self, tmp_path: Path) -> None:
        """Secret variables override same-named variables from infrafoundry.yml."""
        manifest = {
            "name": "test-pkg",
            "variables": {"password": "plaintext-default", "host": "localhost"},
            "resources": ["vm.yaml"],
        }
        resource = {"vm": [{"name": "test-vm", "pass": "{{ password }}"}]}
        secrets = {"variables": {"password": "encrypted-secret"}}

        package_dir = _create_package(tmp_path, manifest, resource, secrets)
        loader = PackageLoader(tmp_path)

        resources, _, _pkg_vars = loader.load_package(package_dir, "proxmox", "test-env")

        assert len(resources) == 1
        assert resources[0].config["pass"] == "encrypted-secret"

    def test_package_without_secrets_works_unchanged(self, tmp_path: Path) -> None:
        """Package without secrets.yaml loads normally with no errors."""
        manifest = {
            "name": "test-pkg",
            "variables": {"host": "localhost"},
            "resources": ["vm.yaml"],
        }
        resource = {"vm": [{"name": "test-vm", "host": "{{ host }}"}]}

        package_dir = _create_package(tmp_path, manifest, resource, secrets_data=None)
        loader = PackageLoader(tmp_path)

        resources, _, _pkg_vars = loader.load_package(package_dir, "proxmox", "test-env")

        assert len(resources) == 1
        assert resources[0].config["host"] == "localhost"

    def test_empty_secrets_yaml_does_not_break(self, tmp_path: Path) -> None:
        """Empty secrets.yaml (no variables key) doesn't cause errors."""
        manifest = {
            "name": "test-pkg",
            "variables": {"host": "localhost"},
            "resources": ["vm.yaml"],
        }
        resource = {"vm": [{"name": "test-vm", "host": "{{ host }}"}]}
        secrets: dict[str, Any] = {}

        package_dir = _create_package(tmp_path, manifest, resource, secrets)
        # Write truly empty file (yaml.dump({}) writes "{}\n", safe_load returns {})
        (package_dir / "secrets.yaml").write_text("")
        loader = PackageLoader(tmp_path)

        resources, _, _pkg_vars = loader.load_package(package_dir, "proxmox", "test-env")

        assert len(resources) == 1
        assert resources[0].config["host"] == "localhost"

    def test_secrets_missing_variables_key_does_not_break(self, tmp_path: Path) -> None:
        """secrets.yaml without a 'variables' key doesn't cause errors."""
        manifest = {
            "name": "test-pkg",
            "variables": {"host": "localhost"},
            "resources": ["vm.yaml"],
        }
        resource = {"vm": [{"name": "test-vm", "host": "{{ host }}"}]}
        secrets = {"description": "no variables here"}

        package_dir = _create_package(tmp_path, manifest, resource, secrets)
        loader = PackageLoader(tmp_path)

        resources, _, _pkg_vars = loader.load_package(package_dir, "proxmox", "test-env")

        assert len(resources) == 1
        assert resources[0].config["host"] == "localhost"

    def test_sops_encrypted_secrets_are_decrypted(self, tmp_path: Path) -> None:
        """SOPS-encrypted secrets.yaml triggers sops --decrypt subprocess."""
        manifest = {
            "name": "test-pkg",
            "variables": {"host": "localhost"},
            "resources": ["vm.yaml"],
        }
        resource = {"vm": [{"name": "test-vm", "host": "{{ host }}"}]}

        package_dir = _create_package(tmp_path, manifest, resource, secrets_data=None)

        # Write a fake SOPS-encrypted file
        sops_content = (
            "variables:\n    password: ENC[AES256_GCM,data:abc123]\nsops:\n    version: 3.7.3\n"
        )
        (package_dir / "secrets.yaml").write_text(sops_content)

        # Mock subprocess.run to simulate sops --decrypt
        decrypted_yaml = "variables:\n  password: decrypted-secret\n"
        mock_result = type("Result", (), {"stdout": decrypted_yaml, "returncode": 0})()

        with patch(
            "infrafoundry.core.config.sops.subprocess.run", return_value=mock_result
        ) as mock_run:
            loader = PackageLoader(tmp_path)
            _resources, _, _pkg_vars = loader.load_package(package_dir, "proxmox", "test-env")

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["sops", "--decrypt", str(package_dir / "secrets.yaml")]

    def test_secret_variables_available_in_rendered_templates(self, tmp_path: Path) -> None:
        """Variables from secrets are used when rendering resource templates."""
        manifest = {
            "name": "test-pkg",
            "variables": {"host": "db.local", "port": "5432"},
            "resources": ["vm.yaml"],
        }
        # Template uses a variable only defined in secrets
        resource_content = (
            "vm:\n  - name: test-vm\n    host: {{ host }}\n    password: {{ db_password }}\n"
        )
        secrets = {"variables": {"db_password": "super-secret"}}

        package_dir = _create_package(tmp_path, manifest, secrets_data=secrets, resource_data=None)
        # Write raw template (not via yaml.dump, to preserve Jinja2 syntax)
        (package_dir / "vm.yaml").write_text(resource_content)

        loader = PackageLoader(tmp_path)
        resources, _, _pkg_vars = loader.load_package(package_dir, "proxmox", "test-env")

        assert len(resources) == 1
        assert resources[0].config["password"] == "super-secret"
        assert resources[0].config["host"] == "db.local"
