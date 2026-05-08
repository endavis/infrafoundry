"""Unit tests for PackageLoader."""

from pathlib import Path

import pytest
import yaml

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.inventory_generator import GENERATED_INVENTORY_FILENAME
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import InvalidConfigurationError


def _create_package(base_dir, env_name, provider, package_name, manifest, resource_files=None):
    """Helper to create a package directory structure.

    Args:
        base_dir: Base envs directory
        env_name: Environment name
        provider: Provider name
        package_name: Package subdirectory name
        manifest: Dict for infrafoundry.yml content
        resource_files: Optional dict of filename -> content
    """
    package_dir = base_dir / env_name / provider / package_name
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


@pytest.mark.unit
class TestDiscoverPackages:
    """Tests for PackageLoader.discover_packages."""

    def test_discover_packages_finds_manifest(self, temp_dir):
        """Subdirectory with infrafoundry.yml is discovered."""
        loader = PackageLoader(temp_dir)
        _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "my-pkg",
            {"name": "my-pkg"},
        )

        packages = loader.discover_packages("dev", "proxmox")
        assert len(packages) == 1
        assert packages[0].name == "my-pkg"

    def test_discover_packages_sorted_order(self, temp_dir):
        """Multiple packages are returned sorted by name."""
        loader = PackageLoader(temp_dir)
        _create_package(temp_dir, "dev", "proxmox", "zeta-pkg", {"name": "zeta"})
        _create_package(temp_dir, "dev", "proxmox", "alpha-pkg", {"name": "alpha"})
        _create_package(temp_dir, "dev", "proxmox", "mid-pkg", {"name": "mid"})

        packages = loader.discover_packages("dev", "proxmox")
        names = [p.name for p in packages]
        assert names == ["alpha-pkg", "mid-pkg", "zeta-pkg"]

    def test_discover_packages_skips_excluded_dirs(self, temp_dir):
        """Directories in EXCLUDED_DIRS are skipped even with manifest."""
        loader = PackageLoader(temp_dir)
        # Create excluded dir with manifest
        excluded_dir = temp_dir / "dev" / "proxmox" / "roles"
        excluded_dir.mkdir(parents=True)
        (excluded_dir / "infrafoundry.yml").write_text("name: roles-pkg\n")

        # Create valid package
        _create_package(temp_dir, "dev", "proxmox", "valid-pkg", {"name": "valid"})

        packages = loader.discover_packages("dev", "proxmox")
        assert len(packages) == 1
        assert packages[0].name == "valid-pkg"

    def test_discover_packages_no_manifest(self, temp_dir):
        """Subdirectory without manifest is ignored."""
        loader = PackageLoader(temp_dir)
        no_manifest_dir = temp_dir / "dev" / "proxmox" / "no-manifest"
        no_manifest_dir.mkdir(parents=True)
        (no_manifest_dir / "some-file.yaml").write_text("key: value\n")

        packages = loader.discover_packages("dev", "proxmox")
        assert packages == []

    def test_discover_packages_empty_provider(self, temp_dir):
        """No subdirs returns empty list."""
        loader = PackageLoader(temp_dir)
        provider_dir = temp_dir / "dev" / "proxmox"
        provider_dir.mkdir(parents=True)

        packages = loader.discover_packages("dev", "proxmox")
        assert packages == []

    def test_discover_packages_nonexistent_provider(self, temp_dir):
        """Non-existent provider dir returns empty list."""
        loader = PackageLoader(temp_dir)
        packages = loader.discover_packages("dev", "nonexistent")
        assert packages == []

    def test_discover_packages_skips_files(self, temp_dir):
        """Files in provider dir are not treated as packages."""
        loader = PackageLoader(temp_dir)
        provider_dir = temp_dir / "dev" / "proxmox"
        provider_dir.mkdir(parents=True)
        (provider_dir / "vm.yaml").write_text("vm: []\n")

        packages = loader.discover_packages("dev", "proxmox")
        assert packages == []


