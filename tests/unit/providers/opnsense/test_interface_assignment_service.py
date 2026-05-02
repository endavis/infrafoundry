"""Unit tests for ``infrafoundry.providers.opnsense.services.interface_assignment``.

Coverage:
    - ``LiveInterfaceAssignment`` dataclass invariants.
    - ``InterfaceAssignmentConfig`` parsing from ``ResourceConfig`` (forward-compat
      schema; ``ipv4``/``ipv6``/``enabled``/``lock`` accepted).
    - ``InterfaceAssignmentService.list()`` against a mocked API client:
      skips rows with empty ``identifier``, parses ``is_physical``/``mtu``,
      passes ``ipv4``/``ipv6`` through.
    - ``export_to_yaml()`` round-trip.
    - ``_row_to_live_assignment`` defensive coercion.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.interface_assignment import (
    InterfaceAssignmentConfig,
    InterfaceAssignmentService,
    LiveInterfaceAssignment,
    _row_to_live_assignment,
    interface_assignment_configs_from_resources,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(
    identifier: str = "lan",
    device: str = "ixl1",
    *,
    description: str = "",
    is_physical: bool = True,
    ipv4: dict[str, Any] | None = None,
    ipv6: dict[str, Any] | None = None,
    macaddr: str = "00:11:22:33:44:55",
    mtu: int | str = 1500,
) -> dict[str, Any]:
    return {
        "identifier": identifier,
        "device": device,
        "description": description,
        "is_physical": is_physical,
        "ipv4": ipv4 if ipv4 is not None else {},
        "ipv6": ipv6 if ipv6 is not None else {},
        "macaddr": macaddr,
        "mtu": mtu,
    }


def _resource(
    name: str,
    *,
    device: str = "ixl1",
    description: str = "",
    enabled: bool | None = None,
    lock: bool | None = None,
    ipv4: dict[str, Any] | None = None,
    ipv6: dict[str, Any] | None = None,
) -> ResourceConfig:
    config: dict[str, Any] = {"device": device, "description": description}
    if enabled is not None:
        config["enabled"] = enabled
    if lock is not None:
        config["lock"] = lock
    if ipv4 is not None:
        config["ipv4"] = ipv4
    if ipv6 is not None:
        config["ipv6"] = ipv6
    return ResourceConfig(
        name=name, type="interface_assignments", provider="opnsense", config=config
    )


# ---------------------------------------------------------------------------
# Dataclass invariants
# ---------------------------------------------------------------------------


class TestLiveInterfaceAssignment:
    def test_frozen_dataclass(self) -> None:
        live = LiveInterfaceAssignment(
            identifier="lan",
            device="ixl1",
            description="LAN",
            is_physical=True,
            ipv4={},
            ipv6={},
            macaddr="aa:bb:cc:dd:ee:ff",
            mtu=1500,
        )
        with pytest.raises(Exception):  # frozen — any attribute write fails  # noqa: B017
            live.identifier = "wan"  # type: ignore[misc]


class TestInterfaceAssignmentConfigDefaults:
    def test_defaults(self) -> None:
        cfg = InterfaceAssignmentConfig(name="lan", device="ixl1", description="")
        assert cfg.enabled is True
        assert cfg.lock is False
        assert cfg.ipv4 == {}
        assert cfg.ipv6 == {}


# ---------------------------------------------------------------------------
# interface_assignment_configs_from_resources
# ---------------------------------------------------------------------------


class TestConfigsFromResources:
    def test_minimal_resource_parses(self) -> None:
        result = interface_assignment_configs_from_resources([_resource("lan")])
        assert len(result) == 1
        assert result[0].name == "lan"
        assert result[0].device == "ixl1"
        assert result[0].description == ""
        assert result[0].enabled is True
        assert result[0].lock is False

    def test_non_matching_resources_ignored(self) -> None:
        ifa = _resource("lan")
        alias = ResourceConfig(name="a", type="aliases", provider="opnsense", config={})
        result = interface_assignment_configs_from_resources([ifa, alias])
        assert len(result) == 1
        assert result[0].name == "lan"

    def test_forward_compat_fields_accepted(self) -> None:
        result = interface_assignment_configs_from_resources(
            [
                _resource(
                    "lan",
                    enabled=False,
                    lock=True,
                    ipv4={"mode": "static", "address": "10.0.0.1/24"},
                    ipv6={"mode": "track6"},
                )
            ]
        )
        cfg = result[0]
        assert cfg.enabled is False
        assert cfg.lock is True
        assert cfg.ipv4["mode"] == "static"
        assert cfg.ipv6["mode"] == "track6"

    def test_missing_device_rejected(self) -> None:
        bad = ResourceConfig(
            name="lan",
            type="interface_assignments",
            provider="opnsense",
            config={"description": "lan"},
        )
        with pytest.raises(ValueError, match="device"):
            interface_assignment_configs_from_resources([bad])

    def test_empty_device_rejected(self) -> None:
        bad = _resource("lan", device="")
        with pytest.raises(ValueError, match="device"):
            interface_assignment_configs_from_resources([bad])

    def test_non_string_description_rejected(self) -> None:
        bad = ResourceConfig(
            name="lan",
            type="interface_assignments",
            provider="opnsense",
            config={"device": "ixl1", "description": 123},
        )
        with pytest.raises(ValueError, match="description"):
            interface_assignment_configs_from_resources([bad])

    def test_non_bool_enabled_rejected(self) -> None:
        bad = ResourceConfig(
            name="lan",
            type="interface_assignments",
            provider="opnsense",
            config={"device": "ixl1", "enabled": "yes"},
        )
        with pytest.raises(ValueError, match="enabled"):
            interface_assignment_configs_from_resources([bad])

    def test_non_bool_lock_rejected(self) -> None:
        bad = ResourceConfig(
            name="lan",
            type="interface_assignments",
            provider="opnsense",
            config={"device": "ixl1", "lock": "yes"},
        )
        with pytest.raises(ValueError, match="lock"):
            interface_assignment_configs_from_resources([bad])

    def test_non_dict_ipv4_rejected(self) -> None:
        bad = ResourceConfig(
            name="lan",
            type="interface_assignments",
            provider="opnsense",
            config={"device": "ixl1", "ipv4": "static"},
        )
        with pytest.raises(ValueError, match="ipv4"):
            interface_assignment_configs_from_resources([bad])

    def test_non_dict_ipv6_rejected(self) -> None:
        bad = ResourceConfig(
            name="lan",
            type="interface_assignments",
            provider="opnsense",
            config={"device": "ixl1", "ipv6": "track6"},
        )
        with pytest.raises(ValueError, match="ipv6"):
            interface_assignment_configs_from_resources([bad])

    def test_non_dict_config_rejected(self) -> None:
        # Pydantic forbids non-dict config at construction time, so the
        # path runs only when external code shoves a string in. Build the
        # ResourceConfig and then mutate.
        bad = _resource("lan")
        object.__setattr__(bad, "config", "not-a-dict")
        with pytest.raises(ValueError, match="non-dict config"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv4_none_treated_as_empty(self) -> None:
        # YAML `ipv4:` with no value parses as None — accept and normalize.
        bad = ResourceConfig(
            name="lan",
            type="interface_assignments",
            provider="opnsense",
            config={"device": "ixl1", "ipv4": None},
        )
        result = interface_assignment_configs_from_resources([bad])
        assert result[0].ipv4 == {}


# ---------------------------------------------------------------------------
# _row_to_live_assignment
# ---------------------------------------------------------------------------


class TestRowToLiveAssignment:
    def test_normal_row(self) -> None:
        row = _row(
            identifier="lan",
            device="ixl1",
            description="LAN",
            is_physical=True,
            ipv4={"mode": "static", "address": "10.0.0.1/24"},
            mtu=1500,
        )
        live = _row_to_live_assignment(row)
        assert live.identifier == "lan"
        assert live.device == "ixl1"
        assert live.description == "LAN"
        assert live.is_physical is True
        assert live.ipv4["address"] == "10.0.0.1/24"
        assert live.mtu == 1500

    def test_string_mtu_coerced(self) -> None:
        live = _row_to_live_assignment(_row(mtu="9000"))
        assert live.mtu == 9000

    def test_invalid_mtu_falls_back_to_zero(self) -> None:
        live = _row_to_live_assignment(_row(mtu="not-a-number"))
        assert live.mtu == 0

    def test_missing_keys_default(self) -> None:
        live = _row_to_live_assignment({"identifier": "lan"})
        assert live.identifier == "lan"
        assert live.device == ""
        assert live.description == ""
        assert live.is_physical is False
        assert live.ipv4 == {}
        assert live.ipv6 == {}
        assert live.macaddr == ""
        assert live.mtu == 0

    def test_non_dict_ipv4_normalized_to_empty_dict(self) -> None:
        # Defensive: if upstream API ever returns a string for ipv4,
        # we don't crash and treat it as no config.
        row = _row()
        row["ipv4"] = "static-mode-as-string"
        live = _row_to_live_assignment(row)
        assert live.ipv4 == {}


# ---------------------------------------------------------------------------
# InterfaceAssignmentService.list
# ---------------------------------------------------------------------------


class TestInterfaceAssignmentServiceList:
    def test_calls_get_interfacesinfo(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        service = InterfaceAssignmentService(client)
        result = service.list()
        client.request.assert_called_once_with("GET", "interfaces/overview/interfacesInfo")
        assert result == []

    def test_skips_rows_with_empty_identifier(self) -> None:
        # Rows without an identifier are physical NICs not assigned to
        # any logical interface — they don't belong in the dump.
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(identifier="lan", device="ixl1"),
                _row(identifier="", device="ixl2"),  # unassigned
                _row(identifier="wan", device="ixl0"),
            ]
        }
        service = InterfaceAssignmentService(client)
        result = service.list()
        assert {r.identifier for r in result} == {"lan", "wan"}
        assert len(result) == 2

    def test_skips_rows_with_missing_identifier(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"device": "ixl0"},  # no identifier key at all
                _row(identifier="lan"),
            ]
        }
        service = InterfaceAssignmentService(client)
        result = service.list()
        assert len(result) == 1
        assert result[0].identifier == "lan"

    def test_filters_non_dict_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(identifier="lan"),
                "not-a-dict",
                _row(identifier="wan", device="ixl0"),
            ]
        }
        service = InterfaceAssignmentService(client)
        result = service.list()
        assert len(result) == 2

    def test_handles_empty_response(self) -> None:
        client = MagicMock()
        client.request.return_value = {}
        service = InterfaceAssignmentService(client)
        assert service.list() == []

    def test_handles_non_dict_response(self) -> None:
        client = MagicMock()
        client.request.return_value = "garbage"
        service = InterfaceAssignmentService(client)
        assert service.list() == []

    def test_handles_non_list_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": "garbage"}
        service = InterfaceAssignmentService(client)
        assert service.list() == []

    def test_parses_is_physical_and_mtu(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(
                    identifier="vlan4000",
                    device="ixl0_vlan4000",
                    is_physical=False,
                    mtu=9000,
                ),
            ]
        }
        service = InterfaceAssignmentService(client)
        result = service.list()
        assert result[0].is_physical is False
        assert result[0].mtu == 9000

    def test_passes_ipv4_ipv6_through_as_dicts(self) -> None:
        ipv4_payload = {"mode": "static", "address": "10.0.0.1", "subnet": 24}
        ipv6_payload = {"mode": "track6", "track6_interface": "wan"}
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(identifier="lan", ipv4=ipv4_payload, ipv6=ipv6_payload),
            ]
        }
        service = InterfaceAssignmentService(client)
        result = service.list()
        assert result[0].ipv4 == ipv4_payload
        assert result[0].ipv6 == ipv6_payload


# ---------------------------------------------------------------------------
# export_to_yaml
# ---------------------------------------------------------------------------


class TestExportToYaml:
    def test_round_trip_structure(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(
                    identifier="lan",
                    device="ixl1",
                    description="LAN",
                    ipv4={"mode": "static", "address": "10.0.0.1/24"},
                ),
                _row(
                    identifier="wan",
                    device="ixl0",
                    description="WAN trunk",
                    ipv4={"mode": "dhcp"},
                ),
            ]
        }
        service = InterfaceAssignmentService(client)
        rendered = service.export_to_yaml()
        parsed = yaml.safe_load(rendered)
        assert "resources" in parsed
        names = {r["name"] for r in parsed["resources"]}
        assert names == {"lan", "wan"}
        for entry in parsed["resources"]:
            assert entry["provider"] == "opnsense"
            assert entry["type"] == "interface_assignments"
            assert "device" in entry["config"]
            assert "description" in entry["config"]
            assert "ipv4" in entry["config"]
            assert "ipv6" in entry["config"]
            assert entry["config"]["enabled"] is True

    def test_export_with_no_assignments(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        service = InterfaceAssignmentService(client)
        parsed = yaml.safe_load(service.export_to_yaml())
        assert parsed == {"resources": []}

    def test_export_skips_unassigned_interfaces(self) -> None:
        # Rows with empty identifier shouldn't end up in the export — the
        # operator is migrating logical interfaces, not raw NICs.
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(identifier="lan"),
                _row(identifier="", device="ixl5"),  # unassigned NIC
            ]
        }
        service = InterfaceAssignmentService(client)
        parsed = yaml.safe_load(service.export_to_yaml())
        assert len(parsed["resources"]) == 1
        assert parsed["resources"][0]["name"] == "lan"

    def test_yaml_is_valid_yaml(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [_row(identifier="lan", description="The LAN interface")]
        }
        service = InterfaceAssignmentService(client)
        rendered = service.export_to_yaml()
        # If yaml.safe_load raises, we have a YAML emission bug.
        assert yaml.safe_load(rendered) is not None
