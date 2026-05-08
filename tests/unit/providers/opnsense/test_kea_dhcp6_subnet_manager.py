"""Unit tests for ``KeaDHCPv6SubnetManager`` (#758).

Coverage:
    - plan/apply/destroy delegate to KeaDHCPService correctly.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes.
    - apply does NOT call ``service.reconfigure`` directly (the runner
      fires the finalization hook instead).
    - get_resource_ids maps live UUIDs to operator-facing names.
    - add_only flag is honored (no deletes when it's set).
    - ``ensure_dhcpv6_enabled`` is invoked with the union of interfaces
      across all subnet resources.
    - The ``FINALIZATION_HOOK`` ClassVar is the documented key.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.kea_dhcp6_subnet import (
    KeaDHCPv6SubnetManager,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _subnet(name: str, *, subnet: str = "fd00:1::/64", **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "subnet": subnet,
        "interface": overrides.pop("interface", "opt1"),
        "description": overrides.pop("description", f"{name} desc"),
    }
    config.update(overrides)
    return ResourceConfig(name=name, type="kea.dhcp6.subnets", provider="opnsense", config=config)


SERVICE_PATH = "infrafoundry.providers.opnsense.components.kea_dhcp6_subnet.KeaDHCPService"


def _make_service_mock(
    *,
    existing: list[dict[str, Any]] | None = None,
    get_responses: dict[str, dict[str, Any]] | None = None,
    add_response: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a ``KeaDHCPService`` mock with sensible defaults."""
    service = MagicMock()
    service.search_dhcpv6_subnets.return_value = existing or []
    if get_responses is not None:
        service.get_dhcpv6_subnet.side_effect = lambda uuid: get_responses.get(
            uuid, {"subnet6": {}}
        )
    else:
        service.get_dhcpv6_subnet.return_value = {"subnet6": {}}
    service.add_dhcpv6_subnet.return_value = add_response or {"result": "saved"}
    service.update_dhcpv6_subnet.return_value = {"result": "saved"}
    return service


# ---------------------------------------------------------------------------
# Class-level metadata
# ---------------------------------------------------------------------------


