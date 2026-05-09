"""Unit tests for ``infrafoundry.providers.opnsense.services.vlan``.

Coverage:
    - Domain dataclasses (``VlanConfig``, ``LiveVlan``, ``Diff``).
    - ``compute_diff`` keyed by ``(device, tag)`` with lock + add-only semantics.
    - ``vlan_configs_from_resources`` validation.
    - ``VlanService`` API method dispatch via ``OPNsenseClient.request``.
    - ``apply_diff`` orchestration.
    - ``export_to_yaml`` round-trip.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.vlan import (
    Diff,
    LiveVlan,
    VlanConfig,
    VlanService,
    _row_to_live_vlan,
    compute_diff,
    vlan_configs_from_resources,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vlan(
    device: str, tag: int, desc: str = "x", pcp: int = 0, *, lock: bool = False
) -> VlanConfig:
    return VlanConfig(
        name=f"vlan-{device}-{tag}",
        device=device,
        tag=tag,
        description=desc,
        priority=pcp,
        lock=lock,
    )


def _live(uuid: str, device: str, tag: int, desc: str = "x", pcp: int = 0) -> LiveVlan:
    return LiveVlan(uuid=uuid, device=device, tag=tag, description=desc, priority=pcp)


def _resource(
    name: str,
    device: str,
    tag: int,
    *,
    description: str = "test",
    priority: int = 0,
    lock: bool | None = None,
) -> ResourceConfig:
    config: dict[str, Any] = {
        "device": device,
        "tag": tag,
        "description": description,
        "priority": priority,
    }
    if lock is not None:
        config["lock"] = lock
    return ResourceConfig(name=name, type="interfaces.vlans", provider="opnsense", config=config)


# ---------------------------------------------------------------------------
# VlanConfig.to_payload
# ---------------------------------------------------------------------------


class TestVlanPayloadShape:
    """API expects ``{"vlan": {"if", "tag", "descr", "pcp"}}`` with stringified ints."""

    def test_payload_keys_and_types(self) -> None:
        v = VlanConfig(name="v1", device="igb0", tag=100, description="hello", priority=3)
        payload = v.to_payload()
        assert set(payload.keys()) == {"vlan"}
        inner = payload["vlan"]
        assert inner["if"] == "igb0"
        # OPNsense expects strings even for integer-looking fields.
        assert inner["tag"] == "100"
        assert inner["descr"] == "hello"
        assert inner["pcp"] == "3"

    def test_diff_key_is_device_and_tag(self) -> None:
        v = VlanConfig(name="something", device="igb0", tag=100, description="x", priority=0)
        assert v.diff_key == ("igb0", 100)

    def test_lock_default_false(self) -> None:
        v = VlanConfig(name="v", device="igb0", tag=10, description="x", priority=0)
        assert v.lock is False


class TestLiveVlanDiffKey:
    def test_diff_key_is_device_and_tag(self) -> None:
        live = LiveVlan(uuid="u1", device="igb0", tag=100, description="x", priority=0)
        assert live.diff_key == ("igb0", 100)


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiff:
    """``compute_diff`` keyed by ``(device, tag)``."""

    def test_no_changes_when_desired_matches_current(self) -> None:
        desired = [_vlan("igb0", 10, "storage", 0)]
        current = [_live("u1", "igb0", 10, "storage", 0)]
        diff = compute_diff(desired, current)
        assert diff.is_empty
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []

    def test_add_only(self) -> None:
        desired = [_vlan("igb0", 10)]
        current: list[LiveVlan] = []
        diff = compute_diff(desired, current)
        assert len(diff.adds) == 1
        assert len(diff.updates) == 0
        assert len(diff.deletes) == 0
        assert diff.adds[0].diff_key == ("igb0", 10)

    def test_remove_only(self) -> None:
        desired: list[VlanConfig] = []
        current = [_live("u1", "igb0", 10)]
        diff = compute_diff(desired, current)
        assert len(diff.adds) == 0
        assert len(diff.updates) == 0
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u1"

    def test_update_only_when_description_differs(self) -> None:
        desired = [_vlan("igb0", 10, desc="new-desc")]
        current = [_live("u1", "igb0", 10, desc="old-desc")]
        diff = compute_diff(desired, current)
        assert len(diff.adds) == 0
        assert len(diff.updates) == 1
        assert len(diff.deletes) == 0
        live, want = diff.updates[0]
        assert live.uuid == "u1"
        assert want.description == "new-desc"

    def test_update_only_when_priority_differs(self) -> None:
        desired = [_vlan("igb0", 10, pcp=3)]
        current = [_live("u1", "igb0", 10, pcp=0)]
        diff = compute_diff(desired, current)
        assert len(diff.updates) == 1

    def test_diff_keypair_is_device_tag_not_name_or_uuid(self) -> None:
        # Same UUID, same description — but different (device, tag) means add+delete.
        desired = [_vlan("igb1", 10, desc="same")]
        current = [_live("u1", "igb0", 10, desc="same")]
        diff = compute_diff(desired, current)
        assert len(diff.adds) == 1
        assert len(diff.deletes) == 1
        assert len(diff.updates) == 0
        assert diff.adds[0].device == "igb1"
        assert diff.deletes[0].device == "igb0"

    def test_mixed_add_update_delete(self) -> None:
        desired = [
            _vlan("igb0", 10, desc="keep"),
            _vlan("igb0", 20, desc="updated"),
            _vlan("igb0", 30, desc="brand-new"),
        ]
        current = [
            _live("u1", "igb0", 10, desc="keep"),
            _live("u2", "igb0", 20, desc="old"),
            _live("u3", "igb0", 99, desc="going-away"),
        ]
        diff = compute_diff(desired, current)
        assert len(diff.adds) == 1
        assert len(diff.updates) == 1
        assert len(diff.deletes) == 1
        assert diff.adds[0].tag == 30
        assert diff.updates[0][0].uuid == "u2"
        assert diff.deletes[0].uuid == "u3"

    def test_locked_yaml_entry_with_match_skipped_from_actions(self) -> None:
        desired = [_vlan("ixl0", 4000, desc="", lock=True)]
        current = [_live("u1", "ixl0", 4000, desc="")]
        diff = compute_diff(desired, current)
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1
        want, have = diff.locked[0]
        assert want.lock is True
        assert have is not None
        assert have.uuid == "u1"

    def test_locked_yaml_entry_without_match_recorded_as_missing(self) -> None:
        desired = [_vlan("igb0", 100, lock=True)]
        current: list[LiveVlan] = []
        diff = compute_diff(desired, current)
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1
        want, have = diff.locked[0]
        assert want.lock is True
        assert have is None

    def test_locked_entry_protects_live_resource_from_delete(self) -> None:
        desired = [
            _vlan("ixl0", 4000, lock=True),
            _vlan("igb1", 100, desc="new"),
        ]
        current = [
            _live("u1", "ixl0", 4000),
            _live("u2", "igb0", 99),
        ]
        diff = compute_diff(desired, current)
        assert len(diff.adds) == 1
        assert diff.adds[0].tag == 100
        assert len(diff.deletes) == 1
        assert diff.deletes[0].uuid == "u2"
        assert len(diff.locked) == 1

    def test_add_only_suppresses_deletes(self) -> None:
        desired = [_vlan("igb1", 100)]
        current = [
            _live("u1", "ixl0", 4000),
            _live("u2", "igb0", 99),
        ]
        diff = compute_diff(desired, current, add_only=True)
        assert len(diff.adds) == 1
        assert len(diff.deletes) == 0
        assert diff.locked == []
        assert not diff.is_empty

    def test_add_only_still_emits_updates(self) -> None:
        desired = [_vlan("igb0", 10, desc="new")]
        current = [_live("u1", "igb0", 10, desc="old")]
        diff = compute_diff(desired, current, add_only=True)
        assert len(diff.updates) == 1
        assert len(diff.deletes) == 0

    def test_add_only_combined_with_lock(self) -> None:
        desired = [
            _vlan("ixl0", 4000, lock=True),
            _vlan("igb1", 100, desc="new"),
        ]
        current = [
            _live("u1", "ixl0", 4000),
            _live("u2", "igb0", 99),
        ]
        diff = compute_diff(desired, current, add_only=True)
        assert len(diff.adds) == 1
        assert len(diff.deletes) == 0
        assert len(diff.locked) == 1


class TestDiffIsEmpty:
    def test_empty_diff(self) -> None:
        assert Diff().is_empty

    def test_non_empty_when_adds(self) -> None:
        diff = Diff(adds=[_vlan("igb0", 10)])
        assert not diff.is_empty

    def test_locked_alone_counts_as_empty(self) -> None:
        # Locked entries are observed-only and don't constitute "work".
        want = _vlan("igb0", 10, lock=True)
        diff = Diff(locked=[(want, None)])
        assert diff.is_empty


# ---------------------------------------------------------------------------
# vlan_configs_from_resources
# ---------------------------------------------------------------------------


class TestVlanConfigsFromResources:
    """ResourceConfig -> VlanConfig conversion validates the same fields the spike does."""

    def test_valid_resource_parses(self) -> None:
        resource = _resource("v1", "igb0", 100, description="test", priority=0)
        result = vlan_configs_from_resources([resource])
        assert len(result) == 1
        assert result[0].device == "igb0"
        assert result[0].tag == 100

    def test_non_vlan_resources_ignored(self) -> None:
        vlan = _resource("v1", "igb0", 100)
        alias = ResourceConfig(name="a", type="firewall.aliases", provider="opnsense", config={})
        result = vlan_configs_from_resources([vlan, alias])
        assert len(result) == 1
        assert result[0].name == "v1"

    def test_missing_required_field(self) -> None:
        bad = ResourceConfig(
            name="v1",
            type="interfaces.vlans",
            provider="opnsense",
            config={"device": "igb0", "tag": 10, "description": "x"},  # priority missing
        )
        with pytest.raises(ValueError, match="priority"):
            vlan_configs_from_resources([bad])

    def test_tag_out_of_range_high(self) -> None:
        bad = _resource("v1", "igb0", 5000)
        with pytest.raises(ValueError, match="tag 5000"):
            vlan_configs_from_resources([bad])

    def test_tag_out_of_range_low(self) -> None:
        bad = _resource("v1", "igb0", 0)
        with pytest.raises(ValueError, match="tag 0"):
            vlan_configs_from_resources([bad])

    def test_priority_out_of_range(self) -> None:
        bad = _resource("v1", "igb0", 10, priority=9)
        with pytest.raises(ValueError, match="priority 9"):
            vlan_configs_from_resources([bad])

    def test_non_integer_tag(self) -> None:
        bad = ResourceConfig(
            name="v1",
            type="interfaces.vlans",
            provider="opnsense",
            config={
                "device": "igb0",
                "tag": "not-an-int",
                "description": "x",
                "priority": 0,
            },
        )
        with pytest.raises(ValueError, match="non-integer"):
            vlan_configs_from_resources([bad])

    def test_empty_device_rejected(self) -> None:
        bad = ResourceConfig(
            name="v1",
            type="interfaces.vlans",
            provider="opnsense",
            config={
                "device": "",
                "tag": 10,
                "description": "x",
                "priority": 0,
            },
        )
        with pytest.raises(ValueError, match="device"):
            vlan_configs_from_resources([bad])

    def test_lock_field_loads_when_present(self) -> None:
        resource = _resource("v1", "igb0", 100, lock=True)
        result = vlan_configs_from_resources([resource])
        assert result[0].lock is True

    def test_lock_default_when_absent(self) -> None:
        resource = _resource("v1", "igb0", 100)
        result = vlan_configs_from_resources([resource])
        assert result[0].lock is False

    def test_lock_must_be_boolean(self) -> None:
        bad = ResourceConfig(
            name="v1",
            type="interfaces.vlans",
            provider="opnsense",
            config={
                "device": "igb0",
                "tag": 10,
                "description": "x",
                "priority": 0,
                "lock": "yes",
            },
        )
        with pytest.raises(ValueError, match="lock must be a boolean"):
            vlan_configs_from_resources([bad])

    def test_description_must_be_string(self) -> None:
        bad = ResourceConfig(
            name="v1",
            type="interfaces.vlans",
            provider="opnsense",
            config={
                "device": "igb0",
                "tag": 10,
                "description": 123,
                "priority": 0,
            },
        )
        with pytest.raises(ValueError, match="description"):
            vlan_configs_from_resources([bad])


# ---------------------------------------------------------------------------
# _row_to_live_vlan
# ---------------------------------------------------------------------------


class TestRowToLiveVlan:
    """Row normalization handles strings, missing keys, and non-numeric values."""

    def test_normal_row(self) -> None:
        row = {"uuid": "u1", "if": "igb0", "tag": "100", "descr": "v100", "pcp": "3"}
        live = _row_to_live_vlan(row)
        assert live.uuid == "u1"
        assert live.device == "igb0"
        assert live.tag == 100
        assert live.priority == 3

    def test_non_numeric_tag_falls_back_to_zero(self) -> None:
        row = {"uuid": "u1", "if": "igb0", "tag": "not-int"}
        live = _row_to_live_vlan(row)
        assert live.tag == 0

    def test_missing_keys_default(self) -> None:
        live = _row_to_live_vlan({})
        assert live.uuid == ""
        assert live.device == ""
        assert live.tag == 0


# ---------------------------------------------------------------------------
# VlanService API methods
# ---------------------------------------------------------------------------


class TestVlanServiceAPIDispatch:
    """The service issues the correct ``client.request`` calls."""

    def test_search_calls_post_searchitem(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        service = VlanService(client)
        result = service.search()
        client.request.assert_called_once_with("POST", "interfaces/vlan_settings/searchItem")
        assert result == []

    def test_search_normalizes_rows(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"uuid": "u1", "if": "igb0", "tag": "10", "descr": "v10", "pcp": "0"},
                "not-a-dict",  # filtered out
                {"uuid": "u2", "if": "igb1", "tag": "20", "descr": "v20", "pcp": "3"},
            ]
        }
        service = VlanService(client)
        result = service.search()
        assert len(result) == 2
        assert {r.uuid for r in result} == {"u1", "u2"}

    def test_search_empty_response(self) -> None:
        client = MagicMock()
        client.request.return_value = {}
        service = VlanService(client)
        assert service.search() == []

    def test_add_posts_payload(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved", "uuid": "new-uuid"}
        service = VlanService(client)
        v = _vlan("igb0", 100, desc="hello", pcp=3)
        result = service.add(v)
        client.request.assert_called_once_with(
            "POST", "interfaces/vlan_settings/addItem", data=v.to_payload()
        )
        assert result["uuid"] == "new-uuid"

    def test_update_posts_with_uuid_in_path(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        service = VlanService(client)
        v = _vlan("igb0", 100, desc="hello")
        service.update("uuid-abc", v)
        client.request.assert_called_once_with(
            "POST",
            "interfaces/vlan_settings/setItem/uuid-abc",
            data=v.to_payload(),
        )

    def test_delete_posts_with_uuid_in_path(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "deleted"}
        service = VlanService(client)
        service.delete("uuid-xyz")
        client.request.assert_called_once_with("POST", "interfaces/vlan_settings/delItem/uuid-xyz")

    def test_reconfigure(self) -> None:
        client = MagicMock()
        client.request.return_value = {"status": "ok"}
        service = VlanService(client)
        service.reconfigure()
        client.request.assert_called_once_with("POST", "interfaces/vlan_settings/reconfigure")


# ---------------------------------------------------------------------------
# apply_diff orchestration
# ---------------------------------------------------------------------------


class TestApplyDiff:
    """``apply_diff`` dispatches add/update/delete and reconfigures once."""

    def test_empty_diff_is_a_noop(self) -> None:
        client = MagicMock()
        service = VlanService(client)
        counts = service.apply_diff(Diff())
        # No mutations, no reconfigure.
        client.request.assert_not_called()
        assert counts == {"created": 0, "updated": 0, "deleted": 0}

    def test_dispatches_add_then_reconfigure(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        service = VlanService(client)
        diff = Diff(adds=[_vlan("igb0", 10)])
        counts = service.apply_diff(diff)
        # addItem then reconfigure.
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "interfaces/vlan_settings/addItem" in endpoints
        assert "interfaces/vlan_settings/reconfigure" in endpoints
        assert counts["created"] == 1

    def test_dispatches_update(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "saved"}
        service = VlanService(client)
        live = _live("u1", "igb0", 10, desc="old")
        want = _vlan("igb0", 10, desc="new")
        diff = Diff(updates=[(live, want)])
        counts = service.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "interfaces/vlan_settings/setItem/u1" in endpoints
        assert counts["updated"] == 1

    def test_dispatches_delete(self) -> None:
        client = MagicMock()
        client.request.return_value = {"result": "deleted"}
        service = VlanService(client)
        live = _live("u1", "igb0", 10)
        diff = Diff(deletes=[live])
        counts = service.apply_diff(diff)
        endpoints = [c.args[1] for c in client.request.call_args_list]
        assert "interfaces/vlan_settings/delItem/u1" in endpoints
        assert counts["deleted"] == 1

    def test_reconfigure_only_called_when_changes(self) -> None:
        client = MagicMock()
        service = VlanService(client)
        service.apply_diff(Diff())
        # Even with reconfigure being available, an empty diff doesn't call it.
        for call in client.request.call_args_list:
            assert call.args[1] != "interfaces/vlan_settings/reconfigure"


class TestComputeDiffViaServiceMethod:
    """Service method ``compute_diff`` mirrors the module-level helper."""

    def test_service_compute_diff_matches_function(self) -> None:
        client = MagicMock()
        service = VlanService(client)
        desired = [_vlan("igb0", 10)]
        live: list[LiveVlan] = []
        result = service.compute_diff(desired, live, add_only=False)
        expected = compute_diff(desired, live, add_only=False)
        assert result.adds == expected.adds


# ---------------------------------------------------------------------------
# export_to_yaml
# ---------------------------------------------------------------------------


class TestExportToYaml:
    """Live VLANs render as nested ``opnsense:`` YAML (ADR-0016, #793 Phase 4)."""

    def test_export_renders_yaml(self) -> None:
        client = MagicMock()
        client.request.return_value = {
            "rows": [
                {"uuid": "u1", "if": "igb0", "tag": "10", "descr": "vlan10", "pcp": "0"},
            ]
        }
        service = VlanService(client)
        text = service.export_to_yaml()
        assert "vlan-igb0-10" in text
        assert "device: igb0" in text
        assert "tag: 10" in text
        # Nested format: VLANs land at opnsense.interfaces.vlans (per ADR-0016).
        assert "opnsense:" in text
        assert "interfaces:" in text
        assert "vlans:" in text

    def test_export_with_no_vlans_yields_empty_resources(self) -> None:
        client = MagicMock()
        client.request.return_value = {"rows": []}
        service = VlanService(client)
        text = service.export_to_yaml()
        # Empty leaf list at opnsense.interfaces.vlans.
        assert "vlans: []" in text