@pytest.mark.unit
class TestParseManifest:
    """Tests for PackageLoader._parse_manifest."""

    def test_parse_manifest_full(self, temp_dir):
        """All fields parse correctly."""
        loader = PackageLoader(temp_dir)
        manifest_data = {
            "name": "ontap-cluster",
            "description": "ONTAP cluster setup",
            "variables": {"cluster_name": "lab-cluster", "node_count": 2},
            "resources": ["vm.yaml", "network.yaml"],
            "events": {"AFTER_APPLY": [{"type": "script", "script": "scripts/setup.sh"}]},
        }
        pkg_dir = temp_dir / "pkg"
        pkg_dir.mkdir()
        manifest_path = pkg_dir / "infrafoundry.yml"
        with open(manifest_path, "w") as f:
            yaml.dump(manifest_data, f)

        manifest = loader._parse_manifest(manifest_path)
        assert manifest.name == "ontap-cluster"
        assert manifest.description == "ONTAP cluster setup"
        assert manifest.variables["cluster_name"] == "lab-cluster"
        assert manifest.resources == ["vm.yaml", "network.yaml"]
        assert len(manifest.events["AFTER_APPLY"]) == 1

    def test_parse_manifest_minimal(self, temp_dir):
        """Name-only manifest works."""
        loader = PackageLoader(temp_dir)
        pkg_dir = temp_dir / "pkg"
        pkg_dir.mkdir()
        manifest_path = pkg_dir / "infrafoundry.yml"
        manifest_path.write_text("name: minimal\n")

        manifest = loader._parse_manifest(manifest_path)
        assert manifest.name == "minimal"
        assert manifest.description is None
        assert manifest.variables == {}
        assert manifest.resources == []
        assert manifest.events == {}

    def test_parse_manifest_invalid_yaml(self, temp_dir):
        """Invalid YAML raises InvalidConfigurationError."""
        loader = PackageLoader(temp_dir)
        pkg_dir = temp_dir / "pkg"
        pkg_dir.mkdir()
        manifest_path = pkg_dir / "infrafoundry.yml"
        manifest_path.write_text("invalid: yaml: content::\n")

        with pytest.raises(InvalidConfigurationError, match="Invalid YAML"):
            loader._parse_manifest(manifest_path)

    def test_parse_manifest_missing_name(self, temp_dir):
        """Missing required 'name' raises InvalidConfigurationError."""
        loader = PackageLoader(temp_dir)
        pkg_dir = temp_dir / "pkg"
        pkg_dir.mkdir()
        manifest_path = pkg_dir / "infrafoundry.yml"
        manifest_path.write_text("description: no name\n")

        with pytest.raises(InvalidConfigurationError, match="Invalid package manifest"):
            loader._parse_manifest(manifest_path)

    def test_parse_manifest_missing_file(self, temp_dir):
        """Missing manifest file raises InvalidConfigurationError."""
        loader = PackageLoader(temp_dir)
        manifest_path = temp_dir / "nonexistent" / "infrafoundry.yml"

        with pytest.raises(InvalidConfigurationError, match="not found"):
            loader._parse_manifest(manifest_path)

    def test_parse_manifest_empty_file(self, temp_dir):
        """Empty manifest file raises InvalidConfigurationError."""
        loader = PackageLoader(temp_dir)
        pkg_dir = temp_dir / "pkg"
        pkg_dir.mkdir()
        manifest_path = pkg_dir / "infrafoundry.yml"
        manifest_path.write_text("")

        with pytest.raises(InvalidConfigurationError, match="must be a YAML mapping"):
            loader._parse_manifest(manifest_path)


@pytest.mark.unit
class TestRenderResourceFile:
    """Tests for PackageLoader._render_resource_file."""

    def test_render_resource_variables(self, temp_dir):
        """Jinja2 variables are substituted correctly."""
        loader = PackageLoader(temp_dir)
        resource_path = temp_dir / "vm.yaml"
        resource_path.write_text(
            "vm:\n  - name: {{ cluster_name }}-node1\n    cores: {{ cores }}\n"
        )

        data = loader._render_resource_file(resource_path, {"cluster_name": "lab", "cores": 4})
        assert data["vm"][0]["name"] == "lab-node1"
        assert data["vm"][0]["cores"] == 4

    def test_render_resource_undefined_var(self, temp_dir):
        """StrictUndefined raises error for missing variables."""
        loader = PackageLoader(temp_dir)
        resource_path = temp_dir / "vm.yaml"
        resource_path.write_text("vm:\n  - name: {{ missing_var }}\n")

        with pytest.raises(InvalidConfigurationError, match="Undefined variable"):
            loader._render_resource_file(resource_path, {})

    def test_render_resource_missing_file(self, temp_dir):
        """Missing resource file raises InvalidConfigurationError."""
        loader = PackageLoader(temp_dir)
        resource_path = temp_dir / "nonexistent.yaml"

        with pytest.raises(InvalidConfigurationError, match="not found"):
            loader._render_resource_file(resource_path, {})

    def test_render_resource_template_syntax_error(self, temp_dir):
        """Template syntax error raises InvalidConfigurationError."""
        loader = PackageLoader(temp_dir)
        resource_path = temp_dir / "bad.yaml"
        resource_path.write_text("vm:\n  - name: {{ broken }\n")

        with pytest.raises(InvalidConfigurationError, match="Template syntax error"):
            loader._render_resource_file(resource_path, {})

    def test_render_resource_empty_result(self, temp_dir):
        """Empty YAML after rendering returns empty dict."""
        loader = PackageLoader(temp_dir)
        resource_path = temp_dir / "empty.yaml"
        resource_path.write_text("# just a comment\n")

        data = loader._render_resource_file(resource_path, {})
        assert data == {}

    def test_render_resource_provider_variable_available(self, temp_dir):
        """Provider kwarg is available as {{ provider }} in templates."""
        loader = PackageLoader(temp_dir)
        resource_path = temp_dir / "vm.yaml"
        resource_path.write_text("vm:\n  - name: node-{{ provider }}\n")

        data = loader._render_resource_file(resource_path, {}, provider="proxmox")
        assert data["vm"][0]["name"] == "node-proxmox"

    def test_render_resource_provider_not_injected_when_none(self, temp_dir):
        """Default provider=None does not inject a provider variable."""
        loader = PackageLoader(temp_dir)
        resource_path = temp_dir / "vm.yaml"
        resource_path.write_text("vm:\n  - name: simple-node\n")

        data = loader._render_resource_file(resource_path, {})
        assert data["vm"][0]["name"] == "simple-node"

    def test_render_resource_provider_does_not_clobber_user_variable(self, temp_dir):
        """User-defined 'provider' in variables takes precedence over injected value."""
        loader = PackageLoader(temp_dir)
        resource_path = temp_dir / "vm.yaml"
        resource_path.write_text("vm:\n  - name: node-{{ provider }}\n")

        data = loader._render_resource_file(
            resource_path, {"provider": "user-defined"}, provider="proxmox"
        )
        assert data["vm"][0]["name"] == "node-user-defined"


