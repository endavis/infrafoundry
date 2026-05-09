"""Unit tests for ``KeaDHCPv6ReservationManager`` (#758).

Coverage:
    - plan/apply/destroy delegate to KeaDHCPService correctly.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes.
    - apply does NOT call ``service.reconfigure`` directly (the runner
      fires the finalization hook).
    - get_resource_ids maps live UUIDs to operator-facing names.
    - The subnet UUID resolver raises ``ReferenceValidationError`` when
      a referenced subnet CIDR has no live match — a behavioral upgrade
      over the legacy silent-skip-with-warning path.
    - The ``FINALIZATION_HOOK`` ClassVar is the documented key.
    - add_only flag is honored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.kea_dhcp6_reservation import (
    KeaDHCPv6ReservationManager,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _reservation(
    name: str,
    *,
    subnet: str = "fd00:1::/64",
    duid: str = "00:01:00:01:2c:3d:00:01",
    ip_address: str = "fd00:1::10",
    hostname: str = "server1",
    description: str = "",
) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="kea.dhcp6.reservations",
        provider="opnsense",
        config={
            "subnet": subnet,
            "ip_address": ip_address,
            "duid": duid,
            "hostname": hostname,
            "description": description,
        },
    )


SERVICE_PATH = "infrafoundry.providers.opnsense.components.kea_dhcp6_reservation.KeaDHCPService"


def _make_service_mock(
    *,
    existing_subnets: list[dict[str, Any]] | None = None,
    existing_reservations: list[dict[str, Any]] | None = None,
    get_reservation_responses: dict[str, dict[str, Any]] | None = None,
    add_response: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a ``KeaDHCPService`` mock with sensible defaults."""
    service = MagicMock()
    service.search_dhcpv6_subnets.return_value = existing_subnets or []
    service.search_dhcpv6_reservations.return_value = existing_reservations or []
    if get_reservation_responses is not None:
        service.get_dhcpv6_reservation.side_effect = lambda uuid: get_reservation_responses.get(
            uuid, {"reservation": {}}
        )
    else:
        service.get_dhcpv6_reservation.return_value = {"reservation": {}}
    service.add_dhcpv6_reservation.return_value = add_response or {"result": "saved"}
    service.update_dhcpv6_reservation.return_value = {"result": "saved"}
    return service


# ---------------------------------------------------------------------------
# Class-level metadata
# ---------------------------------------------------------------------------


class TestFinalizationHook:
    """The manager declares the documented hook key (shared with the subnet manager)."""

    def test_class_attribute_is_kea_reconfigure(self) -> None:
        assert KeaDHCPv6ReservationManager.FINALIZATION_HOOK == "kea_reconfigure"


# ---------------------------------------------------------------------------
# Subnet UUID resolver semantics (the new behavior in #758)
# ---------------------------------------------------------------------------


