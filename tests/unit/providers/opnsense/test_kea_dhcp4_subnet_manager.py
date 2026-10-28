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
    _build_subnet_payload,
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
    return ResourceConfig(name=name, type="kea.dhcp4.subnets", provider="opnsense", config=config)


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
                        "option_data": {"domain_name_servers": "192.168.1.1"},
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
        # 26.1 wire shape: DHCP options nested under option_data (#1165).
        assert payload["option_data"]["domain_name_servers"] == "192.168.1.10,192.168.1.11"

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
                        "option_data": {"ntp_servers": "192.168.1.1"},
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
        assert payload["option_data"]["ntp_servers"] == "10.0.0.123"

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


def _selected(*values: str) -> dict[str, dict[str, Any]]:
    """Live option-dict shape for a multi-select option (as getSubnet returns it)."""
    return {v: {"value": v, "selected": 1} for v in values}


class TestOptionDataWireShape:
    """DHCP options go nested under option_data on 26.1 (#1165)."""

    def test_payload_nests_every_option_and_sends_no_flat_keys(self) -> None:
        payload = _build_subnet_payload(
            _subnet(
                "nettest-lan",
                routers=["192.168.99.1"],
                dns_servers=["192.168.10.1", "192.168.10.2"],
                ntp_servers=["192.168.99.1"],
                domain_search=["endavis.net"],
                domain_name="endavis.net",
            )
        )

        assert payload["option_data"] == {
            "routers": "192.168.99.1",
            "domain_name_servers": "192.168.10.1,192.168.10.2",
            "ntp_servers": "192.168.99.1",
            "domain_search": "endavis.net",
            "domain_name": "endavis.net",
        }
        assert not [
            k for k in payload if k.startswith("option_data_") and k != "option_data_autocollect"
        ]
        assert "domain_name" not in payload

    def test_payload_has_no_option_data_when_none_set(self) -> None:
        assert "option_data" not in _build_subnet_payload(_subnet("plain"))

    def test_missing_live_router_plans_an_update(self, tmp_path: Path) -> None:
        # The opnsense-test case: created through the API, routers left empty.
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.10.0/24", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "description": "vlan10 desc",
                        "option_data": {"routers": {"": {"value": "", "selected": 1}}},
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10", routers=["10.0.10.1"])])

        assert len(diff.updates) == 1
        assert diff.updates[0][1]["option_data"] == {"routers": "10.0.10.1"}

    def test_matching_live_options_need_no_update_in_any_order(self, tmp_path: Path) -> None:
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.10.0/24", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "interface": "opt1",
                        "description": "vlan10 desc",
                        "option_data": {
                            "routers": _selected("10.0.10.1"),
                            "domain_name_servers": _selected("10.0.10.2", "10.0.10.1"),
                            "domain_name": "lab.local",
                        },
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan(
                "test-env",
                [
                    _subnet(
                        "vlan10",
                        routers=["10.0.10.1"],
                        dns_servers=["10.0.10.2", "10.0.10.1"],
                        domain_name="lab.local",
                    )
                ],
            )

        assert diff.updates == []

    def test_option_not_set_in_yaml_is_not_drift(self, tmp_path: Path) -> None:
        # Prod subnets: options filled in the GUI, YAML relies on auto_collect.
        manager = KeaDHCPv4SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "10.0.10.0/24", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet4": {
                        "subnet": "10.0.10.0/24",
                        "interface": "opt1",
                        "description": "vlan10 desc",
                        "option_data": {
                            "routers": _selected("10.0.10.1"),
                            "domain_name_servers": _selected("10.0.10.1"),
                        },
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10")])

        assert diff.updates == []


class TestExportReadsDottedOptionKeys:
    """export_to_yaml reads the dotted option keys 26.1 search rows carry (#1165)."""

    def test_dhcpv4_options_survive_export(self) -> None:
        import yaml

        from infrafoundry.providers.opnsense.services.kea_dhcp import KeaDHCPService

        service = KeaDHCPService(MagicMock())
        # Shape of a live searchSubnet row on opnsense-a (192.168.20.0/24).
        row = {
            "subnet": "192.168.20.0/24",
            "description": "opt2 network",
            "pools": "192.168.20.100-192.168.20.199",
            "option_data_autocollect": "1",
            "option_data.routers": "192.168.20.1",
            "option_data.domain_name_servers": "192.168.20.1,192.168.10.1",
            "option_data.domain_name": "endavis.net",
            "option_data.ntp_servers": "192.168.20.1",
        }
        with (
            patch.object(service, "search_dhcpv4_subnets", return_value=[row]),
            patch.object(service, "search_dhcpv4_reservations", return_value=[]),
            patch.object(service, "search_dhcpv6_subnets", return_value=[]),
            patch.object(service, "search_dhcpv6_reservations", return_value=[]),
        ):
            doc = yaml.safe_load(service.export_to_yaml())

        [subnet] = doc["opnsense"]["kea"]["dhcp4"]["subnets"]
        assert subnet["config"]["routers"] == ["192.168.20.1"]
        assert subnet["config"]["dns_servers"] == ["192.168.20.1", "192.168.10.1"]
        assert subnet["config"]["domain_name"] == "endavis.net"
        assert subnet["config"]["ntp_servers"] == ["192.168.20.1"]