@pytest.mark.unit
class TestParseResourcesFromData:
    """Tests for PackageLoader._parse_resources_from_data."""

    def test_parse_resources_singular_key(self, temp_dir):
        """Singular key (vm) works."""
        loader = PackageLoader(temp_dir)
        data = {"vm": [{"name": "node1", "cores": 4}]}
        resources = loader._parse_resources_from_data(data, "vm.yaml", "proxmox")
        assert len(resources) == 1
        assert resources[0].name == "node1"
        assert resources[0].type == "vm"
        assert resources[0].provider == "proxmox"

    def test_parse_resources_plural_key(self, temp_dir):
        """Plural key (vms) works as fallback."""
        loader = PackageLoader(temp_dir)
        data = {"vms": [{"name": "node1"}, {"name": "node2"}]}
        resources = loader._parse_resources_from_data(data, "vm.yaml", "proxmox")
        assert len(resources) == 2

    def test_parse_resources_hyphenated_filename(self, temp_dir):
        """Hyphenated filename extracts type from first segment."""
        loader = PackageLoader(temp_dir)
        data = {"vm": [{"name": "web-01"}]}
        resources = loader._parse_resources_from_data(data, "vm-cluster.yaml", "proxmox")
        assert len(resources) == 1
        assert resources[0].type == "vm"

    def test_parse_resources_empty_data(self, temp_dir):
        """Empty data returns empty list."""
        loader = PackageLoader(temp_dir)
        resources = loader._parse_resources_from_data({}, "vm.yaml", "proxmox")
        assert resources == []

    def test_parse_resources_non_list_raises(self, temp_dir):
        """Non-list resource value raises InvalidConfigurationError."""
        loader = PackageLoader(temp_dir)
        data = {"vm": {"name": "node1"}}
        with pytest.raises(InvalidConfigurationError, match="Expected list"):
            loader._parse_resources_from_data(data, "vm.yaml", "proxmox")

    def test_parse_resources_skips_non_dict_items(self, temp_dir):
        """Non-dict items in resource list are skipped."""
        loader = PackageLoader(temp_dir)
        data = {"vm": ["not-a-dict", {"name": "valid-vm"}]}
        resources = loader._parse_resources_from_data(data, "vm.yaml", "proxmox")
        assert len(resources) == 1
        assert resources[0].name == "valid-vm"

    def test_parse_resources_skips_items_without_name(self, temp_dir):
        """Dict items without 'name' key are skipped."""
        loader = PackageLoader(temp_dir)
        data = {"vm": [{"cores": 4}, {"name": "valid-vm"}]}
        resources = loader._parse_resources_from_data(data, "vm.yaml", "proxmox")
        assert len(resources) == 1
        assert resources[0].name == "valid-vm"


@pytest.mark.unit
class TestRewriteEventScripts:
    """Tests for PackageLoader._rewrite_event_scripts."""

    def test_rewrite_event_scripts(self, temp_dir):
        """Script paths are rewritten relative to env dir."""
        loader = PackageLoader(temp_dir)
        events = {"AFTER_APPLY": [{"type": "script", "script": "scripts/setup.sh"}]}
        package_dir = temp_dir / "dev" / "proxmox" / "ontap-cluster"
        env_dir = temp_dir / "dev"

        rewritten = loader._rewrite_event_scripts(events, package_dir, env_dir)
        assert rewritten["AFTER_APPLY"][0]["script"] == "proxmox/ontap-cluster/scripts/setup.sh"

    def test_rewrite_event_scripts_non_script_handler(self, temp_dir):
        """Webhook and python handlers are unchanged."""
        loader = PackageLoader(temp_dir)
        events = {
            "AFTER_APPLY": [
                {"type": "webhook", "url": "https://example.com/hook"},
                {"type": "python", "module": "hooks.notify"},
            ]
        }
        package_dir = temp_dir / "dev" / "proxmox" / "pkg"
        env_dir = temp_dir / "dev"

        rewritten = loader._rewrite_event_scripts(events, package_dir, env_dir)
        assert rewritten["AFTER_APPLY"][0]["url"] == "https://example.com/hook"
        assert rewritten["AFTER_APPLY"][1]["module"] == "hooks.notify"

    def test_rewrite_event_scripts_empty(self, temp_dir):
        """Empty events returns empty dict."""
        loader = PackageLoader(temp_dir)
        package_dir = temp_dir / "dev" / "proxmox" / "pkg"
        env_dir = temp_dir / "dev"

        rewritten = loader._rewrite_event_scripts({}, package_dir, env_dir)
        assert rewritten == {}

    def test_rewrite_event_scripts_does_not_mutate_original(self, temp_dir):
        """Original events dict is not mutated."""
        loader = PackageLoader(temp_dir)
        events = {"AFTER_APPLY": [{"type": "script", "script": "scripts/setup.sh"}]}
        package_dir = temp_dir / "dev" / "proxmox" / "pkg"
        env_dir = temp_dir / "dev"

        loader._rewrite_event_scripts(events, package_dir, env_dir)
        # Original should be unchanged
        assert events["AFTER_APPLY"][0]["script"] == "scripts/setup.sh"

    def test_rewrite_event_scripts_multiple_events(self, temp_dir):
        """Multiple event types are all rewritten."""
        loader = PackageLoader(temp_dir)
        events = {
            "AFTER_APPLY": [{"type": "script", "script": "scripts/apply.sh"}],
            "BEFORE_PLAN": [{"type": "script", "script": "scripts/plan.sh"}],
        }
        package_dir = temp_dir / "dev" / "proxmox" / "pkg"
        env_dir = temp_dir / "dev"

        rewritten = loader._rewrite_event_scripts(events, package_dir, env_dir)
        assert rewritten["AFTER_APPLY"][0]["script"] == "proxmox/pkg/scripts/apply.sh"
        assert rewritten["BEFORE_PLAN"][0]["script"] == "proxmox/pkg/scripts/plan.sh"


