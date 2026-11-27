"""Blueprint load and render tests for the reverse-proxy blueprint (#1689).

Loads the real example-config reverse-proxy package through PackageLoader and checks the
merged variables, the generated resources (VM, DHCP, one DNS override per route, the acme
certificate) and the after_apply handler env. Depends only on files in this repository.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from infrafoundry.core.certs.install import parse_target, resolve_target
from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.provider import ResourceConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENVS = REPO_ROOT / "example-config" / "envs"
PACKAGE_DIR = EXAMPLE_ENVS / "dev" / "proxmox" / "reverse-proxy"

MANIFEST = """\
name: {vm_name}
blueprint: reverse-proxy
variables:
  vm_name: {vm_name}
  vmid: {vmid}
  target_node: node1
  disk_storage: local-lvm
  ip_address: "{ip}"
  dhcp_subnet: subnet-a
"""


@pytest.fixture
def loader() -> PackageLoader:
    """PackageLoader pointed at the real example-config envs/ directory."""
    return PackageLoader(EXAMPLE_ENVS, blueprint_resolver=BlueprintResolver(EXAMPLE_ENVS))


def _load(
    tmp_path: Path,
    extra: str = "",
    vm_name: str = "proxy-a",
    vmid: int = 230,
    ip: str = "192.0.2.71",
) -> tuple[list[ResourceConfig], dict[str, Any], dict[str, Any]]:
    envs = tmp_path / "envs"
    package = envs / "test" / "proxmox" / vm_name
    package.mkdir(parents=True)
    (package / "infrafoundry.yml").write_text(
        MANIFEST.format(vm_name=vm_name, vmid=vmid, ip=ip) + textwrap.indent(extra, "  ")
    )
    loader = PackageLoader(envs, blueprint_resolver=BlueprintResolver(envs))
    resources, events, variables = loader.load_package(package, provider="proxmox", env_name="test")
    return list(resources), events, variables


def _example(loader: PackageLoader) -> tuple[list[ResourceConfig], dict[str, Any], dict[str, Any]]:
    resources, events, variables = loader.load_package(
        PACKAGE_DIR, provider="proxmox", env_name="dev"
    )
    return list(resources), events, variables


def _overrides(resources: list[ResourceConfig]) -> dict[str, ResourceConfig]:
    return {r.name: r for r in resources if r.type == "unbound.host_overrides"}


def test_example_merges_defaults_and_overrides(loader: PackageLoader) -> None:
    _resources, _events, variables = _example(loader)

    assert variables["vm_name"] == "reverse-proxy"
    assert variables["ip_address"] == "192.0.2.70"
    assert variables["cores"] == 2
    assert variables["memory"] == 1024
    assert variables["disk_size"] == 32
    assert variables["template_vmid"] == 900
    assert variables["cert_dir"] == "/etc/ssl/infrafoundry"


def _blueprint_default(name: str, var: str) -> int:
    data = yaml.safe_load((REPO_ROOT / "blueprints" / name / "blueprint.yaml").read_text())
    return int(next(v["default"] for v in data["inputs"] if v["name"] == var))


def test_default_disk_size_covers_ubuntu_template_disk() -> None:
    """Proxmox cannot shrink a cloned disk, so the default must not undercut the template."""
    assert _blueprint_default("reverse-proxy", "disk_size") >= _blueprint_default(
        "ubuntu-template", "disk_size"
    )


def test_example_renders_vm_dhcp_dns_and_certificate(loader: PackageLoader) -> None:
    resources, _events, variables = _example(loader)

    vm = next(r for r in resources if r.type == "vm")
    assert vm.config["ssh_host_key"] == {"address": variables["ip_address"]}
    assert vm.config["cores"] == 2
    reservations = [r for r in resources if r.type == "kea.dhcp4.reservations"]
    assert len(reservations) == 1
    assert reservations[0].config["ip_address"] == "192.0.2.70"
    assert set(_overrides(resources)) == {"reverse-proxy-nas", "reverse-proxy-switch"}
    assert [r.name for r in resources if r.provider == "acme"] == ["reverse-proxy-cert"]


def test_host_overrides_point_at_the_proxy_and_describe_the_route(loader: PackageLoader) -> None:
    resources, _events, _variables = _example(loader)
    overrides = _overrides(resources)

    nas = overrides["reverse-proxy-nas"].config
    assert (nas["hostname"], nas["domain"], nas["server"]) == ("nas", "example.com", "192.0.2.70")
    assert "https://192.0.2.20:443" in nas["description"]
    assert "insecure" in nas["description"]
    switch = overrides["reverse-proxy-switch"].config["description"]
    assert "host=upstream" in switch
    assert "from=192.0.2.0/24,100.64.0.0/10" in switch


def test_changed_backend_changes_only_that_description(tmp_path: Path) -> None:
    base = (
        "routes:\n"
        "  - {name: nas, backend: 'https://192.0.2.20'}\n"
        "  - {name: switch, backend: 'https://192.0.2.21'}\n"
        "dns_domain: example.com\n"
    )
    changed = base.replace("192.0.2.21", "192.0.2.22")
    before = _overrides(_load(tmp_path / "a", base)[0])
    after = _overrides(_load(tmp_path / "b", changed)[0])

    assert before["proxy-a-nas"].config == after["proxy-a-nas"].config
    assert before["proxy-a-switch"].config != after["proxy-a-switch"].config
    assert "192.0.2.22" in after["proxy-a-switch"].config["description"]


def test_empty_routes_give_no_host_overrides(tmp_path: Path) -> None:
    resources, _events, _variables = _load(tmp_path, "dns_domain: example.com\n")

    assert _overrides(resources) == {}


def test_routes_without_a_domain_fail(tmp_path: Path) -> None:
    extra = "routes:\n  - {name: nas, backend: 'https://192.0.2.20'}\n"

    with pytest.raises(InvalidConfigurationError):
        _load(tmp_path, extra)


def test_cores_below_two_fail(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigurationError, match="at least 2"):
        _load(tmp_path, "dns_domain: example.com\ncores: 1\n")


def test_no_certificate_names_give_no_acme_resource(tmp_path: Path) -> None:
    resources, _events, _variables = _load(tmp_path, "dns_domain: example.com\n")

    assert [r for r in resources if r.provider == "acme"] == []


def test_certificate_without_a_route_fails(tmp_path: Path) -> None:
    with pytest.raises(InvalidConfigurationError, match="at least one route"):
        _load(tmp_path, "dns_domain: example.com\ncertificate_names: ['*.example.com']\n")


def test_certificate_config_targets_the_proxy_vm(loader: PackageLoader) -> None:
    resources, _events, _variables = _example(loader)
    cert = next(r for r in resources if r.provider == "acme")
    config = cert.config

    assert config["names"] == ["*.example.com"]
    target = config["target"]
    assert target["provider"] == "proxmox"
    assert target["resource"] == "reverse-proxy"
    assert (target["owner"], target["group"], target["key_mode"]) == ("caddy", "caddy", "0600")
    assert target["reload"] == ["systemctl", "reload", "caddy"]
    assert target["verify"] == {"port": 443, "server_name": "nas.example.com"}
    parsed = parse_target(target, config["names"])
    assert parsed.resource == "reverse-proxy"


def test_certificate_target_finds_the_vm_and_asks_for_the_pinned_key(
    loader: PackageLoader,
) -> None:
    resources, _events, _variables = _example(loader)
    cert = next(r for r in resources if r.provider == "acme")

    with pytest.raises(Exception, match="no pinned SSH host key"):
        resolve_target(cert.config["target"], cert.config["names"], resources)


def test_two_instances_get_distinct_resource_names(tmp_path: Path) -> None:
    extra = "dns_domain: example.com\nroutes:\n  - {name: nas, backend: 'https://192.0.2.20'}\n"
    a = _load(tmp_path / "a", extra, vm_name="proxy-a", vmid=230, ip="192.0.2.71")[0]
    b = _load(tmp_path / "b", extra, vm_name="proxy-b", vmid=231, ip="192.0.2.72")[0]

    assert {r.name for r in a}.isdisjoint({r.name for r in b})
    assert "proxy-a-nas" in {r.name for r in a}


def test_after_apply_handler_carries_the_routes(loader: PackageLoader) -> None:
    _resources, events, variables = _example(loader)

    (handler,) = events["after_apply"]
    assert handler["name"] == "reverse-proxy-config"
    assert handler["continue_on_error"] is True
    env = handler["env"]
    assert json.loads(env["RP_ROUTES"]) == variables["routes"]
    assert json.loads(env["RP_ALLOWED"]) == []
    assert env["RP_IP"] == "192.0.2.70"
    assert env["RP_DOMAIN"] == "example.com"


def test_vm_carries_the_reservation_address_for_ip_tags(loader: PackageLoader) -> None:
    """The VM lists the reserved address so it is tagged with it (#1699)."""
    resources, _events, variables = _example(loader)

    vm = next(r for r in resources if r.type == "vm")
    assert vm.config["ip_addresses"] == [variables["ip_address"]] == ["192.0.2.70"]
