"""Integration test for the service-vm blueprint.

Loads the example-config service-vm package via PackageLoader and asserts
that the merged configuration (blueprint defaults + package overrides)
produces the expected proxmox VM and opnsense DHCP resources, plus a
tmp_path-based check for the optional NFS storage path and a multi-instance
regression guard for issue #511.

The test depends only on files checked into this repository:
  - blueprints/service-vm/                          (the blueprint)
  - example-config/envs/dev/proxmox/service-vm/     (the example consumer)

It does NOT depend on the private endavis-infra/ config repo.
"""

import textwrap
from pathlib import Path

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.providers.proxmox import ProxmoxProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "dev" / "proxmox" / "service-vm"


@pytest.fixture
def loader() -> PackageLoader:
    """PackageLoader pointed at the real example-config envs/ directory."""
    resolver = BlueprintResolver(EXAMPLE_ENVS)
    return PackageLoader(EXAMPLE_ENVS, blueprint_resolver=resolver)


def test_service_vm_example_package_loads_blueprint(loader: PackageLoader) -> None:
    """The service-vm example package loads via the blueprint resolver and
    merges blueprint defaults with per-instance overrides."""
    _resources, _events, variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    # --- Per-instance overrides come from the package manifest ---
    assert variables["vm_name"] == "infra-web"
    assert variables["vmid"] == 210
    assert variables["target_node"] == "pve1"
    assert variables["mac_address"] == "BC:24:11:F8:F4:7D"
    assert variables["ip_address"] == "192.168.10.60"
    assert variables["dhcp_subnet"] == "opt1-infrastructure"
    assert variables["tags"] == ["infra", "web"]
    assert variables["dhcp_description"] == "Infrastructure web server (example)"

    # --- Blueprint defaults flow through unchanged ---
    assert variables["template_vmid"] == 900
    assert variables["template_node"] == "pve1"
    assert variables["cores"] == 2
    assert variables["memory"] == 2048
    assert variables["disk_storage"] == "local-lvm"
    assert variables["disk_size"] == 32
    assert variables["bridge"] == "vmbr0"
    assert variables["vlan_tag"] == 10
    assert variables["agent"] is True
    assert variables["onboot"] is True


def test_service_vm_renders_vm_and_dhcp_resources(loader: PackageLoader) -> None:
    """Default path (no NFS): exactly two resources are rendered — a proxmox
    VM and an opnsense kea_reservation, both named after vm_name."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    assert len(resources) == 2

    by_provider = {r.provider: r for r in resources}
    assert set(by_provider) == {"proxmox", "opnsense"}

    vm = by_provider["proxmox"]
    assert vm.type == "vm"
    assert vm.name == "infra-web"

    dhcp = by_provider["opnsense"]
    assert dhcp.type == "kea_reservation"
    assert dhcp.name == "infra-web"


def test_service_vm_vm_config_uses_merged_values(loader: PackageLoader) -> None:
    """Rendered VM config combines blueprint defaults with package overrides."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    vm = next(r for r in resources if r.provider == "proxmox" and r.type == "vm")
    config = vm.config

    # Per-instance overrides
    assert config["name"] == "infra-web"
    assert config["vmid"] == 210
    assert config["target_node"] == "pve1"

    # Blueprint defaults
    assert config["clone"] == {"vm_id": 900, "node_name": "pve1"}
    assert config["cores"] == 2
    assert config["memory"] == 2048
    assert config["disk"] == {"storage": "local-lvm", "size": 32}
    assert config["agent"] is True
    assert config["onboot"] is True

    # Network: single NIC with bridge + vlan tag + mac from per-instance values
    assert len(config["network"]) == 1
    assert config["network"][0]["bridge"] == "vmbr0"
    assert config["network"][0]["tag"] == 10
    assert config["network"][0]["macaddr"] == "BC:24:11:F8:F4:7D"

    # Cloud-init snippets from the package override, HOSTNAME from vm_name
    assert config["cloud_init_snippets"] == [
        "system/hostname",
        "users/ansible",
        "network/dhcp",
        "packages/qemu-agent",
    ]
    assert config["cloud_init_vars"]["HOSTNAME"] == "infra-web"

    # Tags from the package override
    assert config["tags"] == ["infra", "web"]