@pytest.mark.unit
class TestLoadPackage:
    """Tests for PackageLoader.load_package end-to-end."""

    def test_load_package_full(self, temp_dir):
        """End-to-end: manifest + templated resources + events."""
        loader = PackageLoader(temp_dir)
        manifest = {
            "name": "ontap-cluster",
            "description": "ONTAP cluster lab",
            "variables": {"cluster_name": "lab", "node_count": 2},
            "resources": ["vm.yaml"],
            "events": {"AFTER_APPLY": [{"type": "script", "script": "scripts/setup.sh"}]},
        }
        resource_content = (
            "vm:\n"
            "  - name: {{ cluster_name }}-node1\n"
            "    cores: 4\n"
            "  - name: {{ cluster_name }}-node2\n"
            "    cores: 4\n"
        )
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "ontap-cluster",
            manifest,
            {"vm.yaml": resource_content},
        )

        resources, events, _pkg_vars = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 2
        assert resources[0].name == "lab-node1"
        assert resources[1].name == "lab-node2"
        assert resources[0].provider == "proxmox"
        assert resources[0].type == "vm"

        assert "AFTER_APPLY" in events
        assert events["AFTER_APPLY"][0]["script"] == "proxmox/ontap-cluster/scripts/setup.sh"

    def test_load_package_resources_only(self, temp_dir):
        """Package with no events."""
        loader = PackageLoader(temp_dir)
        manifest = {
            "name": "simple-pkg",
            "variables": {"name_prefix": "web"},
            "resources": ["vm.yaml"],
        }
        resource_content = "vm:\n  - name: {{ name_prefix }}-01\n"
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "simple-pkg",
            manifest,
            {"vm.yaml": resource_content},
        )

        resources, events, _pkg_vars = loader.load_package(pkg_dir, "proxmox", "dev")
        assert len(resources) == 1
        assert resources[0].name == "web-01"
        assert events == {}

    def test_load_package_events_only(self, temp_dir):
        """Package with no resources."""
        loader = PackageLoader(temp_dir)
        manifest = {
            "name": "events-only",
            "events": {"BEFORE_PLAN": [{"type": "script", "script": "scripts/check.sh"}]},
        }
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "events-only",
            manifest,
        )

        resources, events, _pkg_vars = loader.load_package(pkg_dir, "proxmox", "dev")
        assert resources == []
        assert "BEFORE_PLAN" in events

    def test_load_package_missing_resource_file(self, temp_dir):
        """Package referencing non-existent resource file raises error."""
        loader = PackageLoader(temp_dir)
        manifest = {
            "name": "broken-pkg",
            "resources": ["nonexistent.yaml"],
        }
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "broken-pkg",
            manifest,
        )

        with pytest.raises(InvalidConfigurationError, match="not found"):
            loader.load_package(pkg_dir, "proxmox", "dev")


