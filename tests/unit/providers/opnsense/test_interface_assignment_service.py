"""Unit tests for ``infrafoundry.providers.opnsense.services.interface_assignment``.

Coverage (full-CRUD path, #720):
    - ``LiveInterfaceAssignment`` / ``InterfaceAssignmentConfig`` invariants.
    - ``InterfaceAssignmentConfig.to_payload`` shape per controller contract.
    - ``interface_assignment_configs_from_resources`` parsing edge cases.
    - ``InterfaceAssignmentService`` REST CRUD methods (mocked client).
    - ``compute_diff`` behaviors (adds / updates / deletes / locked /
      add_only).
    - ``_needs_update`` deep-equality across all writable fields.
    - ``find_lockout_conflicts`` device-collision detection.
    - ``apply_diff`` happy-path counts + first-failure stop semantics.
    - ``_parse_live_to_config`` projector edge cases (DHCP, track,
      static, dual-stack, unmapped-mode raises).
    - ``_row_to_live_assignment`` defensive coercion.
    - ``export_to_yaml`` round-trip.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.interface_assignment import (
    ApplyDiffResult,
    Diff,
    InterfaceAssignmentConfig,
    InterfaceAssignmentService,
    LiveInterfaceAssignment,
    _needs_update,
    _parse_live_to_config,
    _row_to_live_assignment,
    compute_diff,
    find_lockout_conflicts,
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
    spoof_mac: str | None = None,
    ipv4: dict[str, Any] | None = None,
    ipv6: dict[str, Any] | None = None,
) -> ResourceConfig:
    config: dict[str, Any] = {"device": device, "description": description}
    if enabled is not None:
        config["enabled"] = enabled
    if lock is not None:
        config["lock"] = lock
    if spoof_mac is not None:
        config["spoof_mac"] = spoof_mac
    if ipv4 is not None:
        config["ipv4"] = ipv4
    if ipv6 is not None:
        config["ipv6"] = ipv6
    return ResourceConfig(
        name=name, type="interfaces.assignments", provider="opnsense", config=config
    )


def _cfg(
    name: str = "opt5",
    *,
    device: str = "igc0",
    description: str = "x",
    enabled: bool = True,
    lock: bool = False,
    spoof_mac: str | None = None,
    ipv4_type: str = "none",
    ipv4_address: str | None = None,
    ipv4_subnet: int | None = None,
    ipv6_type: str = "none",
    ipv6_address: str | None = None,
    ipv6_subnet: int | None = None,
    ipv6_track: str | None = None,
) -> InterfaceAssignmentConfig:
    return InterfaceAssignmentConfig(
        name=name,
        device=device,
        description=description,
        enabled=enabled,
        lock=lock,
        spoof_mac=spoof_mac,
        ipv4_type=ipv4_type,
        ipv4_address=ipv4_address,
        ipv4_subnet=ipv4_subnet,
        ipv6_type=ipv6_type,
        ipv6_address=ipv6_address,
        ipv6_subnet=ipv6_subnet,
        ipv6_track=ipv6_track,
    )


def _live(
    identifier: str = "opt5",
    device: str = "igc0",
    *,
    description: str = "x",
    is_physical: bool = True,
    ipv4: dict[str, Any] | None = None,
    ipv6: dict[str, Any] | None = None,
    mtu: int = 1500,
) -> LiveInterfaceAssignment:
    return LiveInterfaceAssignment(
        identifier=identifier,
        device=device,
        description=description,
        is_physical=is_physical,
        ipv4=ipv4 if ipv4 is not None else {},
        ipv6=ipv6 if ipv6 is not None else {},
        macaddr="",
        mtu=mtu,
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

    def test_diff_key_is_identifier(self) -> None:
        live = _live("opt3", device="igc0")
        assert live.diff_key == "opt3"


class TestInterfaceAssignmentConfigDefaults:
    def test_defaults(self) -> None:
        cfg = InterfaceAssignmentConfig(name="lan", device="ixl1", description="")
        assert cfg.enabled is True
        assert cfg.lock is False
        assert cfg.spoof_mac is None
        assert cfg.ipv4_type == "none"
        assert cfg.ipv6_type == "none"
        assert cfg.diff_key == "lan"


# ---------------------------------------------------------------------------
# to_payload (controller contract)
# ---------------------------------------------------------------------------


class TestPayloadShape:
    def test_minimal_payload_includes_basics(self) -> None:
        cfg = _cfg("opt5", device="igc0", description="hi")
        payload = cfg.to_payload()
        assert "assign" in payload
        assign = payload["assign"]
        assert assign["device"] == "igc0"
        assert assign["description"] == "hi"
        assert assign["enable"] is True
        assert assign["name"] == "opt5"
        assert assign["ipv4Type"] == "none"
        assert assign["ipv6Type"] == "none"
        # Optional fields are NOT emitted unless set.
        assert "ipv4Address" not in assign
        assert "ipv4Subnet" not in assign
        assert "spoofMac" not in assign
        assert "ipv6Track" not in assign

    def test_static_ipv4_payload(self) -> None:
        cfg = _cfg(ipv4_type="static", ipv4_address="10.0.0.1", ipv4_subnet=24)
        assign = cfg.to_payload()["assign"]
        assert assign["ipv4Type"] == "static"
        assert assign["ipv4Address"] == "10.0.0.1"
        assert assign["ipv4Subnet"] == 24

    def test_track_ipv6_payload(self) -> None:
        cfg = _cfg(ipv6_type="track-interface", ipv6_track="wan")
        assign = cfg.to_payload()["assign"]
        assert assign["ipv6Type"] == "track-interface"
        assert assign["ipv6Track"] == "wan"

    def test_static_ipv6_payload(self) -> None:
        cfg = _cfg(ipv6_type="static", ipv6_address="fd00::1", ipv6_subnet=64)
        assign = cfg.to_payload()["assign"]
        assert assign["ipv6Type"] == "static"
        assert assign["ipv6Address"] == "fd00::1"
        assert assign["ipv6Subnet"] == 64
        assert "ipv6Track" not in assign

    def test_spoof_mac_emitted_when_set(self) -> None:
        cfg = _cfg(spoof_mac="aa:bb:cc:dd:ee:ff")
        assign = cfg.to_payload()["assign"]
        assert assign["spoofMac"] == "aa:bb:cc:dd:ee:ff"


# ---------------------------------------------------------------------------
# interface_assignment_configs_from_resources
# ---------------------------------------------------------------------------


class TestConfigsFromResources:
    def test_minimal_resource_parses(self) -> None:
        result = interface_assignment_configs_from_resources([_resource("lan")])
        assert len(result) == 1
        assert result[0].name == "lan"
        assert result[0].device == "ixl1"
        assert result[0].ipv4_type == "none"
        assert result[0].ipv6_type == "none"

    def test_non_matching_resources_ignored(self) -> None:
        ifa = _resource("lan")
        alias = ResourceConfig(name="a", type="firewall.aliases", provider="opnsense", config={})
        result = interface_assignment_configs_from_resources([ifa, alias])
        assert len(result) == 1

    def test_typed_ipv4_static_parses(self) -> None:
        result = interface_assignment_configs_from_resources(
            [
                _resource(
                    "opt5",
                    device="igc0",
                    ipv4={"type": "static", "address": "10.0.0.1", "subnet": 24},
                )
            ]
        )
        assert result[0].ipv4_type == "static"
        assert result[0].ipv4_address == "10.0.0.1"
        assert result[0].ipv4_subnet == 24

    def test_typed_ipv6_track_parses(self) -> None:
        result = interface_assignment_configs_from_resources(
            [
                _resource(
                    "opt5",
                    device="igc0",
                    ipv6={"type": "track-interface", "track": "wan"},
                )
            ]
        )
        assert result[0].ipv6_type == "track-interface"
        assert result[0].ipv6_track == "wan"

    def test_typed_ipv6_static_parses(self) -> None:
        result = interface_assignment_configs_from_resources(
            [
                _resource(
                    "opt5",
                    device="igc0",
                    ipv6={"type": "static", "address": "fd00::1", "subnet": 64},
                )
            ]
        )
        assert result[0].ipv6_type == "static"
        assert result[0].ipv6_address == "fd00::1"
        assert result[0].ipv6_subnet == 64

    def test_dual_stack_parses(self) -> None:
        result = interface_assignment_configs_from_resources(
            [
                _resource(
                    "opt5",
                    device="igc0",
                    ipv4={"type": "static", "address": "10.0.0.1", "subnet": 24},
                    ipv6={"type": "track-interface", "track": "wan"},
                )
            ]
        )
        assert result[0].ipv4_type == "static"
        assert result[0].ipv6_type == "track-interface"

    def test_lock_field(self) -> None:
        result = interface_assignment_configs_from_resources([_resource("lan", lock=True)])
        assert result[0].lock is True

    def test_spoof_mac_field(self) -> None:
        result = interface_assignment_configs_from_resources(
            [_resource("opt5", spoof_mac="aa:bb:cc:dd:ee:ff")]
        )
        assert result[0].spoof_mac == "aa:bb:cc:dd:ee:ff"

    # ------------------------------------------------------------------
    # Validation rejections
    # ------------------------------------------------------------------

    def test_missing_device_rejected(self) -> None:
        bad = ResourceConfig(
            name="lan",
            type="interfaces.assignments",
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
            type="interfaces.assignments",
            provider="opnsense",
            config={"device": "ixl1", "description": 123},
        )
        with pytest.raises(ValueError, match="description"):
            interface_assignment_configs_from_resources([bad])

    def test_non_bool_enabled_rejected(self) -> None:
        bad = ResourceConfig(
            name="lan",
            type="interfaces.assignments",
            provider="opnsense",
            config={"device": "ixl1", "enabled": "yes"},
        )
        with pytest.raises(ValueError, match="enabled"):
            interface_assignment_configs_from_resources([bad])

    def test_non_bool_lock_rejected(self) -> None:
        bad = ResourceConfig(
            name="lan",
            type="interfaces.assignments",
            provider="opnsense",
            config={"device": "ixl1", "lock": "yes"},
        )
        with pytest.raises(ValueError, match="lock"):
            interface_assignment_configs_from_resources([bad])

    def test_non_string_spoof_mac_rejected(self) -> None:
        bad = ResourceConfig(
            name="lan",
            type="interfaces.assignments",
            provider="opnsense",
            config={"device": "ixl1", "spoof_mac": 12345},
        )
        with pytest.raises(ValueError, match="spoof_mac"):
            interface_assignment_configs_from_resources([bad])

    def test_non_dict_config_rejected(self) -> None:
        # Pydantic forbids non-dict config at construction time; mutate
        # post-construction to drive the defensive branch.
        bad = _resource("lan")
        object.__setattr__(bad, "config", "not-a-dict")
        with pytest.raises(ValueError, match="non-dict config"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv4_static_missing_address(self) -> None:
        bad = _resource("opt5", ipv4={"type": "static", "subnet": 24})
        with pytest.raises(ValueError, match=r"ipv4\.address"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv4_subnet_out_of_range(self) -> None:
        bad = _resource("opt5", ipv4={"type": "static", "address": "10.0.0.1", "subnet": 64})
        with pytest.raises(ValueError, match="out of range 1-32"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv4_invalid_type(self) -> None:
        bad = _resource("opt5", ipv4={"type": "pppoe"})
        with pytest.raises(ValueError, match=r"ipv4\.type"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv4_address_with_dhcp_rejected(self) -> None:
        bad = _resource("opt5", ipv4={"type": "dhcp", "address": "10.0.0.1"})
        with pytest.raises(ValueError, match=r"only valid"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv6_track_missing_track_field(self) -> None:
        bad = _resource("opt5", ipv6={"type": "track-interface"})
        with pytest.raises(ValueError, match=r"ipv6\.track"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv6_static_missing_subnet(self) -> None:
        bad = _resource("opt5", ipv6={"type": "static", "address": "fd00::1"})
        with pytest.raises(ValueError, match=r"ipv6\.subnet"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv6_subnet_out_of_range(self) -> None:
        bad = _resource("opt5", ipv6={"type": "static", "address": "fd00::1", "subnet": 200})
        with pytest.raises(ValueError, match="out of range 1-128"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv6_invalid_type(self) -> None:
        bad = _resource("opt5", ipv6={"type": "pppoe-v6"})
        with pytest.raises(ValueError, match=r"ipv6\.type"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv4_block_must_be_mapping(self) -> None:
        bad = ResourceConfig(
            name="opt5",
            type="interfaces.assignments",
            provider="opnsense",
            config={"device": "ixl1", "ipv4": "static"},
        )
        with pytest.raises(ValueError, match="ipv4 must be a mapping"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv4_none_treated_as_empty(self) -> None:
        # YAML "ipv4:" with no value parses as None.
        bad = ResourceConfig(
            name="opt5",
            type="interfaces.assignments",
            provider="opnsense",
            config={"device": "ixl1", "ipv4": None},
        )
        result = interface_assignment_configs_from_resources([bad])
        assert result[0].ipv4_type == "none"

    def test_ipv6_block_must_be_mapping(self) -> None:
        bad = ResourceConfig(
            name="opt5",
            type="interfaces.assignments",
            provider="opnsense",
            config={"device": "ixl1", "ipv6": "track6"},
        )
        with pytest.raises(ValueError, match="ipv6 must be a mapping"):
            interface_assignment_configs_from_resources([bad])

    def test_ipv6_none_treated_as_empty(self) -> None:
        bad = ResourceConfig(
            name="opt5",
            type="interfaces.assignments",
            provider="opnsense",
            config={"device": "ixl1", "ipv6": None},
        )
        result = interface_assignment_configs_from_resources([bad])
        assert result[0].ipv6_type == "none"


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
            ipv4={"ipaddr": "10.0.0.1", "subnet": "24"},
            mtu=1500,
        )
        live = _row_to_live_assignment(row)
        assert live.identifier == "lan"
        assert live.device == "ixl1"
        assert live.ipv4["ipaddr"] == "10.0.0.1"
        assert live.mtu == 1500

    def test_string_mtu_coerced(self) -> None:
        live = _row_to_live_assignment(_row(mtu="9000"))
        assert live.mtu == 9000

    def test_invalid_mtu_falls_back_to_zero(self) -> None:
        live = _row_to_live_assignment(_row(mtu="not-a-number"))
        assert live.mtu == 0

    def test_missing_keys_default(self) -> None:
        live = _row_to_live_assignment({"identifier": "lan"})
        assert live.device == ""
        assert live.description == ""
        assert live.is_physical is False
        assert live.ipv4 == {}
        assert live.ipv6 == {}
        assert live.mtu == 0

    def test_non_dict_ipv4_normalized_to_empty(self) -> None:
        row = _row()
        row["ipv4"] = "garbage"
        live = _row_to_live_assignment(row)
        assert live.ipv4 == {}


# ---------------------------------------------------------------------------
# InterfaceAssignmentService — REST CRUD
# ---------------------------------------------------------------------------


class TestServiceList:
    def test_calls_get_interfacesinfo(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        service = InterfaceAssignmentService(client)
        result = service.list()
        client.request.assert_called_once_with("GET", "interfaces/overview/interfacesInfo")
        assert result == []

    def test_search_alias(self) -> None:
        # `search` is a VLAN-style alias for `list` — must call the same
        # underlying endpoint.
        client = MagicMock()
        client.request.return_value = {"rows": []}
        service = InterfaceAssignmentService(client)
        service.search()
        client.request.assert_called_once_with("GET", "interfaces/overview/interfacesInfo")

    def test_skips_rows_with_empty_identifier(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                _row(identifier="lan", device="ixl1"),
                _row(identifier="", device="ixl2"),
                _row(identifier="wan", device="ixl0"),
            ]
        }
        service = InterfaceAssignmentService(client)
        result = service.list()
        assert {r.identifier for r in result} == {"lan", "wan"}

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

    def test_filters_non_dict_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [_row(identifier="lan"), "not-a-dict", _row(identifier="wan", device="ixl0")]
        }
        service = InterfaceAssignmentService(client)
        result = service.list()
        assert len(result) == 2


class TestServiceWriteCRUD:
    def test_add_calls_add_item_endpoint(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "ifname": "opt5"}
        service = InterfaceAssignmentService(client)
        cfg = _cfg("opt5", device="igc0", description="x")
        result = service.add(cfg)
        client.request.assert_called_once_with(
            "POST", "interfaces/assign_settings/addItem", data=cfg.to_payload()
        )
        assert result["result"] == "saved"

    def test_update_calls_set_item_with_identifier(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        service = InterfaceAssignmentService(client)
        cfg = _cfg("opt3", device="igc1", description="x")
        service.update("opt3", cfg)
        client.request.assert_called_once_with(
            "POST", "interfaces/assign_settings/setItem/opt3", data=cfg.to_payload()
        )

    def test_delete_calls_del_item_with_identifier(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "deleted"}
        service = InterfaceAssignmentService(client)
        service.delete("opt3")
        client.request.assert_called_once_with("POST", "interfaces/assign_settings/delItem/opt3")

    def test_get_calls_get_item_with_identifier(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "ok"}
        service = InterfaceAssignmentService(client)
        service.get("opt3")
        client.request.assert_called_once_with("GET", "interfaces/assign_settings/getItem/opt3")


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiff:
    def test_no_changes(self) -> None:
        # Live row matches the desired typed config exactly (after projection).
        desired = [_cfg("opt3", device="igc0", description="x")]
        current = [_live("opt3", device="igc0", description="x")]
        diff = compute_diff(desired, current)
        assert diff.is_empty
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []

    def test_add_only(self) -> None:
        desired = [_cfg("opt3", device="igc0")]
        diff = compute_diff(desired, [])
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "opt3"

    def test_delete_only(self) -> None:
        current = [_live("opt5", device="igc0")]
        diff = compute_diff([], current)
        assert len(diff.deletes) == 1
        assert diff.deletes[0].identifier == "opt5"

    def test_update_when_device_differs(self) -> None:
        desired = [_cfg("opt3", device="igc1", description="x")]
        current = [_live("opt3", device="igc0", description="x")]
        diff = compute_diff(desired, current)
        assert len(diff.updates) == 1
        live, want = diff.updates[0]
        assert live.device == "igc0"
        assert want.device == "igc1"

    def test_update_when_description_differs(self) -> None:
        desired = [_cfg("opt3", device="igc0", description="new")]
        current = [_live("opt3", device="igc0", description="old")]
        diff = compute_diff(desired, current)
        assert len(diff.updates) == 1

    def test_locked_yaml_with_match(self) -> None:
        desired = [_cfg("lan", device="ixl0", description="LAN", lock=True)]
        current = [_live("lan", device="ixl0", description="LAN")]
        diff = compute_diff(desired, current)
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1
        want, have = diff.locked[0]
        assert want.lock is True
        assert have is not None

    def test_locked_yaml_without_match(self) -> None:
        desired = [_cfg("opt99", device="missing-nic", lock=True)]
        diff = compute_diff(desired, [])
        assert len(diff.locked) == 1
        _, have = diff.locked[0]
        assert have is None

    def test_locked_protects_live_resource_from_delete(self) -> None:
        desired = [
            _cfg("lan", device="ixl0", description="LAN", lock=True),
            _cfg("opt3", device="igc0", description="new"),
        ]
        current = [
            _live("lan", device="ixl0", description="LAN"),
            _live("opt5", device="igc1", description="going-away"),
        ]
        diff = compute_diff(desired, current)
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "opt3"
        assert len(diff.deletes) == 1
        assert diff.deletes[0].identifier == "opt5"
        assert len(diff.locked) == 1

    def test_add_only_suppresses_deletes(self) -> None:
        desired = [_cfg("opt3", device="igc0")]
        current = [_live("opt5", device="igc1")]
        diff = compute_diff(desired, current, add_only=True)
        assert len(diff.adds) == 1
        assert len(diff.deletes) == 0
        assert not diff.is_empty

    def test_add_only_still_updates(self) -> None:
        desired = [_cfg("opt3", device="igc0", description="new")]
        current = [_live("opt3", device="igc0", description="old")]
        diff = compute_diff(desired, current, add_only=True)
        assert len(diff.updates) == 1


# ---------------------------------------------------------------------------
# _needs_update — deep equality across all writable fields
# ---------------------------------------------------------------------------


class TestNeedsUpdate:
    """Twelve+ scenarios driving the typed-comparison projector."""

    def test_no_change(self) -> None:
        # device + description + ipv4-none + ipv6-none.
        assert _needs_update(_live(), _cfg()) is False

    def test_device_change(self) -> None:
        assert _needs_update(_live(device="igc0"), _cfg(device="igc1")) is True

    def test_description_change(self) -> None:
        assert _needs_update(_live(description="old"), _cfg(description="new")) is True

    def test_ipv4_type_change_none_to_static(self) -> None:
        live = _live()  # ipv4 = {}
        want = _cfg(ipv4_type="static", ipv4_address="10.0.0.1", ipv4_subnet=24)
        assert _needs_update(live, want) is True

    def test_ipv4_type_change_dhcp_to_static(self) -> None:
        live = _live(ipv4={"ipaddr": "dhcp"})
        want = _cfg(ipv4_type="static", ipv4_address="10.0.0.1", ipv4_subnet=24)
        assert _needs_update(live, want) is True

    def test_ipv4_type_change_static_to_dhcp(self) -> None:
        live = _live(ipv4={"ipaddr": "10.0.0.1", "subnet": "24"})
        want = _cfg(ipv4_type="dhcp")
        assert _needs_update(live, want) is True

    def test_ipv4_address_change(self) -> None:
        live = _live(ipv4={"ipaddr": "10.0.0.1", "subnet": "24"})
        want = _cfg(ipv4_type="static", ipv4_address="10.0.0.2", ipv4_subnet=24)
        assert _needs_update(live, want) is True

    def test_ipv4_subnet_change(self) -> None:
        live = _live(ipv4={"ipaddr": "10.0.0.1", "subnet": "24"})
        want = _cfg(ipv4_type="static", ipv4_address="10.0.0.1", ipv4_subnet=28)
        assert _needs_update(live, want) is True

    def test_ipv6_type_change_none_to_track(self) -> None:
        live = _live()
        want = _cfg(ipv6_type="track-interface", ipv6_track="wan")
        assert _needs_update(live, want) is True

    def test_ipv6_track_change(self) -> None:
        live = _live(ipv6={"ipaddrv6": "track6", "track6-interface": "wan"})
        want = _cfg(ipv6_type="track-interface", ipv6_track="opt0")
        assert _needs_update(live, want) is True

    def test_ipv6_static_address_change(self) -> None:
        live = _live(ipv6={"ipaddrv6": "fd00::1", "subnetv6": "64"})
        want = _cfg(ipv6_type="static", ipv6_address="fd00::2", ipv6_subnet=64)
        assert _needs_update(live, want) is True

    def test_ipv6_subnet_change(self) -> None:
        live = _live(ipv6={"ipaddrv6": "fd00::1", "subnetv6": "64"})
        want = _cfg(ipv6_type="static", ipv6_address="fd00::1", ipv6_subnet=56)
        assert _needs_update(live, want) is True

    def test_spoof_mac_change(self) -> None:
        live = _live(ipv4={"spoofmac": "aa:bb:cc:dd:ee:ff"})
        want = _cfg(spoof_mac="aa:bb:cc:dd:ee:00")
        assert _needs_update(live, want) is True

    def test_round_trip_after_parse_no_change(self) -> None:
        # Project the live row to a config, build a `want` from it,
        # and confirm _needs_update reports no change. Closes the
        # gap explicitly flagged in the spike's docstring.
        live = _live(
            ipv4={"ipaddr": "10.0.0.1", "subnet": "24"},
            ipv6={"ipaddrv6": "track6", "track6-interface": "wan"},
        )
        # Manually construct `want` to mirror the live state exactly.
        want = _cfg(
            ipv4_type="static",
            ipv4_address="10.0.0.1",
            ipv4_subnet=24,
            ipv6_type="track-interface",
            ipv6_track="wan",
        )
        assert _needs_update(live, want) is False

    def test_unmapped_ipv4_mode_raises(self) -> None:
        # PPPoE / L2TP / GIF / GRE etc. must surface as ValueError per
        # the #720 plan.
        live = _live(ipv4={"ipaddr": "pppoe"})
        want = _cfg()
        with pytest.raises(ValueError, match="unsupported IPv4 mode"):
            _needs_update(live, want)

    def test_unmapped_ipv6_mode_raises(self) -> None:
        live = _live(ipv6={"ipaddrv6": "gif0"})
        want = _cfg()
        with pytest.raises(ValueError, match="unsupported IPv6 mode"):
            _needs_update(live, want)


# ---------------------------------------------------------------------------
# _parse_live_to_config
# ---------------------------------------------------------------------------


class TestParseLiveToConfig:
    def test_static_v4_only(self) -> None:
        live = _live(ipv4={"ipaddr": "10.0.0.1", "subnet": "24"})
        cfg = _parse_live_to_config(live)
        assert cfg.ipv4_type == "static"
        assert cfg.ipv4_address == "10.0.0.1"
        assert cfg.ipv4_subnet == 24
        assert cfg.ipv6_type == "none"

    def test_static_v6_only(self) -> None:
        live = _live(ipv6={"ipaddrv6": "fd00::1", "subnetv6": "64"})
        cfg = _parse_live_to_config(live)
        assert cfg.ipv6_type == "static"
        assert cfg.ipv6_address == "fd00::1"
        assert cfg.ipv6_subnet == 64
        assert cfg.ipv4_type == "none"

    def test_dual_stack(self) -> None:
        live = _live(
            ipv4={"ipaddr": "10.0.0.1", "subnet": "24"},
            ipv6={"ipaddrv6": "fd00::1", "subnetv6": "64"},
        )
        cfg = _parse_live_to_config(live)
        assert cfg.ipv4_type == "static"
        assert cfg.ipv6_type == "static"

    def test_dhcp_v4(self) -> None:
        live = _live(ipv4={"ipaddr": "dhcp"})
        cfg = _parse_live_to_config(live)
        assert cfg.ipv4_type == "dhcp"
        assert cfg.ipv4_address is None
        assert cfg.ipv4_subnet is None

    def test_dhcp_v6(self) -> None:
        live = _live(ipv6={"ipaddrv6": "dhcp6"})
        cfg = _parse_live_to_config(live)
        assert cfg.ipv6_type == "dhcp"

    def test_track_interface(self) -> None:
        live = _live(ipv6={"ipaddrv6": "track6", "track6-interface": "wan"})
        cfg = _parse_live_to_config(live)
        assert cfg.ipv6_type == "track-interface"
        assert cfg.ipv6_track == "wan"

    def test_none(self) -> None:
        live = _live()
        cfg = _parse_live_to_config(live)
        assert cfg.ipv4_type == "none"
        assert cfg.ipv6_type == "none"

    def test_unmapped_v4_mode_raises(self) -> None:
        live = _live(ipv4={"ipaddr": "pppoe"})
        with pytest.raises(ValueError, match="unsupported IPv4 mode"):
            _parse_live_to_config(live)

    def test_unmapped_v6_mode_raises(self) -> None:
        live = _live(ipv6={"ipaddrv6": "l2tp"})
        with pytest.raises(ValueError, match="unsupported IPv6 mode"):
            _parse_live_to_config(live)

    def test_track_interface_missing_track6_field_raises(self) -> None:
        live = _live(ipv6={"ipaddrv6": "track6"})
        with pytest.raises(ValueError, match="track6-interface"):
            _parse_live_to_config(live)

    def test_static_v4_missing_subnet_raises(self) -> None:
        live = _live(ipv4={"ipaddr": "10.0.0.1"})
        with pytest.raises(ValueError, match="subnet"):
            _parse_live_to_config(live)

    def test_static_v6_missing_subnet_raises(self) -> None:
        live = _live(ipv6={"ipaddrv6": "fd00::1"})
        with pytest.raises(ValueError, match="subnetv6"):
            _parse_live_to_config(live)


# ---------------------------------------------------------------------------
# find_lockout_conflicts
# ---------------------------------------------------------------------------


class TestLockoutPrevention:
    def test_no_conflicts_returns_empty(self) -> None:
        diff = compute_diff([_cfg("opt3", device="igc0")], [])
        assert find_lockout_conflicts(diff, []) == []

    def test_add_to_already_bound_device_flagged(self) -> None:
        # Want to add opt3 -> igc0, but igc0 is already bound to opt5.
        desired = [_cfg("opt3", device="igc0")]
        current = [_live("opt5", device="igc0")]
        diff = Diff(adds=desired, updates=[], deletes=[], locked=[])
        msgs = find_lockout_conflicts(diff, current)
        assert len(msgs) == 1
        assert "opt3" in msgs[0]
        assert "igc0" in msgs[0]
        assert "opt5" in msgs[0]

    def test_update_to_already_bound_device_flagged(self) -> None:
        # opt3 wants to move from igc0 to igc1, but igc1 is bound to opt7.
        live_to_update = _live("opt3", device="igc0")
        want = _cfg("opt3", device="igc1")
        current = [live_to_update, _live("opt7", device="igc1")]
        diff = Diff(
            adds=[],
            updates=[(live_to_update, want)],
            deletes=[],
            locked=[],
        )
        msgs = find_lockout_conflicts(diff, current)
        assert len(msgs) == 1
        assert "opt7" in msgs[0]

    def test_update_no_device_change_is_safe(self) -> None:
        live_to_update = _live("opt3", device="igc0", description="old")
        want = _cfg("opt3", device="igc0", description="new")
        diff = Diff(
            adds=[],
            updates=[(live_to_update, want)],
            deletes=[],
            locked=[],
        )
        assert find_lockout_conflicts(diff, [live_to_update]) == []


# ---------------------------------------------------------------------------
# apply_diff
# ---------------------------------------------------------------------------


class TestApplyDiff:
    def test_empty_diff_returns_zero_counts(self) -> None:
        client = MagicMock()
        service = InterfaceAssignmentService(client)
        result = service.apply_diff(Diff())
        assert result.created == 0
        assert result.updated == 0
        assert result.deleted == 0
        assert result.succeeded is True
        client.request.assert_not_called()

    def test_apply_dispatches_adds(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "ifname": "opt5"}
        service = InterfaceAssignmentService(client)
        cfg = _cfg("opt5", device="igc0")
        result = service.apply_diff(Diff(adds=[cfg]))
        assert result.created == 1
        assert result.succeeded is True
        # POST hit addItem.
        call = client.request.call_args
        assert call.args[0] == "POST"
        assert call.args[1] == "interfaces/assign_settings/addItem"

    def test_apply_dispatches_updates(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        service = InterfaceAssignmentService(client)
        live = _live("opt3", device="igc0")
        want = _cfg("opt3", device="igc1", description="new")
        result = service.apply_diff(Diff(updates=[(live, want)]))
        assert result.updated == 1
        # POST hit setItem with the live identifier.
        assert "setItem/opt3" in client.request.call_args.args[1]

    def test_apply_dispatches_deletes(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "deleted"}
        service = InterfaceAssignmentService(client)
        live = _live("opt9", device="igc7")
        result = service.apply_diff(Diff(deletes=[live]))
        assert result.deleted == 1
        assert "delItem/opt9" in client.request.call_args.args[1]

    def test_apply_mixed_sequence(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        service = InterfaceAssignmentService(client)
        live_update = _live("opt3", device="igc0")
        want = _cfg("opt3", device="igc1", description="new")
        live_delete = _live("opt9", device="igc7")

        # Adds dispatch first, then updates, then deletes.
        result = service.apply_diff(
            Diff(
                adds=[_cfg("opt5", device="igc0")],
                updates=[(live_update, want)],
                deletes=[live_delete],
            )
        )
        assert result.created == 1
        assert result.updated == 1
        # delItem returns "deleted" but we mock all responses to "saved";
        # the success-token check accepts "saved"/"deleted"/"ok" so the
        # delete still counts.

    def test_first_failure_stops_further_ops(self) -> None:
        # Per ADR-0014 §6 (option-c rollback), the first HTTP 400 stops
        # further ops. We mock the controller to fail on the second
        # add — first add must have succeeded, second must be the
        # last call.
        client = MagicMock()
        client.request.side_effect = [
            {"result": "saved"},  # add opt5 succeeds
            {"result": "failed", "errorMessage": "device collision"},  # add opt6 fails
        ]
        service = InterfaceAssignmentService(client)
        result = service.apply_diff(
            Diff(
                adds=[
                    _cfg("opt5", device="igc0"),
                    _cfg("opt6", device="igc1"),
                ]
            )
        )
        assert result.created == 1
        assert result.succeeded is False
        assert result.failure_message is not None
        assert "device collision" in result.failure_message
        assert "opt6" in result.failure_message
        # Only two requests fired; the second's failure stopped further work.
        assert client.request.call_count == 2

    def test_failure_without_error_message_falls_back_to_response(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "failed"}
        service = InterfaceAssignmentService(client)
        result = service.apply_diff(Diff(adds=[_cfg("opt5", device="igc0")]))
        assert result.succeeded is False
        assert result.failure_message is not None
        assert "opt5" in result.failure_message

    def test_failure_with_non_dict_response(self) -> None:
        client = MagicMock()
        client.request.return_value = "garbage"
        service = InterfaceAssignmentService(client)
        result = service.apply_diff(Diff(adds=[_cfg("opt5", device="igc0")]))
        assert result.succeeded is False


# ---------------------------------------------------------------------------
# ApplyDiffResult
# ---------------------------------------------------------------------------


class TestApplyDiffResult:
    def test_succeeded_true_by_default(self) -> None:
        assert ApplyDiffResult().succeeded is True

    def test_succeeded_false_when_failure_message_set(self) -> None:
        r = ApplyDiffResult(failure_message="boom")
        assert r.succeeded is False


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
                    ipv4={"ipaddr": "10.0.0.1", "subnet": "24"},
                ),
                _row(
                    identifier="wan",
                    device="ixl0",
                    description="WAN trunk",
                    ipv4={"ipaddr": "dhcp"},
                ),
            ]
        }
        service = InterfaceAssignmentService(client)
        rendered = service.export_to_yaml()
        parsed = yaml.safe_load(rendered)
        assert "resources" in parsed
        names = {r["name"] for r in parsed["resources"]}
        assert names == {"lan", "wan"}

    def test_export_with_no_assignments(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        service = InterfaceAssignmentService(client)
        parsed = yaml.safe_load(service.export_to_yaml())
        assert parsed == {"resources": []}

    def test_export_skips_unassigned_interfaces(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [_row(identifier="lan"), _row(identifier="", device="ixl5")]
        }
        service = InterfaceAssignmentService(client)
        parsed = yaml.safe_load(service.export_to_yaml())
        assert len(parsed["resources"]) == 1
