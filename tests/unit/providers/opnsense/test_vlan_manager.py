"""Unit tests for ``VlanManager``.

Coverage:
    - plan/apply/destroy delegate to VlanService correctly.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes.
    - get_resource_ids maps live UUIDs to operator-facing names.
    - migrate exports YAML.
    - lock semantics honored on destroy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome
from infrafoundry.providers.opnsense.components.vlan import VlanManager
from infrafoundry.providers.opnsense.services.vlan import (
    Diff,
    LiveVlan,
    VlanConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(name: str, device: str, tag: int, *, lock: bool = False) -> ResourceConfig:
    config: dict[str, Any] = {
        "device": device,
        "tag": tag,
        "description": "test",
        "priority": 0,
    }
    if lock:
        config["lock"] = True
    return ResourceConfig(name=name, type="interfaces.vlans", provider="opnsense", config=config)


SERVICE_PATH = "infrafoundry.providers.opnsense.components.vlan.VlanService"


def _make_service_mock(
    *,
    live: list[LiveVlan] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mocked ``VlanService`` with sensible defaults."""
    service = MagicMock()
    service.search.return_value = live if live is not None else []
    service.compute_diff.return_value = diff if diff is not None else Diff()
    service.apply_diff.return_value = (
        apply_counts if apply_counts is not None else {"created": 0, "updated": 0, "deleted": 0}
    )
    return service


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class TestVlanManagerPlan:
    def test_plan_returns_diff(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources = [_resource("v1", "igb0", 10)]
        diff = Diff(adds=[VlanConfig("v1", "igb0", 10, "test", 0)])
        service_mock = _make_service_mock(diff=diff)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", resources)
        assert result.adds == diff.adds
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)
        service_mock.compute_diff.assert_called_once()

    def test_plan_threads_add_only(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources = [_resource("v1", "igb0", 10)]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources, add_only=True)
        # add_only kwarg propagated to service.compute_diff.
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestVlanManagerApply:
    def test_apply_returns_counts(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources = [_resource("v1", "igb0", 10)]
        diff = Diff(adds=[VlanConfig("v1", "igb0", 10, "test", 0)])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        assert result["resources_created"] == 1
        assert result["resources_updated"] == 0
        assert result["resources_deleted"] == 0
        assert result["success"] is True

    def test_apply_emits_add_outcome(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources = [_resource("v1", "igb0", 10)]
        diff = Diff(adds=[VlanConfig("v1", "igb0", 10, "test", 0)])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "add"
        assert outcomes[0].resource_name == "v1"
        assert outcomes[0].address == "opnsense_vlan.v1"

    def test_apply_emits_update_outcome(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources = [_resource("v1", "igb0", 10)]
        live = LiveVlan(uuid="u1", device="igb0", tag=10, description="old", priority=0)
        want = VlanConfig("v1", "igb0", 10, "new", 0)
        diff = Diff(updates=[(live, want)])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 1, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "update"
        assert outcomes[0].resource_name == "v1"

    def test_apply_emits_delete_outcome_with_synthetic_name(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = LiveVlan(uuid="u1", device="igb0", tag=99, description="dead", priority=0)
        diff = Diff(deletes=[live])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 0, "deleted": 1}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes: list[ResourceOutcome] = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "delete"
        assert outcomes[0].resource_name == "vlan-igb0-99"

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources = [_resource("v1", "igb0", 10)]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestVlanManagerDestroy:
    def test_destroy_deletes_matching_live_vlans(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources = [_resource("v1", "igb0", 10)]
        live = LiveVlan(uuid="u1", device="igb0", tag=10, description="x", priority=0)
        service_mock = _make_service_mock(live=[live])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_called_once_with("u1")
        service_mock.reconfigure.assert_called_once()
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0

    def test_destroy_skips_when_no_live_match(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources = [_resource("v1", "igb0", 10)]
        service_mock = _make_service_mock(live=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.reconfigure.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources = [_resource("wan-trunk", "ixl0", 4000, lock=True)]
        live = LiveVlan(uuid="u1", device="ixl0", tag=4000, description="x", priority=0)
        service_mock = _make_service_mock(live=[live])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.reconfigure.assert_not_called()
        assert result["locked_skipped"] == 1


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestVlanManagerGetResourceIds:
    def test_maps_names_to_uuids(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources = [_resource("v1", "igb0", 10), _resource("v2", "igb0", 20)]
        live = [
            LiveVlan(uuid="u1", device="igb0", tag=10, description="x", priority=0),
            LiveVlan(uuid="u2", device="igb0", tag=20, description="x", priority=0),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"v1": "u1", "v2": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        resources = [_resource("v1", "igb0", 10), _resource("v2", "igb0", 20)]
        live = [LiveVlan(uuid="u1", device="igb0", tag=10, description="x", priority=0)]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"v1": "u1"}


# ---------------------------------------------------------------------------
# list / migrate
# ---------------------------------------------------------------------------


class TestVlanManagerListAndMigrate:
    def test_list_returns_live_vlans(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        live = [LiveVlan(uuid="u1", device="igb0", tag=10, description="x", priority=0)]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        assert result == live

    def test_migrate_returns_yaml_string(self, tmp_path: Path) -> None:
        manager = VlanManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")
        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once()
