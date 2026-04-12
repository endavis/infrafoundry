"""Unit tests for multi-provider blueprint support in PackageLoader."""

import pytest
import yaml

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
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
class TestMultiProviderBlueprint:
    """Tests for provider-conditional resource selection in blueprints."""

    def test_selects_correct_resources_for_provider(self, temp_dir):
        """Blueprint with providers section selects correct resource files."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "multi-bp",
            {
                "name": "multi-bp",
                "defaults": {"vm_name": "node"},
                "providers": {
                    "proxmox": {
                        "resources": ["providers/proxmox/vm.yaml"],
                    },
                    "oci": {
                        "resources": ["providers/oci/instance.yaml"],
                    },
                },
            },
            {
                "providers/proxmox/vm.yaml": "vm:\n  - name: {{ vm_name }}-proxmox\n",
                "providers/oci/instance.yaml": "instance:\n  - name: {{ vm_name }}-oci\n",
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "my-cluster",
            {
                "name": "my-cluster",
                "blueprint": "multi-bp",
            },
        )

        resources, _, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert resources[0].name == "node-proxmox"
        assert resources[0].provider == "proxmox"

    def test_selects_oci_provider_resources(self, temp_dir):
        """Blueprint with providers section selects OCI resources when provider is oci."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "multi-bp-oci",
            {
                "name": "multi-bp-oci",
                "defaults": {"vm_name": "node"},
                "providers": {
                    "proxmox": {
                        "resources": ["providers/proxmox/vm.yaml"],
                    },
                    "oci": {
                        "resources": ["providers/oci/instance.yaml"],
                    },
                },
            },
            {
                "providers/proxmox/vm.yaml": "vm:\n  - name: {{ vm_name }}-proxmox\n",
                "providers/oci/instance.yaml": "instance:\n  - name: {{ vm_name }}-oci\n",
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "oci",
            "my-cluster",
            {
                "name": "my-cluster",
                "blueprint": "multi-bp-oci",
            },
        )

        resources, _, _ = loader.load_package(pkg_dir, "oci", "dev")

        assert len(resources) == 1
        assert resources[0].name == "node-oci"
        assert resources[0].provider == "oci"

    def test_backward_compat_no_providers_section(self, temp_dir):
        """Blueprint without providers section works as before."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "classic-bp",
            {
                "name": "classic-bp",
                "defaults": {"vm_name": "legacy"},
                "resources": ["vm.yaml"],
            },
            {"vm.yaml": "vm:\n  - name: {{ vm_name }}-01\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "legacy-pkg",
            {
                "name": "legacy-pkg",
                "blueprint": "classic-bp",
            },
        )

        resources, _, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert resources[0].name == "legacy-01"

    def test_shared_defaults_merge_order(self, temp_dir):
        """Defaults merge: blueprint.defaults < providers[x].defaults < package.variables."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "merge-bp",
            {
                "name": "merge-bp",
                "defaults": {
                    "cores": 2,
                    "memory": 4096,
                    "disk": 50,
                },
                "providers": {
                    "proxmox": {
                        "resources": ["providers/proxmox/vm.yaml"],
                        "defaults": {
                            "memory": 8192,
                            "target_node": "pve1",
                        },
                    },
                },
            },
            {
                "providers/proxmox/vm.yaml": (
                    "vm:\n"
                    "  - name: node-01\n"
                    "    cores: {{ cores }}\n"
                    "    memory: {{ memory }}\n"
                    "    disk: {{ disk }}\n"
                    "    target_node: {{ target_node }}\n"
                ),
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "merge-pkg",
            {
                "name": "merge-pkg",
                "blueprint": "merge-bp",
                "variables": {"cores": 4},
            },
        )

        _, _, variables = loader.load_package(pkg_dir, "proxmox", "dev")

        # blueprint default: cores=2, overridden by package: cores=4
        assert variables["cores"] == 4
        # blueprint default: memory=4096, overridden by provider defaults: memory=8192
        assert variables["memory"] == 8192
        # blueprint default: disk=50, not overridden
        assert variables["disk"] == 50
        # provider default: target_node=pve1, not in blueprint defaults
        assert variables["target_node"] == "pve1"

    def test_package_variables_override_provider_defaults(self, temp_dir):
        """Package variables take priority over provider-specific defaults."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "override-bp",
            {
                "name": "override-bp",
                "defaults": {"cores": 2},
                "providers": {
                    "proxmox": {
                        "resources": ["providers/proxmox/vm.yaml"],
                        "defaults": {"target_node": "pve1"},
                    },
                },
            },
            {
                "providers/proxmox/vm.yaml": (
                    "vm:\n  - name: node-01\n    target_node: {{ target_node }}\n"
                ),
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "override-pkg",
            {
                "name": "override-pkg",
                "blueprint": "override-bp",
                "variables": {"target_node": "pve2"},
            },
        )

        _, _, variables = loader.load_package(pkg_dir, "proxmox", "dev")

        assert variables["target_node"] == "pve2"

    def test_missing_provider_in_providers_section_raises(self, temp_dir):
        """Blueprint with providers section but package's provider not listed raises error."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "limited-bp",
            {
                "name": "limited-bp",
                "defaults": {},
                "providers": {
                    "proxmox": {
                        "resources": ["vm.yaml"],
                    },
                },
            },
            {"vm.yaml": "vm:\n  - name: test\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "esxi",
            "my-pkg",
            {
                "name": "my-pkg",
                "blueprint": "limited-bp",
            },
        )

        with pytest.raises(InvalidConfigurationError, match="no resources for provider 'esxi'"):
            loader.load_package(pkg_dir, "esxi", "dev")

    def test_providers_section_but_no_provider_in_package_raises(self, temp_dir):
        """Blueprint with providers section but no provider for package raises error.

        This tests the edge case where both manifest.provider and the directory-
        inferred provider argument are empty.
        """
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "needs-provider-bp",
            {
                "name": "needs-provider-bp",
                "defaults": {},
                "providers": {
                    "proxmox": {
                        "resources": ["vm.yaml"],
                    },
                },
            },
            {"vm.yaml": "vm:\n  - name: test\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        # Create package under a provider dir but pass empty provider to load_package
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "misc",
            "no-provider-pkg",
            {
                "name": "no-provider-pkg",
                "blueprint": "needs-provider-bp",
            },
        )

        with pytest.raises(InvalidConfigurationError, match="has no provider"):
            loader.load_package(pkg_dir, "", "dev")

    def test_package_own_resources_override_provider_resources(self, temp_dir):
        """Package's own resources take priority even with providers section."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "override-res-bp",
            {
                "name": "override-res-bp",
                "defaults": {"vm_name": "node"},
                "providers": {
                    "proxmox": {
                        "resources": ["providers/proxmox/vm.yaml"],
                    },
                },
            },
            {
                "providers/proxmox/vm.yaml": "vm:\n  - name: {{ vm_name }}-bp\n",
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "custom-pkg",
            {
                "name": "custom-pkg",
                "blueprint": "override-res-bp",
                "resources": ["vm.yaml"],
            },
            {"vm.yaml": "vm:\n  - name: {{ vm_name }}-custom\n"},
        )

        resources, _, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert resources[0].name == "node-custom"

    def test_provider_from_manifest_field(self, temp_dir):
        """Provider from manifest's provider field is used for provider lookup."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "manifest-provider-bp",
            {
                "name": "manifest-provider-bp",
                "defaults": {"vm_name": "node"},
                "providers": {
                    "oci": {
                        "resources": ["providers/oci/instance.yaml"],
                    },
                },
            },
            {
                "providers/oci/instance.yaml": "instance:\n  - name: {{ vm_name }}-oci\n",
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        # Package is under 'proxmox' dir but declares provider: oci in manifest
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "cross-provider-pkg",
            {
                "name": "cross-provider-pkg",
                "blueprint": "manifest-provider-bp",
                "provider": "oci",
            },
        )

        resources, _, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert resources[0].name == "node-oci"
        assert resources[0].provider == "oci"

    def test_selects_provider_specific_events(self, temp_dir):
        """Blueprint with provider-specific events selects correct events for provider."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "events-bp",
            {
                "name": "events-bp",
                "defaults": {"vm_name": "node"},
                "providers": {
                    "proxmox": {
                        "resources": ["providers/proxmox/vm.yaml"],
                        "events": {
                            "on_create": [
                                {
                                    "type": "script",
                                    "name": "proxmox-setup",
                                    "script": "scripts/proxmox/setup.sh",
                                    "timeout": 300,
                                }
                            ],
                        },
                    },
                    "oci": {
                        "resources": ["providers/oci/instance.yaml"],
                        "events": {
                            "on_create": [
                                {
                                    "type": "script",
                                    "name": "oci-setup",
                                    "script": "scripts/oci/setup.sh",
                                    "timeout": 600,
                                }
                            ],
                            "before_destroy": [
                                {
                                    "type": "script",
                                    "name": "oci-cleanup",
                                    "script": "scripts/oci/cleanup.sh",
                                    "timeout": 60,
                                }
                            ],
                        },
                    },
                },
            },
            {
                "providers/proxmox/vm.yaml": "vm:\n  - name: {{ vm_name }}-proxmox\n",
                "providers/oci/instance.yaml": "instance:\n  - name: {{ vm_name }}-oci\n",
                "scripts/proxmox/setup.sh": "#!/bin/bash\necho proxmox\n",
                "scripts/oci/setup.sh": "#!/bin/bash\necho oci\n",
                "scripts/oci/cleanup.sh": "#!/bin/bash\necho cleanup\n",
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)

        # Proxmox package should get proxmox events
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "events-pkg-proxmox",
            {
                "name": "events-pkg-proxmox",
                "blueprint": "events-bp",
            },
        )
        _, events, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert "on_create" in events
        assert len(events["on_create"]) == 1
        assert events["on_create"][0]["name"] == "proxmox-setup"
        assert "before_destroy" not in events

    def test_selects_oci_provider_specific_events(self, temp_dir):
        """Blueprint with provider-specific events selects OCI events when provider is oci."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "events-bp-oci",
            {
                "name": "events-bp-oci",
                "defaults": {"vm_name": "node"},
                "providers": {
                    "proxmox": {
                        "resources": ["providers/proxmox/vm.yaml"],
                        "events": {
                            "on_create": [
                                {
                                    "type": "script",
                                    "name": "proxmox-setup",
                                    "script": "scripts/proxmox/setup.sh",
                                    "timeout": 300,
                                }
                            ],
                        },
                    },
                    "oci": {
                        "resources": ["providers/oci/instance.yaml"],
                        "events": {
                            "on_create": [
                                {
                                    "type": "script",
                                    "name": "oci-setup",
                                    "script": "scripts/oci/setup.sh",
                                    "timeout": 600,
                                }
                            ],
                            "before_destroy": [
                                {
                                    "type": "script",
                                    "name": "oci-cleanup",
                                    "script": "scripts/oci/cleanup.sh",
                                    "timeout": 60,
                                }
                            ],
                        },
                    },
                },
            },
            {
                "providers/proxmox/vm.yaml": "vm:\n  - name: {{ vm_name }}-proxmox\n",
                "providers/oci/instance.yaml": "instance:\n  - name: {{ vm_name }}-oci\n",
                "scripts/proxmox/setup.sh": "#!/bin/bash\necho proxmox\n",
                "scripts/oci/setup.sh": "#!/bin/bash\necho oci\n",
                "scripts/oci/cleanup.sh": "#!/bin/bash\necho cleanup\n",
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)

        # OCI package should get oci events (including before_destroy)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "oci",
            "events-pkg-oci",
            {
                "name": "events-pkg-oci",
                "blueprint": "events-bp-oci",
            },
        )
        _, events, _ = loader.load_package(pkg_dir, "oci", "dev")

        assert "on_create" in events
        assert len(events["on_create"]) == 1
        assert events["on_create"][0]["name"] == "oci-setup"
        assert "before_destroy" in events
        assert len(events["before_destroy"]) == 1
        assert events["before_destroy"][0]["name"] == "oci-cleanup"

    def test_package_events_override_provider_events(self, temp_dir):
        """Package's own events take priority over provider-specific events."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "events-override-bp",
            {
                "name": "events-override-bp",
                "defaults": {"vm_name": "node"},
                "providers": {
                    "proxmox": {
                        "resources": ["vm.yaml"],
                        "events": {
                            "on_create": [
                                {
                                    "type": "script",
                                    "name": "bp-setup",
                                    "script": "scripts/setup.sh",
                                    "timeout": 300,
                                }
                            ],
                        },
                    },
                },
            },
            {
                "vm.yaml": "vm:\n  - name: {{ vm_name }}-01\n",
                "scripts/setup.sh": "#!/bin/bash\necho blueprint\n",
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "events-override-pkg",
            {
                "name": "events-override-pkg",
                "blueprint": "events-override-bp",
                "events": {
                    "on_create": [
                        {
                            "type": "script",
                            "name": "pkg-setup",
                            "script": "scripts/my-setup.sh",
                            "timeout": 600,
                        }
                    ],
                },
            },
            {"scripts/my-setup.sh": "#!/bin/bash\necho package\n"},
        )

        _, events, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert "on_create" in events
        assert len(events["on_create"]) == 1
        assert events["on_create"][0]["name"] == "pkg-setup"

    def test_provider_events_not_inherited_when_no_providers_section(self, temp_dir):
        """Blueprint without providers section uses top-level events as before."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "classic-events-bp",
            {
                "name": "classic-events-bp",
                "defaults": {"vm_name": "node"},
                "resources": ["vm.yaml"],
                "events": {
                    "on_create": [
                        {
                            "type": "script",
                            "name": "classic-setup",
                            "script": "scripts/setup.sh",
                            "timeout": 300,
                        }
                    ],
                },
            },
            {
                "vm.yaml": "vm:\n  - name: {{ vm_name }}-01\n",
                "scripts/setup.sh": "#!/bin/bash\necho classic\n",
            },
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "classic-events-pkg",
            {
                "name": "classic-events-pkg",
                "blueprint": "classic-events-bp",
            },
        )

        _, events, _ = loader.load_package(pkg_dir, "proxmox", "dev")

        assert "on_create" in events
        assert len(events["on_create"]) == 1
        assert events["on_create"][0]["name"] == "classic-setup"

    def test_providers_without_defaults_key(self, temp_dir):
        """Provider block without defaults key works (no provider-specific defaults)."""
        resolver = BlueprintResolver(temp_dir)
        resolver.blueprints_dir = temp_dir.parent / "blueprints"
        _create_blueprint(
            temp_dir,
            "no-prov-defaults-bp",
            {
                "name": "no-prov-defaults-bp",
                "defaults": {"vm_name": "node"},
                "providers": {
                    "proxmox": {
                        "resources": ["vm.yaml"],
                    },
                },
            },
            {"vm.yaml": "vm:\n  - name: {{ vm_name }}-01\n"},
        )

        loader = PackageLoader(temp_dir, blueprint_resolver=resolver)
        pkg_dir = _create_package(
            temp_dir,
            "dev",
            "proxmox",
            "simple-pkg",
            {
                "name": "simple-pkg",
                "blueprint": "no-prov-defaults-bp",
            },
        )

        resources, _, variables = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert resources[0].name == "node-01"
        assert variables["vm_name"] == "node"
