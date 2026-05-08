"""Unit tests for ``KeaDHCPv4SubnetManager`` (#777).

Coverage:
    - plan/apply/destroy delegate to KeaDHCPService correctly.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes.
    - apply does NOT call ``service.reconfigure`` directly (the runner
      fires the finalization hook instead).
    - DNS / NTP drift on existing subnets is detected as an update (the
      cutover-regression case from the prod migration plan).
    - get_resource_ids maps live UUIDs to operator-facing names.
    - add_only flag is honored (no deletes when it's set).
    - ``ensure_dhcpv4_enabled`` is invoked with the union of interfaces
      across all subnet resources.
    - The ``FINALIZATION_HOOK`` ClassVar is the documented key
      (``"kea_reconfigure"``, shared with the DHCPv4 reservation
      manager and both DHCPv6 managers).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.kea_dhcp4_subnet import (
    KeaDHCPv4SubnetManager,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _subnet(name: str, *, subnet: str = "10.0.10.0/24", **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "subnet": subnet,
        "interface": overrides.pop("interface", "opt1"),
        "description": overrides.pop("description", f"{name} desc"),
    }
    config.update(overrides)
    return ResourceConfig(name=name, type="kea_subnet", provider="opnsense", config=config)


SERVICE_PATH = "infrafoundry.providers.opnsense.components.kea_dhcp4_subnet.KeaDHCPService"


def _make_service_mock(
    *,
    existing: list[dict[str, Any]] | None = None,
    get_responses: dict[str, dict[str, Any]] | None = None,
    add_response: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a ``KeaDHCPService`` mock with sensible defaults."""
    service = MagicMock()
    service.search_dhcpv4_subnets.return_value = existing or []
    if get_responses is not None:
        service.get_dhcpv4_subnet.side_effect = lambda uuid: get_responses.get(
            uuid, {"subnet4": {}}
        )
    else:
        service.get_dhcpv4_subnet.return_value = {"subnet4": {}}
    service.add_dhcpv4_subnet.return_value = add_response or {"result": "saved"}
    service.update_dhcpv4_subnet.return_value = {"result": "saved"}
    return service


# ---------------------------------------------------------------------------
# Class-level metadata
# ---------------------------------------------------------------------------


