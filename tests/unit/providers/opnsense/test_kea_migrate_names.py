"""Kea DHCP ``config migrate`` names are unique and non-empty (#1340)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import yaml

from infrafoundry.core.config import ConfigManager
from infrafoundry.providers.opnsense.components.kea_dhcp import KeaDHCPManager
from infrafoundry.providers.opnsense.services.kea_dhcp import KeaDHCPService


def _service(
    v4s: list[dict[str, Any]] | None = None,
    v4r: list[dict[str, Any]] | None = None,
    v6s: list[dict[str, Any]] | None = None,
    v6r: list[dict[str, Any]] | None = None,
) -> KeaDHCPService:
    service = KeaDHCPService(MagicMock())
    service.search_dhcpv4_subnets = MagicMock(return_value=v4s or [])  # type: ignore[method-assign]
    service.search_dhcpv4_reservations = MagicMock(return_value=v4r or [])  # type: ignore[method-assign]
    service.search_dhcpv6_subnets = MagicMock(return_value=v6s or [])  # type: ignore[method-assign]
    service.search_dhcpv6_reservations = MagicMock(return_value=v6r or [])  # type: ignore[method-assign]
    return service


def _names(doc: str, leaf: str) -> list[str]:
    node = yaml.safe_load(doc)["opnsense"]["kea"]
    version, kind = leaf.split(".")
    return [e["name"] for e in node[version][kind]]


def _all_names(doc: str) -> list[str]:
    return [
        n
        for leaf in ("dhcp4.subnets", "dhcp4.reservations", "dhcp6.subnets", "dhcp6.reservations")
        for n in _names(doc, leaf)
    ]


def _res(hostname: str, mac: str) -> dict[str, Any]:
    return {"hostname": hostname, "hw_address": mac, "ip_address": "192.0.2.10", "subnet": "x"}


def test_unchanged_when_no_collision() -> None:
    doc = _service(
        v4s=[{"description": "My Lan", "subnet": "192.0.2.0/24"}],
        v4r=[_res("Web-1", "02:00:00:00:00:01")],
        v6s=[{"description": "lan", "subnet": "2001:db8::/64"}],
        v6r=[{"hostname": "web-1", "duid": "00:01", "ip_address": "2001:db8::5"}],
    ).export_to_yaml()
    assert _names(doc, "dhcp4.subnets") == ["my_lan"]
    assert _names(doc, "dhcp4.reservations") == ["web_1"]
    assert _names(doc, "dhcp6.subnets") == ["lan_v6"]
    assert _names(doc, "dhcp6.reservations") == ["web_1_v6"]


def test_empty_subnet_description_gets_name() -> None:
    doc = _service(v4s=[{"description": "", "subnet": "192.0.2.0/24"}]).export_to_yaml()
    assert _names(doc, "dhcp4.subnets") == ["192-0-2-0-24"]


def test_empty_subnet_description_without_cidr_uses_index() -> None:
    doc = _service(v4s=[{"description": ""}]).export_to_yaml()
    assert _names(doc, "dhcp4.subnets") == ["kea-dhcp4-subnets-1"]


def test_duplicate_subnet_descriptions_suffixed() -> None:
    doc = _service(
        v4s=[
            {"description": "lan", "subnet": "192.0.2.0/24"},
            {"description": "LAN", "subnet": "198.51.100.0/24"},
        ]
    ).export_to_yaml()
    assert _names(doc, "dhcp4.subnets") == ["lan", "lan-2"]


def test_reservation_collisions_and_missing_hostnames() -> None:
    doc = _service(
        v4r=[
            _res("web-1", "02:00:00:00:00:01"),
            _res("web_1", "02:00:00:00:00:02"),
            _res("", "02:00:00:00:00:03"),
            _res("", ""),
        ]
    ).export_to_yaml()
    assert _names(doc, "dhcp4.reservations") == [
        "web_1",
        "web_1-2",
        "02-00-00-00-00-03",
        "kea-dhcp4-reservations-4",
    ]


def test_v6_empty_and_duplicate_names() -> None:
    doc = _service(
        v6s=[{"description": "", "subnet": "2001:db8::/64"}, {"description": ""}],
        v6r=[
            {"hostname": "a-b", "duid": "00:01"},
            {"hostname": "a_b", "duid": "00:02"},
            {"hostname": "", "duid": "", "ip_address": "2001:db8::9"},
            {"hostname": ""},
        ],
    ).export_to_yaml()
    assert _names(doc, "dhcp6.subnets") == ["2001-db8-64_v6", "kea-dhcp6-subnets-2"]
    assert _names(doc, "dhcp6.reservations") == [
        "a_b_v6",
        "a_b_v6-2",
        "2001-db8-9_v6",
        "kea-dhcp6-reservations-4",
    ]


def test_names_unique_across_types() -> None:
    doc = _service(
        v4s=[{"description": "x_v6", "subnet": "192.0.2.0/24"}],
        v6s=[{"description": "x", "subnet": "2001:db8::/64"}],
    ).export_to_yaml()
    names = _all_names(doc)
    assert len(names) == len(set(names)) == 2


def test_reserved_names_avoided() -> None:
    doc = _service(v4s=[{"description": "lan", "subnet": "192.0.2.0/24"}]).export_to_yaml(
        reserved={"lan"}
    )
    assert _names(doc, "dhcp4.subnets") == ["lan-2"]


def test_existing_names_pinned_by_identity() -> None:
    service = _service(
        v4s=[
            {"description": "lan", "subnet": "192.0.2.0/24"},
            {"description": "other", "subnet": "198.51.100.0/24"},
        ],
        v4r=[_res("web", "02:00:00:00:00:01")],
    )
    doc = service.export_to_yaml(
        existing={
            "kea.dhcp4.subnets": {"198.51.100.0/24": "lan"},
            "kea.dhcp4.reservations": {"02:00:00:00:00:01": "keep-me"},
        }
    )
    # The pinned subnet takes "lan"; the other one's base name clashes and is suffixed.
    assert _names(doc, "dhcp4.subnets") == ["lan-2", "lan"]
    assert _names(doc, "dhcp4.reservations") == ["keep-me"]


def _manager_migrate(tmp_path: Path, env_yaml: str) -> str:
    target = tmp_path / "env" / "resources" / "existing.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(env_yaml, encoding="utf-8")
    service = _service(
        v4s=[{"description": "lan", "subnet": "192.0.2.0/24"}],
        v4r=[_res("web", "02:00:00:00:00:01")],
    )
    with patch.object(KeaDHCPService, "from_environment", return_value=service):
        return KeaDHCPManager(tmp_path).migrate("env")


def test_manager_reserves_other_types_names(tmp_path: Path) -> None:
    env_yaml = (
        "opnsense:\n  unbound:\n    host_overrides:\n      - name: lan\n"
        "        config:\n          hostname: lan\n          domain: example.com\n"
    )
    doc = _manager_migrate(tmp_path, env_yaml)
    assert _names(doc, "dhcp4.subnets") == ["lan-2"]


def test_manager_pins_existing_kea_names(tmp_path: Path) -> None:
    env_yaml = (
        "opnsense:\n  kea:\n    dhcp4:\n      subnets:\n        - name: office\n"
        "          config:\n            subnet: 192.0.2.0/24\n"
        "      reservations:\n        - name: lan\n"
        "          config:\n            hw_address: 02:00:00:00:00:01\n"
        "            ip_address: 192.0.2.10\n            subnet: 192.0.2.0/24\n"
    )
    doc = _manager_migrate(tmp_path, env_yaml)
    assert _names(doc, "dhcp4.subnets") == ["office"]
    assert _names(doc, "dhcp4.reservations") == ["lan"]


def test_generated_yaml_loads_without_duplicates(tmp_path: Path) -> None:
    doc = _service(
        v4s=[{"description": "", "subnet": "192.0.2.0/24"}, {"description": ""}],
        v4r=[_res("web-1", "02:00:00:00:00:01"), _res("web_1", "02:00:00:00:00:02")],
        v6s=[{"description": ""}],
        v6r=[{"hostname": ""}],
    ).export_to_yaml()
    target = tmp_path / "env" / "opnsense" / "kea.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(doc, encoding="utf-8")
    resources = ConfigManager(tmp_path).get_all_resources_all_providers("env")
    assert len([r for r in resources if r.provider == "opnsense"]) == 6


def _migrate_with(tmp_path: Path, env_yaml: str, service: KeaDHCPService) -> str:
    target = tmp_path / "env" / "resources" / "existing.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(env_yaml, encoding="utf-8")
    with patch.object(KeaDHCPService, "from_environment", return_value=service):
        return KeaDHCPManager(tmp_path).migrate("env")


def test_v4_reservations_sharing_a_mac_keep_their_names(tmp_path: Path) -> None:
    mac = "02:00:00:00:00:64"
    ips = ["192.0.2.100", "198.51.100.100", "203.0.113.100"]
    names = ["lan-device-100", "opt2-device-100", "host-x"]
    env_yaml = "opnsense:\n  kea:\n    dhcp4:\n      reservations:\n" + "".join(
        f"        - name: {n}\n          config:\n            hw_address: {mac.upper()}\n"
        f"            ip_address: {ip}\n"
        for n, ip in zip(names, ips, strict=True)
    )
    service = _service(
        v4r=[
            {"hostname": "device-100", "hw_address": mac, "ip_address": ip} for ip in reversed(ips)
        ]
    )
    doc = _migrate_with(tmp_path, env_yaml, service)
    assert _names(doc, "dhcp4.reservations") == list(reversed(names))


def test_v6_reservations_sharing_a_duid_keep_their_names(tmp_path: Path) -> None:
    duid = "00:01:00:01:02:03"
    ips = ["2001:db8:1::10", "2001:db8:2::10"]
    names = ["first-host", "second-host"]
    env_yaml = "opnsense:\n  kea:\n    dhcp6:\n      reservations:\n" + "".join(
        f"        - name: {n}\n          config:\n            duid: '{duid}'\n"
        f"            ip_address: {ip}\n"
        for n, ip in zip(names, ips, strict=True)
    )
    service = _service(
        v6r=[{"hostname": "dev", "duid": duid, "ip_address": ip} for ip in reversed(ips)]
    )
    doc = _migrate_with(tmp_path, env_yaml, service)
    assert _names(doc, "dhcp6.reservations") == list(reversed(names))
