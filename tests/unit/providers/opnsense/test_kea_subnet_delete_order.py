"""End to end: a kea subnet leaves YAML and its reservations are not orphaned (#1264).

Uses the real runner and the real DHCPv4 subnet and reservation managers against an
in-memory fake of the Kea service. OPNsense neither cascades a subnet delete nor
refuses it, so the fake behaves the same: deleting a subnet leaves its reservations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.runners.opnsense_direct_runner import OPNsenseDirectRunner
from infrafoundry.providers.opnsense.components.kea_dhcp4_reservation import (
    KeaDHCPv4ReservationManager,
)
from infrafoundry.providers.opnsense.components.kea_dhcp4_subnet import KeaDHCPv4SubnetManager
from infrafoundry.providers.opnsense.services.kea_dhcp import KeaDHCPService

SUBNETS = "kea.dhcp4.subnets"
RESERVATIONS = "kea.dhcp4.reservations"


class FakeKea:
    """Just enough of ``KeaDHCPService`` for the two managers, with a call log."""

    def __init__(self, subnets: dict[str, str], reservations: list[dict[str, Any]]) -> None:
        self.subnets = dict(subnets)  # uuid -> cidr
        self.reservations = [dict(r) for r in reservations]
        self.log: list[str] = []
        self._next = 0

    def search_dhcpv4_subnets(self) -> list[dict[str, Any]]:
        return [{"uuid": u, "subnet": c} for u, c in self.subnets.items()]

    def search_dhcpv4_reservations(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.reservations]

    def get_dhcpv4_subnet(self, uuid: str) -> dict[str, Any]:
        return {"subnet4": {}}

    def get_dhcpv4_reservation(self, uuid: str) -> dict[str, Any]:
        return {"reservation": {}}

    def ensure_dhcpv4_enabled(self, interfaces: list[str]) -> None:
        self.log.append("ensure_enabled")

    def add_dhcpv4_subnet(self, data: dict[str, Any]) -> dict[str, Any]:
        self._next += 1
        uuid = f"new-sub-{self._next}"
        self.subnets[uuid] = str(data["subnet"])
        self.log.append(f"add_subnet {data['subnet']}")
        return {"result": "saved", "uuid": uuid}

    def update_dhcpv4_subnet(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        self.log.append(f"update_subnet {uuid}")
        return {"result": "saved"}

    def delete_dhcpv4_subnet(self, uuid: str) -> dict[str, Any]:
        self.log.append(f"delete_subnet {self.subnets[uuid]}")
        del self.subnets[uuid]  # no cascade
        return {"result": "deleted"}

    def add_dhcpv4_reservation(self, data: dict[str, Any]) -> dict[str, Any]:
        self.log.append(f"add_reservation {data['hw_address']}")
        self.reservations.append({**data, "uuid": f"new-res-{data['hw_address']}"})
        return {"result": "saved"}

    def update_dhcpv4_reservation(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        self.log.append(f"update_reservation {uuid}")
        return {"result": "saved"}

    def delete_dhcpv4_reservation(self, uuid: str) -> dict[str, Any]:
        row = next(r for r in self.reservations if r["uuid"] == uuid)
        self.log.append(f"delete_reservation {row['hw_address']}")
        self.reservations.remove(row)
        return {"result": "deleted"}

    def orphans(self) -> list[str]:
        return [r["hw_address"] for r in self.reservations if r["subnet"] not in self.subnets]


def _subnet(name: str, cidr: str) -> ResourceConfig:
    return ResourceConfig(
        name=name, type=SUBNETS, provider="opnsense", config={"subnet": cidr, "interface": "opt1"}
    )


def _reservation(name: str, ref: str, mac: str) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type=RESERVATIONS,
        provider="opnsense",
        config={"subnet_ref": ref, "hw_address": mac, "ip_address": "10.0.1.5"},
    )


@pytest.fixture
def provider(tmp_path: Path) -> MagicMock:
    provider = MagicMock()
    provider.name = "opnsense"
    provider._current_environment = "dev"
    provider.config_dir = tmp_path
    provider.get_direct_api_resource_types.return_value = {
        SUBNETS: KeaDHCPv4SubnetManager,
        RESERVATIONS: KeaDHCPv4ReservationManager,
    }
    return provider


def _run(
    provider: MagicMock, fake: FakeKea, yaml: list[ResourceConfig], managed: Any
) -> tuple[dict[str, Any], MagicMock]:
    runner = OPNsenseDirectRunner()
    runner.console = MagicMock()
    with (
        patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=yaml),
        patch.object(KeaDHCPService, "from_environment", return_value=fake),
    ):
        result = runner.apply(provider, managed_resources=managed)
    return dict(result), runner.console


def test_managed_reservation_is_deleted_before_its_subnet_and_unmanaged_blocks(
    provider: MagicMock,
) -> None:
    fake = FakeKea(
        {"u-a": "10.0.1.0/24", "u-b": "172.21.2.0/24"},
        [
            {"uuid": "r-a", "subnet": "u-a", "hw_address": "aa:aa", "ip_address": "10.0.1.5"},
            {"uuid": "r-h", "subnet": "u-b", "hw_address": "hh:hh", "ip_address": "172.21.2.5"},
        ],
    )
    managed = {
        SUBNETS: [_subnet("a", "10.0.1.0/24"), _subnet("b", "172.21.2.0/24")],
        RESERVATIONS: [_reservation("ra", "a", "aa:aa")],
    }

    result, console = _run(provider, fake, [], managed)

    assert result["success"] is True
    # Subnet A's reservation goes first, while A is still live; then A itself.
    assert fake.log == ["delete_reservation aa:aa", "delete_subnet 10.0.1.0/24"]
    assert fake.orphans() == []
    # B is kept because of the hand-made reservation, which is untouched.
    assert fake.subnets == {"u-b": "172.21.2.0/24"}
    assert [r["hw_address"] for r in fake.reservations] == ["hh:hh"]
    released = {(r["resource_type"], r["name"]) for r in result["released_resources"]}
    assert released == {(RESERVATIONS, "ra"), (SUBNETS, "a")}
    printed = [str(c.args[0]) for c in console.print.call_args_list]
    assert any("[yellow]" in p and "172.21.2.0/24" in p and "hh:hh" in p for p in printed)


def test_plan_reports_the_blocked_subnet(provider: MagicMock) -> None:
    fake = FakeKea(
        {"u-b": "172.21.2.0/24"},
        [{"uuid": "r-h", "subnet": "u-b", "hw_address": "hh:hh", "ip_address": "172.21.2.5"}],
    )
    managed = {SUBNETS: [_subnet("b", "172.21.2.0/24")]}
    runner = OPNsenseDirectRunner()
    runner.console = MagicMock()
    with (
        patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]),
        patch.object(KeaDHCPService, "from_environment", return_value=fake),
    ):
        plan = runner.plan(provider, managed_resources=managed)
    assert "1 blocked (kept)." in plan["changes_summary"]
    assert plan["has_changes"] is False


def test_new_subnet_and_reservation_on_it_are_still_added_in_order(provider: MagicMock) -> None:
    fake = FakeKea({}, [])
    yaml = [_subnet("n", "10.0.9.0/24"), _reservation("rn", "n", "nn:nn")]

    result, _ = _run(provider, fake, yaml, {})

    assert result["success"] is True
    assert fake.log == ["ensure_enabled", "add_subnet 10.0.9.0/24", "add_reservation nn:nn"]
    assert fake.reservations[0]["subnet"] == "new-sub-1"
