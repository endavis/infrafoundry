"""The ontap-cluster blueprint's ``cluster_bridge`` input (#1158).

Loads a package through PackageLoader so the real ``vm.yaml`` renders with the
real blueprint defaults. With ``cluster_bridge`` unset every NIC stays on
``bridge``; with it set, only the cluster interconnect ports e0a/e0b move.
"""

import textwrap
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader

BASE_VARIABLES = """\
  cluster_name: ontap-demo
  cluster_mgmt_ip: "172.20.99.80"
  data_lif1_ip: "172.20.99.83"
  data_lif2_ip: "172.20.99.84"
  node01_name: ontap-node-1
  node01_vmid: 1130
  node01_target: node2
  node01_mgmt_ip: "172.20.99.81"
  node02_name: ontap-node-2
  node02_vmid: 1131
  node02_target: node3
  node02_mgmt_ip: "172.20.99.82"
"""


def _vm_networks(tmp_path: Path, extra_variables: str = "") -> list[list[dict[str, Any]]]:
    envs = tmp_path / "envs"
    package = envs / "test" / "proxmox" / "ontap-cluster-demo"
    package.mkdir(parents=True)
    (package / "infrafoundry.yml").write_text(
        "name: ontap-cluster-demo\n"
        "blueprint: ontap-cluster\n"
        "variables:\n" + BASE_VARIABLES + textwrap.indent(extra_variables, "  ")
    )
    loader = PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))
    resources, _events, _variables = loader.load_package(
        package, provider="proxmox", env_name="test"
    )
    vms = [r for r in resources if r.type in ("vm", "ova_vm")]
    assert len(vms) == 2
    return [vm.config["network"] for vm in vms]


@pytest.mark.unit
def test_default_keeps_every_nic_on_bridge(tmp_path: Path) -> None:
    for network in _vm_networks(tmp_path):
        assert [nic["bridge"] for nic in network] == ["vmbr0"] * 4
        # mgmt_vlan defaults to 10 and still tags only e0c/e0d.
        assert [nic.get("tag") for nic in network] == [None, None, 10, 10]


@pytest.mark.unit
def test_cluster_bridge_moves_only_the_interconnect_ports(tmp_path: Path) -> None:
    networks = _vm_networks(tmp_path, 'bridge: demolan\nmgmt_vlan: ""\ncluster_bridge: democlus\n')

    for network in networks:
        assert [nic["bridge"] for nic in network] == ["democlus", "democlus", "demolan", "demolan"]
        assert all("tag" not in nic for nic in network)
