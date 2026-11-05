"""Kea subnet and reservation managers: the delete phase and the delete refusal (#1264).

Each test runs for DHCPv4 (keyed on ``hw_address``) and DHCPv6 (keyed on ``duid``).
OPNsense does not cascade a subnet delete to its reservations, so a subnet is only
deleted once the reservations on it are gone, and is kept while a reservation
InfraFoundry does not manage still uses it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components import (
    kea_dhcp4_reservation,
    kea_dhcp4_subnet,
    kea_dhcp6_reservation,
    kea_dhcp6_subnet,
)


@dataclass(frozen=True)
class Family:
    """Everything that differs between the DHCPv4 and DHCPv6 managers."""

    v: str
    subnet_mgr: Any
    res_mgr: Any
    subnet_module: Any
    res_module: Any
    ident: str
    cidr: str
    other_cidr: str
    ident_a: str
    ident_b: str

    @property
    def subnet_type(self) -> str:
        return f"kea.dhcp{self.v}.subnets"

    @property
    def res_type(self) -> str:
        return f"kea.dhcp{self.v}.reservations"

    def subnet(self, name: str, cidr: str | None = None) -> ResourceConfig:
        return ResourceConfig(
            name=name,
            type=self.subnet_type,
            provider="opnsense",
            config={"subnet": cidr or self.cidr},
        )

    def reservation(self, name: str, ident: str, *, ref: str = "sub") -> ResourceConfig:
        return ResourceConfig(
            name=name,
            type=self.res_type,
            provider="opnsense",
            config={"subnet_ref": ref, self.ident: ident, "ip_address": "10.0.10.5"},
        )

    def service(
        self,
        subnets: list[dict[str, Any]],
        reservations: list[dict[str, Any]],
    ) -> MagicMock:
        service = MagicMock()
        getattr(service, f"search_dhcpv{self.v}_subnets").return_value = subnets
        getattr(service, f"search_dhcpv{self.v}_reservations").return_value = reservations
        getattr(service, f"get_dhcpv{self.v}_reservation").return_value = {"reservation": {}}
        return service

    def live_res(self, uuid: str, subnet_uuid: str, ident: str) -> dict[str, Any]:
        return {
            "uuid": uuid,
            "subnet": subnet_uuid,
            self.ident: ident,
            "ip_address": "10.0.10.5",
        }

    def patched(self, module: Any, service: MagicMock) -> Any:
        return patch.object(
            module.KeaDHCPService, "from_environment", MagicMock(return_value=service)
        )


V4 = Family(
    "4",
    kea_dhcp4_subnet.KeaDHCPv4SubnetManager,
    kea_dhcp4_reservation.KeaDHCPv4ReservationManager,
    kea_dhcp4_subnet,
    kea_dhcp4_reservation,
    "hw_address",
    "10.0.10.0/24",
    "10.0.20.0/24",
    "aa:bb:cc:dd:ee:01",
    "aa:bb:cc:dd:ee:02",
)
V6 = Family(
    "6",
    kea_dhcp6_subnet.KeaDHCPv6SubnetManager,
    kea_dhcp6_reservation.KeaDHCPv6ReservationManager,
    kea_dhcp6_subnet,
    kea_dhcp6_reservation,
    "duid",
    "fd00:1::/64",
    "fd00:2::/64",
    "00:01:00:01:aa",
    "00:01:00:01:bb",
)

FAMILIES = pytest.mark.parametrize("fam", [V4, V6], ids=["dhcpv4", "dhcpv6"])


def _live_subnets(fam: Family) -> list[dict[str, Any]]:
    return [{"subnet": fam.cidr, "uuid": "u-sub"}]


class TestMetadata:
    @FAMILIES
    def test_markers(self, fam: Family) -> None:
        assert fam.subnet_mgr.SPLIT_DELETE_PHASE is True
        assert fam.res_mgr.SPLIT_DELETE_PHASE is True
        assert fam.res_type == fam.subnet_mgr.DEPENDENT_RESOURCE_TYPE


class TestReservationDeletesOnly:
    @FAMILIES
    def test_only_deletes_with_no_per_object_reads(self, fam: Family, tmp_path: Path) -> None:
        live = [
            fam.live_res("r-keep", "u-sub", fam.ident_a),
            fam.live_res("r-gone", "u-sub", fam.ident_b),
        ]
        service = fam.service(_live_subnets(fam), live)
        yaml_res = [fam.reservation("keep", fam.ident_a)]
        managed = [fam.reservation("gone", fam.ident_b)]
        with fam.patched(fam.res_module, service):
            result = fam.res_mgr(tmp_path).apply(
                "dev",
                yaml_res,
                deletes_only=True,
                managed_resources=managed,
                sibling_resources=[fam.subnet("sub")],
                managed_sibling_resources=[fam.subnet("sub")],
            )
        assert result["resources_deleted"] == 1
        assert result["resources_created"] == 0
        assert result["resources_updated"] == 0
        getattr(service, f"delete_dhcpv{fam.v}_reservation").assert_called_once_with("r-gone")
        getattr(service, f"get_dhcpv{fam.v}_reservation").assert_not_called()
        getattr(service, f"add_dhcpv{fam.v}_reservation").assert_not_called()

    @FAMILIES
    def test_reservation_on_a_subnet_not_live_yet_does_not_raise(
        self, fam: Family, tmp_path: Path
    ) -> None:
        service = fam.service([], [])
        yaml_res = [fam.reservation("new", fam.ident_a, ref="fresh")]
        with fam.patched(fam.res_module, service):
            result = fam.res_mgr(tmp_path).apply(
                "dev",
                yaml_res,
                deletes_only=True,
                sibling_resources=[fam.subnet("fresh")],
            )
        assert result["resources_deleted"] == 0
        getattr(service, f"add_dhcpv{fam.v}_reservation").assert_not_called()


class TestReservationsKeptOnSubnets:
    @FAMILIES
    def test_classifies_yaml_managed_unmanaged_and_legacy(self, fam: Family) -> None:
        module = fam.res_module
        live = [
            fam.live_res("r-yaml", "u-sub", fam.ident_a),
            fam.live_res("r-managed", "u-sub", fam.ident_b),
            fam.live_res("r-hand", "u-sub", "hand"),
            fam.live_res("r-elsewhere", "u-other", "hand"),
        ]
        name_to_cidr = {"sub": fam.cidr}
        cidr_to_uuid = {fam.cidr: "u-sub"}
        kept = module.reservations_kept_on_subnets(
            live,
            {"u-sub"},
            yaml_reservations=[fam.reservation("y", fam.ident_a)],
            managed_reservations=[fam.reservation("m", fam.ident_b)],
            name_to_cidr=name_to_cidr,
            cidr_to_uuid=cidr_to_uuid,
        )
        assert set(kept) == {"u-sub"}
        assert kept["u-sub"] == [f"{fam.ident_a} 10.0.10.5", "hand 10.0.10.5"]

        legacy = module.reservations_kept_on_subnets(
            live,
            {"u-sub"},
            yaml_reservations=[fam.reservation("y", fam.ident_a)],
            managed_reservations=None,
            name_to_cidr=name_to_cidr,
            cidr_to_uuid=cidr_to_uuid,
        )
        assert legacy["u-sub"] == [f"{fam.ident_a} 10.0.10.5"]

    @FAMILIES
    def test_unresolvable_yaml_row_does_not_raise(self, fam: Family) -> None:
        kept = fam.res_module.reservations_kept_on_subnets(
            [fam.live_res("r", "u-sub", "hand")],
            {"u-sub"},
            yaml_reservations=[fam.reservation("bad", fam.ident_a, ref="nope")],
            managed_reservations=[],
            name_to_cidr={},
            cidr_to_uuid={fam.cidr: "u-sub"},
        )
        assert kept == {"u-sub": ["hand 10.0.10.5"]}


class TestSubnetPlanRefusal:
    @FAMILIES
    def test_unmanaged_reservation_blocks_the_delete(self, fam: Family, tmp_path: Path) -> None:
        service = fam.service(_live_subnets(fam), [fam.live_res("r-hand", "u-sub", "hand")])
        with fam.patched(fam.subnet_module, service):
            diff = fam.subnet_mgr(tmp_path).plan(
                "dev",
                [],
                managed_resources=[fam.subnet("sub")],
                dependent_resources=[],
                managed_dependent_resources=[],
            )
        assert diff.deletes == []
        assert diff.blocked == [("u-sub", fam.cidr, ["hand 10.0.10.5"])]
        assert diff.is_empty
        assert len(diff.warnings) == 1
        warning = diff.warnings[0]
        assert fam.cidr in warning
        assert "hand 10.0.10.5" in warning
        assert "1 reservation(s) InfraFoundry does not manage" in warning

    @FAMILIES
    def test_managed_reservations_missing_from_yaml_do_not_block(
        self, fam: Family, tmp_path: Path
    ) -> None:
        service = fam.service(_live_subnets(fam), [fam.live_res("r", "u-sub", fam.ident_b)])
        with fam.patched(fam.subnet_module, service):
            diff = fam.subnet_mgr(tmp_path).plan(
                "dev",
                [],
                managed_resources=[fam.subnet("sub")],
                dependent_resources=[],
                managed_dependent_resources=[fam.reservation("m", fam.ident_b)],
            )
        assert diff.deletes == [("u-sub", fam.cidr)]
        assert diff.blocked == []

    @FAMILIES
    def test_legacy_run_only_blocks_on_yaml_reservations(self, fam: Family, tmp_path: Path) -> None:
        live = [fam.live_res("r", "u-sub", fam.ident_b)]
        literal = ResourceConfig(
            name="lit",
            type=fam.res_type,
            provider="opnsense",
            config={"subnet": fam.cidr, fam.ident: fam.ident_a, "ip_address": "10.0.10.9"},
        )
        with fam.patched(fam.subnet_module, fam.service(_live_subnets(fam), live)):
            no_yaml = fam.subnet_mgr(tmp_path).plan("dev", [], dependent_resources=[])
        assert no_yaml.deletes == [("u-sub", fam.cidr)]
        live.append(fam.live_res("r2", "u-sub", fam.ident_a))
        with fam.patched(fam.subnet_module, fam.service(_live_subnets(fam), live)):
            with_yaml = fam.subnet_mgr(tmp_path).plan("dev", [], dependent_resources=[literal])
        assert with_yaml.deletes == []
        assert with_yaml.blocked[0][2] == [f"{fam.ident_a} 10.0.10.5"]


class TestSubnetDeletesOnlyApply:
    @FAMILIES
    def test_only_deletes_and_no_reads(self, fam: Family, tmp_path: Path) -> None:
        subnets = [
            {"subnet": fam.cidr, "uuid": "u-sub"},
            {"subnet": fam.other_cidr, "uuid": "u-old"},
        ]
        service = fam.service(subnets, [])
        yaml_subnet = ResourceConfig(
            name="sub",
            type=fam.subnet_type,
            provider="opnsense",
            config={"subnet": fam.cidr, "interface": "opt1"},
        )
        with fam.patched(fam.subnet_module, service):
            result = fam.subnet_mgr(tmp_path).apply(
                "dev",
                [yaml_subnet],
                deletes_only=True,
                managed_resources=[fam.subnet("old", fam.other_cidr)],
            )
        assert result["resources_deleted"] == 1
        assert result["warnings"] == []
        getattr(service, f"delete_dhcpv{fam.v}_subnet").assert_called_once_with("u-old")
        getattr(service, f"get_dhcpv{fam.v}_subnet").assert_not_called()
        getattr(service, f"add_dhcpv{fam.v}_subnet").assert_not_called()
        getattr(service, f"update_dhcpv{fam.v}_subnet").assert_not_called()
        getattr(service, f"ensure_dhcpv{fam.v}_enabled").assert_not_called()

    @FAMILIES
    def test_remaining_reservation_blocks_and_keeps_the_row_managed(
        self, fam: Family, tmp_path: Path
    ) -> None:
        service = fam.service(_live_subnets(fam), [fam.live_res("r-hand", "u-sub", "hand")])
        with fam.patched(fam.subnet_module, service):
            result = fam.subnet_mgr(tmp_path).apply(
                "dev", [], deletes_only=True, managed_resources=[fam.subnet("sub")]
            )
        assert result["resources_deleted"] == 0
        assert result["unresolved_managed"] == ["sub"]
        assert len(result["warnings"]) == 1
        getattr(service, f"delete_dhcpv{fam.v}_subnet").assert_not_called()

    @FAMILIES
    def test_add_only_neither_deletes_nor_searches_reservations(
        self, fam: Family, tmp_path: Path
    ) -> None:
        service = fam.service(_live_subnets(fam), [fam.live_res("r", "u-sub", "hand")])
        with fam.patched(fam.subnet_module, service):
            result = fam.subnet_mgr(tmp_path).apply(
                "dev", [], add_only=True, managed_resources=[fam.subnet("sub")]
            )
        assert result["resources_deleted"] == 0
        getattr(service, f"delete_dhcpv{fam.v}_subnet").assert_not_called()
        getattr(service, f"search_dhcpv{fam.v}_reservations").assert_not_called()


class TestSubnetDestroy:
    @FAMILIES
    def test_skips_a_subnet_that_still_has_reservations(self, fam: Family, tmp_path: Path) -> None:
        subnets = [
            {"subnet": fam.cidr, "uuid": "u-sub"},
            {"subnet": fam.other_cidr, "uuid": "u-free"},
        ]
        service = fam.service(subnets, [fam.live_res("r", "u-sub", "hand")])
        resources = [fam.subnet("a"), fam.subnet("b", fam.other_cidr)]
        with fam.patched(fam.subnet_module, service):
            result = fam.subnet_mgr(tmp_path).destroy("dev", resources)
        assert result["resources_destroyed"] == 1
        assert result["blocked_skipped"] == 1
        assert fam.cidr in result["warnings"][0]
        getattr(service, f"delete_dhcpv{fam.v}_subnet").assert_called_once_with("u-free")