class TestSubnetReferenceResolver:
    """The resolver raises ReferenceValidationError on missing live subnet."""

    def test_unknown_subnet_raises_reference_validation_error(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u1"}],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            with pytest.raises(ReferenceValidationError) as excinfo:
                manager.plan("test-env", [_reservation("server1-v6", subnet="fd00:99::/64")])
        assert "server1-v6" in str(excinfo.value)
        assert "fd00:99::/64" in str(excinfo.value)

    def test_known_subnet_resolves(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_reservation("server1-v6")])
        assert len(diff.adds) == 1
        # Reservation payload carries the resolved subnet UUID, not the CIDR.
        assert diff.adds[0]["subnet"] == "u-sub-1"


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_add_when_reservation_missing(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_reservation("server1-v6")])
        assert len(diff.adds) == 1
        assert diff.updates == []
        assert diff.deletes == []

    def test_plan_update_when_fields_differ(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:00:01",
                    "subnet": "u-sub-1",
                    "uuid": "u-res-1",
                }
            ],
            get_reservation_responses={
                "u-res-1": {
                    "reservation": {
                        "subnet": "u-sub-1",
                        "ip_address": "fd00:1::10",
                        "duid": "00:01:00:01:2c:3d:00:01",
                        "hostname": "server1-old",
                        "description": "",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_reservation("server1-v6", hostname="server1-new")])
        assert diff.adds == []
        assert len(diff.updates) == 1
        uuid, payload = diff.updates[0]
        assert uuid == "u-res-1"
        assert payload["hostname"] == "server1-new"

    def test_plan_no_change_when_fields_match(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:00:01",
                    "subnet": "u-sub-1",
                    "uuid": "u-res-1",
                }
            ],
            get_reservation_responses={
                "u-res-1": {
                    "reservation": {
                        "subnet": "u-sub-1",
                        "ip_address": "fd00:1::10",
                        "duid": "00:01:00:01:2c:3d:00:01",
                        "hostname": "server1",
                        "description": "",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_reservation("server1-v6")])
        assert diff.is_empty

    def test_plan_delete_when_live_reservation_not_in_yaml(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:99:99",
                    "subnet": "u-sub-1",
                    "uuid": "u-stale",
                }
            ],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [])
        assert len(diff.deletes) == 1
        live_uuid, descriptor = diff.deletes[0]
        assert live_uuid == "u-stale"
        assert descriptor == "00:01:00:01:2c:3d:99:99"

    def test_plan_add_only_suppresses_deletes(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:99:99",
                    "subnet": "u-sub-1",
                    "uuid": "u-stale",
                }
            ],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [], add_only=True)
        assert diff.deletes == []


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_creates_reservation_and_emits_outcome(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_reservation("server1-v6")])

        service.add_dhcpv6_reservation.assert_called_once()
        sent = service.add_dhcpv6_reservation.call_args.args[0]
        assert "__name__" not in sent
        assert sent["subnet"] == "u-sub-1"
        assert sent["ip_address"] == "fd00:1::10"

        assert result["resources_created"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "add"
        assert outcome.resource_name == "server1-v6"
        assert outcome.address == "opnsense_kea_dhcp6_reservation.server1-v6"
        # Reconfigure is the runner's responsibility, not the manager's.
        service.reconfigure.assert_not_called()

    def test_apply_updates_reservation_when_fields_differ(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:00:01",
                    "subnet": "u-sub-1",
                    "uuid": "u-res-1",
                }
            ],
            get_reservation_responses={
                "u-res-1": {
                    "reservation": {
                        "subnet": "u-sub-1",
                        "ip_address": "fd00:1::10",
                        "duid": "00:01:00:01:2c:3d:00:01",
                        "hostname": "server1-old",
                        "description": "",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_reservation("server1-v6", hostname="server1-new")])

        service.update_dhcpv6_reservation.assert_called_once()
        update_uuid, payload = service.update_dhcpv6_reservation.call_args.args
        assert update_uuid == "u-res-1"
        assert "__name__" not in payload
        assert payload["hostname"] == "server1-new"

        assert result["resources_updated"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "update"
        service.reconfigure.assert_not_called()

    def test_apply_deletes_reservation_not_in_yaml(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:99:99",
                    "subnet": "u-sub-1",
                    "uuid": "u-stale",
                }
            ],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [])
        service.delete_dhcpv6_reservation.assert_called_once_with("u-stale")
        assert result["resources_deleted"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "delete"
        assert outcome.resource_name == "reservation-00:01:00:01:2c:3d:99:99"
        service.reconfigure.assert_not_called()

    def test_apply_raises_on_unknown_subnet_reference(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            with pytest.raises(ReferenceValidationError):
                manager.apply(
                    "test-env",
                    [_reservation("server1-v6", subnet="fd00:99::/64")],
                )

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:99:99",
                    "subnet": "u-sub-1",
                    "uuid": "u-stale",
                }
            ],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [], add_only=True)
        service.delete_dhcpv6_reservation.assert_not_called()
        assert result["resources_deleted"] == 0


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_reservations(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:00:01",
                    "subnet": "u-sub-1",
                    "uuid": "u-res-1",
                }
            ],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.destroy("test-env", [_reservation("server1-v6")])
        service.delete_dhcpv6_reservation.assert_called_once_with("u-res-1")
        assert result["resources_destroyed"] == 1

    def test_destroy_skips_when_no_match(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.destroy("test-env", [_reservation("server1-v6")])
        service.delete_dhcpv6_reservation.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_raises_on_unknown_subnet_reference(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            with pytest.raises(ReferenceValidationError):
                manager.destroy(
                    "test-env",
                    [_reservation("server1-v6", subnet="fd00:99::/64")],
                )


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[
                {
                    "duid": "00:01:00:01:2c:3d:00:01",
                    "subnet": "u-sub-1",
                    "uuid": "u-res-1",
                }
            ],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.get_resource_ids("test-env", [_reservation("server1-v6")])
        assert result == {"server1-v6": "u-res-1"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6ReservationManager(tmp_path)
        service = _make_service_mock(
            existing_subnets=[{"subnet": "fd00:1::/64", "uuid": "u-sub-1"}],
            existing_reservations=[],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.get_resource_ids("test-env", [_reservation("server1-v6")])
        assert result == {}
