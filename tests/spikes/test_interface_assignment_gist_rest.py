"""Unit tests for the gist-based REST interface_assignments spike.

Target module: ``tools/spikes/interface_assignment_gist_rest/interface_assignment_gist_rest.py``.

These tests cover env-var loading, YAML parsing/validation, the diff engine,
the apply loop's mutation dispatch, lockout-prevention, the auto-rollback
path, and the install helper's checksum logic. No live OPNsense box is
contacted — ``OPNsenseClient`` and ``subprocess.run`` are patched at the
spike module's import paths, mirroring ``tests/spikes/test_vlan_direct_api.py``.

Live-box validation is operator-driven and recorded in
``docs/development/opnsense-spike-interface-assignment-gist-findings.md``.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# The spike package lives under ``tools/spikes/`` which is already on sys.path.
from tools.spikes.interface_assignment_gist_rest import install as installer
from tools.spikes.interface_assignment_gist_rest import (
    interface_assignment_gist_rest as spike,
)

SPIKE_CLIENT_PATH = (
    "tools.spikes.interface_assignment_gist_rest.interface_assignment_gist_rest.OPNsenseClient"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(
    name: str,
    device: str,
    *,
    description: str = "",
    enabled: bool = True,
    lock: bool = False,
    ipv4_type: str = "none",
    ipv4_address: str | None = None,
    ipv4_subnet: int | None = None,
    ipv6_type: str = "none",
    ipv6_address: str | None = None,
    ipv6_subnet: int | None = None,
    ipv6_track: str | None = None,
) -> spike.InterfaceAssignmentConfig:
    return spike.InterfaceAssignmentConfig(
        name=name,
        device=device,
        description=description,
        enabled=enabled,
        lock=lock,
        ipv4_type=ipv4_type,
        ipv4_address=ipv4_address,
        ipv4_subnet=ipv4_subnet,
        ipv6_type=ipv6_type,
        ipv6_address=ipv6_address,
        ipv6_subnet=ipv6_subnet,
        ipv6_track=ipv6_track,
    )


def _live(
    identifier: str,
    device: str,
    *,
    description: str = "",
    is_physical: bool = True,
    ipv4: dict[str, Any] | None = None,
    ipv6: dict[str, Any] | None = None,
    macaddr: str = "",
    mtu: int = 1500,
) -> spike.LiveInterfaceAssignment:
    return spike.LiveInterfaceAssignment(
        identifier=identifier,
        device=device,
        description=description,
        is_physical=is_physical,
        ipv4=ipv4 or {},
        ipv6=ipv6 or {},
        macaddr=macaddr,
        mtu=mtu,
    )


# ---------------------------------------------------------------------------
# load_env_credentials
# ---------------------------------------------------------------------------


class TestLoadEnvCredentials:
    """Env var resolution into a ``Credentials`` dataclass."""

    def test_happy_path(self) -> None:
        env = {
            "OPNSENSE_API_URL": "https://fw.example.lan",
            "OPNSENSE_API_KEY": "key-123",
            "OPNSENSE_API_SECRET": "secret-456",
            "OPNSENSE_VERIFY_SSL": "true",
        }
        creds = spike.load_env_credentials(env)
        assert creds.api_url == "https://fw.example.lan"
        assert creds.api_key == "key-123"
        assert creds.api_secret == "secret-456"
        assert creds.verify_ssl is True

    def test_missing_api_secret_raises(self) -> None:
        env = {"OPNSENSE_API_URL": "https://fw", "OPNSENSE_API_KEY": "k"}
        with pytest.raises(RuntimeError) as exc_info:
            spike.load_env_credentials(env)
        assert "OPNSENSE_API_SECRET" in str(exc_info.value)

    def test_empty_string_treated_as_missing(self) -> None:
        env = {"OPNSENSE_API_URL": "", "OPNSENSE_API_KEY": "k", "OPNSENSE_API_SECRET": "s"}
        with pytest.raises(RuntimeError, match="OPNSENSE_API_URL"):
            spike.load_env_credentials(env)

    @pytest.mark.parametrize("falsey", ["false", "False", "0", "no", "off", "OFF"])
    def test_verify_ssl_falsey(self, falsey: str) -> None:
        env = {
            "OPNSENSE_API_URL": "https://fw",
            "OPNSENSE_API_KEY": "k",
            "OPNSENSE_API_SECRET": "s",
            "OPNSENSE_VERIFY_SSL": falsey,
        }
        creds = spike.load_env_credentials(env)
        assert creds.verify_ssl is False

    def test_verify_ssl_default_true(self) -> None:
        env = {
            "OPNSENSE_API_URL": "https://fw",
            "OPNSENSE_API_KEY": "k",
            "OPNSENSE_API_SECRET": "s",
        }
        creds = spike.load_env_credentials(env)
        assert creds.verify_ssl is True


# ---------------------------------------------------------------------------
# load_assignments_from_yaml
# ---------------------------------------------------------------------------


class TestLoadAssignmentsFromYaml:
    """YAML parsing + per-field validation."""

    def test_minimal_valid(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: spike
""",
            encoding="utf-8",
        )
        result = spike.load_assignments_from_yaml(path)
        assert len(result) == 1
        cfg = result[0]
        assert cfg.name == "opt5"
        assert cfg.device == "igc0"
        assert cfg.description == "spike"
        assert cfg.enabled is True
        assert cfg.lock is False
        assert cfg.ipv4_type == "none"
        assert cfg.ipv6_type == "none"

    def test_full_dual_stack(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt6
  config:
    device: igc1
    description: dual-stack
    enabled: true
    spoof_mac: "aa:bb:cc:dd:ee:ff"
    ipv4:
      type: static
      address: 10.0.0.1
      subnet: 24
    ipv6:
      type: track-interface
      track: wan
""",
            encoding="utf-8",
        )
        cfgs = spike.load_assignments_from_yaml(path)
        assert len(cfgs) == 1
        cfg = cfgs[0]
        assert cfg.spoof_mac == "aa:bb:cc:dd:ee:ff"
        assert cfg.ipv4_type == "static"
        assert cfg.ipv4_address == "10.0.0.1"
        assert cfg.ipv4_subnet == 24
        assert cfg.ipv6_type == "track-interface"
        assert cfg.ipv6_track == "wan"

    def test_static_ipv6(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt7
  config:
    device: igc2
    description: ""
    ipv6:
      type: static
      address: "fd00:1::1"
      subnet: 64
""",
            encoding="utf-8",
        )
        cfg = spike.load_assignments_from_yaml(path)[0]
        assert cfg.ipv6_type == "static"
        assert cfg.ipv6_address == "fd00:1::1"
        assert cfg.ipv6_subnet == 64

    def test_lock_field(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: lan
  lock: true
  config:
    device: ixl0
    description: LAN
""",
            encoding="utf-8",
        )
        cfg = spike.load_assignments_from_yaml(path)[0]
        assert cfg.lock is True

    def test_other_resource_types_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "mixed.yaml"
        path.write_text(
            """
- provider: opnsense
  type: vlan
  name: irrelevant
  config: {device: igb0, tag: 10, description: a, priority: 0}
- provider: opnsense
  type: interface_assignments
  name: opt8
  config: {device: igc3, description: kept}
""",
            encoding="utf-8",
        )
        cfgs = spike.load_assignments_from_yaml(path)
        assert len(cfgs) == 1
        assert cfgs[0].name == "opt8"

    def test_top_level_not_list_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("provider: opnsense\n", encoding="utf-8")
        with pytest.raises(ValueError, match="top-level list"):
            spike.load_assignments_from_yaml(path)

    def test_missing_device_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    description: missing-device
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="device"):
            spike.load_assignments_from_yaml(path)

    def test_invalid_lock_type(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  lock: "true"
  config:
    device: igc0
    description: test
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="lock must be a boolean"):
            spike.load_assignments_from_yaml(path)

    def test_invalid_enabled_type(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: test
    enabled: "yes"
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="enabled must be a boolean"):
            spike.load_assignments_from_yaml(path)

    def test_ipv4_static_missing_address(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: ""
    ipv4:
      type: static
      subnet: 24
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=r"ipv4\.address"):
            spike.load_assignments_from_yaml(path)

    def test_ipv4_subnet_out_of_range(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: ""
    ipv4:
      type: static
      address: 10.0.0.1
      subnet: 64
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="out of range 1-32"):
            spike.load_assignments_from_yaml(path)

    def test_ipv4_invalid_type(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: ""
    ipv4:
      type: pppoe
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=r"ipv4\.type"):
            spike.load_assignments_from_yaml(path)

    def test_ipv4_address_provided_with_dhcp_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: ""
    ipv4:
      type: dhcp
      address: 10.0.0.1
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=r"ipv4\.address/subnet only valid"):
            spike.load_assignments_from_yaml(path)

    def test_ipv6_track_missing_track_field(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: ""
    ipv6:
      type: track-interface
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=r"ipv6\.track"):
            spike.load_assignments_from_yaml(path)

    def test_ipv6_static_missing_subnet(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: ""
    ipv6:
      type: static
      address: "fd00::1"
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=r"ipv6\.subnet"):
            spike.load_assignments_from_yaml(path)

    def test_ipv6_subnet_out_of_range(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: ""
    ipv6:
      type: static
      address: "fd00::1"
      subnet: 200
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="out of range 1-128"):
            spike.load_assignments_from_yaml(path)

    def test_ipv6_invalid_type(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: ""
    ipv6:
      type: pppoe-v6
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=r"ipv6\.type"):
            spike.load_assignments_from_yaml(path)

    def test_ipv4_block_must_be_mapping(self, tmp_path: Path) -> None:
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: ""
    ipv4: "not-a-mapping"
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="ipv4 must be a mapping"):
            spike.load_assignments_from_yaml(path)


# ---------------------------------------------------------------------------
# InterfaceAssignmentConfig.to_payload
# ---------------------------------------------------------------------------


class TestPayloadShape:
    """The PHP controller expects ``{"assign": {<fields>}}``."""

    def test_minimal_payload_includes_basics(self) -> None:
        cfg = _cfg("opt5", "igc0", description="hi")
        payload = cfg.to_payload()
        assert "assign" in payload
        assign = payload["assign"]
        assert assign["device"] == "igc0"
        assert assign["description"] == "hi"
        assert assign["enable"] is True
        assert assign["name"] == "opt5"
        assert assign["ipv4Type"] == "none"
        assert assign["ipv6Type"] == "none"
        # No ipv4Address/Subnet/spoofMac/ipv6Track when not set.
        assert "ipv4Address" not in assign
        assert "ipv4Subnet" not in assign
        assert "spoofMac" not in assign
        assert "ipv6Track" not in assign

    def test_static_ipv4_payload(self) -> None:
        cfg = _cfg(
            "opt5",
            "igc0",
            description="hi",
            ipv4_type="static",
            ipv4_address="10.0.0.1",
            ipv4_subnet=24,
        )
        assign = cfg.to_payload()["assign"]
        assert assign["ipv4Type"] == "static"
        assert assign["ipv4Address"] == "10.0.0.1"
        assert assign["ipv4Subnet"] == 24

    def test_track_ipv6_payload(self) -> None:
        cfg = _cfg("opt5", "igc0", description="hi", ipv6_type="track-interface", ipv6_track="wan")
        assign = cfg.to_payload()["assign"]
        assert assign["ipv6Type"] == "track-interface"
        assert assign["ipv6Track"] == "wan"

    def test_static_ipv6_payload(self) -> None:
        cfg = _cfg(
            "opt5",
            "igc0",
            description="hi",
            ipv6_type="static",
            ipv6_address="fd00::1",
            ipv6_subnet=64,
        )
        assign = cfg.to_payload()["assign"]
        assert assign["ipv6Type"] == "static"
        assert assign["ipv6Address"] == "fd00::1"
        assert assign["ipv6Subnet"] == 64
        # Track field not emitted when type is static.
        assert "ipv6Track" not in assign

    def test_spoof_mac_emitted_when_set(self) -> None:
        cfg = _cfg("opt5", "igc0", description="x")
        cfg2 = spike.InterfaceAssignmentConfig(
            name=cfg.name,
            device=cfg.device,
            description=cfg.description,
            spoof_mac="aa:bb:cc:dd:ee:ff",
        )
        assign = cfg2.to_payload()["assign"]
        assert assign["spoofMac"] == "aa:bb:cc:dd:ee:ff"


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


class TestComputeDiff:
    """Diff keyed by logical interface name (identifier)."""

    def test_no_changes(self) -> None:
        desired = [_cfg("opt3", "igc0", description="x")]
        current = [_live("opt3", "igc0", description="x")]
        diff = spike.compute_diff(desired, current)
        assert diff.is_empty
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []

    def test_add_only(self) -> None:
        desired = [_cfg("opt3", "igc0")]
        diff = spike.compute_diff(desired, [])
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "opt3"

    def test_delete_only(self) -> None:
        current = [_live("opt5", "igc0")]
        diff = spike.compute_diff([], current)
        assert len(diff.deletes) == 1
        assert diff.deletes[0].identifier == "opt5"

    def test_update_when_device_differs(self) -> None:
        desired = [_cfg("opt3", "igc1", description="x")]
        current = [_live("opt3", "igc0", description="x")]
        diff = spike.compute_diff(desired, current)
        assert len(diff.updates) == 1
        live, want = diff.updates[0]
        assert live.device == "igc0"
        assert want.device == "igc1"

    def test_update_when_description_differs(self) -> None:
        desired = [_cfg("opt3", "igc0", description="new")]
        current = [_live("opt3", "igc0", description="old")]
        diff = spike.compute_diff(desired, current)
        assert len(diff.updates) == 1

    def test_locked_yaml_with_match(self) -> None:
        desired = [_cfg("lan", "ixl0", description="LAN", lock=True)]
        current = [_live("lan", "ixl0", description="LAN")]
        diff = spike.compute_diff(desired, current)
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1
        want, have = diff.locked[0]
        assert want.lock is True
        assert have is not None

    def test_locked_yaml_without_match(self) -> None:
        desired = [_cfg("opt99", "missing-nic", lock=True)]
        diff = spike.compute_diff(desired, [])
        assert len(diff.locked) == 1
        _, have = diff.locked[0]
        assert have is None

    def test_locked_protects_live_resource_from_delete(self) -> None:
        desired = [
            _cfg("lan", "ixl0", lock=True),
            _cfg("opt3", "igc0", description="new"),
        ]
        current = [
            _live("lan", "ixl0"),
            _live("opt5", "igc1", description="going-away"),
        ]
        diff = spike.compute_diff(desired, current)
        # opt3 add, opt5 delete, lan locked
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "opt3"
        assert len(diff.deletes) == 1
        assert diff.deletes[0].identifier == "opt5"
        assert len(diff.locked) == 1

    def test_add_only_suppresses_deletes(self) -> None:
        desired = [_cfg("opt3", "igc0")]
        current = [_live("opt5", "igc1")]
        diff = spike.compute_diff(desired, current, add_only=True)
        assert len(diff.adds) == 1
        assert len(diff.deletes) == 0
        assert not diff.is_empty

    def test_add_only_still_updates(self) -> None:
        desired = [_cfg("opt3", "igc0", description="new")]
        current = [_live("opt3", "igc0", description="old")]
        diff = spike.compute_diff(desired, current, add_only=True)
        assert len(diff.updates) == 1


# ---------------------------------------------------------------------------
# Lockout-prevention
# ---------------------------------------------------------------------------


class TestLockoutPrevention:
    """``find_lockout_conflicts`` must catch device collisions before apply."""

    def test_no_conflicts_returns_empty(self) -> None:
        diff = spike.compute_diff([_cfg("opt3", "igc0")], [])
        assert spike.find_lockout_conflicts(diff, []) == []

    def test_add_to_already_bound_device_flagged(self) -> None:
        # We want to add opt3 -> igc0, but igc0 is already bound to opt5.
        desired = [_cfg("opt3", "igc0")]
        current = [_live("opt5", "igc0")]
        diff = spike.Diff(adds=desired, updates=[], deletes=[], locked=[])
        msgs = spike.find_lockout_conflicts(diff, current)
        assert len(msgs) == 1
        assert "opt3" in msgs[0]
        assert "igc0" in msgs[0]
        assert "opt5" in msgs[0]

    def test_update_to_already_bound_device_flagged(self) -> None:
        # opt3 wants to move from igc0 to igc1, but igc1 is bound to opt7.
        live_to_update = _live("opt3", "igc0")
        want = _cfg("opt3", "igc1")
        current = [live_to_update, _live("opt7", "igc1")]
        diff = spike.Diff(
            adds=[],
            updates=[(live_to_update, want)],
            deletes=[],
            locked=[],
        )
        msgs = spike.find_lockout_conflicts(diff, current)
        assert len(msgs) == 1
        assert "opt3" in msgs[0]
        assert "igc1" in msgs[0]
        assert "opt7" in msgs[0]

    def test_update_no_device_change_is_safe(self) -> None:
        live_to_update = _live("opt3", "igc0", description="old")
        want = _cfg("opt3", "igc0", description="new")
        diff = spike.Diff(
            adds=[],
            updates=[(live_to_update, want)],
            deletes=[],
            locked=[],
        )
        msgs = spike.find_lockout_conflicts(diff, [live_to_update])
        assert msgs == []


# ---------------------------------------------------------------------------
# REST helpers — fetch / add / update / delete / get / search
# ---------------------------------------------------------------------------


class TestRestHelpers:
    """Each REST helper hits the right module/controller/command coordinates."""

    def test_fetch_interfaces_info(self) -> None:
        client = MagicMock()
        client.get.return_value = {
            "rows": [
                {
                    "identifier": "lan",
                    "device": "ixl0",
                    "description": "LAN",
                    "is_physical": True,
                    "ipv4": {"address": "192.168.1.1"},
                    "ipv6": {},
                    "macaddr": "aa:bb:cc:dd:ee:ff",
                    "mtu": "1500",
                },
                {
                    # Empty identifier — unassigned NIC, must be filtered.
                    "identifier": "",
                    "device": "igc7",
                    "description": "",
                    "is_physical": True,
                    "ipv4": {},
                    "ipv6": {},
                    "macaddr": "",
                    "mtu": 0,
                },
            ]
        }
        result = spike.fetch_interfaces_info(client)
        assert len(result) == 1
        assert result[0].identifier == "lan"
        assert result[0].mtu == 1500
        client.get.assert_called_once_with("interfaces", "overview", "interfacesInfo")

    def test_fetch_with_non_dict_response(self) -> None:
        client = MagicMock()
        client.get.return_value = "garbage"
        assert spike.fetch_interfaces_info(client) == []

    def test_fetch_with_malformed_rows(self) -> None:
        client = MagicMock()
        client.get.return_value = {
            "rows": [
                "not-a-dict",
                {"identifier": "opt1", "device": "igc0"},
            ]
        }
        result = spike.fetch_interfaces_info(client)
        assert len(result) == 1
        assert result[0].identifier == "opt1"

    def test_fetch_handles_unparseable_mtu(self) -> None:
        client = MagicMock()
        client.get.return_value = {
            "rows": [
                {
                    "identifier": "opt1",
                    "device": "igc0",
                    "description": "",
                    "is_physical": True,
                    "ipv4": {},
                    "ipv6": {},
                    "macaddr": "",
                    "mtu": "garbage",
                }
            ]
        }
        result = spike.fetch_interfaces_info(client)
        assert result[0].mtu == 0

    def test_add_assignment(self) -> None:
        client = MagicMock()
        client.post.return_value = {"result": "saved", "ifname": "opt5"}
        cfg = _cfg("opt5", "igc0", description="x")
        result = spike.add_assignment(client, cfg)
        assert result == {"result": "saved", "ifname": "opt5"}
        client.post.assert_called_once_with(
            "interfaces", "assign_settings", "addItem", json=cfg.to_payload()
        )

    def test_update_assignment(self) -> None:
        client = MagicMock()
        client.post.return_value = {"result": "saved", "ifname": "opt3"}
        cfg = _cfg("opt3", "igc1", description="x")
        result = spike.update_assignment(client, "opt3", cfg)
        assert result == {"result": "saved", "ifname": "opt3"}
        client.post.assert_called_once_with(
            "interfaces", "assign_settings", "setItem", "opt3", json=cfg.to_payload()
        )

    def test_delete_assignment(self) -> None:
        client = MagicMock()
        client.post.return_value = {"result": "deleted"}
        result = spike.delete_assignment(client, "opt3")
        assert result == {"result": "deleted"}
        client.post.assert_called_once_with("interfaces", "assign_settings", "delItem", "opt3")

    def test_get_assignment(self) -> None:
        client = MagicMock()
        client.get.return_value = {"result": "ok", "assign": {"device": "igc0"}}
        result = spike.get_assignment(client, "opt3")
        assert result["result"] == "ok"
        client.get.assert_called_once_with("interfaces", "assign_settings", "getItem", "opt3")

    def test_search_assignments_via_controller(self) -> None:
        client = MagicMock()
        client.post.return_value = {
            "result": "ok",
            "rows": [{"uuid": "opt1", "device": "igc0"}, "garbage", {"uuid": "opt2"}],
            "total": 2,
        }
        result = spike.search_assignments_via_controller(client)
        assert len(result) == 2
        client.post.assert_called_once_with("interfaces", "assign_settings", "searchItem")

    def test_search_with_non_dict_response(self) -> None:
        client = MagicMock()
        client.post.return_value = "garbage"
        assert spike.search_assignments_via_controller(client) == []

    def test_add_returns_raw_when_response_not_dict(self) -> None:
        client = MagicMock()
        client.post.return_value = "weird-string"
        cfg = _cfg("opt5", "igc0", description="x")
        result = spike.add_assignment(client, cfg)
        assert result == {"raw": "weird-string"}


# ---------------------------------------------------------------------------
# Backup helpers
# ---------------------------------------------------------------------------


class TestBackupHelpers:
    """List + capture latest + revert backup."""

    def test_list_returns_list_response_directly(self) -> None:
        client = MagicMock()
        client.get.return_value = ["snap1", "snap2"]
        assert spike.list_backup_ids(client) == ["snap1", "snap2"]

    def test_list_unwraps_dict_with_backups_key(self) -> None:
        client = MagicMock()
        client.get.return_value = {"backups": ["a", "b"]}
        assert spike.list_backup_ids(client) == ["a", "b"]

    def test_list_unwraps_flat_dict(self) -> None:
        client = MagicMock()
        client.get.return_value = {"snap1": {}, "snap2": {}}
        # We can't depend on dict ordering for the result list, so check membership.
        assert set(spike.list_backup_ids(client)) == {"snap1", "snap2"}

    def test_list_handles_unexpected_type(self) -> None:
        client = MagicMock()
        client.get.return_value = "garbage"
        assert spike.list_backup_ids(client) == []

    def test_capture_latest_returns_first(self) -> None:
        client = MagicMock()
        client.get.return_value = ["newest", "older"]
        assert spike.capture_latest_backup_id(client) == "newest"

    def test_capture_latest_returns_none_when_empty(self) -> None:
        client = MagicMock()
        client.get.return_value = []
        assert spike.capture_latest_backup_id(client) is None

    def test_revert_to_backup(self) -> None:
        client = MagicMock()
        client.post.return_value = {"status": "ok"}
        result = spike.revert_to_backup(client, "snap-id-1")
        assert result == {"status": "ok"}
        client.post.assert_called_once_with("core", "backup", "revertBackup", "snap-id-1")

    def test_revert_returns_raw_on_non_dict(self) -> None:
        client = MagicMock()
        client.post.return_value = "weird"
        result = spike.revert_to_backup(client, "snap-1")
        assert result == {"raw": "weird"}


# ---------------------------------------------------------------------------
# Apply loop — dispatch + auto-rollback
# ---------------------------------------------------------------------------


class TestCmdApply:
    """``cmd_apply`` dispatches mutations only when ``--confirm`` is passed."""

    @staticmethod
    def _yaml_with_one(tmp_path: Path, name: str, device: str) -> Path:
        path = tmp_path / "ia.yaml"
        path.write_text(
            f"""
- provider: opnsense
  type: interface_assignments
  name: {name}
  config:
    device: {device}
    description: spike
""",
            encoding="utf-8",
        )
        return path

    def test_dry_run_dispatches_no_mutations(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        client = MagicMock()
        client.get.return_value = {"rows": []}
        yaml_path = self._yaml_with_one(tmp_path, "opt5", "igc0")

        rc = spike.cmd_apply(client, yaml_path, confirm=False)

        assert rc == 0
        # No add/set/del POSTs were made (only the GET for interfacesInfo).
        for call in client.post.call_args_list:
            args = call.args
            # Note: searchItem, addItem, setItem, delItem all POST to "assign_settings".
            assert args[0:2] != ("interfaces", "assign_settings")
        out = capsys.readouterr().out
        assert "Dry run" in out

    def test_no_diff_skips_mutations(self, tmp_path: Path) -> None:
        client = MagicMock()
        # Existing row exactly matches the YAML.
        client.get.return_value = {
            "rows": [
                {
                    "identifier": "opt5",
                    "device": "igc0",
                    "description": "spike",
                    "is_physical": True,
                    "ipv4": {},
                    "ipv6": {},
                    "macaddr": "",
                    "mtu": 1500,
                }
            ]
        }
        yaml_path = self._yaml_with_one(tmp_path, "opt5", "igc0")

        rc = spike.cmd_apply(client, yaml_path, confirm=True)

        assert rc == 0
        # No mutating POSTs.
        post_calls = [
            call
            for call in client.post.call_args_list
            if call.args[0:2] == ("interfaces", "assign_settings")
        ]
        assert post_calls == []

    def test_confirm_dispatches_add(self, tmp_path: Path) -> None:
        client = MagicMock()

        # interfacesInfo (read) returns empty; backups returns one snapshot.
        # The MagicMock `.get` is shared by both, so use side_effect for ordering.
        def get_side_effect(*args: Any, **kwargs: Any) -> Any:
            if args[2] == "interfacesInfo":
                return {"rows": []}
            if args[2] == "backups":
                return ["snap-1"]
            return {}

        client.get.side_effect = get_side_effect
        client.post.return_value = {"result": "saved", "ifname": "opt5"}
        yaml_path = self._yaml_with_one(tmp_path, "opt5", "igc0")

        rc = spike.cmd_apply(client, yaml_path, confirm=True)

        assert rc == 0
        # A POST went to addItem with the right payload.
        add_calls = [
            call
            for call in client.post.call_args_list
            if call.args[0:3] == ("interfaces", "assign_settings", "addItem")
        ]
        assert len(add_calls) == 1
        payload = add_calls[0].kwargs["json"]
        assert payload["assign"]["device"] == "igc0"
        assert payload["assign"]["name"] == "opt5"

    def test_lockout_blocks_apply(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        client = MagicMock()
        # Existing row binds igc0 to opt9 — so adding opt5 -> igc0 must fail.
        client.get.return_value = {
            "rows": [
                {
                    "identifier": "opt9",
                    "device": "igc0",
                    "description": "incumbent",
                    "is_physical": True,
                    "ipv4": {},
                    "ipv6": {},
                    "macaddr": "",
                    "mtu": 1500,
                }
            ]
        }
        yaml_path = self._yaml_with_one(tmp_path, "opt5", "igc0")

        rc = spike.cmd_apply(client, yaml_path, confirm=True, add_only=True)

        assert rc == 1
        # No POST was made (lockout fires before the apply loop).
        post_calls = [
            call
            for call in client.post.call_args_list
            if call.args[0:2] == ("interfaces", "assign_settings")
        ]
        assert post_calls == []
        out = capsys.readouterr().out
        assert "Lockout risk" in out

    def test_apply_failure_triggers_auto_rollback(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        client = MagicMock()
        client.get.side_effect = lambda *args, **_: (
            {"rows": []} if args[2] == "interfacesInfo" else ["snap-1"]
        )

        # First POST — addItem — returns failed. Subsequent POST — revertBackup —
        # returns ok. Track post-call sequence using side_effect.
        post_responses = [
            {"result": "failed", "errorMessage": "device collision"},  # addItem fails
            {"status": "ok"},  # revertBackup succeeds
        ]
        client.post.side_effect = post_responses
        yaml_path = self._yaml_with_one(tmp_path, "opt5", "igc0")

        rc = spike.cmd_apply(client, yaml_path, confirm=True)

        assert rc == 1
        # Two POSTs: addItem (failed), revertBackup (rollback).
        assert client.post.call_count == 2
        rollback_call = client.post.call_args_list[1]
        assert rollback_call.args[0:3] == ("core", "backup", "revertBackup")
        assert rollback_call.args[3] == "snap-1"
        out = capsys.readouterr().out
        assert "Apply failed" in out
        assert "Auto-rollback" in out

    def test_no_rollback_flag_skips_revert(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.get.return_value = {"rows": []}
        client.post.return_value = {"result": "failed", "errorMessage": "boom"}
        yaml_path = self._yaml_with_one(tmp_path, "opt5", "igc0")

        rc = spike.cmd_apply(client, yaml_path, confirm=True, no_rollback=True)

        assert rc == 1
        # Only one POST — the addItem (failed). No rollback.
        assert client.post.call_count == 1
        assert client.post.call_args.args[2] == "addItem"

    def test_backup_snapshot_id_override(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.get.return_value = {"rows": []}
        # add fails; rollback is invoked with the supplied id, not from list_backup_ids.
        client.post.side_effect = [
            {"result": "failed", "errorMessage": "boom"},
            {"status": "ok"},
        ]
        yaml_path = self._yaml_with_one(tmp_path, "opt5", "igc0")

        rc = spike.cmd_apply(client, yaml_path, confirm=True, backup_snapshot_id="manual-snap-99")

        assert rc == 1
        rollback_call = client.post.call_args_list[1]
        assert rollback_call.args[0:3] == ("core", "backup", "revertBackup")
        assert rollback_call.args[3] == "manual-snap-99"
        # client.get for backups must NOT have been called (we skip auto-capture).
        get_paths = [c.args[0:3] for c in client.get.call_args_list]
        assert ("core", "backup", "backups") not in get_paths

    def test_update_path_dispatches_set_item(self, tmp_path: Path) -> None:
        client = MagicMock()

        # interfacesInfo: opt5 currently bound to igc0 with description "old".
        # backups: ["snap-1"]
        def get_side_effect(*args: Any, **_: Any) -> Any:
            if args[2] == "interfacesInfo":
                return {
                    "rows": [
                        {
                            "identifier": "opt5",
                            "device": "igc0",
                            "description": "old",
                            "is_physical": True,
                            "ipv4": {},
                            "ipv6": {},
                            "macaddr": "",
                            "mtu": 1500,
                        }
                    ]
                }
            return ["snap-1"]

        client.get.side_effect = get_side_effect
        client.post.return_value = {"result": "saved", "ifname": "opt5"}
        # YAML targets opt5 -> igc0 with description "spike", forcing setItem.
        yaml_path = self._yaml_with_one(tmp_path, "opt5", "igc0")

        rc = spike.cmd_apply(client, yaml_path, confirm=True)

        assert rc == 0
        set_calls = [call for call in client.post.call_args_list if call.args[2] == "setItem"]
        assert len(set_calls) == 1
        assert set_calls[0].args[3] == "opt5"

    def test_delete_path_dispatches_del_item(self, tmp_path: Path) -> None:
        client = MagicMock()

        # interfacesInfo: opt5 exists, but YAML asks for opt9 with no opt5 entry.
        def get_side_effect(*args: Any, **_: Any) -> Any:
            if args[2] == "interfacesInfo":
                return {
                    "rows": [
                        {
                            "identifier": "opt5",
                            "device": "igc0",
                            "description": "going",
                            "is_physical": True,
                            "ipv4": {},
                            "ipv6": {},
                            "macaddr": "",
                            "mtu": 1500,
                        }
                    ]
                }
            return ["snap-1"]

        client.get.side_effect = get_side_effect
        client.post.return_value = {"result": "deleted"}
        # YAML wants opt9 -> igc1, so opt5 gets deleted.
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt9
  config:
    device: igc1
    description: replacement
""",
            encoding="utf-8",
        )

        rc = spike.cmd_apply(client, path, confirm=True)

        assert rc == 0
        del_calls = [call for call in client.post.call_args_list if call.args[2] == "delItem"]
        assert len(del_calls) == 1
        assert del_calls[0].args[3] == "opt5"


