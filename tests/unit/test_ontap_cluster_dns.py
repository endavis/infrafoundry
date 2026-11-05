"""The ontap-cluster blueprint's DNS host overrides (#1251).

Loads a package through PackageLoader so the real ``dns.yaml`` renders with the
real blueprint defaults. Overrides are emitted only when ``publish_dns`` is
true, and each one carries the IP of the matching DHCP reservation.
"""

import textwrap
from pathlib import Path

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

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
  ontap_password: test-password
"""

OVERRIDE = "unbound.host_overrides"
RESERVATION = "kea.dhcp4.reservations"


def _load(tmp_path: Path, extra_variables: str = "") -> list[ResourceConfig]:
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
    return list(resources)


def _identity(resources: list[ResourceConfig]) -> set[tuple[str, str, str]]:
    return {(r.provider, r.type, r.name) for r in resources}


@pytest.mark.unit
@pytest.mark.parametrize(
    "extra",
    ["", 'dns_domain: "lab.test"\n', 'publish_dns: "false"\ndns_domain: "lab.test"\n'],
    ids=["default", "domain-only", "quoted-false"],
)
def test_no_overrides_unless_publish_dns_is_true(tmp_path: Path, extra: str) -> None:
    resources = _load(tmp_path, extra)

    assert [r for r in resources if r.type == OVERRIDE] == []
    # Same resources as before the feature: two VMs and five reservations.
    assert _identity(resources) == _identity(_load(tmp_path / "again"))
    assert sum(r.type == RESERVATION for r in resources) == 5


@pytest.mark.unit
def test_publish_dns_emits_one_override_per_reservation(tmp_path: Path) -> None:
    resources = _load(tmp_path, 'publish_dns: true\ndns_domain: "lab.test"\n')

    overrides = {r.name: r for r in resources if r.type == OVERRIDE}
    assert set(overrides) == {
        "ontap-demo-dns",
        "ontap-node-1-dns",
        "ontap-node-2-dns",
        "ontap-demo-data1-dns",
        "ontap-demo-data2-dns",
    }
    assert all(r.provider == "opnsense" for r in overrides.values())
    assert all(r.config["domain"] == "lab.test" for r in overrides.values())

    reservations = {
        r.config["hostname"]: r.config["ip_address"] for r in resources if r.type == RESERVATION
    }
    published = {o.config["hostname"]: o.config["server"] for o in overrides.values()}
    assert published == reservations
    assert len(published) == 5


@pytest.mark.unit
def test_publish_dns_without_domain_fails(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigurationError, match="dns_domain must be set when publish_dns"):
        _load(tmp_path, "publish_dns: true\n")
