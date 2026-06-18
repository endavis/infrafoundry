"""Unit tests for ``CronJobsManager`` (#789).

Manager (``CronJobsManager``):
    - test_plan_no_change
    - test_plan_add
    - test_plan_update
    - test_plan_delete
    - test_plan_full_reconcile
    - test_plan_add_only_suppresses_deletes
    - test_apply_returns_correct_counts
    - test_apply_resource_outcomes
    - test_apply_does_not_call_reconfigure
    - test_destroy_deletes_locked_skipped
    - test_destroy_calls_reconfigure_directly
    - test_destroy_no_reconfigure_when_nothing_deleted
    - test_get_resource_ids
    - test_finalization_hook_declared
    - test_migrate_delegates_to_service

The manager tests patch ``CronJobsService.from_environment`` so each test
hands the manager a pre-built mock with whatever live state is needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.cron_jobs import CronJobsManager
from infrafoundry.providers.opnsense.services.cron_jobs import (
    CronJobConfig,
    Diff,
    LiveCronJob,
)

SERVICE_PATH = "infrafoundry.providers.opnsense.components.cron_jobs.CronJobsService"

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _resource(
    name: str = "acmeclient-auto-renew",
    *,
    config: dict[str, Any] | None = None,
) -> ResourceConfig:
    if config is None:
        config = {
            "enabled": True,
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "acmeclient cron-auto-renew",
            "origin": "AcmeClient",
        }
    return ResourceConfig(name=name, type="cron.jobs", provider="opnsense", config=config)


def _config(
    name: str = "acmeclient-auto-renew",
    *,
    command: str = "acmeclient cron-auto-renew",
    hours: str = "2",
    lock: bool = False,
) -> CronJobConfig:
    return CronJobConfig(
        name=name,
        enabled=True,
        minutes="0",
        hours=hours,
        days="*",
        months="*",
        weekdays="*",
        who="root",
        command=command,
        origin="AcmeClient",
        lock=lock,
    )


def _live_job(
    uuid: str = "uuid-1",
    managed_name: str = "acmeclient-auto-renew",
) -> LiveCronJob:
    raw: dict[str, Any] = {
        "uuid": uuid,
        "description": f"[infrafoundry:{managed_name}]",
        "enabled": "1",
        "minutes": "0",
        "hours": "2",
        "days": "*",
        "months": "*",
        "weekdays": "*",
        "who": "root",
        "command": "acmeclient cron-auto-renew",
        "parameters": "",
        "origin": "AcmeClient",
    }
    return LiveCronJob(
        uuid=uuid, managed_name=managed_name, description="", origin="AcmeClient", raw=raw
    )


def _make_service_mock(
    *,
    live: list[LiveCronJob] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a CronJobsService mock with pre-set return values."""
    service: MagicMock = MagicMock()
    service.search.return_value = live if live is not None else []
    service.compute_diff.return_value = diff if diff is not None else Diff()
    service.apply_diff.return_value = (
        apply_counts if apply_counts is not None else {"created": 0, "updated": 0, "deleted": 0}
    )
    return service


