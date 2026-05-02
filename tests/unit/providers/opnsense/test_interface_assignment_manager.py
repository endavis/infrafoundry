"""Unit tests for ``InterfaceAssignmentManager``.

Coverage:
    - plan/apply/destroy are loud no-ops returning success and informational messages.
    - get_resource_ids maps operator names to live identifiers via the service.
    - list/migrate delegate to ``InterfaceAssignmentService``.
    - Result shape matches what the runner expects (counts + ``message``).
    - The ``ReadOnlyDiff`` helper has the surface the runner's plan summary expects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.interface_assignment import (
    InterfaceAssignmentManager,
    ReadOnlyDiff,
)
from infrafoundry.providers.opnsense.services.interface_assignment import (
    LiveInterfaceAssignment,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(
    name: str,
    *,
    device: str = "ixl1",
    description: str = "",
    extra: dict[str, Any] | None = None,
) -> ResourceConfig:
    config: dict[str, Any] = {"device": device, "description": description}
    if extra:
        config.update(extra)
    return ResourceConfig(
        name=name, type="interface_assignments", provider="opnsense", config=config
    )


def _live(identifier: str, device: str = "ixl1") -> LiveInterfaceAssignment:
    return LiveInterfaceAssignment(
        identifier=identifier,
        device=device,
        description=identifier.upper(),
        is_physical=True,
        ipv4={},
        ipv6={},
        macaddr="00:11:22:33:44:55",
        mtu=1500,
    )


SERVICE_PATH = (
    "infrafoundry.providers.opnsense.components.interface_assignment.InterfaceAssignmentService"
)


# ---------------------------------------------------------------------------
# ReadOnlyDiff
# ---------------------------------------------------------------------------


class TestReadOnlyDiff:
    def test_has_runner_recognized_shape(self) -> None:
        diff = ReadOnlyDiff()
        # Runner's plan-summary helper checks read_only first.
        assert diff.read_only is True
        assert "read-only" in diff.message
        # All operation lists are empty so summary aggregation works.
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert diff.locked == []
        # is_empty drives runner's has_changes aggregation.
        assert diff.is_empty is True


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_returns_read_only_diff(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        diff = manager.plan("test-env", [_resource("lan")])
        assert isinstance(diff, ReadOnlyDiff)
        assert diff.is_empty is True
        assert diff.read_only is True

    def test_does_not_call_service(self, tmp_path: Path) -> None:
        # plan is purely informational — no API call should fire.
        manager = InterfaceAssignmentManager(tmp_path)
        with patch(SERVICE_PATH) as svc_cls:
            manager.plan("test-env", [_resource("lan")])
        svc_cls.from_environment.assert_not_called()

    def test_plan_accepts_add_only_kwarg(self, tmp_path: Path) -> None:
        # The runner threads add_only into manager.plan — even though
        # this manager ignores it, the kwarg must not raise.
        manager = InterfaceAssignmentManager(tmp_path)
        diff = manager.plan("test-env", [_resource("lan")], add_only=True)
        assert isinstance(diff, ReadOnlyDiff)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_returns_zero_counts_and_message(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        result = manager.apply("test-env", [_resource("lan")])
        assert result["success"] is True
        assert result["resources_created"] == 0
        assert result["resources_updated"] == 0
        assert result["resources_deleted"] == 0
        assert result["resource_outcomes"] == []
        assert "read-only" in result["message"]
        assert "1 assignment" in result["message"]

    def test_pluralization_on_zero_assignments(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        result = manager.apply("test-env", [])
        # "0 assignments" is grammatical English; we use 's' suffix when count != 1.
        assert "0 assignments" in result["message"]

    def test_pluralization_on_multiple_assignments(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        result = manager.apply("test-env", [_resource("lan"), _resource("wan", device="ixl0")])
        assert "2 assignments" in result["message"]

    def test_apply_does_not_call_service(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        with patch(SERVICE_PATH) as svc_cls:
            manager.apply("test-env", [_resource("lan")])
        svc_cls.from_environment.assert_not_called()

    def test_apply_accepts_kwargs(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        # Both kwargs the runner threads in must be accepted.
        result = manager.apply("test-env", [_resource("lan")], auto_approve=True, add_only=True)
        assert result["success"] is True


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_returns_zero_destroyed(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        result = manager.destroy("test-env", [_resource("lan")])
        assert result["success"] is True
        assert result["resources_destroyed"] == 0
        assert "read-only" in result["message"]
        assert "nothing destroyed" in result["message"]

    def test_destroy_does_not_call_service(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        with patch(SERVICE_PATH) as svc_cls:
            manager.destroy("test-env", [_resource("lan")])
        svc_cls.from_environment.assert_not_called()


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_resource_name_to_live_identifier(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = MagicMock()
        service_mock.list.return_value = [_live("lan"), _live("wan", device="ixl0")]
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            ids = manager.get_resource_ids(
                "test-env", [_resource("lan"), _resource("wan", device="ixl0")]
            )
        assert ids == {"lan": "lan", "wan": "wan"}

    def test_omits_resources_without_live_match(self, tmp_path: Path) -> None:
        # If YAML names don't appear on the box, omit them — the state DB
        # will skip those updates and they'll surface in validation.
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = MagicMock()
        service_mock.list.return_value = [_live("lan")]
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            ids = manager.get_resource_ids("test-env", [_resource("lan"), _resource("opt99")])
        assert ids == {"lan": "lan"}

    def test_returns_empty_when_no_resources(self, tmp_path: Path) -> None:
        # Should not even hit the service when there's nothing to match.
        manager = InterfaceAssignmentManager(tmp_path)
        with patch(SERVICE_PATH) as svc_cls:
            ids = manager.get_resource_ids("test-env", [])
        assert ids == {}
        svc_cls.from_environment.assert_not_called()

    def test_calls_service_with_env_name(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = MagicMock()
        service_mock.list.return_value = []
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.get_resource_ids("test-env", [_resource("lan")])
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestList:
    def test_returns_service_results(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        live = [_live("lan"), _live("wan", device="ixl0")]
        service_mock = MagicMock()
        service_mock.list.return_value = live
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        assert result == live


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------


class TestMigrate:
    def test_delegates_to_service(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            yaml_str = manager.migrate("test-env")
        assert yaml_str == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once()
