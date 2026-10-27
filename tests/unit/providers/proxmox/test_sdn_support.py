"""Unit tests for Proxmox SDN zone and vnet support (#1137).

Covers resource type registration, sdn.tf rendering, the two SDN appliers, and
the ``depends_on`` that orders VMs and containers after a managed vnet.
"""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider

PEERS = ["192.168.10.100", "192.168.10.101", "192.168.10.102"]
DEPENDS = "depends_on = [proxmox_sdn_applier.apply]"


@pytest.fixture
def provider(tmp_path: Path) -> ProxmoxProvider:
    """Create a ProxmoxProvider writing into tmp_path."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = ProxmoxProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


def _zone(name: str = "nettest", **config: Any) -> ResourceConfig:
    return ResourceConfig(
        name=name, type="sdn_zone", provider="proxmox", config={"peers": PEERS, **config}
    )


def _vnet(name: str = "ntlan", zone: str = "nettest", **config: Any) -> ResourceConfig:
    return ResourceConfig(
        name=name, type="sdn_vnet", provider="proxmox", config={"zone": zone, "tag": 9900, **config}
    )


def _vm(name: str, bridge: str) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="vm",
        provider="proxmox",
        config={"name": name, "vmid": 9990, "target_node": "pve3", "network": [{"bridge": bridge}]},
    )


def _generate(provider: ProxmoxProvider, resources: list[ResourceConfig]) -> dict[str, str]:
    provider.generate_terraform(resources)
    return {f.name: f.read_text() for f in provider.terraform_dir.glob("*.tf")}


class TestRegistration:
    def test_types_and_terraform_mapping(self, provider: ProxmoxProvider) -> None:
        assert {"sdn_zone", "sdn_vnet"} <= set(provider.get_resource_types())
        mapping = provider.get_terraform_resource_types()
        assert mapping["sdn_zone"] == ["proxmox_sdn_zone_vxlan"]
        assert mapping["sdn_vnet"] == ["proxmox_sdn_vnet"]

    def test_dependencies(self, provider: ProxmoxProvider) -> None:
        deps = provider.get_dependencies()
        assert deps["sdn_vnet"] == ["sdn_zone"]
        assert "sdn_vnet" in deps["vm"]
        assert "sdn_vnet" in deps["container"]


class TestRendering:
    def test_zone_vnet_and_appliers(self, provider: ProxmoxProvider) -> None:
        files = _generate(
            provider, [_zone(mtu=8950, nodes=["pve1", "pve3"]), _vnet(alias="NetApp test")]
        )
        sdn = files["sdn.tf"]

        assert 'resource "proxmox_sdn_zone_vxlan" "nettest"' in sdn
        assert 'peers = ["192.168.10.100", "192.168.10.101", "192.168.10.102"]' in sdn
        assert "mtu   = 8950" in sdn
        assert 'nodes = ["pve1", "pve3"]' in sdn
        assert 'resource "proxmox_sdn_vnet" "ntlan"' in sdn
        assert "zone = proxmox_sdn_zone_vxlan.nettest.id" in sdn
        assert "tag  = 9900" in sdn
        assert 'alias = "NetApp test"' in sdn

    def test_finalize_applier_runs_last_on_destroy(self, provider: ProxmoxProvider) -> None:
        sdn = _generate(provider, [_zone(), _vnet()])["sdn.tf"]

        finalize = sdn.split('resource "proxmox_sdn_applier" "finalize" {')[1].split("}")[0]
        assert "on_create  = false" in finalize
        assert "on_destroy = true" in finalize
        assert sdn.count("depends_on = [proxmox_sdn_applier.finalize]") == 2

    def test_apply_applier_tracks_every_zone_and_vnet(self, provider: ProxmoxProvider) -> None:
        sdn = _generate(provider, [_zone(), _vnet(), _vnet("ntdata", tag=9901)])["sdn.tf"]

        refs = "[proxmox_sdn_zone_vxlan.nettest, proxmox_sdn_vnet.ntlan, proxmox_sdn_vnet.ntdata]"
        assert f"depends_on = {refs}" in sdn
        assert f"replace_triggered_by = {refs}" in sdn

    def test_config_id_overrides_name_and_zone_resolves_by_name(
        self, provider: ProxmoxProvider
    ) -> None:
        sdn = _generate(
            provider, [_zone("netapp-test", id="nettest"), _vnet("lan", zone="netapp-test")]
        )["sdn.tf"]

        assert 'id    = "nettest"' in sdn
        assert "zone = proxmox_sdn_zone_vxlan.nettest.id" in sdn
        assert 'id   = "lan"' in sdn

    def test_no_sdn_resources_writes_no_sdn_file(self, provider: ProxmoxProvider) -> None:
        files = _generate(provider, [_vm("plain", "vmbr0")])

        assert "sdn.tf" not in files
        assert DEPENDS not in files["vms.tf"]

    def test_invalid_config_blocks_generation(self, provider: ProxmoxProvider) -> None:
        with pytest.raises(SchemaValidationError, match="proxmox_sdn_vnet_ntlan_zone"):
            provider.generate_terraform([_zone(), _vnet(zone="missing")])


class TestOrdering:
    def test_only_vms_on_a_managed_vnet_depend_on_the_applier(
        self, provider: ProxmoxProvider
    ) -> None:
        vms = _generate(provider, [_zone(), _vnet(), _vm("on-vnet", "ntlan"), _vm("off", "vmbr0")])[
            "vms.tf"
        ]

        on_vnet = vms.split('"proxmox_virtual_environment_vm" "on_vnet"')[1].split("resource ")[0]
        off = vms.split('"proxmox_virtual_environment_vm" "off"')[1]
        assert DEPENDS in on_vnet
        assert DEPENDS not in off

    def test_container_on_a_managed_vnet(self, provider: ProxmoxProvider) -> None:
        container = ResourceConfig(
            name="ct1",
            type="container",
            provider="proxmox",
            config={
                "name": "ct1",
                "ctid": 9980,
                "target_node": "pve3",
                "ostemplate": "local:vztmpl/debian.tar.zst",
                "network": {"name": "eth0", "bridge": "ntlan"},
            },
        )

        files = _generate(provider, [_zone(), _vnet(), container])

        assert DEPENDS in files["containers.tf"]

    def test_disk_image_vm_on_a_managed_vnet(self, provider: ProxmoxProvider) -> None:
        vm = _vm("appliance", "ntlan")
        vm.config.update({"disk_image_source": "/var/lib/vz/images/app.img", "memory": 2048})

        files = _generate(provider, [_zone(), _vnet(), vm])

        assert DEPENDS in files["ova_vms.tf"]
