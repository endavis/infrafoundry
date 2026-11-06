"""Managed-set deletes through the component managers (#1256, ADR-0018).

Each manager gets ``managed_resources`` (the rows InfraFoundry applied before) and
deletes only matching live objects. The kea, host-alias and assignment managers
derive their keys from live lookups, so they are exercised against mocked services
wired to the real diff engines.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components import (
    kea_dhcp4_reservation,
    kea_dhcp4_subnet,
    kea_dhcp6_reservation,
    kea_dhcp6_subnet,
)
from infrafoundry.providers.opnsense.components.interface_assignment import (
    InterfaceAssignmentManager,
)
from infrafoundry.providers.opnsense.components.unbound_forward import UnboundForwardManager
from infrafoundry.providers.opnsense.components.unbound_host_alias import (
    UnboundHostAliasManager,
)
from infrafoundry.providers.opnsense.components.vlan import VlanManager
from infrafoundry.providers.opnsense.services import (
    interface_assignment as ifa_service,
)
from infrafoundry.providers.opnsense.services import unbound_forward as forward_service
from infrafoundry.providers.opnsense.services import unbound_host_alias as alias_service
from infrafoundry.providers.opnsense.services import vlan as vlan_service
from infrafoundry.providers.opnsense.services.interface_assignment import (
    ApplyDiffResult,
    LiveInterfaceAssignment,
)
from infrafoundry.providers.opnsense.services.unbound_host_alias import LiveUnboundHostAlias

COMPONENTS = "infrafoundry.providers.opnsense.components"


def _row(type_name: str, name: str, **config: Any) -> ResourceConfig:
    return ResourceConfig(name=name, type=type_name, provider="opnsense", config=config)


# ---------------------------------------------------------------------------
# Managers keyed by config alone
# ---------------------------------------------------------------------------


class TestConfigKeyedManagers:
    def test_all_declare_managed_set_scope(self) -> None:
        for manager in (
            VlanManager,
            UnboundForwardManager,
            UnboundHostAliasManager,
            InterfaceAssignmentManager,
            kea_dhcp4_subnet.KeaDHCPv4SubnetManager,
            kea_dhcp6_subnet.KeaDHCPv6SubnetManager,
            kea_dhcp4_reservation.KeaDHCPv4ReservationManager,
            kea_dhcp6_reservation.KeaDHCPv6ReservationManager,
        ):
            assert manager.DELETE_SCOPE == "managed_set"

    def test_forward_plan_deletes_only_managed(self, tmp_path: Path) -> None:
        live = [
            forward_service.LiveUnboundForward(
                uuid="u1", type="dot", domain="x.lan", server="1.1.1.1", port="853"
            ),
            forward_service.LiveUnboundForward(
                uuid="u2", type="dot", domain="hand.lan", server="9.9.9.9", port="853"
            ),
        ]
        service = MagicMock()
        service.search.return_value = live
        service.compute_diff.side_effect = forward_service.compute_diff
        managed = [
            _row("unbound.forwards", "f1", type="dot", domain="x.lan", server="1.1.1.1", port=853)
        ]
        with patch(f"{COMPONENTS}.unbound_forward.UnboundForwardService") as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = UnboundForwardManager(tmp_path).plan("env", [], managed_resources=managed)
        assert [d.uuid for d in diff.deletes] == ["u1"]
        assert [u.uuid for u in diff.unmanaged] == ["u2"]

    def test_forward_plan_without_managed_resources_is_legacy(self, tmp_path: Path) -> None:
        live = [
            forward_service.LiveUnboundForward(
                uuid="u2", type="dot", domain="hand.lan", server="9.9.9.9", port="853"
            )
        ]
        service = MagicMock()
        service.search.return_value = live
        service.compute_diff.side_effect = forward_service.compute_diff
        with patch(f"{COMPONENTS}.unbound_forward.UnboundForwardService") as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = UnboundForwardManager(tmp_path).plan("env", [])
        assert [d.uuid for d in diff.deletes] == ["u2"]
        assert diff.unmanaged == []

    def test_forward_apply_outcomes_cover_managed_deletes_only(self, tmp_path: Path) -> None:
        live = [
            forward_service.LiveUnboundForward(
                uuid="u1", type="dot", domain="x.lan", server="1.1.1.1", port="853"
            ),
            forward_service.LiveUnboundForward(
                uuid="u2", type="dot", domain="hand.lan", server="9.9.9.9", port="853"
            ),
        ]
        service = MagicMock()
        service.search.return_value = live
        service.compute_diff.side_effect = forward_service.compute_diff
        service.apply_diff.return_value = {"created": 0, "updated": 0, "deleted": 1}
        managed = [
            _row("unbound.forwards", "f1", type="dot", domain="x.lan", server="1.1.1.1", port=853)
        ]
        with patch(f"{COMPONENTS}.unbound_forward.UnboundForwardService") as svc_cls:
            svc_cls.from_environment.return_value = service
            result = UnboundForwardManager(tmp_path).apply("env", [], managed_resources=managed)
        assert [o.action for o in result["resource_outcomes"]] == ["delete"]
        applied = service.apply_diff.call_args.args[0]
        assert [d.uuid for d in applied.deletes] == ["u1"]

    def test_vlan_plan_deletes_only_managed(self, tmp_path: Path) -> None:
        live = [
            vlan_service.LiveVlan(uuid="v1", device="igb0", tag=10, description="", priority=0),
            vlan_service.LiveVlan(uuid="v2", device="igb0", tag=20, description="", priority=0),
        ]
        service = MagicMock()
        service.search.return_value = live
        service.compute_diff.side_effect = vlan_service.compute_diff
        managed = [
            _row("interfaces.vlans", "vlan10", device="igb0", tag=10, description="", priority=0)
        ]
        with patch(f"{COMPONENTS}.vlan.VlanService") as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = VlanManager(tmp_path).plan("env", [], managed_resources=managed)
        assert [d.uuid for d in diff.deletes] == ["v1"]
        assert [u.uuid for u in diff.unmanaged] == ["v2"]

    def test_apply_reports_unparseable_managed_rows_as_unresolved(self, tmp_path: Path) -> None:
        service = MagicMock()
        service.search.return_value = []
        service.compute_diff.side_effect = vlan_service.compute_diff
        service.apply_diff.return_value = {"created": 0, "updated": 0, "deleted": 0}
        managed = [_row("interfaces.vlans", "broken", tag="not-a-number")]
        with patch(f"{COMPONENTS}.vlan.VlanService") as svc_cls:
            svc_cls.from_environment.return_value = service
            result = VlanManager(tmp_path).apply("env", [], managed_resources=managed)
        assert result["unresolved_managed"] == ["broken"]

    def test_unparseable_managed_row_is_never_deleted(self, tmp_path: Path) -> None:
        live = [vlan_service.LiveVlan(uuid="v1", device="igb0", tag=10, description="", priority=0)]
        service = MagicMock()
        service.search.return_value = live
        service.compute_diff.side_effect = vlan_service.compute_diff
        managed = [_row("interfaces.vlans", "broken", tag="not-a-number")]
        with patch(f"{COMPONENTS}.vlan.VlanService") as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = VlanManager(tmp_path).plan("env", [], managed_resources=managed)
        assert diff.deletes == []
        assert [u.uuid for u in diff.unmanaged] == ["v1"]


# ---------------------------------------------------------------------------
# Kea subnets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("family", ["4", "6"])
class TestKeaSubnets:
    def _manager(self, family: str, tmp_path: Path) -> Any:
        module = kea_dhcp4_subnet if family == "4" else kea_dhcp6_subnet
        cls = module.KeaDHCPv4SubnetManager if family == "4" else module.KeaDHCPv6SubnetManager
        return cls(tmp_path), f"{COMPONENTS}.kea_dhcp{family}_subnet.KeaDHCPService"

    def _service(self, family: str, subnets: list[dict[str, Any]]) -> MagicMock:
        service = MagicMock()
        getattr(service, f"search_dhcpv{family}_subnets").return_value = subnets
        return service

    def _cidr(self, family: str, n: int) -> str:
        return f"10.0.{n}.0/24" if family == "4" else f"2001:db8:{n}::/64"

    def test_managed_cidr_deleted_and_unmanaged_kept(self, family: str, tmp_path: Path) -> None:
        manager, path = self._manager(family, tmp_path)
        mine, hand = self._cidr(family, 1), self._cidr(family, 2)
        service = self._service(
            family, [{"subnet": mine, "uuid": "u1"}, {"subnet": hand, "uuid": "u2"}]
        )
        managed = [_row(f"kea.dhcp{family}.subnets", "mine", subnet=mine)]
        with patch(path) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("env", [], managed_resources=managed)
        assert diff.deletes == [("u1", mine)]
        assert diff.unmanaged == [("u2", hand)]
        assert diff.is_empty is False

    def test_unmanaged_only_is_an_empty_diff(self, family: str, tmp_path: Path) -> None:
        manager, path = self._manager(family, tmp_path)
        hand = self._cidr(family, 2)
        service = self._service(family, [{"subnet": hand, "uuid": "u2"}])
        with patch(path) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("env", [], managed_resources=[])
        assert diff.deletes == []
        assert diff.is_empty is True
        assert diff.unmanaged == [("u2", hand)]

    def test_legacy_mode_still_deletes_everything_missing(
        self, family: str, tmp_path: Path
    ) -> None:
        manager, path = self._manager(family, tmp_path)
        hand = self._cidr(family, 2)
        service = self._service(family, [{"subnet": hand, "uuid": "u2"}])
        with patch(path) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("env", [])
        assert diff.deletes == [("u2", hand)]

    def test_apply_with_no_yaml_deletes_managed_without_enabling_service(
        self, family: str, tmp_path: Path
    ) -> None:
        manager, path = self._manager(family, tmp_path)
        mine, hand = self._cidr(family, 1), self._cidr(family, 2)
        service = self._service(
            family, [{"subnet": mine, "uuid": "u1"}, {"subnet": hand, "uuid": "u2"}]
        )
        managed = [_row(f"kea.dhcp{family}.subnets", "mine", subnet=mine)]
        with patch(path) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("env", [], managed_resources=managed)
        assert result["resources_deleted"] == 1
        getattr(service, f"delete_dhcpv{family}_subnet").assert_called_once_with("u1")
        getattr(service, f"ensure_dhcpv{family}_enabled").assert_not_called()


# ---------------------------------------------------------------------------
# Kea reservations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("family", ["4", "6"])
class TestKeaReservations:
    def _setup(
        self,
        family: str,
        tmp_path: Path,
        *,
        subnets: list[dict[str, Any]],
        reservations: list[dict[str, Any]],
    ) -> tuple[Any, MagicMock, str]:
        module = kea_dhcp4_reservation if family == "4" else kea_dhcp6_reservation
        cls = (
            module.KeaDHCPv4ReservationManager
            if family == "4"
            else module.KeaDHCPv6ReservationManager
        )
        service = MagicMock()
        getattr(service, f"search_dhcpv{family}_subnets").return_value = subnets
        getattr(service, f"search_dhcpv{family}_reservations").return_value = reservations
        return cls(tmp_path), service, f"{COMPONENTS}.kea_dhcp{family}_reservation.KeaDHCPService"

    def _id_field(self, family: str) -> str:
        return "hw_address" if family == "4" else "duid"

    def _live(self, family: str, uuid: str, ident: str, subnet_uuid: str) -> dict[str, Any]:
        return {"uuid": uuid, self._id_field(family): ident, "subnet": subnet_uuid}

    def _cidr(self, family: str) -> str:
        return "10.0.10.0/24" if family == "4" else "2001:db8:10::/64"

    def _managed(self, family: str, name: str, ident: str, **extra: Any) -> ResourceConfig:
        return _row(
            f"kea.dhcp{family}.reservations", name, **{self._id_field(family): ident}, **extra
        )

    def _plan(self, family: str, manager: Any, service: MagicMock, path: str, **kwargs: Any) -> Any:
        with patch(path) as svc_cls:
            svc_cls.from_environment.return_value = service
            return manager.plan("env", [], **kwargs)

    def test_managed_row_with_literal_subnet_is_deleted(self, family: str, tmp_path: Path) -> None:
        cidr = self._cidr(family)
        manager, service, path = self._setup(
            family,
            tmp_path,
            subnets=[{"subnet": cidr, "uuid": "s1"}],
            reservations=[
                self._live(family, "r1", "aa:01", "s1"),
                self._live(family, "r2", "aa:02", "s1"),
            ],
        )
        managed = [self._managed(family, "mine", "aa:01", subnet=cidr)]
        diff = self._plan(family, manager, service, path, managed_resources=managed)
        assert [d[0] for d in diff.deletes] == ["r1"]
        assert [u[0] for u in diff.unmanaged] == ["r2"]

    def test_managed_row_resolves_subnet_ref_through_managed_siblings(
        self, family: str, tmp_path: Path
    ) -> None:
        cidr = self._cidr(family)
        manager, service, path = self._setup(
            family,
            tmp_path,
            subnets=[{"subnet": cidr, "uuid": "s1"}],
            reservations=[self._live(family, "r1", "aa:01", "s1")],
        )
        managed = [self._managed(family, "mine", "aa:01", subnet_ref="lan")]
        siblings = [_row(f"kea.dhcp{family}.subnets", "lan", subnet=cidr)]
        diff = self._plan(
            family,
            manager,
            service,
            path,
            managed_resources=managed,
            managed_sibling_resources=siblings,
        )
        assert [d[0] for d in diff.deletes] == ["r1"]

    def test_same_identifier_in_another_subnet_is_kept(self, family: str, tmp_path: Path) -> None:
        cidr = self._cidr(family)
        manager, service, path = self._setup(
            family,
            tmp_path,
            subnets=[{"subnet": cidr, "uuid": "s1"}, {"subnet": "other", "uuid": "s2"}],
            reservations=[
                self._live(family, "r1", "aa:01", "s1"),
                self._live(family, "r2", "aa:01", "s2"),
            ],
        )
        managed = [self._managed(family, "mine", "aa:01", subnet=cidr)]
        diff = self._plan(family, manager, service, path, managed_resources=managed)
        assert [d[0] for d in diff.deletes] == ["r1"]
        assert [u[0] for u in diff.unmanaged] == ["r2"]

    def test_orphan_reservation_of_managed_row_with_unresolvable_subnet_is_deleted(
        self, family: str, tmp_path: Path
    ) -> None:
        manager, service, path = self._setup(
            family,
            tmp_path,
            subnets=[{"subnet": "live", "uuid": "s-live"}],
            reservations=[
                self._live(family, "orphan", "aa:01", "s-gone"),
                self._live(family, "elsewhere", "aa:01", "s-live"),
                self._live(family, "other-orphan", "aa:99", "s-gone"),
            ],
        )
        managed = [self._managed(family, "mine", "aa:01", subnet_ref="removed-subnet")]
        diff = self._plan(family, manager, service, path, managed_resources=managed)
        assert [d[0] for d in diff.deletes] == ["orphan"]
        assert sorted(u[0] for u in diff.unmanaged) == ["elsewhere", "other-orphan"]

    def test_unresolvable_row_without_orphan_match_deletes_nothing(
        self, family: str, tmp_path: Path
    ) -> None:
        manager, service, path = self._setup(
            family,
            tmp_path,
            subnets=[{"subnet": "live", "uuid": "s-live"}],
            reservations=[self._live(family, "r1", "aa:01", "s-live")],
        )
        managed = [self._managed(family, "mine", "aa:01", subnet_ref="removed-subnet")]
        diff = self._plan(family, manager, service, path, managed_resources=managed)
        assert diff.deletes == []
        assert [u[0] for u in diff.unmanaged] == ["r1"]

    def test_managed_row_without_identifier_is_skipped_with_warning(
        self, family: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        cidr = self._cidr(family)
        manager, service, path = self._setup(
            family,
            tmp_path,
            subnets=[{"subnet": cidr, "uuid": "s1"}],
            reservations=[self._live(family, "r1", "", "s1")],
        )
        managed = [_row(f"kea.dhcp{family}.reservations", "mine", subnet=cidr)]
        with caplog.at_level(logging.WARNING):
            diff = self._plan(family, manager, service, path, managed_resources=managed)
        assert diff.deletes == []
        assert "mine" in caplog.text

    def test_yaml_rows_still_raise_on_unknown_subnet(self, family: str, tmp_path: Path) -> None:
        manager, service, path = self._setup(
            family, tmp_path, subnets=[{"subnet": "live", "uuid": "s1"}], reservations=[]
        )
        yaml_row = self._managed(family, "y", "aa:01", subnet="nowhere")
        with patch(path) as svc_cls:
            svc_cls.from_environment.return_value = service
            with pytest.raises(ReferenceValidationError):
                manager.plan("env", [yaml_row], managed_resources=[])

    def test_apply_reports_fail_closed_rows_but_not_resolved_absent_ones(
        self, family: str, tmp_path: Path
    ) -> None:
        cidr = self._cidr(family)
        manager, service, path = self._setup(
            family,
            tmp_path,
            subnets=[{"subnet": cidr, "uuid": "s1"}],
            reservations=[self._live(family, "r-other", "aa:77", "s1")],
        )
        managed = [
            # Resolves to a key, but the object is already gone from the box.
            self._managed(family, "absent", "aa:01", subnet=cidr),
            # Subnet cannot be resolved and no orphan reservation matches.
            self._managed(family, "stuck", "aa:02", subnet_ref="removed-subnet"),
            # No identifier at all.
            _row(f"kea.dhcp{family}.reservations", "noid", subnet=cidr),
        ]
        with patch(path) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("env", [], managed_resources=managed)
        assert result["unresolved_managed"] == ["noid", "stuck"]
        assert result["resources_deleted"] == 0

    def test_legacy_mode_deletes_everything_missing(self, family: str, tmp_path: Path) -> None:
        manager, service, path = self._setup(
            family,
            tmp_path,
            subnets=[{"subnet": "live", "uuid": "s1"}],
            reservations=[self._live(family, "r1", "aa:01", "s1")],
        )
        diff = self._plan(family, manager, service, path)
        assert [d[0] for d in diff.deletes] == ["r1"]
        assert diff.unmanaged == []

    def test_apply_deletes_only_managed(self, family: str, tmp_path: Path) -> None:
        cidr = self._cidr(family)
        manager, service, path = self._setup(
            family,
            tmp_path,
            subnets=[{"subnet": cidr, "uuid": "s1"}],
            reservations=[
                self._live(family, "r1", "aa:01", "s1"),
                self._live(family, "r2", "aa:02", "s1"),
            ],
        )
        managed = [self._managed(family, "mine", "aa:01", subnet=cidr)]
        with patch(path) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("env", [], managed_resources=managed)
        assert result["resources_deleted"] == 1
        getattr(service, f"delete_dhcpv{family}_reservation").assert_called_once_with("r1")


# ---------------------------------------------------------------------------
# Unbound host aliases
# ---------------------------------------------------------------------------


def _live_alias(
    uuid: str, host_uuid: str, hostname: str, domain: str = "internal"
) -> LiveUnboundHostAlias:
    return LiveUnboundHostAlias(
        uuid=uuid,
        host_uuid=host_uuid,
        hostname=hostname,
        raw={"uuid": uuid, "host": host_uuid, "hostname": hostname, "domain": domain},
    )


def _alias_row(name: str, host: str, hostname: str) -> ResourceConfig:
    return _row("unbound.host_aliases", name, host=host, hostname=hostname, domain="internal")


class TestHostAliases:
    PATH = f"{COMPONENTS}.unbound_host_alias.UnboundHostAliasService"

    def _service(
        self, live: list[LiveUnboundHostAlias], overrides: list[dict[str, Any]]
    ) -> MagicMock:
        service = MagicMock()
        service.search.return_value = live
        service.search_host_overrides.return_value = overrides
        service.compute_diff.side_effect = alias_service.compute_diff
        service.apply_diff.return_value = {"created": 0, "updated": 0, "deleted": 0}
        return service

    def _plan(self, service: MagicMock, tmp_path: Path, **kwargs: Any) -> Any:
        with patch(self.PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            return UnboundHostAliasManager(tmp_path).plan("env", [], **kwargs)

    OVERRIDES: ClassVar[list[dict[str, Any]]] = [
        {"uuid": "p1", "hostname": "db-primary", "domain": "internal"}
    ]

    def test_managed_alias_with_live_parent_is_deleted(self, tmp_path: Path) -> None:
        service = self._service(
            [_live_alias("a1", "p1", "db"), _live_alias("a2", "p1", "hand")], self.OVERRIDES
        )
        diff = self._plan(
            service, tmp_path, managed_resources=[_alias_row("mine", "db-primary", "db")]
        )
        assert [d.uuid for d in diff.deletes] == ["a1"]
        assert [u.uuid for u in diff.unmanaged] == ["a2"]

    def test_unmanaged_alias_is_kept_with_empty_managed_set(self, tmp_path: Path) -> None:
        service = self._service([_live_alias("a2", "p1", "hand")], self.OVERRIDES)
        diff = self._plan(service, tmp_path, managed_resources=[])
        assert diff.deletes == []
        assert [u.uuid for u in diff.unmanaged] == ["a2"]

    def test_managed_alias_whose_parent_is_gone_matches_orphan_by_hostname(
        self, tmp_path: Path
    ) -> None:
        service = self._service(
            [
                _live_alias("orphan", "p-gone", "db"),
                _live_alias("attached", "p1", "db"),
                _live_alias("other-orphan", "p-gone", "web"),
            ],
            self.OVERRIDES,
        )
        diff = self._plan(
            service, tmp_path, managed_resources=[_alias_row("mine", "removed-host", "db")]
        )
        assert [d.uuid for d in diff.deletes] == ["orphan"]
        assert sorted(u.uuid for u in diff.unmanaged) == ["attached", "other-orphan"]

    def test_orphan_in_another_domain_is_not_matched(self, tmp_path: Path) -> None:
        service = self._service(
            [_live_alias("foreign", "p-gone", "db", domain="elsewhere")], self.OVERRIDES
        )
        diff = self._plan(
            service, tmp_path, managed_resources=[_alias_row("mine", "removed-host", "db")]
        )
        assert diff.deletes == []
        assert [u.uuid for u in diff.unmanaged] == ["foreign"]

    def test_ambiguous_orphan_match_deletes_nothing_and_stays_unresolved(
        self, tmp_path: Path
    ) -> None:
        service = self._service(
            [_live_alias("o1", "p-gone", "db"), _live_alias("o2", "p-gone2", "db")],
            self.OVERRIDES,
        )
        with patch(self.PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = UnboundHostAliasManager(tmp_path).apply(
                "env", [], managed_resources=[_alias_row("mine", "removed-host", "db")]
            )
        assert result["unresolved_managed"] == ["mine"]
        _, kwargs = service.compute_diff.call_args
        assert not kwargs.get("managed_keys")

    def test_unresolvable_row_without_orphan_is_skipped_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        service = self._service([_live_alias("a1", "p1", "db")], self.OVERRIDES)
        with caplog.at_level(logging.WARNING):
            diff = self._plan(
                service,
                tmp_path,
                managed_resources=[_alias_row("mine", "removed-host", "db")],
            )
        assert diff.deletes == []
        assert "mine" in caplog.text

    def test_yaml_alias_with_unknown_host_still_raises(self, tmp_path: Path) -> None:
        service = self._service([], self.OVERRIDES)
        with patch(self.PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            with pytest.raises(ReferenceValidationError):
                UnboundHostAliasManager(tmp_path).plan(
                    "env", [_alias_row("y", "nowhere", "x")], managed_resources=[]
                )

    def test_unparseable_managed_row_is_skipped(self, tmp_path: Path) -> None:
        service = self._service([_live_alias("a1", "p1", "db")], self.OVERRIDES)
        bad = _row("unbound.host_aliases", "bad")  # no host / hostname
        diff = self._plan(service, tmp_path, managed_resources=[bad])
        assert diff.deletes == []

    def test_legacy_mode_deletes_everything_missing(self, tmp_path: Path) -> None:
        service = self._service([_live_alias("a2", "p1", "hand")], self.OVERRIDES)
        diff = self._plan(service, tmp_path)
        assert [d.uuid for d in diff.deletes] == ["a2"]

    def test_apply_reports_fail_closed_rows_as_unresolved(self, tmp_path: Path) -> None:
        service = self._service([_live_alias("a1", "p1", "db")], self.OVERRIDES)
        managed = [
            _alias_row("resolved", "db-primary", "db"),
            _alias_row("stuck", "removed-host", "nomatch"),
            _row("unbound.host_aliases", "bad"),
        ]
        with patch(self.PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = UnboundHostAliasManager(tmp_path).apply("env", [], managed_resources=managed)
        assert result["unresolved_managed"] == ["bad", "stuck"]

    def test_apply_uses_the_managed_keys(self, tmp_path: Path) -> None:
        service = self._service([_live_alias("a1", "p1", "db")], self.OVERRIDES)
        service.apply_diff.return_value = {"created": 0, "updated": 0, "deleted": 1}
        with patch(self.PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = UnboundHostAliasManager(tmp_path).apply(
                "env", [], managed_resources=[_alias_row("mine", "db-primary", "db")]
            )
        assert result["resources_deleted"] == 1
        assert [d.uuid for d in service.apply_diff.call_args.args[0].deletes] == ["a1"]


# ---------------------------------------------------------------------------
# Interface assignments
# ---------------------------------------------------------------------------


def _live_ifa(identifier: str) -> LiveInterfaceAssignment:
    return LiveInterfaceAssignment(
        identifier=identifier,
        device=f"dev-{identifier}",
        description="",
        is_physical=True,
        ipv4={},
        ipv6={},
        macaddr="",
        mtu=1500,
    )


class TestInterfaceAssignments:
    PATH = f"{COMPONENTS}.interface_assignment.InterfaceAssignmentService"
    INSTALLER = f"{COMPONENTS}.interface_assignment.installer"

    def _service(self, live: list[LiveInterfaceAssignment]) -> MagicMock:
        service = MagicMock()
        service.list.return_value = live
        service.compute_diff.side_effect = ifa_service.compute_diff
        service.apply_diff.return_value = ApplyDiffResult(deleted=1)
        return service

    def _managed(self, *names: str) -> list[ResourceConfig]:
        return [_row("interfaces.assignments", n, device=f"dev-{n}") for n in names]

    def test_managed_opt3_is_deleted_and_lan_wan_are_not(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        service = self._service([_live_ifa("lan"), _live_ifa("wan"), _live_ifa("opt3")])
        with patch(self.PATH) as svc_cls, caplog.at_level(logging.WARNING):
            svc_cls.from_environment.return_value = service
            diff = InterfaceAssignmentManager(tmp_path).plan(
                "env", [], managed_resources=self._managed("lan", "wan", "opt3")
            )
        assert [d.identifier for d in diff.deletes] == ["opt3"]
        assert {u.identifier for u in diff.unmanaged} == {"lan", "wan"}
        assert "lan" in caplog.text

    def test_unmanaged_assignment_is_kept(self, tmp_path: Path) -> None:
        service = self._service([_live_ifa("opt3")])
        with patch(self.PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = InterfaceAssignmentManager(tmp_path).plan("env", [], managed_resources=[])
        assert diff.deletes == []

    def test_apply_without_yaml_lists_then_installs_then_writes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPNSENSE_API_URL", "https://fw-prod")
        order: list[str] = []
        service = self._service([_live_ifa("opt3")])

        def _list() -> list[LiveInterfaceAssignment]:
            order.append("list")
            return [_live_ifa("opt3")]

        def _apply_diff(_diff: Any) -> ApplyDiffResult:
            order.append("apply_diff")
            return ApplyDiffResult(deleted=1)

        service.list.side_effect = _list
        service.apply_diff.side_effect = _apply_diff
        with patch(self.PATH) as svc_cls, patch(self.INSTALLER) as installer:
            installer.ensure_installed.side_effect = lambda: order.append("install")
            svc_cls.from_environment.return_value = service
            result = InterfaceAssignmentManager(tmp_path).apply(
                "env", [], managed_resources=self._managed("opt3")
            )
        assert order == ["list", "install", "apply_diff"]
        assert result["resources_deleted"] == 1

    def _no_ssh(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in (
            "OPNSENSE_API_URL",
            "OPNSENSE_SSH_HOST",
            "OPNSENSE_SSH_KEY",
            "OPNSENSE_SSH_USER",
        ):
            monkeypatch.delenv(var, raising=False)

    def test_apply_with_nothing_to_write_succeeds_without_ssh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._no_ssh(monkeypatch)
        service = self._service([])
        with patch(self.PATH) as svc_cls, patch(self.INSTALLER) as installer:
            svc_cls.from_environment.return_value = service
            InterfaceAssignmentManager(tmp_path).apply("env", [], managed_resources=[])
        installer.ensure_installed.assert_not_called()

    def test_apply_without_ssh_credentials_fails_before_any_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for var in (
            "OPNSENSE_API_URL",
            "OPNSENSE_SSH_HOST",
            "OPNSENSE_SSH_KEY",
            "OPNSENSE_SSH_USER",
        ):
            monkeypatch.delenv(var, raising=False)
        service = self._service([_live_ifa("opt3")])
        with patch(self.PATH) as svc_cls, patch(self.INSTALLER):
            svc_cls.from_environment.return_value = service
            with pytest.raises(RuntimeError):
                InterfaceAssignmentManager(tmp_path).apply(
                    "env", [], managed_resources=self._managed("opt3")
                )
        service.apply_diff.assert_not_called()
