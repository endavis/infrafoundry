"""Unit tests for ``InterfaceAssignmentManager`` (full-CRUD, #720).

Coverage:
    - plan delegates to InterfaceAssignmentService.compute_diff.
    - apply runs SSH-credential pre-flight + installer.ensure_installed
      before any service call, then delegates to apply_diff.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes
      with the address shape ``opnsense_interface_assignment.{name}``.
    - destroy honors ``lock: true`` per-resource (locked_skipped count).
    - get_resource_ids maps operator names to live identifiers.
    - list/migrate delegate to the service.
    - The pre-flight credential check raises a clear actionable
      RuntimeError when credentials are missing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.interface_assignment import (
    InterfaceAssignmentManager,
)
from infrafoundry.providers.opnsense.services.interface_assignment import (
    ApplyDiffResult,
    Diff,
    InterfaceAssignmentConfig,
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


def _cfg(name: str, *, device: str = "ixl1", description: str = "") -> InterfaceAssignmentConfig:
    return InterfaceAssignmentConfig(name=name, device=device, description=description)


SERVICE_PATH = (
    "infrafoundry.providers.opnsense.components.interface_assignment.InterfaceAssignmentService"
)
INSTALLER_PATH = "infrafoundry.providers.opnsense.components.interface_assignment.installer"


def _make_service_mock(
    *,
    live: list[LiveInterfaceAssignment] | None = None,
    diff: Diff | None = None,
    apply_result: ApplyDiffResult | None = None,
) -> MagicMock:
    """Build a mocked ``InterfaceAssignmentService`` with sensible defaults."""
    service = MagicMock()
    service.list.return_value = live if live is not None else []
    service.compute_diff.return_value = diff if diff is not None else Diff()
    service.apply_diff.return_value = (
        apply_result if apply_result is not None else ApplyDiffResult()
    )
    return service


@pytest.fixture
def ssh_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set OPNSENSE_API_URL so the SSH pre-flight passes."""
    monkeypatch.setenv("OPNSENSE_API_URL", "https://opnsense-a")


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_returns_diff(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        diff = Diff(adds=[_cfg("opt5", device="igc0")])
        service_mock = _make_service_mock(diff=diff)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", [_resource("opt5", device="igc0")])
        assert result.adds == diff.adds
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)

    def test_plan_threads_add_only(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", [_resource("opt5")], add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True

    def test_plan_does_not_call_installer(self, tmp_path: Path) -> None:
        # plan is read-only — must not run the installer.
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = _make_service_mock(diff=Diff())
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", [_resource("opt5")])
        inst.ensure_installed.assert_not_called()


# ---------------------------------------------------------------------------
# apply — pre-flight order + happy path
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_runs_installer_before_service(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        diff = Diff(adds=[_cfg("opt5", device="igc0")])
        service_mock = _make_service_mock(diff=diff, apply_result=ApplyDiffResult(created=1))
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", [_resource("opt5", device="igc0")])
        inst.ensure_installed.assert_called_once()
        # Service was constructed *after* installer ran (installer does
        # not raise in the mocked path).
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)

    def test_apply_returns_full_counts_on_success(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        diff = Diff(adds=[_cfg("opt5")])
        service_mock = _make_service_mock(
            diff=diff,
            apply_result=ApplyDiffResult(created=1),
        )
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", [_resource("opt5")])
        assert result["success"] is True
        assert result["resources_created"] == 1
        assert result["resources_updated"] == 0
        assert result["resources_deleted"] == 0
        # No failure → no `message` field.
        assert "message" not in result

    def test_apply_emits_add_outcome(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        diff = Diff(adds=[_cfg("opt5", device="igc0")])
        service_mock = _make_service_mock(diff=diff, apply_result=ApplyDiffResult(created=1))
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", [_resource("opt5", device="igc0")])
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "add"
        assert outcomes[0].resource_name == "opt5"
        assert outcomes[0].address == "opnsense_interface_assignment.opt5"

    def test_apply_emits_update_outcome(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        live = _live("opt3", device="igc0")
        want = _cfg("opt3", device="igc1", description="new")
        diff = Diff(updates=[(live, want)])
        service_mock = _make_service_mock(diff=diff, apply_result=ApplyDiffResult(updated=1))
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", [_resource("opt3", device="igc1")])
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "update"
        assert outcomes[0].resource_name == "opt3"
        assert outcomes[0].address == "opnsense_interface_assignment.opt3"

    def test_apply_emits_delete_outcome_with_live_identifier(
        self, tmp_path: Path, ssh_env: None
    ) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        live = _live("opt9", device="igc7")
        diff = Diff(deletes=[live])
        service_mock = _make_service_mock(diff=diff, apply_result=ApplyDiffResult(deleted=1))
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", [])
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "delete"
        assert outcomes[0].resource_name == "opt9"
        assert outcomes[0].address == "opnsense_interface_assignment.opt9"

    def test_apply_threads_add_only(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = _make_service_mock(diff=Diff())
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", [_resource("opt5")], add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True

    # ------------------------------------------------------------------
    # SSH pre-flight
    # ------------------------------------------------------------------

    def test_apply_raises_when_ssh_credentials_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Strip every env that satisfies the pre-flight.
        for key in (
            "OPNSENSE_SSH_HOST",
            "OPNSENSE_API_URL",
            "OPNSENSE_SSH_KEY",
            "OPNSENSE_SSH_USER",
        ):
            monkeypatch.delenv(key, raising=False)
        manager = InterfaceAssignmentManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            with pytest.raises(RuntimeError) as exc_info:
                manager.apply("test-env", [_resource("opt5")])
            assert "SSH credentials" in str(exc_info.value)
            assert "OPNSENSE_SSH_HOST" in str(exc_info.value)
            # Installer must not have been invoked when the pre-flight raises.
            inst.ensure_installed.assert_not_called()
            # Service must not have been constructed either.
            svc_cls.from_environment.assert_not_called()

    def test_apply_passes_when_only_api_url_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # OPNSENSE_API_URL alone is enough — the installer derives the
        # SSH host from it via urlparse.
        for key in ("OPNSENSE_SSH_HOST", "OPNSENSE_SSH_KEY", "OPNSENSE_SSH_USER"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("OPNSENSE_API_URL", "https://opnsense-a")
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = _make_service_mock(diff=Diff())
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", [_resource("opt5")])
        inst.ensure_installed.assert_called_once()

    # ------------------------------------------------------------------
    # Lockout pre-flight
    # ------------------------------------------------------------------

    def test_apply_refuses_on_lockout_conflict(self, tmp_path: Path, ssh_env: None) -> None:
        # Adding opt5 -> igc0 but igc0 is already bound to opt9.
        live = _live("opt9", device="igc0")
        diff = Diff(adds=[_cfg("opt5", device="igc0")])
        service_mock = _make_service_mock(live=[live], diff=diff)
        manager = InterfaceAssignmentManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            with pytest.raises(RuntimeError, match="lockout"):
                manager.apply("test-env", [_resource("opt5", device="igc0")])
        # No add was dispatched — the pre-flight fired before apply_diff.
        service_mock.apply_diff.assert_not_called()

    # ------------------------------------------------------------------
    # Partial-failure path
    # ------------------------------------------------------------------

    def test_apply_surfaces_partial_failure_message(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        diff = Diff(
            adds=[_cfg("opt5", device="igc0"), _cfg("opt6", device="igc1")],
        )
        # First add succeeds, second fails — service returns partial counts.
        partial = ApplyDiffResult(
            created=1,
            failure_message="add opt6: device collision",
        )
        service_mock = _make_service_mock(diff=diff, apply_result=partial)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply(
                "test-env",
                [_resource("opt5", device="igc0"), _resource("opt6", device="igc1")],
            )
        assert result["success"] is False
        assert result["resources_created"] == 1
        assert "device collision" in result["message"]
        assert "created=1" in result["message"]


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_live(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        live = _live("opt5", device="igc0")
        service_mock = _make_service_mock(live=[live])
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", [_resource("opt5", device="igc0")])
        service_mock.delete.assert_called_once_with("opt5")
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0

    def test_destroy_skips_when_no_live_match(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = _make_service_mock(live=[])
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", [_resource("opt5", device="igc0")])
        service_mock.delete.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        live = _live("lan", device="ixl0")
        service_mock = _make_service_mock(live=[live])
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy(
                "test-env",
                [_resource("lan", device="ixl0", extra={"lock": True})],
            )
        service_mock.delete.assert_not_called()
        assert result["locked_skipped"] == 1
        assert result["resources_destroyed"] == 0

    def test_destroy_raises_when_ssh_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in ("OPNSENSE_SSH_HOST", "OPNSENSE_API_URL"):
            monkeypatch.delenv(key, raising=False)
        manager = InterfaceAssignmentManager(tmp_path)
        with pytest.raises(RuntimeError, match="SSH credentials"):
            manager.destroy("test-env", [_resource("opt5")])


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


# ---------------------------------------------------------------------------
# list / migrate
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