def test_service_vm_dhcp_config_uses_merged_values(loader: PackageLoader) -> None:
    """Rendered kea_reservation config uses per-instance values and lowercases
    the hw_address."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    dhcp = next(r for r in resources if r.provider == "opnsense" and r.type == "kea_reservation")
    config = dhcp.config

    assert config["subnet_ref"] == "opt1-infrastructure"
    # hw_address must be lowercased by the blueprint template
    assert config["hw_address"] == "bc:24:11:f8:f4:7d"
    assert config["ip_address"] == "192.168.10.60"
    assert config["hostname"] == "infra-web"
    assert config["description"] == "Infrastructure web server (example)"


def test_service_vm_does_not_emit_storage_resource(loader: PackageLoader) -> None:
    """The service-vm blueprint owns only VM + DHCP. Cluster-level storage
    pools belong in a dedicated storage package, not in per-VM blueprints,
    so the rendered resource set must never contain a ``proxmox.storage``
    entry regardless of package variables (regression guard for #622).
    """
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    types = {(r.provider, r.type) for r in resources}
    assert ("proxmox", "storage") not in types


def test_service_vm_blueprint_supports_multiple_instances(tmp_path: Path) -> None:
    """Two packages instantiating the service-vm blueprint must produce
    distinct resources without colliding on the framework resource identifier.

    Regression guard against #511-style bugs: the outer ``name`` of every
    blueprint resource must be templated so multi-instance use is safe.
    """
    envs = tmp_path / "envs"
    pkg_a = envs / "test" / "proxmox" / "svc-a"
    pkg_b = envs / "test" / "proxmox" / "svc-b"
    pkg_a.mkdir(parents=True)
    pkg_b.mkdir(parents=True)

    (pkg_a / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: svc-a
            description: "Service VM A"
            blueprint: service-vm
            variables:
              vm_name: svc-a
              vmid: 220
              target_node: pve1
              mac_address: "AA:AA:AA:AA:AA:01"
              ip_address: "192.168.10.71"
              dhcp_subnet: subnet-a
            """
        )
    )
    (pkg_b / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: svc-b
            description: "Service VM B"
            blueprint: service-vm
            variables:
              vm_name: svc-b
              vmid: 221
              target_node: pve2
              mac_address: "BB:BB:BB:BB:BB:02"
              ip_address: "192.168.10.72"
              dhcp_subnet: subnet-b
            """
        )
    )

    resolver = BlueprintResolver(envs)
    pkg_loader = PackageLoader(envs, blueprint_resolver=resolver)

    resources_a, _events_a, _ = pkg_loader.load_package(pkg_a, provider="proxmox", env_name="test")
    resources_b, _events_b, _ = pkg_loader.load_package(pkg_b, provider="proxmox", env_name="test")

    assert len(resources_a) == 2
    assert len(resources_b) == 2

    # VM resources have distinct templated identifiers
    vm_a = next(r for r in resources_a if r.type == "vm")
    vm_b = next(r for r in resources_b if r.type == "vm")
    assert vm_a.name == "svc-a"
    assert vm_b.name == "svc-b"
    assert vm_a.config["vmid"] == 220
    assert vm_b.config["vmid"] == 221
    assert vm_a.config["target_node"] == "pve1"
    assert vm_b.config["target_node"] == "pve2"

    # DHCP reservations also distinct
    dhcp_a = next(r for r in resources_a if r.type == "kea_reservation")
    dhcp_b = next(r for r in resources_b if r.type == "kea_reservation")
    assert dhcp_a.name == "svc-a"
    assert dhcp_b.name == "svc-b"
    assert dhcp_a.config["ip_address"] == "192.168.10.71"
    assert dhcp_b.config["ip_address"] == "192.168.10.72"
    assert dhcp_a.config["subnet_ref"] == "subnet-a"
    assert dhcp_b.config["subnet_ref"] == "subnet-b"


def test_service_vm_config_passes_proxmox_validation(tmp_path: Path) -> None:
    """End-to-end regression guard for issue #622.

    Loads the service-vm blueprint and runs the rendered proxmox VM
    resource through ``ProxmoxProvider.generate_terraform``, which invokes
    ``VMConfigValidator`` / ``StorageConfigValidator`` (wired in by #621).
    If the blueprint ever re-introduces a bad schema — either on the VM
    itself or by smuggling back a non-cluster-level storage resource —
    this test fails.

    Also asserts that the service-vm blueprint never renders a
    ``proxmox.storage`` resource: Proxmox storage pools are cluster-wide
    concerns and belong in a dedicated storage package, not in per-VM
    blueprints.
    """
    envs = tmp_path / "envs"
    pkg = envs / "test" / "proxmox" / "svc"
    pkg.mkdir(parents=True)

    (pkg / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: svc
            description: "Service VM for validator e2e test"
            blueprint: service-vm
            variables:
              vm_name: svc
              vmid: 213
              target_node: pve1
              mac_address: "AA:BB:CC:DD:EE:FF"
              ip_address: "192.168.10.63"
              dhcp_subnet: opt1-infrastructure
            """
        )
    )

    resolver = BlueprintResolver(envs)
    pkg_loader = PackageLoader(envs, blueprint_resolver=resolver)

    resources, _events, _variables = pkg_loader.load_package(
        pkg, provider="proxmox", env_name="test"
    )

    # Provider fixture pattern mirrors tests/unit/providers/proxmox/test_storage_support.py
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    provider = ProxmoxProvider(config_dir, output_dir)
    provider.set_environment("test")

    proxmox_resources = [r for r in resources if r.provider == "proxmox"]

    # Blueprint must not smuggle in cluster-wide concerns as per-VM resources.
    assert all(r.type != "storage" for r in proxmox_resources)

    # Must NOT raise SchemaValidationError.
    provider.generate_terraform(proxmox_resources)

    # The rendered storage.tf (always present, provider emits it per env)
    # must be empty of actual resource blocks, because the blueprint emits
    # no storage resources.
    storage_tf_candidates = list(tmp_path.rglob("storage.tf"))
    for candidate in storage_tf_candidates:
        assert "proxmox_virtual_environment_storage" not in candidate.read_text()
