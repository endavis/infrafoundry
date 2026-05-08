"""Integration test for the aiqum blueprint conversion.

Loads the real example-config aiqum package via PackageLoader and asserts that
the merged configuration (blueprint defaults + package overrides) produces the
expected proxmox VM and opnsense DHCP resources, plus the inherited on_create
event handler. This is the regression guard for issue #502 and follows the
pattern established by ``test_rocky9_blueprint.py`` (see #503, #511).

The test depends only on files checked into this repository:
  - blueprints/aiqum/                          (the blueprint)
  - example-config/envs/dev/proxmox/aiqum/     (the example consumer)

It does NOT depend on the private endavis-infra/ config repo.
"""

import textwrap
from pathlib import Path

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "dev" / "proxmox" / "aiqum"


@pytest.fixture
def loader() -> PackageLoader:
    """PackageLoader pointed at the real example-config envs/ directory."""
    resolver = BlueprintResolver(EXAMPLE_ENVS)
    return PackageLoader(EXAMPLE_ENVS, blueprint_resolver=resolver)


def test_aiqum_example_package_loads_blueprint(loader: PackageLoader) -> None:
    """The aiqum example package loads via the blueprint resolver and merges
    blueprint defaults with per-instance overrides."""
    _resources, _events, variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    # --- Per-instance overrides come from the package manifest ---
    assert variables["vm_name"] == "aiqum"
    assert variables["vmid"] == 222
    assert variables["target_node"] == "pve1"
    assert variables["disk_storage"] == "local-lvm"
    assert variables["ip_address"] == "192.168.1.50"
    assert variables["dhcp_subnet"] == "my-subnet"

    # --- Blueprint defaults flow through unchanged ---
    assert variables["template_vmid"] == 901
    assert variables["cores"] == 4
    assert variables["memory"] == 12288
    assert variables["disk_size"] == 150
    assert variables["bridge"] == "vmbr0"
    assert variables["vlan_tag"] == 10
    assert variables["aiqum_admin_user"] == "umadmin"
    assert variables["smtp_port"] == 587
    assert variables["ontap_admin_user"] == "admin"


def test_aiqum_example_renders_vm_and_dhcp_resources(loader: PackageLoader) -> None:
    """The merged config produces exactly two resources: a proxmox VM and an
    opnsense kea_reservation, both named after vm_name."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    assert len(resources) == 2

    by_provider = {r.provider: r for r in resources}
    assert set(by_provider) == {"proxmox", "opnsense"}

    vm = by_provider["proxmox"]
    assert vm.type == "vm"
    assert vm.name == "aiqum"

    dhcp = by_provider["opnsense"]
    assert dhcp.type == "kea.dhcp4.reservations"
    assert dhcp.name == "aiqum"


def test_aiqum_example_vm_config_uses_merged_values(loader: PackageLoader) -> None:
    """Rendered VM config combines blueprint defaults with package overrides."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    vm = next(r for r in resources if r.provider == "proxmox" and r.type == "vm")
    config = vm.config

    # Per-instance overrides
    assert config["name"] == "aiqum"
    assert config["vmid"] == 222
    assert config["target_node"] == "pve1"
    assert config["disk"]["storage"] == "local-lvm"

    # Blueprint defaults
    assert config["clone"] == {"vm_id": 901, "node_name": "pve1"}
    assert config["cores"] == 4
    assert config["memory"] == 12288
    assert config["disk"]["size"] == 150
    assert config["agent"] is True
    assert config["onboot"] is True
    assert config["tags"] == ["ontap", "aiqum"]

    # Network: single NIC with bridge + vlan tag from blueprint defaults
    assert len(config["network"]) == 1
    assert config["network"][0]["bridge"] == "vmbr0"
    assert config["network"][0]["tag"] == 10
    # mac_address default is empty, so no macaddr key on the NIC
    assert "macaddr" not in config["network"][0]

    # Cloud-init snippets are recipe-level metadata baked into the blueprint
    assert config["cloud_init_snippets"] == [
        "users/ansible",
        "network/dhcp",
        "packages/qemu-agent",
        "system/hostname",
    ]


def test_aiqum_example_dhcp_config_uses_merged_values(loader: PackageLoader) -> None:
    """Rendered kea_reservation config uses per-instance values."""
    resources, _events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    dhcp = next(
        r for r in resources if r.provider == "opnsense" and r.type == "kea.dhcp4.reservations"
    )
    config = dhcp.config

    assert config["subnet_ref"] == "my-subnet"
    assert config["ip_address"] == "192.168.1.50"
    assert config["hostname"] == "aiqum"
    assert config["description"] == "NetApp Active IQ Unified Manager"