# ---------------------------------------------------------------------------
# cmd_list / cmd_inspect / cmd_plan
# ---------------------------------------------------------------------------


class TestCmdList:
    def test_list_emits_yaml(self, capsys: pytest.CaptureFixture[str]) -> None:
        client = MagicMock()
        client.get.return_value = {
            "rows": [
                {
                    "identifier": "lan",
                    "device": "ixl0",
                    "description": "LAN",
                    "is_physical": True,
                    "ipv4": {},
                    "ipv6": {},
                    "macaddr": "",
                    "mtu": 1500,
                }
            ]
        }
        rc = spike.cmd_list(client)
        assert rc == 0
        out = capsys.readouterr().out
        assert "interface_assignments" in out
        assert "name: lan" in out
        assert "device: ixl0" in out

    def test_list_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        client = MagicMock()
        client.get.return_value = {"rows": []}
        rc = spike.cmd_list(client)
        assert rc == 0
        assert "no interface assignments" in capsys.readouterr().out


class TestCmdPlan:
    def test_plan_renders_diff(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        client = MagicMock()
        client.get.return_value = {"rows": []}
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: spike
""",
            encoding="utf-8",
        )
        rc = spike.cmd_plan(client, path)
        assert rc == 0
        out = capsys.readouterr().out
        assert "1 to add" in out
        assert "opt5" in out


class TestCmdInspect:
    def test_inspect_skips_checksum_when_ssh_env_missing(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Strip both SSH env AND OPNSENSE_API_URL so installer.load_ssh_target
        # has nothing to fall back on and raises RuntimeError. (Without
        # API_URL stripped, the host would be derived from it.)
        for key in (
            "OPNSENSE_SSH_HOST",
            "OPNSENSE_SSH_KEY",
            "OPNSENSE_SSH_USER",
            "OPNSENSE_API_URL",
        ):
            monkeypatch.delenv(key, raising=False)
        client = MagicMock()
        client.detect_version.return_value = "26.1.6_2"
        client.get.return_value = {"rows": []}

        rc = spike.cmd_inspect(client)

        assert rc == 0
        out = capsys.readouterr().out
        assert "26.1.6_2" in out
        assert "Controller checksum check skipped" in out

    def test_inspect_reports_checksum_when_ssh_target_loadable(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key_file = tmp_path / "id_rsa"
        key_file.write_text("dummy", encoding="utf-8")
        monkeypatch.setenv("OPNSENSE_SSH_HOST", "fw")
        monkeypatch.setenv("OPNSENSE_SSH_KEY", str(key_file))

        client = MagicMock()
        client.detect_version.return_value = "26.1.6_2"
        client.get.return_value = {"rows": []}

        with patch.object(installer, "verify_installed_checksum") as verify:
            verify.return_value = (True, "abc123def456789", "abc123def456789")
            rc = spike.cmd_inspect(client)

        assert rc == 0
        out = capsys.readouterr().out
        assert "Controller installed and current" in out

    def test_inspect_returns_1_when_interfaces_info_fails(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in ("OPNSENSE_SSH_HOST", "OPNSENSE_SSH_KEY"):
            monkeypatch.delenv(key, raising=False)
        client = MagicMock()
        client.detect_version.return_value = "26.1.6_2"
        client.get.side_effect = RuntimeError("boom")

        rc = spike.cmd_inspect(client)

        assert rc == 1
        assert "interfacesInfo probe failed" in capsys.readouterr().out

    def test_inspect_reports_missing_controller(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key_file = tmp_path / "id_rsa"
        key_file.write_text("dummy", encoding="utf-8")
        monkeypatch.setenv("OPNSENSE_SSH_HOST", "fw")
        monkeypatch.setenv("OPNSENSE_SSH_KEY", str(key_file))

        client = MagicMock()
        client.detect_version.return_value = "26.1.6_2"
        client.get.return_value = {"rows": []}

        with patch.object(installer, "verify_installed_checksum") as verify:
            verify.return_value = (False, None, "abc123def456789")
            rc = spike.cmd_inspect(client)

        assert rc == 0
        assert "NOT installed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# build_client
# ---------------------------------------------------------------------------


class TestBuildClient:
    def test_uses_auto_detect_version_true(self) -> None:
        creds = spike.Credentials(
            api_url="https://fw",
            api_key="k",
            api_secret="s",
            verify_ssl=False,
        )
        with patch(SPIKE_CLIENT_PATH) as client_cls:
            spike.build_client(creds)
        client_cls.assert_called_once_with(
            base_url="https://fw",
            api_key="k",
            api_secret="s",
            verify_ssl=False,
            auto_detect_version=True,
        )


# ---------------------------------------------------------------------------
# main() — argparse + finally close()
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_inspect_closes_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in ("OPNSENSE_SSH_HOST", "OPNSENSE_SSH_KEY"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("OPNSENSE_API_URL", "https://fw")
        monkeypatch.setenv("OPNSENSE_API_KEY", "k")
        monkeypatch.setenv("OPNSENSE_API_SECRET", "s")
        monkeypatch.setenv("OPNSENSE_VERIFY_SSL", "false")

        fake = MagicMock()
        fake.detect_version.return_value = "26.1.6_2"
        fake.get.return_value = {"rows": []}

        with patch(SPIKE_CLIENT_PATH, return_value=fake):
            rc = spike.main(["inspect"])

        assert rc == 0
        fake.close.assert_called_once()

    def test_main_propagates_missing_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in ("OPNSENSE_API_URL", "OPNSENSE_API_KEY", "OPNSENSE_API_SECRET"):
            monkeypatch.delenv(key, raising=False)
        with pytest.raises(RuntimeError, match="Missing"):
            spike.main(["inspect"])

    def test_main_install_does_not_open_client(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # ``install`` is SSH-only — it should NOT instantiate OPNsenseClient
        # nor read REST env vars.
        for key in ("OPNSENSE_API_URL", "OPNSENSE_API_KEY", "OPNSENSE_API_SECRET"):
            monkeypatch.delenv(key, raising=False)
        key_file = tmp_path / "id_rsa"
        key_file.write_text("dummy", encoding="utf-8")
        monkeypatch.setenv("OPNSENSE_SSH_HOST", "fw")
        monkeypatch.setenv("OPNSENSE_SSH_KEY", str(key_file))

        with (
            patch(SPIKE_CLIENT_PATH) as client_cls,
            patch.object(installer, "install_controller") as install,
        ):
            rc = spike.main(["install"])

        assert rc == 0
        client_cls.assert_not_called()
        install.assert_called_once()

    def test_main_apply_dry_run(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("OPNSENSE_API_URL", "https://fw")
        monkeypatch.setenv("OPNSENSE_API_KEY", "k")
        monkeypatch.setenv("OPNSENSE_API_SECRET", "s")
        monkeypatch.setenv("OPNSENSE_VERIFY_SSL", "false")
        path = tmp_path / "ia.yaml"
        path.write_text(
            """
- provider: opnsense
  type: interface_assignments
  name: opt5
  config:
    device: igc0
    description: spike
""",
            encoding="utf-8",
        )
        fake = MagicMock()
        fake.get.return_value = {"rows": []}

        with patch(SPIKE_CLIENT_PATH, return_value=fake):
            rc = spike.main(["apply", str(path)])

        assert rc == 0
        fake.close.assert_called_once()


# ---------------------------------------------------------------------------
# _raise_on_failure
# ---------------------------------------------------------------------------


class TestRaiseOnFailure:
    def test_saved_passes(self) -> None:
        spike._raise_on_failure({"result": "saved", "ifname": "opt5"}, "add opt5")

    def test_deleted_passes(self) -> None:
        spike._raise_on_failure({"result": "deleted"}, "delItem opt5")

    def test_ok_passes(self) -> None:
        spike._raise_on_failure({"result": "ok"}, "getItem opt5")

    def test_failed_raises_runtime(self) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            spike._raise_on_failure(
                {"result": "failed", "errorMessage": "device taken"}, "add opt5"
            )
        assert "device taken" in str(exc_info.value)
        assert "add opt5" in str(exc_info.value)

    def test_failed_without_message_falls_back_to_response(self) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            spike._raise_on_failure({"result": "failed"}, "add opt5")
        assert "add opt5" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Module reload sanity
# ---------------------------------------------------------------------------


def test_spike_module_imports_cleanly() -> None:
    """Importing the spike must not contact the network or read env vars eagerly."""
    sys.modules.pop(
        "tools.spikes.interface_assignment_gist_rest.interface_assignment_gist_rest", None
    )
    reloaded: Any = importlib.import_module(
        "tools.spikes.interface_assignment_gist_rest.interface_assignment_gist_rest"
    )
    assert hasattr(reloaded, "main")
    assert hasattr(reloaded, "compute_diff")
    assert hasattr(reloaded, "find_lockout_conflicts")


# ---------------------------------------------------------------------------
# Installer module — checksum + SSH flow (subprocess.run patched)
# ---------------------------------------------------------------------------


class TestInstallerLoadSshTarget:
    def test_minimal_happy_path(self, tmp_path: Path) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("dummy", encoding="utf-8")
        env = {
            "OPNSENSE_SSH_HOST": "fw.lan",
            "OPNSENSE_SSH_KEY": str(key),
        }
        target = installer.load_ssh_target(env)
        assert target.host == "fw.lan"
        assert target.user == "root"
        assert target.port == 22
        assert target.key_path == key
        assert target.install_path.endswith("AssignSettingsController.php")

    def test_overrides_user_and_port(self, tmp_path: Path) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("dummy", encoding="utf-8")
        env = {
            "OPNSENSE_SSH_HOST": "fw.lan",
            "OPNSENSE_SSH_KEY": str(key),
            "OPNSENSE_SSH_USER": "admin",
            "OPNSENSE_SSH_PORT": "2222",
            "OPNSENSE_INSTALL_PATH": "/custom/path/Foo.php",
        }
        target = installer.load_ssh_target(env)
        assert target.user == "admin"
        assert target.port == 2222
        assert target.install_path == "/custom/path/Foo.php"

    def test_missing_host_raises_when_no_api_url(self, tmp_path: Path) -> None:
        # No SSH host and no API URL to derive from → still raises.
        key = tmp_path / "id_rsa"
        key.write_text("d", encoding="utf-8")
        env = {"OPNSENSE_SSH_KEY": str(key)}
        with pytest.raises(RuntimeError, match="OPNSENSE_SSH_HOST"):
            installer.load_ssh_target(env)

    def test_host_derived_from_api_url(self) -> None:
        # OPNSENSE_API_URL hostname is used when SSH_HOST is unset.
        env = {"OPNSENSE_API_URL": "https://opnsense-a:8443"}
        target = installer.load_ssh_target(env)
        assert target.host == "opnsense-a"

    def test_explicit_ssh_host_wins_over_api_url(self) -> None:
        # If both are set, SSH_HOST takes precedence.
        env = {
            "OPNSENSE_SSH_HOST": "fw.internal",
            "OPNSENSE_API_URL": "https://opnsense-a",
        }
        target = installer.load_ssh_target(env)
        assert target.host == "fw.internal"

    def test_missing_key_is_optional(self) -> None:
        # Without OPNSENSE_SSH_KEY the script falls back to ssh-agent /
        # ~/.ssh/config; key_path on the SshTarget is None.
        env = {"OPNSENSE_SSH_HOST": "fw"}
        target = installer.load_ssh_target(env)
        assert target.key_path is None

    def test_nonexistent_key_path_raises(self, tmp_path: Path) -> None:
        env = {
            "OPNSENSE_SSH_HOST": "fw",
            "OPNSENSE_SSH_KEY": str(tmp_path / "missing"),
        }
        with pytest.raises(RuntimeError, match="does not exist"):
            installer.load_ssh_target(env)

    def test_invalid_port_raises(self, tmp_path: Path) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("d", encoding="utf-8")
        env = {
            "OPNSENSE_SSH_HOST": "fw",
            "OPNSENSE_SSH_KEY": str(key),
            "OPNSENSE_SSH_PORT": "not-a-number",
        }
        with pytest.raises(RuntimeError, match="must be an integer"):
            installer.load_ssh_target(env)


class TestInstallerChecksum:
    def test_compute_local_checksum(self, tmp_path: Path) -> None:
        f = tmp_path / "x.txt"
        f.write_bytes(b"hello world")
        # Known SHA-256 of b"hello world".
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert installer.compute_local_checksum(f) == expected

    def test_local_controller_path_resolves(self) -> None:
        path = installer.local_controller_path()
        assert path.name == "AssignSettingsController.php"
        assert path.exists()


class TestInstallerSshFlow:
    """SSH/SCP invocations are mocked at the installer's subprocess.run path."""

    @staticmethod
    def _target(tmp_path: Path) -> installer.SshTarget:
        key = tmp_path / "id_rsa"
        key.write_text("d", encoding="utf-8")
        return installer.SshTarget(
            host="fw.lan",
            user="root",
            port=22,
            key_path=key,
            install_path="/usr/local/Foo.php",
        )

    def _result(self, *, returncode: int = 0, stdout: str = "", stderr: str = "") -> Any:
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr
        )

    def test_fetch_remote_checksum_present(self, tmp_path: Path) -> None:
        target = self._target(tmp_path)
        with patch.object(installer, "_run") as run:
            run.return_value = self._result(stdout="abc123def456789\n")
            sha = installer.fetch_remote_checksum(target)
        assert sha == "abc123def456789"

    def test_fetch_remote_checksum_missing(self, tmp_path: Path) -> None:
        target = self._target(tmp_path)
        with patch.object(installer, "_run") as run:
            run.return_value = self._result(stdout="MISSING\n")
            sha = installer.fetch_remote_checksum(target)
        assert sha is None

    def test_fetch_remote_checksum_ssh_failure(self, tmp_path: Path) -> None:
        target = self._target(tmp_path)
        with patch.object(installer, "_run") as run:
            run.return_value = self._result(returncode=255, stderr="connection refused")
            with pytest.raises(RuntimeError, match="SSH probe failed"):
                installer.fetch_remote_checksum(target)

    def test_verify_installed_checksum_match(self, tmp_path: Path) -> None:
        target = self._target(tmp_path)
        with patch.object(installer, "fetch_remote_checksum") as remote:
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            remote.return_value = local_sum
            matches, remote_sum, ls = installer.verify_installed_checksum(target)
        assert matches is True
        assert remote_sum == local_sum
        assert ls == local_sum

    def test_verify_installed_checksum_mismatch(self, tmp_path: Path) -> None:
        target = self._target(tmp_path)
        with patch.object(installer, "fetch_remote_checksum") as remote:
            remote.return_value = "different-sha"
            matches, _, _ = installer.verify_installed_checksum(target)
        assert matches is False

    def test_install_skips_when_already_current(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = self._target(tmp_path)
        with patch.object(installer, "verify_installed_checksum") as verify:
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            verify.return_value = (True, local_sum, local_sum)
            installed = installer.install_controller(target)
        assert installed is False
        assert "already current" in capsys.readouterr().out

    def test_install_runs_full_lifecycle(self, tmp_path: Path) -> None:
        target = self._target(tmp_path)
        with (
            patch.object(installer, "verify_installed_checksum") as verify,
            patch.object(installer, "_run") as run,
        ):
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            # First call: pre-install check (mismatch). Second call: post-install check (match).
            verify.side_effect = [(False, None, local_sum), (True, local_sum, local_sum)]
            run.return_value = self._result(returncode=0)
            installed = installer.install_controller(target)
        assert installed is True
        # SCP + chmod + 2x service restart = 4 _run calls.
        assert run.call_count == 4
        # First call must be SCP; following calls must use SSH.
        assert run.call_args_list[0].args[0][0] == "scp"
        for c in run.call_args_list[1:]:
            assert c.args[0][0] == "ssh"

    def test_install_scp_failure_raises(self, tmp_path: Path) -> None:
        target = self._target(tmp_path)
        with (
            patch.object(installer, "verify_installed_checksum") as verify,
            patch.object(installer, "_run") as run,
        ):
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            verify.return_value = (False, None, local_sum)
            run.return_value = self._result(returncode=1, stderr="scp: permission denied")
            with pytest.raises(RuntimeError, match="SCP failed"):
                installer.install_controller(target)

    def test_install_post_check_mismatch_raises(self, tmp_path: Path) -> None:
        target = self._target(tmp_path)
        with (
            patch.object(installer, "verify_installed_checksum") as verify,
            patch.object(installer, "_run") as run,
        ):
            local_sum = installer.compute_local_checksum(installer.local_controller_path())
            # pre-check: mismatch; post-check: still mismatch (install silently failed).
            verify.side_effect = [
                (False, None, local_sum),
                (False, "different-sha", local_sum),
            ]
            run.return_value = self._result(returncode=0)
            with pytest.raises(RuntimeError, match="Post-install checksum mismatch"):
                installer.install_controller(target)


class TestInstallerCli:
    def test_main_install_dispatches_to_helper(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("d", encoding="utf-8")
        monkeypatch.setenv("OPNSENSE_SSH_HOST", "fw")
        monkeypatch.setenv("OPNSENSE_SSH_KEY", str(key))
        with (
            patch.object(installer, "_ensure_ssh_tools_present"),
            patch.object(installer, "install_controller") as inst,
        ):
            rc = installer.main(["install"])
        assert rc == 0
        inst.assert_called_once()
        # force flag default is False.
        _, kwargs = inst.call_args
        assert kwargs.get("force") is False

    def test_main_install_force_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("d", encoding="utf-8")
        monkeypatch.setenv("OPNSENSE_SSH_HOST", "fw")
        monkeypatch.setenv("OPNSENSE_SSH_KEY", str(key))
        with (
            patch.object(installer, "_ensure_ssh_tools_present"),
            patch.object(installer, "install_controller") as inst,
        ):
            installer.main(["install", "--force"])
        _, kwargs = inst.call_args
        assert kwargs.get("force") is True

    def test_main_verify_match_returns_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("d", encoding="utf-8")
        monkeypatch.setenv("OPNSENSE_SSH_HOST", "fw")
        monkeypatch.setenv("OPNSENSE_SSH_KEY", str(key))
        with (
            patch.object(installer, "_ensure_ssh_tools_present"),
            patch.object(installer, "verify_installed_checksum") as verify,
        ):
            verify.return_value = (True, "abc123def456789", "abc123def456789")
            rc = installer.main(["verify"])
        assert rc == 0
        assert "OK" in capsys.readouterr().out

    def test_main_verify_missing_returns_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("d", encoding="utf-8")
        monkeypatch.setenv("OPNSENSE_SSH_HOST", "fw")
        monkeypatch.setenv("OPNSENSE_SSH_KEY", str(key))
        with (
            patch.object(installer, "_ensure_ssh_tools_present"),
            patch.object(installer, "verify_installed_checksum") as verify,
        ):
            verify.return_value = (False, None, "abc123def456789")
            rc = installer.main(["verify"])
        assert rc == 1
        assert "MISSING" in capsys.readouterr().out

    def test_main_verify_mismatch_returns_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        key = tmp_path / "id_rsa"
        key.write_text("d", encoding="utf-8")
        monkeypatch.setenv("OPNSENSE_SSH_HOST", "fw")
        monkeypatch.setenv("OPNSENSE_SSH_KEY", str(key))
        with (
            patch.object(installer, "_ensure_ssh_tools_present"),
            patch.object(installer, "verify_installed_checksum") as verify,
        ):
            verify.return_value = (False, "deadbeef00000000", "abc123def456789")
            rc = installer.main(["verify"])
        assert rc == 1
        assert "MISMATCH" in capsys.readouterr().out

    def test_ensure_ssh_tools_present_raises_when_missing(self) -> None:
        with (
            patch.object(installer.shutil, "which", return_value=None),
            pytest.raises(RuntimeError, match="not on PATH"),
        ):
            installer._ensure_ssh_tools_present()