class TestMultiProviderResources:
    """Tests for multi-provider resource support in packages."""

    def test_resource_centric_format(self, temp_dir):
        """Resource-centric format with explicit provider and type per item."""
        loader = PackageLoader(temp_dir)
        manifest = {
            "name": "multi-provider",
            "resources": ["resources.yaml"],
        }
        resource_content = """
resources:
  - provider: proxmox
    type: ova_vm
    name: ontap-node-01
    config:
      vmid: 220
      target_node: pve1
  - provider: opnsense
    type: kea_reservation
    name: ontap-node-01
    config:
      subnet_ref: opt1-infrastructure
      ip_address: "192.168.10.201"
"""
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "multi-provider",
            manifest,
            {"resources.yaml": resource_content},
        )

        resources, _, _pkg_vars = loader.load_package(pkg_dir, "proxmox", "dev")
        assert len(resources) == 2
        assert resources[0].provider == "proxmox"
        assert resources[0].type == "ova_vm"
        assert resources[0].name == "ontap-node-01"
        assert resources[1].provider == "opnsense"
        assert resources[1].type == "kea.dhcp4.reservations"

    def test_resource_centric_default_provider(self, temp_dir):
        """Resource-centric items without provider use parent provider."""
        loader = PackageLoader(temp_dir)
        manifest = {
            "name": "default-provider",
            "resources": ["resources.yaml"],
        }
        resource_content = """
resources:
  - type: vm
    name: web-01
    config:
      vmid: 100
"""
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "default-provider",
            manifest,
            {"resources.yaml": resource_content},
        )

        resources, _, _pkg_vars = loader.load_package(pkg_dir, "proxmox", "dev")
        assert len(resources) == 1
        assert resources[0].provider == "proxmox"
        assert resources[0].type == "vm"

    def test_resource_centric_missing_type(self, temp_dir):
        """Resource-centric item without type raises error."""
        loader = PackageLoader(temp_dir)
        manifest = {
            "name": "no-type",
            "resources": ["resources.yaml"],
        }
        resource_content = """
resources:
  - provider: proxmox
    name: bad-resource
    config:
      vmid: 100
"""
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "no-type",
            manifest,
            {"resources.yaml": resource_content},
        )

        with pytest.raises(InvalidConfigurationError, match="missing 'type'"):
            loader.load_package(pkg_dir, "proxmox", "dev")

    def test_provider_centric_with_provider_override(self, temp_dir):
        """Provider-centric format items can override provider."""
        loader = PackageLoader(temp_dir)
        manifest = {
            "name": "override",
            "resources": ["vms.yaml"],
        }
        resource_content = """
vms:
  - name: vm-01
    vmid: 100
  - name: vm-02
    vmid: 101
    provider: esxi
"""
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "override",
            manifest,
            {"vms.yaml": resource_content},
        )

        resources, _, _pkg_vars = loader.load_package(pkg_dir, "proxmox", "dev")
        assert len(resources) == 2
        assert resources[0].provider == "proxmox"
        assert resources[1].provider == "esxi"

    def test_resource_centric_with_variables(self, temp_dir):
        """Resource-centric format works with Jinja2 variable rendering."""
        loader = PackageLoader(temp_dir)
        manifest = {
            "name": "templated",
            "variables": {"node_name": "ontap-01", "vmid": 220},
            "resources": ["resources.yaml"],
        }
        resource_content = """
resources:
  - provider: proxmox
    type: ova_vm
    name: "{{ node_name }}"
    config:
      vmid: {{ vmid }}
"""
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "templated",
            manifest,
            {"resources.yaml": resource_content},
        )

        resources, _, _pkg_vars = loader.load_package(pkg_dir, "proxmox", "dev")
        assert len(resources) == 1
        assert resources[0].name == "ontap-01"
        assert resources[0].config["vmid"] == 220


def _create_blueprint(base_dir, name, manifest_data, extra_files=None):
    """Helper to create a blueprint directory under config_repo/blueprints/.

    Args:
        base_dir: The envs/ directory (base_dir.parent / "blueprints" is used)
        name: Blueprint name
        manifest_data: Dict for blueprint.yaml
        extra_files: Optional dict of relative_path -> content
    """
    blueprint_dir = base_dir.parent / "blueprints" / name
    blueprint_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = blueprint_dir / "blueprint.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest_data, f)

    if extra_files:
        for rel_path, content in extra_files.items():
            file_path = blueprint_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                file_path.write_text(content)
            else:
                with open(file_path, "w") as f:
                    yaml.dump(content, f)

    return blueprint_dir