def test_aiqum_blueprint_inherits_events(loader: PackageLoader) -> None:
    """The on_create event handler is inherited from the blueprint and its
    requires field is rendered with the per-instance vm_name."""
    _resources, events, _variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )

    assert "on_create" in events
    handlers = events["on_create"]
    assert len(handlers) == 1

    handler = handlers[0]
    assert handler["type"] == "script"
    assert handler["name"] == "aiqum-setup"
    assert handler["script"].endswith("scripts/aiqum-post-terraform.sh")
    assert handler["timeout"] == 5400
    assert handler["continue_on_error"] is False
    # Templated requires field rendered with per-instance vm_name
    assert handler["requires"] == ["aiqum"]


def test_aiqum_blueprint_supports_multiple_instances(tmp_path: Path) -> None:
    """Two packages instantiating the aiqum blueprint must produce distinct
    resources without colliding on the framework resource identifier.

    Regression guard against #511-style bugs: the outer ``name`` of every
    blueprint resource must be templated so multi-instance use is safe.
    """
    envs = tmp_path / "envs"
    pkg_a = envs / "test" / "proxmox" / "aiqum-a"
    pkg_b = envs / "test" / "proxmox" / "aiqum-b"
    pkg_a.mkdir(parents=True)
    pkg_b.mkdir(parents=True)

    (pkg_a / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: aiqum-a
            description: "AIQUM instance A"
            blueprint: aiqum
            variables:
              vm_name: aiqum-a
              vmid: 230
              target_node: pve1
              disk_storage: local-lvm
              ip_address: "192.168.1.51"
              dhcp_subnet: subnet-a
              aiqum_admin_password: "pw-a"
              aiqum_admin_email: "a@example.com"
              aiqum_url_base: "http://web/aiqum"
              jumphost: "ansible@host"
              smtp_server: "smtp.example.com"
              smtp_user: "aiqum"
              smtp_password: "pw"
              ontap_cluster_ip: "192.168.1.220"
              ontap_admin_password: "pw"
            """
        )
    )
    (pkg_b / "infrafoundry.yml").write_text(
        textwrap.dedent(
            """\
            name: aiqum-b
            description: "AIQUM instance B"
            blueprint: aiqum
            variables:
              vm_name: aiqum-b
              vmid: 231
              target_node: pve2
              disk_storage: local-lvm
              ip_address: "192.168.1.52"
              dhcp_subnet: subnet-b
              aiqum_admin_password: "pw-b"
              aiqum_admin_email: "b@example.com"
              aiqum_url_base: "http://web/aiqum"
              jumphost: "ansible@host"
              smtp_server: "smtp.example.com"
              smtp_user: "aiqum"
              smtp_password: "pw"
              ontap_cluster_ip: "192.168.1.221"
              ontap_admin_password: "pw"
            """
        )
    )

    resolver = BlueprintResolver(envs)
    loader = PackageLoader(envs, blueprint_resolver=resolver)

    resources_a, events_a, _ = loader.load_package(pkg_a, provider="proxmox", env_name="test")
    resources_b, events_b, _ = loader.load_package(pkg_b, provider="proxmox", env_name="test")

    assert len(resources_a) == 2
    assert len(resources_b) == 2

    # VM resources have distinct templated identifiers
    vm_a = next(r for r in resources_a if r.type == "vm")
    vm_b = next(r for r in resources_b if r.type == "vm")
    assert vm_a.name == "aiqum-a"
    assert vm_b.name == "aiqum-b"
    assert vm_a.config["vmid"] == 230
    assert vm_b.config["vmid"] == 231
    assert vm_a.config["target_node"] == "pve1"
    assert vm_b.config["target_node"] == "pve2"

    # DHCP reservations also distinct
    dhcp_a = next(r for r in resources_a if r.type == "kea.dhcp4.reservations")
    dhcp_b = next(r for r in resources_b if r.type == "kea.dhcp4.reservations")
    assert dhcp_a.name == "aiqum-a"
    assert dhcp_b.name == "aiqum-b"
    assert dhcp_a.config["ip_address"] == "192.168.1.51"
    assert dhcp_b.config["ip_address"] == "192.168.1.52"
    assert dhcp_a.config["subnet_ref"] == "subnet-a"
    assert dhcp_b.config["subnet_ref"] == "subnet-b"

    # Events are per-instance: requires field references the correct vm_name
    assert events_a["on_create"][0]["requires"] == ["aiqum-a"]
    assert events_b["on_create"][0]["requires"] == ["aiqum-b"]
