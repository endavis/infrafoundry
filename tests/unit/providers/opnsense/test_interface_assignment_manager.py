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
from infrafoundry.providers.opnsense.services._credentials import reset_warning_state_for_tests
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
    device: str = "vtnet1",
    description: str = "",
    extra: dict[str, Any] | None = None,
) -> ResourceConfig:
    config: dict[str, Any] = {"device": device, "description": description}
    if extra:
        config.update(extra)
    return ResourceConfig(
        name=name, type="interfaces.assignments", provider="opnsense", config=config
    )


def _live(identifier: str, device: str = "vtnet1") -> LiveInterfaceAssignment:
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


def _cfg(name: str, *, device: str = "vtnet1", description: str = "") -> InterfaceAssignmentConfig:
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


_SSH_ENV_VARS = (
    "OPNSENSE_SSH_HOST",
    "OPNSENSE_SSH_USER",
    "OPNSENSE_SSH_PORT",
    "OPNSENSE_SSH_KEY",
    "OPNSENSE_API_URL",
    "INFRAFOUNDRY_ALLOW_ENV_OVERRIDE",
)


@pytest.fixture(autouse=True)
def provider_settings(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Isolate SSH resolution from the real environment and settings files.

    Clears the SSH/API env vars and the override gate, and patches the
    manager's settings loader to return a mutable dict (initially just an
    ``api_url``) that tests may edit.
    """
    for var in _SSH_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    reset_warning_state_for_tests()
    settings: dict[str, Any] = {"api_url": "https://fw.test"}
    monkeypatch.setattr(
        InterfaceAssignmentManager,
        "_load_provider_settings",
        lambda self, env_name, provider_name: settings,
    )
    return settings


@pytest.fixture
def ssh_env() -> None:
    """Marker for tests that write: the autouse settings already carry an ``api_url``."""


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_returns_diff(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        diff = Diff(adds=[_cfg("opt5", device="em0")])
        service_mock = _make_service_mock(diff=diff)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", [_resource("opt5", device="em0")])
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
        diff = Diff(adds=[_cfg("opt5", device="em0")])
        service_mock = _make_service_mock(diff=diff, apply_result=ApplyDiffResult(created=1))
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", [_resource("opt5", device="em0")])
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
        diff = Diff(adds=[_cfg("opt5", device="em0")])
        service_mock = _make_service_mock(diff=diff, apply_result=ApplyDiffResult(created=1))
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", [_resource("opt5", device="em0")])
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "add"
        assert outcomes[0].resource_name == "opt5"
        assert outcomes[0].address == "opnsense_interface_assignment.opt5"

    def test_apply_emits_update_outcome(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        live = _live("opt3", device="em0")
        want = _cfg("opt3", device="em1", description="new")
        diff = Diff(updates=[(live, want)])
        service_mock = _make_service_mock(diff=diff, apply_result=ApplyDiffResult(updated=1))
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", [_resource("opt3", device="em1")])
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "update"
        assert outcomes[0].resource_name == "opt3"
        assert outcomes[0].address == "opnsense_interface_assignment.opt3"

    def test_apply_emits_delete_outcome_with_live_identifier(
        self, tmp_path: Path, ssh_env: None
    ) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        live = _live("opt9", device="em7")
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
        self, tmp_path: Path, provider_settings: dict[str, Any]
    ) -> None:
        # No ssh_host and no api_url: no host can resolve.
        provider_settings.clear()
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = _make_service_mock(diff=Diff(adds=[_cfg("opt5")]))
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            with pytest.raises(RuntimeError) as exc_info:
                manager.apply("test-env", [_resource("opt5")])
            assert "SSH credentials" in str(exc_info.value)
            assert "OPNSENSE_SSH_HOST" in str(exc_info.value)
            # Installer and writes must not run when the pre-flight raises.
            inst.ensure_installed.assert_not_called()
            service_mock.apply_diff.assert_not_called()

    def test_apply_passes_when_only_api_url_set(self, tmp_path: Path) -> None:
        # The settings api_url alone is enough: the SSH host is its hostname.
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = _make_service_mock(diff=Diff(adds=[_cfg("opt5")]))
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", [_resource("opt5")])
        inst.ensure_installed.assert_called_once()
        target = inst.ensure_installed.call_args.args[0]
        assert target.host == "fw.test"

    def test_apply_passes_settings_ssh_host_to_installer(
        self, tmp_path: Path, provider_settings: dict[str, Any]
    ) -> None:
        # WAN-443 / LAN-SSH case: the API host is not where sshd listens.
        provider_settings.update(
            {"api_url": "https://172.20.99.1", "ssh_host": "172.20.10.250", "ssh_user": "admin"}
        )
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = _make_service_mock(diff=Diff(adds=[_cfg("opt5")]))
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", [_resource("opt5")])
        inst.ensure_installed.assert_called_once()
        target = inst.ensure_installed.call_args.args[0]
        assert target.host == "172.20.10.250"
        assert target.user == "admin"

    def test_apply_ignores_ungated_env_ssh_host(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPNSENSE_SSH_HOST", "203.0.113.9")
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = _make_service_mock(diff=Diff(adds=[_cfg("opt5")]))
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", [_resource("opt5")])
        assert inst.ensure_installed.call_args.args[0].host == "fw.test"

    def test_apply_empty_diff_skips_preflight_and_install(
        self, tmp_path: Path, provider_settings: dict[str, Any]
    ) -> None:
        provider_settings.clear()
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = _make_service_mock(diff=Diff())
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", [_resource("opt5")])
        inst.ensure_installed.assert_not_called()
        assert result["success"] is True

    def test_apply_lists_before_installing(self, tmp_path: Path, ssh_env: None) -> None:
        calls: list[str] = []
        service_mock = _make_service_mock(diff=Diff(adds=[_cfg("opt5")]))

        def _list() -> list[LiveInterfaceAssignment]:
            calls.append("list")
            return []

        def _apply_diff(_diff: Diff) -> ApplyDiffResult:
            calls.append("apply_diff")
            return ApplyDiffResult(created=1)

        service_mock.list.side_effect = _list
        service_mock.apply_diff.side_effect = _apply_diff
        manager = InterfaceAssignmentManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            inst.ensure_installed.side_effect = lambda _target: calls.append("install")
            manager.apply("test-env", [_resource("opt5")])
        assert calls == ["list", "install", "apply_diff"]

    # ------------------------------------------------------------------
    # Lockout pre-flight
    # ------------------------------------------------------------------

    def test_apply_refuses_on_lockout_conflict(self, tmp_path: Path, ssh_env: None) -> None:
        # Adding opt5 -> em0 but em0 is already bound to opt9.
        live = _live("opt9", device="em0")
        diff = Diff(adds=[_cfg("opt5", device="em0")])
        service_mock = _make_service_mock(live=[live], diff=diff)
        manager = InterfaceAssignmentManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            with pytest.raises(RuntimeError, match="lockout"):
                manager.apply("test-env", [_resource("opt5", device="em0")])
        # No add was dispatched — the pre-flight fired before apply_diff.
        service_mock.apply_diff.assert_not_called()

    def test_apply_lockout_conflict_raises_before_install(
        self, tmp_path: Path, ssh_env: None
    ) -> None:
        live = _live("opt9", device="em0")
        diff = Diff(adds=[_cfg("opt5", device="em0")])
        service_mock = _make_service_mock(live=[live], diff=diff)
        manager = InterfaceAssignmentManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            with pytest.raises(RuntimeError, match="lockout"):
                manager.apply("test-env", [_resource("opt5", device="em0")])
        inst.ensure_installed.assert_not_called()


# ---------------------------------------------------------------------------
# apply — deletes_only (runner delete phase, #1271)
# ---------------------------------------------------------------------------


class TestDeletesOnly:
    def test_split_marker(self) -> None:
        assert InterfaceAssignmentManager.SPLIT_DELETE_PHASE is True

    def test_deletes_only_drops_adds_and_updates(self, tmp_path: Path, ssh_env: None) -> None:
        live = _live("opt9", device="em7")
        diff = Diff(
            adds=[_cfg("opt5")],
            updates=[(_live("opt3"), _cfg("opt3", device="em1"))],
            deletes=[live],
        )
        service_mock = _make_service_mock(diff=diff, apply_result=ApplyDiffResult(deleted=1))
        manager = InterfaceAssignmentManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", [_resource("opt5")], deletes_only=True)
        sent = service_mock.apply_diff.call_args.args[0]
        assert sent.adds == []
        assert sent.updates == []
        assert sent.deletes == [live]
        assert [o.action for o in result["resource_outcomes"]] == ["delete"]
        inst.ensure_installed.assert_called_once()

    def test_deletes_only_without_deletes_needs_no_ssh(
        self, tmp_path: Path, provider_settings: dict[str, Any]
    ) -> None:
        provider_settings.clear()
        service_mock = _make_service_mock(diff=Diff(adds=[_cfg("opt5")]))
        manager = InterfaceAssignmentManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", [_resource("opt5")], deletes_only=True)
        inst.ensure_installed.assert_not_called()
        assert result["resource_outcomes"] == []

    def test_add_only_forward_pass_with_adds_installs_once(
        self, tmp_path: Path, ssh_env: None
    ) -> None:
        service_mock = _make_service_mock(
            diff=Diff(adds=[_cfg("opt5")]), apply_result=ApplyDiffResult(created=1)
        )
        manager = InterfaceAssignmentManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
        ):
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", [_resource("opt5")], add_only=True)
        inst.ensure_installed.assert_called_once()

    # ------------------------------------------------------------------
    # Partial-failure path
    # ------------------------------------------------------------------

    def test_apply_surfaces_partial_failure_message(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        diff = Diff(
            adds=[_cfg("opt5", device="em0"), _cfg("opt6", device="em1")],
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
                [_resource("opt5", device="em0"), _resource("opt6", device="em1")],
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
        live = _live("opt5", device="em0")
        service_mock = _make_service_mock(live=[live])
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", [_resource("opt5", device="em0")])
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
            result = manager.destroy("test-env", [_resource("opt5", device="em0")])
        service_mock.delete.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path, ssh_env: None) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        live = _live("lan", device="vtnet0")
        service_mock = _make_service_mock(live=[live])
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH),
        ):
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy(
                "test-env",
                [_resource("lan", device="vtnet0", extra={"lock": True})],
            )
        service_mock.delete.assert_not_called()
        assert result["locked_skipped"] == 1
        assert result["resources_destroyed"] == 0

    def test_destroy_raises_when_ssh_missing(
        self, tmp_path: Path, provider_settings: dict[str, Any]
    ) -> None:
        provider_settings.clear()
        manager = InterfaceAssignmentManager(tmp_path)
        with (
            patch(SERVICE_PATH) as svc_cls,
            patch(INSTALLER_PATH) as inst,
            pytest.raises(RuntimeError, match="SSH credentials"),
        ):
            manager.destroy("test-env", [_resource("opt5")])
        inst.ensure_installed.assert_not_called()
        svc_cls.from_environment.assert_not_called()


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_resource_name_to_live_identifier(self, tmp_path: Path) -> None:
        manager = InterfaceAssignmentManager(tmp_path)
        service_mock = MagicMock()
        service_mock.list.return_value = [_live("lan"), _live("wan", device="vtnet0")]
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            ids = manager.get_resource_ids(
                "test-env", [_resource("lan"), _resource("wan", device="vtnet0")]
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
        live = [_live("lan"), _live("wan", device="vtnet0")]
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