# ---------------------------------------------------------------------------
# Manager: plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_no_change(self, tmp_path: Path) -> None:
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(live=[_live_job()], diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert diff.is_empty

    def test_plan_add(self, tmp_path: Path) -> None:
        job = _config()
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(live=[], diff=Diff(adds=[job]))
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "acmeclient-auto-renew"

    def test_plan_update(self, tmp_path: Path) -> None:
        live = _live_job()
        want = _config(hours="3")
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(live=[live], diff=Diff(updates=[(live, want)]))
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert len(diff.updates) == 1
        assert diff.updates[0][1].hours == "3"

    def test_plan_delete(self, tmp_path: Path) -> None:
        live = _live_job()
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(live=[live], diff=Diff(deletes=[live]))
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [])
        assert len(diff.deletes) == 1

    def test_plan_full_reconcile(self, tmp_path: Path) -> None:
        """add + update + delete combined in one diff."""
        live1 = _live_job(uuid="u1", managed_name="job-to-update")
        live2 = _live_job(uuid="u2", managed_name="job-to-delete")
        add_cfg = _config(name="new-job", command="new-cmd")
        update_cfg = _config(name="job-to-update", hours="3")
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(
            live=[live1, live2],
            diff=Diff(adds=[add_cfg], updates=[(live1, update_cfg)], deletes=[live2]),
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            diff = manager.plan("test-env", [_resource()])
        assert len(diff.adds) == 1
        assert len(diff.updates) == 1
        assert len(diff.deletes) == 1

    def test_plan_add_only_suppresses_deletes(self, tmp_path: Path) -> None:
        """add_only=True: the flag is forwarded to compute_diff."""
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            manager.plan("test-env", [_resource()], add_only=True)
        service.compute_diff.assert_called_once()
        kwargs = service.compute_diff.call_args.kwargs
        assert kwargs.get("add_only") is True

    def test_plan_passes_env_to_from_environment(self, tmp_path: Path) -> None:
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock()
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            manager.plan("prod", [_resource()], provider_name="opnsense")
        svc_cls.from_environment.assert_called_once_with("prod", "opnsense", tmp_path)


# ---------------------------------------------------------------------------
# Manager: apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_returns_correct_counts(self, tmp_path: Path) -> None:
        add_cfg = _config(name="new-job", command="new-cmd")
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(
            diff=Diff(adds=[add_cfg]),
            apply_counts={"created": 1, "updated": 0, "deleted": 0},
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])
        assert result["resources_created"] == 1
        assert result["resources_updated"] == 0
        assert result["resources_deleted"] == 0
        assert result["success"] is True

    def test_apply_resource_outcomes(self, tmp_path: Path) -> None:
        add_cfg = _config(name="new-job", command="new-cmd")
        live = _live_job()
        want = _config(hours="3")
        del_live = _live_job(uuid="u-del", managed_name="old-job")
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(
            diff=Diff(adds=[add_cfg], updates=[(live, want)], deletes=[del_live]),
            apply_counts={"created": 1, "updated": 1, "deleted": 1},
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.apply("test-env", [_resource()])

        outcomes = result["resource_outcomes"]
        actions = [(o.action, o.resource_name) for o in outcomes]
        assert ("add", "new-job") in actions
        assert ("update", "acmeclient-auto-renew") in actions
        assert ("delete", "old-job") in actions

    def test_apply_does_not_call_reconfigure(self, tmp_path: Path) -> None:
        """apply must NOT call service.reconfigure() — the runner fires the hook."""
        add_cfg = _config(name="new-job", command="new-cmd")
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(
            diff=Diff(adds=[add_cfg]),
            apply_counts={"created": 1, "updated": 0, "deleted": 0},
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            manager.apply("test-env", [_resource()])
        service.reconfigure.assert_not_called()

    def test_apply_calls_apply_diff(self, tmp_path: Path) -> None:
        manager = CronJobsManager(tmp_path)
        diff = Diff(adds=[_config(name="j1", command="c1")])
        service = _make_service_mock(
            diff=diff,
            apply_counts={"created": 1, "updated": 0, "deleted": 0},
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            manager.apply("test-env", [_resource()])
        service.apply_diff.assert_called_once_with(diff)


# ---------------------------------------------------------------------------
# Manager: destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_live_jobs(self, tmp_path: Path) -> None:
        live = _live_job()
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(live=[live])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.destroy("test-env", [_resource()])
        service.delete.assert_called_once_with("uuid-1")
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0

    def test_destroy_calls_reconfigure_directly(self, tmp_path: Path) -> None:
        """destroy calls service.reconfigure() directly (not via hook)."""
        live = _live_job()
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(live=[live])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            manager.destroy("test-env", [_resource()])
        service.reconfigure.assert_called_once()

    def test_destroy_no_reconfigure_when_nothing_deleted(self, tmp_path: Path) -> None:
        """No live matching jobs → reconfigure not called."""
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(live=[])  # empty live
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            manager.destroy("test-env", [_resource()])
        service.reconfigure.assert_not_called()

    def test_destroy_locked_skipped(self, tmp_path: Path) -> None:
        """Locked resources skip delete and increment locked_skipped."""
        live = _live_job()
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(live=[live])
        locked_resource = _resource(
            config={
                "enabled": True,
                "minutes": "0",
                "hours": "2",
                "days": "*",
                "months": "*",
                "weekdays": "*",
                "who": "root",
                "command": "acmeclient cron-auto-renew",
                "origin": "AcmeClient",
                "lock": True,
            }
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.destroy("test-env", [locked_resource])
        service.delete.assert_not_called()
        service.reconfigure.assert_not_called()
        assert result["locked_skipped"] == 1
        assert result["resources_destroyed"] == 0


# ---------------------------------------------------------------------------
# Manager: get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_get_resource_ids(self, tmp_path: Path) -> None:
        live = _live_job(uuid="uuid-abc")
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(live=[live])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {"acmeclient-auto-renew": "uuid-abc"}

    def test_get_resource_ids_missing_from_live(self, tmp_path: Path) -> None:
        """Job not on the box is absent from the result dict."""
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock(live=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.get_resource_ids("test-env", [_resource()])
        assert result == {}


# ---------------------------------------------------------------------------
# Manager: finalization hook
# ---------------------------------------------------------------------------


class TestFinalizationHook:
    def test_finalization_hook_declared(self) -> None:
        """CronJobsManager.FINALIZATION_HOOK == 'cron_reconfigure'."""
        assert CronJobsManager.FINALIZATION_HOOK == "cron_reconfigure"


# ---------------------------------------------------------------------------
# Manager: migrate
# ---------------------------------------------------------------------------


class TestMigrate:
    def test_migrate_delegates_to_service(self, tmp_path: Path) -> None:
        """migrate() calls service.export_to_yaml() and returns its output."""
        expected_yaml = "opnsense:\n  cron:\n    jobs: []\n"
        manager = CronJobsManager(tmp_path)
        service = _make_service_mock()
        service.export_to_yaml.return_value = expected_yaml
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service
            result = manager.migrate("test-env")
        assert result == expected_yaml
        service.export_to_yaml.assert_called_once()