class TestFinalizationHook:
    """The manager declares the documented hook key."""

    def test_class_attribute_is_kea_reconfigure(self) -> None:
        assert KeaDHCPv6SubnetManager.FINALIZATION_HOOK == "kea_reconfigure"


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_add_when_subnet_missing(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(existing=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10-v6")])
        assert len(diff.adds) == 1
        assert diff.updates == []
        assert diff.deletes == []
        assert not diff.is_empty

    def test_plan_update_when_fields_differ(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "fd00:1::/64", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": "opt1",
                        "description": "old desc",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10-v6", description="new desc")])
        assert diff.adds == []
        assert len(diff.updates) == 1
        uuid, payload = diff.updates[0]
        assert uuid == "u1"
        assert payload["description"] == "new desc"
        assert payload["__name__"] == "vlan10-v6"

    def test_plan_no_change_when_fields_match(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "fd00:1::/64", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": "opt1",
                        "description": "vlan10-v6 desc",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10-v6")])
        assert diff.is_empty

    def test_plan_delete_when_live_subnet_not_in_yaml(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[
                {"subnet": "fd00:1::/64", "uuid": "u1"},
                {"subnet": "fd00:9::/64", "uuid": "u9"},
            ],
            get_responses={
                "u1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": "opt1",
                        "description": "vlan10-v6 desc",
                    }
                },
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10-v6")])
        assert len(diff.deletes) == 1
        uuid, addr = diff.deletes[0]
        assert uuid == "u9"
        assert addr == "fd00:9::/64"

    def test_plan_add_only_suppresses_deletes(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[
                {"subnet": "fd00:1::/64", "uuid": "u1"},
                {"subnet": "fd00:9::/64", "uuid": "u9"},
            ],
            get_responses={
                "u1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": "opt1",
                        "description": "vlan10-v6 desc",
                    }
                },
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_subnet("vlan10-v6")], add_only=True)
        assert diff.deletes == []
        assert diff.is_empty


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_creates_subnet_and_emits_outcome(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(existing=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_subnet("vlan10-v6")])

        service.add_dhcpv6_subnet.assert_called_once()
        # Outgoing payload: subnet/interface/description, no leaked __name__.
        sent = service.add_dhcpv6_subnet.call_args.args[0]
        assert "__name__" not in sent
        assert sent["subnet"] == "fd00:1::/64"

        assert result["resources_created"] == 1
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "add"
        assert outcomes[0].resource_name == "vlan10-v6"
        assert outcomes[0].address == "opnsense_kea_dhcp6_subnet.vlan10-v6"
        # The reconfigure call lives on the runner's finalization hook,
        # not on the manager — verify the manager doesn't fire it directly.
        service.reconfigure.assert_not_called()

    def test_apply_updates_subnet_when_fields_differ(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "fd00:1::/64", "uuid": "u1"}],
            get_responses={
                "u1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": "opt1",
                        "description": "old desc",
                    }
                }
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_subnet("vlan10-v6", description="new desc")])

        service.update_dhcpv6_subnet.assert_called_once()
        update_uuid, update_payload = service.update_dhcpv6_subnet.call_args.args
        assert update_uuid == "u1"
        assert "__name__" not in update_payload
        assert update_payload["description"] == "new desc"

        assert result["resources_updated"] == 1
        outcomes = result["resource_outcomes"]
        assert outcomes[0].action == "update"
        assert outcomes[0].resource_name == "vlan10-v6"
        service.reconfigure.assert_not_called()

    def test_apply_deletes_subnet_not_in_yaml(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[
                {"subnet": "fd00:1::/64", "uuid": "u1"},
                {"subnet": "fd00:9::/64", "uuid": "u9"},
            ],
            get_responses={
                "u1": {
                    "subnet6": {
                        "subnet": "fd00:1::/64",
                        "interface": "opt1",
                        "description": "vlan10-v6 desc",
                    }
                },
            },
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_subnet("vlan10-v6")])

        service.delete_dhcpv6_subnet.assert_called_once_with("u9")
        assert result["resources_deleted"] == 1
        outcome = result["resource_outcomes"][0]
        assert outcome.action == "delete"
        assert outcome.resource_name == "subnet-fd00:9::/64"
        service.reconfigure.assert_not_called()

    def test_apply_calls_ensure_dhcpv6_enabled_with_sorted_interfaces(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(existing=[])
        resources = [
            _subnet("vlan10-v6", subnet="fd00:1::/64", interface="opt2"),
            _subnet("vlan20-v6", subnet="fd00:2::/64", interface="opt1"),
        ]
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            manager.apply("test-env", resources)
        service.ensure_dhcpv6_enabled.assert_called_once_with(["opt1", "opt2"])

    def test_apply_skips_ensure_dhcpv6_enabled_when_no_interfaces(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(existing=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            # An empty resource list means no interfaces — no enable call.
            manager.apply("test-env", [])
        service.ensure_dhcpv6_enabled.assert_not_called()

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "fd00:9::/64", "uuid": "u9"}],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [], add_only=True)
        # add_only suppresses the otherwise-implied delete of u9.
        service.delete_dhcpv6_subnet.assert_not_called()
        assert result["resources_deleted"] == 0


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_subnets(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "fd00:1::/64", "uuid": "u1"}],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.destroy("test-env", [_subnet("vlan10-v6")])
        service.delete_dhcpv6_subnet.assert_called_once_with("u1")
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0

    def test_destroy_skips_when_no_match(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(existing=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.destroy("test-env", [_subnet("vlan10-v6")])
        service.delete_dhcpv6_subnet.assert_not_called()
        assert result["resources_destroyed"] == 0


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[
                {"subnet": "fd00:1::/64", "uuid": "u1"},
                {"subnet": "fd00:2::/64", "uuid": "u2"},
            ],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.get_resource_ids(
                "test-env",
                [
                    _subnet("vlan10-v6", subnet="fd00:1::/64"),
                    _subnet("vlan20-v6", subnet="fd00:2::/64"),
                ],
            )
        assert result == {"vlan10-v6": "u1", "vlan20-v6": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = KeaDHCPv6SubnetManager(tmp_path)
        service = _make_service_mock(
            existing=[{"subnet": "fd00:1::/64", "uuid": "u1"}],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.get_resource_ids(
                "test-env",
                [
                    _subnet("vlan10-v6", subnet="fd00:1::/64"),
                    _subnet("vlan99-v6", subnet="fd00:99::/64"),
                ],
            )
        assert result == {"vlan10-v6": "u1"}