@pytest.mark.unit
class TestBlueprintIntegration:
    """Tests for blueprint resolution in PackageLoader."""

    def test_blueprint_defaults_merged(self, temp_dir):
        """Blueprint defaults are merged under package variables."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "test-bp",
            {
                "name": "test-bp",
                "defaults": {"cluster_name": "default-cluster", "node_count": 2},
                "resources": ["vm.yaml"],
            },
            {"vm.yaml": "vm:\n  - name: {{ cluster_name }}-node\n    count: {{ node_count }}\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        # Package overrides cluster_name but inherits node_count
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "my-cluster",
            {
                "name": "my-cluster",
                "blueprint": "test-bp",
                "variables": {"cluster_name": "prod-cluster"},
            },
        )

        resources, _, variables = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert resources[0].name == "prod-cluster-node"
        assert variables["cluster_name"] == "prod-cluster"
        assert variables["node_count"] == 2

    def test_blueprint_resources_inherited(self, temp_dir):
        """Package without resources inherits from blueprint."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "infra-bp",
            {
                "name": "infra-bp",
                "defaults": {"vm_name": "web"},
                "resources": ["vm.yaml"],
            },
            {"vm.yaml": "vm:\n  - name: {{ vm_name }}-01\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "web-pkg",
            {
                "name": "web-pkg",
                "blueprint": "infra-bp",
            },
        )

        resources, _, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert resources[0].name == "web-01"

    def test_blueprint_events_inherited(self, temp_dir):
        """Package without events inherits from blueprint."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        bp_dir = _create_blueprint(
            temp_dir,
            "event-bp",
            {
                "name": "event-bp",
                "events": {"AFTER_APPLY": [{"type": "script", "script": "scripts/setup.sh"}]},
            },
            {"scripts/setup.sh": "#!/bin/bash\necho setup\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "event-pkg",
            {
                "name": "event-pkg",
                "blueprint": "event-bp",
            },
        )

        _, events, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert "AFTER_APPLY" in events
        # Script resolves to blueprint (absolute path) since not in package
        assert str(bp_dir) in events["AFTER_APPLY"][0]["script"]

    def test_package_overrides_blueprint_resources(self, temp_dir):
        """Package's own resources take priority over blueprint."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "override-bp",
            {
                "name": "override-bp",
                "defaults": {"name_prefix": "bp"},
                "resources": ["vm.yaml"],
            },
            {"vm.yaml": "vm:\n  - name: {{ name_prefix }}-node\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "custom-pkg",
            {
                "name": "custom-pkg",
                "blueprint": "override-bp",
                "variables": {"name_prefix": "custom"},
                "resources": ["vm.yaml"],
            },
            {"vm.yaml": "vm:\n  - name: {{ name_prefix }}-custom\n"},
        )

        resources, _, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert resources[0].name == "custom-custom"

    def test_blueprint_file_fallback(self, temp_dir):
        """Resource files fall back to blueprint dir when not in package."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "fallback-bp",
            {
                "name": "fallback-bp",
                "defaults": {"host": "web"},
                "resources": ["vm.yaml"],
            },
            {"vm.yaml": "vm:\n  - name: {{ host }}-server\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        # Package references vm.yaml from blueprint resources,
        # but does NOT have vm.yaml locally
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "fallback-pkg",
            {
                "name": "fallback-pkg",
                "blueprint": "fallback-bp",
            },
        )

        resources, _, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert resources[0].name == "web-server"

    def test_package_file_preferred_over_blueprint(self, temp_dir):
        """Package's own resource file is used even if blueprint has same name."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "prefer-bp",
            {
                "name": "prefer-bp",
                "defaults": {"x": "bp-value"},
                "resources": ["vm.yaml"],
            },
            {"vm.yaml": "vm:\n  - name: blueprint-vm\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "prefer-pkg",
            {
                "name": "prefer-pkg",
                "blueprint": "prefer-bp",
            },
            {"vm.yaml": "vm:\n  - name: package-vm\n"},
        )

        resources, _, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert resources[0].name == "package-vm"

    def test_no_blueprint_works_unchanged(self, temp_dir):
        """Packages without blueprint: key work exactly as before."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)

        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "normal-pkg",
            {
                "name": "normal-pkg",
                "variables": {"prefix": "app"},
                "resources": ["vm.yaml"],
            },
            {"vm.yaml": "vm:\n  - name: {{ prefix }}-01\n"},
        )

        resources, _, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert resources[0].name == "app-01"

    def test_blueprint_without_resolver_raises(self, temp_dir):
        """Package referencing blueprint without resolver raises error."""
        loader = PackageLoader(temp_dir)  # No resolver

        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "bad-pkg",
            {
                "name": "bad-pkg",
                "blueprint": "nonexistent",
            },
        )

        with pytest.raises(InvalidConfigurationError, match="no blueprint resolver"):
            loader.load_package(pkg_dir, "proxmox", "dev")

    def test_blueprint_inventory_inherited(self, temp_dir):
        """Inventory from blueprint is inherited and generated."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "inv-bp",
            {
                "name": "inv-bp",
                "defaults": {"host_ip": "10.0.0.1"},
                "inventory": {
                    "groups": {
                        "servers": {
                            "hosts": {
                                "server-01": {
                                    "ansible_host": "{{ host_ip }}",
                                }
                            }
                        }
                    }
                },
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "inv-pkg",
            {
                "name": "inv-pkg",
                "blueprint": "inv-bp",
            },
        )

        loader.load_package(pkg_dir, "proxmox", "dev")

        inventory_path = pkg_dir / GENERATED_INVENTORY_FILENAME
        assert inventory_path.exists()

        with open(inventory_path) as f:
            data = yaml.safe_load(f)

        assert data["groups"]["servers"]["hosts"]["server-01"]["ansible_host"] == "10.0.0.1"

    def test_package_inventory_overrides_blueprint(self, temp_dir):
        """Package's own inventory overrides blueprint inventory."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "inv-override-bp",
            {
                "name": "inv-override-bp",
                "defaults": {"host_ip": "10.0.0.1"},
                "inventory": {"groups": {"blueprint_group": {"hosts": {"bp-host": {}}}}},
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "inv-override-pkg",
            {
                "name": "inv-override-pkg",
                "blueprint": "inv-override-bp",
                "inventory": {"groups": {"package_group": {"hosts": {"pkg-host": {}}}}},
            },
        )

        loader.load_package(pkg_dir, "proxmox", "dev")

        inventory_path = pkg_dir / GENERATED_INVENTORY_FILENAME
        assert inventory_path.exists()

        with open(inventory_path) as f:
            data = yaml.safe_load(f)

        assert "package_group" in data["groups"]
        assert "blueprint_group" not in data["groups"]

    def test_blueprint_handler_tagged_with_blueprint_dir(self, temp_dir):
        """Event handlers from blueprint packages have _blueprint_dir tag."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        bp_dir = _create_blueprint(
            temp_dir,
            "tagged-bp",
            {
                "name": "tagged-bp",
                "events": {"AFTER_APPLY": [{"type": "script", "script": "scripts/run.sh"}]},
            },
            {"scripts/run.sh": "#!/bin/bash\necho run\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "tagged-pkg",
            {
                "name": "tagged-pkg",
                "blueprint": "tagged-bp",
            },
        )

        _, events, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        handler = events["AFTER_APPLY"][0]
        assert handler["_blueprint_dir"] == str(bp_dir)
        assert handler["_package"] == "tagged-pkg"

    def test_blueprint_inventory_with_loop_renders_via_consumer_variables(self, temp_dir):
        """Blueprint inventory `{% for %}` expands using consumer-supplied workers."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"

        blueprint_dir = temp_dir.parent / "blueprints" / "loop-bp"
        blueprint_dir.mkdir(parents=True, exist_ok=True)
        (blueprint_dir / "blueprint.yaml").write_text(
            "name: loop-bp\n"
            "inventory:\n"
            "  groups:\n"
            "    k3s_workers:\n"
            "      hosts:\n"
            "        {% for w in workers %}\n"
            "        {{ w.name }}:\n"
            '          ansible_host: "{{ w.ip }}"\n'
            "        {% endfor %}\n"
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = temp_dir / "dev" / "proxmox" / "loop-pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "infrafoundry.yml").write_text(
            "name: loop-pkg\n"
            "blueprint: loop-bp\n"
            "variables:\n"
            "  workers:\n"
            "    - name: worker-01\n"
            "      ip: 10.0.0.11\n"
            "    - name: worker-02\n"
            "      ip: 10.0.0.12\n"
        )

        loader.load_package(pkg_dir, "proxmox", "dev")

        inventory_path = pkg_dir / GENERATED_INVENTORY_FILENAME
        assert inventory_path.exists()
        with open(inventory_path) as f:
            data = yaml.safe_load(f)
        hosts = data["groups"]["k3s_workers"]["hosts"]
        assert set(hosts.keys()) == {"worker-01", "worker-02"}
        assert hosts["worker-01"]["ansible_host"] == "10.0.0.11"
        assert hosts["worker-02"]["ansible_host"] == "10.0.0.12"

    def test_package_inventory_with_loop(self, temp_dir):
        """Package-level inventory with `{% for %}` expands using package variables."""
        loader = PackageLoader(temp_dir)
        pkg_dir = temp_dir / "dev" / "proxmox" / "pkg-loop"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "infrafoundry.yml").write_text(
            "name: pkg-loop\n"
            "variables:\n"
            "  nodes:\n"
            "    - name: n1\n"
            "      addr: 1.1.1.1\n"
            "    - name: n2\n"
            "      addr: 2.2.2.2\n"
            "inventory:\n"
            "  groups:\n"
            "    cluster:\n"
            "      hosts:\n"
            "        {% for n in nodes %}\n"
            "        {{ n.name }}:\n"
            '          ansible_host: "{{ n.addr }}"\n'
            "        {% endfor %}\n"
        )

        loader.load_package(pkg_dir, "proxmox", "dev")

        inventory_path = pkg_dir / GENERATED_INVENTORY_FILENAME
        assert inventory_path.exists()
        with open(inventory_path) as f:
            data = yaml.safe_load(f)
        hosts = data["groups"]["cluster"]["hosts"]
        assert set(hosts.keys()) == {"n1", "n2"}
        assert hosts["n1"]["ansible_host"] == "1.1.1.1"
        assert hosts["n2"]["ansible_host"] == "2.2.2.2"

    def test_blueprint_inventory_raw_inheritance(self, temp_dir):
        """Blueprint `inventory_raw` is inherited onto a consumer with no inventory."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"

        blueprint_dir = temp_dir.parent / "blueprints" / "raw-inherit-bp"
        blueprint_dir.mkdir(parents=True, exist_ok=True)
        (blueprint_dir / "blueprint.yaml").write_text(
            "name: raw-inherit-bp\n"
            "defaults:\n"
            "  host_ip: 10.0.0.99\n"
            "inventory:\n"
            "  groups:\n"
            "    only:\n"
            "      hosts:\n"
            "        sole:\n"
            '          ansible_host: "{{ host_ip }}"\n'
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "raw-inherit-pkg",
            {
                "name": "raw-inherit-pkg",
                "blueprint": "raw-inherit-bp",
            },
        )

        loader.load_package(pkg_dir, "proxmox", "dev")

        inventory_path = pkg_dir / GENERATED_INVENTORY_FILENAME
        assert inventory_path.exists()
        with open(inventory_path) as f:
            data = yaml.safe_load(f)
        assert data["groups"]["only"]["hosts"]["sole"]["ansible_host"] == "10.0.0.99"

    def test_secrets_override_blueprint_defaults(self, temp_dir):
        """Secrets take priority over both blueprint defaults and package vars."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "secret-bp",
            {
                "name": "secret-bp",
                "defaults": {"password": "bp-default", "host": "bp-host"},
                "resources": ["vm.yaml"],
            },
            {"vm.yaml": "vm:\n  - name: {{ host }}\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "secret-pkg",
            {
                "name": "secret-pkg",
                "blueprint": "secret-bp",
                "variables": {"host": "pkg-host"},
            },
            # secrets.yaml with variable overrides
            {"secrets.yaml": "variables:\n  password: secret-password\n  host: secret-host\n"},
        )

        resources, _, variables = loader.load_package(pkg_dir, "proxmox", "dev")

        # Secrets override everything
        assert variables["password"] == "secret-password"
        assert variables["host"] == "secret-host"
        assert resources[0].name == "secret-host"


@pytest.mark.unit
class TestHandlerConfigTagging:
    """Tests for _package_dir/_package/_blueprint_dir injection on handler configs."""

    def test_load_package_tags_package_event_handlers_with_package_dir(self, temp_dir):
        """Package-level event handlers carry _package_dir pointing at the package."""
        loader = PackageLoader(temp_dir)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "tagged-pkg",
            {
                "name": "tagged-pkg",
                "events": {
                    "AFTER_APPLY": [{"type": "script", "script": "scripts/run.sh"}],
                },
            },
            {"scripts/run.sh": "#!/bin/bash\necho run\n"},
        )

        _, events, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        handler = events["AFTER_APPLY"][0]
        assert handler["_package"] == "tagged-pkg"
        assert handler["_package_dir"] == str(pkg_dir)
        assert "_blueprint_dir" not in handler

    def test_load_package_tags_resource_event_handlers_with_package_dir(self, temp_dir):
        """Resource-level event handlers carry _package and _package_dir tags."""
        loader = PackageLoader(temp_dir)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "res-evt-pkg",
            {
                "name": "res-evt-pkg",
                "resources": ["vm.yaml"],
            },
            {
                "vm.yaml": (
                    "vm:\n"
                    "  - name: my-vm\n"
                    "    events:\n"
                    "      AFTER_APPLY:\n"
                    "        - type: script\n"
                    "          script: scripts/post.sh\n"
                ),
                "scripts/post.sh": "#!/bin/bash\necho post\n",
            },
        )

        resources, _, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        resource = resources[0]
        assert resource.events is not None
        handler = resource.events["AFTER_APPLY"][0]
        assert handler["_package"] == "res-evt-pkg"
        assert handler["_package_dir"] == str(pkg_dir)
        assert "_blueprint_dir" not in handler

    def test_load_package_handler_package_dir_matches_inventory_output_dir(self, temp_dir):
        """_package_dir on handlers points at the dir where inventory was generated."""
        loader = PackageLoader(temp_dir)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "inv-tagged-pkg",
            {
                "name": "inv-tagged-pkg",
                "events": {
                    "AFTER_APPLY": [{"type": "script", "script": "scripts/run.sh"}],
                },
                "inventory": {
                    "groups": {
                        "all": {
                            "hosts": {
                                "host-01": {"ansible_host": "10.0.0.5"},
                            }
                        }
                    }
                },
            },
            {"scripts/run.sh": "#!/bin/bash\necho run\n"},
        )

        _, events, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        handler = events["AFTER_APPLY"][0]
        expected_inventory = Path(handler["_package_dir"]) / GENERATED_INVENTORY_FILENAME
        assert expected_inventory.exists()
        # And the dir the generator wrote to is exactly the package dir
        assert (pkg_dir / GENERATED_INVENTORY_FILENAME).exists()
        assert handler["_package_dir"] == str(pkg_dir)

    def test_blueprint_consumer_tags_resource_handlers_with_blueprint_dir(self, temp_dir):
        """When a package consumes a blueprint, resource-level handlers also get _blueprint_dir."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        bp_dir = _create_blueprint(
            temp_dir,
            "res-evt-bp",
            {
                "name": "res-evt-bp",
                "resources": ["vm.yaml"],
            },
            {
                "vm.yaml": (
                    "vm:\n"
                    "  - name: bp-vm\n"
                    "    events:\n"
                    "      AFTER_APPLY:\n"
                    "        - type: script\n"
                    "          script: scripts/bp-post.sh\n"
                ),
                "scripts/bp-post.sh": "#!/bin/bash\necho bp-post\n",
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "bp-consumer",
            {
                "name": "bp-consumer",
                "blueprint": "res-evt-bp",
            },
        )

        resources, _, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        resource = resources[0]
        assert resource.events is not None
        handler = resource.events["AFTER_APPLY"][0]
        assert handler["_package"] == "bp-consumer"
        assert handler["_package_dir"] == str(pkg_dir)
        assert handler["_blueprint_dir"] == str(bp_dir)