class TestFinalizationHook:
    """The manager declares the documented hook key."""

    def test_class_attribute_is_kea_reconfigure(self) -> None:
        assert KeaDHCPv4SubnetManager.FINALIZATION_HOOK == "kea_reconfigure"


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_add_when_subnet_missing(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(existing=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10")])
        assert len(diff.adds) == 1
        assert diff.updates == []
        assert diff.deletes == []
        assert not diff.is_empty

    def test_plan_update_when_fields_differ(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.10.0/24", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "interface": "opt1",
                        "description": "old desc",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10", description="new desc")])
        assert diff.adds == []
        assert len(diff.updates) == 1
        uuid, payload = diff.updates[0]
        assert uuid == "u1"
        assert payload["description"] == "new desc"
        assert payload["__name__"] == "vlan10"

    def test_plan_update_when_dns_servers_differ_cutover_regression(self, tmp_path: Path) -> None:
        """Cutover-regression case: DNS server drift detected as an update.

        The 2026-05-08 prod cutover plan listed 7 DNS/NTP-only changes on
        existing subnets that the legacy terraform path captured cleanly.
        After migrating to direct-API the diff engine must detect the same
        drift and emit a single update per subnet (not delete+add).
        """
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.10.0/24", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "interface": "opt1",
                        "description": "vlan10 desc",
                        "option_data_dns_servers": "192.168.1.1",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            # Operator updates DNS servers (e.g., points at new resolvers).
            diff = manager.plan(
                "test-env",
                [_subnet("vlan10", dns_servers=["192.168.1.10", "192.168.1.11"])],
            )
        assert diff.adds == []
        assert len(diff.updates) == 1
        uuid, payload = diff.updates[0]
        assert uuid == "u1"
        # DHCPv4 wire shape: flat option_data_dns_servers, not nested.
        assert payload["option_data_dns_servers"] == "192.168.1.10,192.168.1.11"

    def test_plan_update_when_ntp_servers_differ_cutover_regression(self, tmp_path: Path) -> None:
        """Cutover-regression case: NTP server drift detected as an update."""
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.10.0/24", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "interface": "opt1",
                        "description": "vlan10 desc",
                        "option_data_ntp_servers": "192.168.1.1",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan(
                "test-env",
                [_subnet("vlan10", ntp_servers=["10.0.0.123"])],
            )
        assert diff.adds == []
        assert len(diff.updates) == 1
        _, payload = diff.updates[0]
        assert payload["option_data_ntp_servers"] == "10.0.0.123"

    def test_plan_no_change_when_fields_match(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.10.0/24", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "interface": "opt1",
                        "description": "vlan10 desc",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10")])
        assert diff.is_empty

    def test_plan_delete_when_live_subnet_not_in_yaml(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[
                {"subnet": "10.0.10.0/24", "uuid": "u1"},
                {"subnet": "10.0.99.0/24", "uuid": "u9"},
            ],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "interface": "opt1",
                        "description": "vlan10 desc",
                    }
                },
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10")])
        assert len(diff.deletes) == 1
        uuid, addr = diff.deletes[0]
        assert uuid == "u9"
        assert addr == "10.0.99.0/24"

    def test_plan_add_only_suppresses_deletes(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[
                {"subnet": "10.0.10.0/24", "uuid": "u1"},
                {"subnet": "10.0.99.0/24", "uuid": "u9"},
            ],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "interface": "opt1",
                        "description": "vlan10 desc",
                    }
                },
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10")], add_only=True)
        assert diff.deletes == []
        assert diff.is_empty


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_creates_subnet_and_emits_outcome(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(existing=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_subnet("vlan10")])

        service.add_dhcpv4_subnet.assert_called_once()
        # Outgoing payload: subnet/interface/description, no leaked __name__.
        sent = service.add_dhcpv4_subnet.call_args.args[0]
        assert "__name__" not in sent
        assert sent["subnet"] == "10.0.10.0/24"

        assert result["resources_created"] == 1
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "add"
        assert outcomes[0].resource_name == "vlan10"
        assert outcomes[0].address == "opnsense_kea_subnet.vlan10"
        # The reconfigure call lives on the runner's finalization hook,
        # not on the manager — verify the manager doesn't fire it directly.
        service.reconfigure.assert_not_called()

    def test_apply_updates_subnet_when_fields_differ(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.10.0/24", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "interface": "opt1",
                        "description": "old desc",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_subnet("vlan10", description="new desc")])

        service.update_dhcpv4_subnet.assert_called_once()
        update_uuid, update_payload = service.update_dhcpv4_subnet.call_args.args
        assert update_uuid == "u1"
        assert "__name__" not in update_payload
        assert update_payload["description"] == "new desc"

        assert result["resources_updated"] == 1
        outcomes = result["resource_outcomes"]
        assert outcomes[0].action == "update"
        assert outcomes[0].resource_name == "vlan10"
        service.reconfigure.assert_not_called()

    def test_apply_deletes_subnet_not_in_yaml(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[
                {"subnet": "10.0.10.0/24", "uuid": "u1"},
                {"subnet": "10.0.99.0/24", "uuid": "u9"},
            ],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "interface": "opt1",
                        "description": "vlan10 desc",
                    }
                },
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_subnet("vlan10")])

        service.delete_dhcpv4_subnet.assert_called_once_with("u9")
        assert result["resources_deleted"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "delete"
        assert outcome.resource_name == "subnet-10.0.99.0/24"
        service.reconfigure.assert_not_called()

    def test_apply_calls_ensure_dhcpv4_enabled_with_sorted_interfaces(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(existing=[])
        resources = [
            _subnet("vlan10", subnet="10.0.10.0/24", interface="opt2"),
            _subnet("vlan20", subnet="10.0.20.0/24", interface="opt1"),
        ]
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            manager.apply("test-env", resources)
        service.ensure_dhcpv4_enabled.assert_called_once_with(["opt1", "opt2"])

    def test_apply_skips_ensure_dhcpv4_enabled_when_no_interfaces(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(existing=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            # An empty resource list means no interfaces — no enable call.
            manager.apply("test-env", [])
        service.ensure_dhcpv4_enabled.assert_not_called()

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.99.0/24", "uuid": "u9"}],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [], add_only=True)
        # add_only suppresses the otherwise-implied delete of u9.
        service.delete_dhcpv4_subnet.assert_not_called()
        assert result["resources_deleted"] == 0

    def test_apply_idempotent_no_changes_on_reapply(self, tmp_path: Path) -> None:
        """Re-applying a no-change YAML produces 0/0/0 (the round-trip property)."""
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.10.0/24", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "interface": "opt1",
                        "description": "vlan10 desc",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_subnet("vlan10")])
        assert result["resources_created"] == 0
        assert result["resources_updated"] == 0
        assert result["resources_deleted"] == 0


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_subnets(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.10.0/24", "uuid": "u1"}],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.destroy("test-env", [_subnet("vlan10")])
        service.delete_dhcpv4_subnet.assert_called_once_with("u1")
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0

    def test_destroy_skips_when_no_match(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(existing=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.destroy("test-env", [_subnet("vlan10")])
        service.delete_dhcpv4_subnet.assert_not_called()
        assert result["resources_destroyed"] == 0


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[
                {"subnet": "10.0.10.0/24", "uuid": "u1"},
                {"subnet": "10.0.20.0/24", "uuid": "u2"},
            ],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.get_resource_ids(
                "test-env",
                [
                    _subnet("vlan10", subnet="10.0.10.0/24"),
                    _subnet("vlan20", subnet="10.0.20.0/24"),
                ],
            )
        assert result == {"vlan10": "u1", "vlan20": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.10.0/24", "uuid": "u1"}],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.get_resource_ids(
                "test-env",
                [
                    _subnet("vlan10", subnet="10.0.10.0/24"),
                    _subnet("vlan99", subnet="10.0.99.0/24"),
                ],
            )
        assert result == {"vlan10": "u1"}
