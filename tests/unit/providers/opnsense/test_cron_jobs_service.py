"""Unit tests for ``infrafoundry.providers.opnsense.services.cron_jobs`` (#789).

Coverage:
    - Identity-suffix encoder/parser (round-trip + malformed cases).
    - ``parse_identity`` raises ``OpnsenseDriftError`` on a malformed marker.
    - ``cron_job_configs_from_resources`` rejects a forged ``[infrafoundry:``
      marker in the operator ``description``.
    - ``compute_diff`` add / update / delete / no-op / lock / add_only.
    - Unmanaged (unmarked) live rows ignored by the diff.
    - ``lock`` honored — skipped in diff, counted in ``Diff.locked``.
    - ``add_only`` suppresses updates and deletes.
    - ``to_payload`` forces ``origin="cron"`` on the wire regardless of YAML value.
    - ``export_to_yaml`` emits the ``opnsense.cron.jobs`` nested path and
      round-trips through the loader.
    - ``plugin_conflicts`` detects a shared ``command`` with an unmanaged row.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.config.package_loader import (
    DOTTED_RESOURCE_SHAPES,
    NESTED_PROVIDER_NAMESPACE,
    PackageLoader,
)
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.services.cron_jobs import (
    CronJobConfig,
    CronJobsService,
    Diff,
    LiveCronJob,
    OpnsenseDriftError,
    _row_to_live,
    compute_diff,
    cron_job_configs_from_resources,
    encode_identity,
    parse_identity,
    plugin_conflicts,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _config(
    name: str = "acmeclient-auto-renew",
    *,
    enabled: bool = True,
    minutes: str = "0",
    hours: str = "2",
    days: str = "*",
    months: str = "*",
    weekdays: str = "*",
    who: str = "root",
    command: str = "acmeclient cron-auto-renew",
    parameters: str = "",
    description: str = "",
    origin: str = "AcmeClient",
    lock: bool = False,
) -> CronJobConfig:
    """Build a canonical ``CronJobConfig`` for testing."""
    return CronJobConfig(
        name=name,
        enabled=enabled,
        minutes=minutes,
        hours=hours,
        days=days,
        months=months,
        weekdays=weekdays,
        who=who,
        command=command,
        parameters=parameters,
        description=description,
        origin=origin,
        lock=lock,
    )


def _live(
    uuid: str = "uuid-1",
    *,
    managed_name: str | None = "acmeclient-auto-renew",
    description: str = "",
    origin: str = "AcmeClient",
    raw: dict[str, Any] | None = None,
) -> LiveCronJob:
    """Build a ``LiveCronJob`` whose ``raw`` mirrors a real searchJobs row."""
    if raw is None:
        encoded_desc = (
            f"{description} [infrafoundry:{managed_name}]"
            if description
            else f"[infrafoundry:{managed_name}]"
        )
        raw = {
            "uuid": uuid,
            "description": encoded_desc if managed_name else description,
            "enabled": "1",
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "acmeclient cron-auto-renew",
            "parameters": "",
            "origin": origin,
        }
    return LiveCronJob(
        uuid=uuid,
        managed_name=managed_name,
        description=description,
        origin=origin,
        raw=raw,
    )


def _resource(
    name: str = "acmeclient-auto-renew",
    *,
    config: dict[str, Any] | None = None,
) -> ResourceConfig:
    """Build a ``cron.jobs`` ``ResourceConfig``."""
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


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------


class TestEncodeIdentity:
    def test_with_user_description(self) -> None:
        result = encode_identity("my-job", "Certificate renewal")
        assert result == "Certificate renewal [infrafoundry:my-job]"

    def test_without_user_description(self) -> None:
        result = encode_identity("my-job", "")
        assert result == "[infrafoundry:my-job]"

    def test_round_trip(self) -> None:
        """encode → parse recovers original values."""
        encoded = encode_identity("my-job", "Cert renewal")
        name, user_desc = parse_identity(encoded)
        assert name == "my-job"
        assert user_desc == "Cert renewal"

    def test_round_trip_empty_description(self) -> None:
        encoded = encode_identity("my-job", "")
        name, user_desc = parse_identity(encoded)
        assert name == "my-job"
        assert user_desc == ""


class TestParseIdentity:
    def test_unmanaged_row_returns_none_name(self) -> None:
        name, user_desc = parse_identity("Some unmanaged cron job")
        assert name is None
        assert user_desc == "Some unmanaged cron job"

    def test_managed_no_user_description(self) -> None:
        name, user_desc = parse_identity("[infrafoundry:my-job]")
        assert name == "my-job"
        assert user_desc == ""

    def test_managed_with_user_description(self) -> None:
        name, user_desc = parse_identity("Cert renewal [infrafoundry:my-job]")
        assert name == "my-job"
        assert user_desc == "Cert renewal"

    def test_malformed_marker_raises(self) -> None:
        """Description contains ``[infrafoundry:...]`` but doesn't match the regex."""
        with pytest.raises(OpnsenseDriftError):
            parse_identity("Oops [infrafoundry:UPPERCASE] extra text")

    def test_malformed_empty_name_raises(self) -> None:
        """Name must be non-empty and match ``[a-z0-9-]+``."""
        with pytest.raises(OpnsenseDriftError):
            parse_identity("[infrafoundry:]")


# ---------------------------------------------------------------------------
# CronJobConfig.to_payload wire-key mapping
# ---------------------------------------------------------------------------


class TestCronJobConfigToPayload:
    def test_wire_key_mapping(self) -> None:
        """Schedule fields pass through 1:1: days→days, months→months, weekdays→weekdays."""
        cfg = _config(days="5", months="6", weekdays="0")
        payload = cfg.to_payload()
        job = payload["job"]
        # Correct wire keys (verified by live probe 2026-06-18)
        assert "days" in job
        assert "months" in job
        assert "weekdays" in job
        assert job["days"] == "5"
        assert job["months"] == "6"
        assert job["weekdays"] == "0"
        # Old wrong keys must NOT appear
        assert "mday" not in job
        assert "month" not in job
        assert "wday" not in job

    def test_enabled_true_serializes_to_one(self) -> None:
        payload = _config(enabled=True).to_payload()
        assert payload["job"]["enabled"] == "1"

    def test_enabled_false_serializes_to_zero(self) -> None:
        payload = _config(enabled=False).to_payload()
        assert payload["job"]["enabled"] == "0"

    def test_description_suffix_appended(self) -> None:
        cfg = _config(name="my-job", description="Cert renewal")
        payload = cfg.to_payload()
        assert payload["job"]["description"] == "Cert renewal [infrafoundry:my-job]"

    def test_origin_forced_to_cron(self) -> None:
        """to_payload() always emits origin="cron" regardless of the config value.

        delJob is delete-protected for non-"cron" origins on OPNsense.
        Forcing "cron" ensures we can always delete our managed jobs.
        """
        payload = _config(origin="AcmeClient").to_payload()
        assert payload["job"]["origin"] == "cron"

    def test_origin_forced_to_cron_when_default(self) -> None:
        """Even with the default origin ("cron"), the wire value is "cron"."""
        payload = _config(origin="cron").to_payload()
        assert payload["job"]["origin"] == "cron"

    def test_lock_and_name_not_in_payload(self) -> None:
        payload = _config(lock=True).to_payload()
        assert "lock" not in payload["job"]
        assert "name" not in payload["job"]


# ---------------------------------------------------------------------------
# cron_job_configs_from_resources
# ---------------------------------------------------------------------------


class TestCronJobConfigsFromResources:
    def test_skips_non_cron_type(self) -> None:
        non_cron = ResourceConfig(name="ignore-me", type="radvd", provider="opnsense", config={})
        result = cron_job_configs_from_resources([non_cron, _resource()])
        assert len(result) == 1
        assert result[0].name == "acmeclient-auto-renew"

    def test_rejects_forged_identity_prefix(self) -> None:
        """Operator must not embed ``[infrafoundry:...]`` in ``description``."""
        forged = _resource(
            config={
                "description": "legit [infrafoundry:evil]",
                "command": "evil",
                "who": "root",
            }
        )
        with pytest.raises(ValueError, match="reserved"):
            cron_job_configs_from_resources([forged])

    def test_rejects_non_cron_type(self) -> None:
        """Non-``cron.jobs`` resources are silently skipped."""
        non_cron = ResourceConfig(name="other", type="radvd", provider="opnsense", config={})
        result = cron_job_configs_from_resources([non_cron])
        assert result == []


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiff:
    def test_no_change(self) -> None:
        desired = [_config()]
        live = [_live()]
        diff = compute_diff(desired, live)
        assert diff.is_empty

    def test_add(self) -> None:
        desired = [_config()]
        live: list[LiveCronJob] = []
        diff = compute_diff(desired, live)
        assert len(diff.adds) == 1
        assert diff.adds[0].name == "acmeclient-auto-renew"
        assert diff.updates == []
        assert diff.deletes == []

    def test_update_detected(self) -> None:
        desired = [_config(hours="3")]  # different hour
        live_raw = {
            "uuid": "uuid-1",
            "description": "[infrafoundry:acmeclient-auto-renew]",
            "enabled": "1",
            "minutes": "0",
            "hours": "2",  # old value
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "acmeclient cron-auto-renew",
            "parameters": "",
            "origin": "AcmeClient",
        }
        live = [
            LiveCronJob(
                uuid="uuid-1",
                managed_name="acmeclient-auto-renew",
                description="",
                origin="AcmeClient",
                raw=live_raw,
            )
        ]
        diff = compute_diff(desired, live)
        assert diff.adds == []
        assert len(diff.updates) == 1
        live_job, want = diff.updates[0]
        assert live_job.uuid == "uuid-1"
        assert want.hours == "3"
        assert diff.deletes == []

    def test_delete(self) -> None:
        desired: list[CronJobConfig] = []
        live = [_live()]
        diff = compute_diff(desired, live)
        assert diff.adds == []
        assert diff.updates == []
        assert len(diff.deletes) == 1
        assert diff.deletes[0].managed_name == "acmeclient-auto-renew"

    def test_unmanaged_live_ignored(self) -> None:
        unmanaged = _live(
            uuid="uuid-unmanaged",
            managed_name=None,
            raw={
                "uuid": "uuid-unmanaged",
                "description": "Some unmanaged job with no tag",
                "enabled": "1",
                "minutes": "0",
                "hours": "2",
                "days": "*",
                "months": "*",
                "weekdays": "*",
                "who": "root",
                "command": "acmeclient cron-auto-renew",
                "parameters": "",
                "origin": "",
            },
        )
        diff = compute_diff([_config()], [_live(), unmanaged])
        assert diff.is_empty  # the desired job already matches the managed live
        assert diff.deletes == []  # unmanaged row never ends up in deletes

    def test_lock_skipped_in_diff(self) -> None:
        desired = [_config(lock=True)]
        live = [_live()]
        diff = compute_diff(desired, live)
        assert diff.adds == []
        assert diff.updates == []
        assert diff.deletes == []
        assert len(diff.locked) == 1

    def test_add_only_suppresses_deletes_only(self) -> None:
        """``add_only=True`` suppresses deletes but still allows adds and updates.

        A managed live job absent from desired is NOT deleted when add_only=True.
        A managed live job that differs from desired IS still updated.
        """
        # desired: acmeclient-auto-renew with hours=3 (update), no "other-job" (would delete)
        desired = [_config(hours="3")]  # different hour → update candidate
        second_raw = {
            "uuid": "uuid-2",
            "description": "[infrafoundry:other-job]",
            "enabled": "1",
            "minutes": "0",
            "hours": "1",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "other-command",
            "parameters": "",
            "origin": "",
        }
        second_live = LiveCronJob(
            uuid="uuid-2",
            managed_name="other-job",
            description="",
            origin="",
            raw=second_raw,
        )
        live_raw = {
            "uuid": "uuid-1",
            "description": "[infrafoundry:acmeclient-auto-renew]",
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
        managed_live = LiveCronJob(
            uuid="uuid-1",
            managed_name="acmeclient-auto-renew",
            description="",
            origin="AcmeClient",
            raw=live_raw,
        )
        diff = compute_diff(desired, [managed_live, second_live], add_only=True)
        # Delete suppressed — "other-job" absent from desired but not deleted
        assert diff.deletes == []
        # Update still emitted — hours differ
        assert len(diff.updates) == 1
        assert diff.updates[0][0].uuid == "uuid-1"


# ---------------------------------------------------------------------------
# plugin_conflicts
# ---------------------------------------------------------------------------


class TestPluginConflicts:
    def test_detects_shared_command(self) -> None:
        desired = [_config(command="acmeclient cron-auto-renew")]
        # Unmanaged live job sharing the same command.
        unmanaged_raw: dict[str, Any] = {
            "uuid": "uuid-unmanaged",
            "description": "Legacy renewal script",
            "command": "acmeclient cron-auto-renew",
        }
        unmanaged = LiveCronJob(
            uuid="uuid-unmanaged",
            managed_name=None,
            description="Legacy renewal script",
            origin="",
            raw=unmanaged_raw,
        )
        conflicts = plugin_conflicts(desired, [unmanaged])
        assert len(conflicts) == 1
        want, conflicting = conflicts[0]
        assert want.command == "acmeclient cron-auto-renew"
        assert conflicting.uuid == "uuid-unmanaged"

    def test_managed_live_not_conflicted(self) -> None:
        """Managed live jobs (with a tag) are not returned as conflicts."""
        desired = [_config(command="acmeclient cron-auto-renew")]
        # _live() default raw has command="acmeclient cron-auto-renew" and managed_name set.
        managed = _live()
        conflicts = plugin_conflicts(desired, [managed])
        assert conflicts == []

    def test_different_commands_no_conflict(self) -> None:
        desired = [_config(command="cmd-a")]
        unmanaged_raw: dict[str, Any] = {
            "uuid": "u1",
            "description": "unmanaged",
            "command": "cmd-b",
        }
        unmanaged = LiveCronJob(
            uuid="u1", managed_name=None, description="unmanaged", origin="", raw=unmanaged_raw
        )
        assert plugin_conflicts(desired, [unmanaged]) == []


# ---------------------------------------------------------------------------
# _row_to_live
# ---------------------------------------------------------------------------


class TestRowToLive:
    def test_managed_row_parsed(self) -> None:
        row = {
            "uuid": "uuid-1",
            "description": "Cert renewal [infrafoundry:my-job]",
            "origin": "AcmeClient",
        }
        result = _row_to_live(row)
        assert result.uuid == "uuid-1"
        assert result.managed_name == "my-job"
        assert result.description == "Cert renewal"
        assert result.origin == "AcmeClient"

    def test_unmanaged_row(self) -> None:
        row = {
            "uuid": "u2",
            "description": "No tag here",
            "origin": "",
        }
        result = _row_to_live(row)
        assert result.managed_name is None
        assert result.description == "No tag here"

    def test_malformed_tag_raises(self) -> None:
        row = {
            "uuid": "u3",
            "description": "Bad [infrafoundry:UPPERCASE] junk",
            "origin": "",
        }
        with pytest.raises(OpnsenseDriftError):
            _row_to_live(row)


# ---------------------------------------------------------------------------
# CronJobsService via mocked client
# ---------------------------------------------------------------------------


def _make_client(*, search_rows: list[dict[str, Any]] | None = None) -> MagicMock:
    client = MagicMock()

    def _request(method: str, path: str, **kwargs: Any) -> Any:
        if "searchJobs" in path:
            return {"rows": search_rows or []}
        if "addJob" in path:
            return {"result": "saved", "uuid": "new-uuid"}
        if "setJob" in path:
            return {"result": "saved"}
        if "delJob" in path:
            return {"result": "deleted"}
        if "reconfigure" in path:
            return {"status": "ok"}
        return {}

    client.request.side_effect = _request
    return client


class TestCronJobsServiceApiMethods:
    def test_search_returns_live_jobs(self) -> None:
        rows = [
            {
                "uuid": "uuid-1",
                "description": "[infrafoundry:my-job]",
                "enabled": "1",
                "minutes": "0",
                "hours": "2",
                "days": "*",
                "months": "*",
                "weekdays": "*",
                "who": "root",
                "command": "cmd",
                "parameters": "",
                "origin": "",
            }
        ]
        service = CronJobsService(_make_client(search_rows=rows))
        live = service.search()
        assert len(live) == 1
        assert live[0].managed_name == "my-job"

    def test_add_calls_add_job(self) -> None:
        service = CronJobsService(_make_client())
        cfg = _config()
        result = service.add(cfg)
        assert result.get("result") == "saved"

    def test_update_calls_set_job(self) -> None:
        service = CronJobsService(_make_client())
        cfg = _config()
        result = service.update("uuid-1", cfg)
        assert result.get("result") == "saved"

    def test_delete_calls_del_job(self) -> None:
        service = CronJobsService(_make_client())
        result = service.delete("uuid-1")
        assert result.get("result") == "deleted"

    def test_reconfigure(self) -> None:
        service = CronJobsService(_make_client())
        result = service.reconfigure()
        assert result.get("status") == "ok"


class TestApplyDiff:
    def test_empty_diff_no_calls(self) -> None:
        service = CronJobsService(_make_client())
        diff = Diff()
        counts = service.apply_diff(diff)
        assert counts == {"created": 0, "updated": 0, "deleted": 0}

    def test_apply_diff_counts(self) -> None:
        rows = [
            {
                "uuid": "uuid-existing",
                "description": "[infrafoundry:existing-job]",
                "enabled": "1",
                "minutes": "0",
                "hours": "2",
                "days": "*",
                "months": "*",
                "weekdays": "*",
                "who": "root",
                "command": "existing-cmd",
                "parameters": "",
                "origin": "",
            }
        ]
        service = CronJobsService(_make_client(search_rows=rows))
        add_cfg = _config(name="new-job", command="new-cmd")
        update_live = LiveCronJob(
            uuid="uuid-existing",
            managed_name="existing-job",
            description="",
            origin="",
            raw=rows[0],
        )
        update_cfg = _config(name="existing-job", command="existing-cmd", hours="3")
        del_live = LiveCronJob(
            uuid="uuid-del",
            managed_name="del-job",
            description="",
            origin="",
            raw={},
        )
        diff = Diff(
            adds=[add_cfg],
            updates=[(update_live, update_cfg)],
            deletes=[del_live],
        )
        counts = service.apply_diff(diff)
        assert counts == {"created": 1, "updated": 1, "deleted": 1}


# ---------------------------------------------------------------------------
# export_to_yaml round-trip
# ---------------------------------------------------------------------------


def _round_trip(yaml_text: str, source_filename: str) -> list[ResourceConfig]:
    data = yaml.safe_load(yaml_text)
    assert isinstance(data, dict)
    nested = data.get(NESTED_PROVIDER_NAMESPACE)
    assert isinstance(nested, dict)
    loader = PackageLoader(base_dir=Path("/tmp/unused"))
    return loader._parse_nested_provider_format(nested, NESTED_PROVIDER_NAMESPACE, source_filename)


class TestExportToYaml:
    def test_emits_cron_jobs_nested_path(self) -> None:
        managed_row = {
            "uuid": "uuid-1",
            "description": "AcmeClient cert renewal [infrafoundry:acmeclient-auto-renew]",
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
        service = CronJobsService(_make_client(search_rows=[managed_row]))
        yaml_text = service.export_to_yaml()

        data = yaml.safe_load(yaml_text)
        assert NESTED_PROVIDER_NAMESPACE in data
        cursor = data[NESTED_PROVIDER_NAMESPACE]
        assert "cron" in cursor
        assert "jobs" in cursor["cron"]
        leaf = cursor["cron"]["jobs"]
        assert isinstance(leaf, list)
        assert len(leaf) == 1
        assert leaf[0]["name"] == "acmeclient-auto-renew"

    def test_unmanaged_excluded(self) -> None:
        rows = [
            {
                "uuid": "u1",
                "description": "[infrafoundry:managed-job]",
                "enabled": "1",
                "minutes": "*",
                "hours": "*",
                "days": "*",
                "months": "*",
                "weekdays": "*",
                "who": "root",
                "command": "managed-cmd",
                "parameters": "",
                "origin": "",
            },
            {
                "uuid": "u2",
                "description": "Unmanaged — no tag",
                "enabled": "1",
                "minutes": "*",
                "hours": "*",
                "days": "*",
                "months": "*",
                "weekdays": "*",
                "who": "root",
                "command": "unmanaged-cmd",
                "parameters": "",
                "origin": "",
            },
        ]
        service = CronJobsService(_make_client(search_rows=rows))
        yaml_text = service.export_to_yaml()

        data = yaml.safe_load(yaml_text)
        leaf = data[NESTED_PROVIDER_NAMESPACE]["cron"]["jobs"]
        assert len(leaf) == 1
        assert leaf[0]["name"] == "managed-job"

    def test_round_trip_through_loader(self) -> None:
        managed_row = {
            "uuid": "uuid-1",
            "description": "[infrafoundry:acmeclient-auto-renew]",
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
        service = CronJobsService(_make_client(search_rows=[managed_row]))
        yaml_text = service.export_to_yaml()

        parsed = _round_trip(yaml_text, "cron_jobs.yaml")
        assert len(parsed) == 1
        assert parsed[0].name == "acmeclient-auto-renew"
        assert parsed[0].type == "cron.jobs"
        assert parsed[0].config["command"] == "acmeclient cron-auto-renew"

    def test_export_emits_origin_cron_regardless_of_live_value(self) -> None:
        """export_to_yaml always emits origin: cron even when the live record has a plugin origin.

        Exporting the live plugin origin (e.g. "AcmeClient") would produce YAML that
        triggers a validator WARNING and then a perpetual no-op update on next apply
        (since origin is excluded from drift detection).  Emitting "cron" makes the
        migrated YAML match what InfraFoundry writes on the wire.
        """
        managed_row = {
            "uuid": "uuid-1",
            "description": "[infrafoundry:job1]",
            "enabled": "1",
            "minutes": "0",
            "hours": "1",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "cmd",
            "parameters": "",
            "origin": "MyPlugin",
        }
        service = CronJobsService(_make_client(search_rows=[managed_row]))
        yaml_text = service.export_to_yaml()
        parsed = _round_trip(yaml_text, "cron_jobs.yaml")
        assert parsed[0].config["origin"] == "cron"

    def test_cron_jobs_dotted_type_registered(self) -> None:
        """``cron.jobs`` must be registered in DOTTED_RESOURCE_SHAPES as 'list'."""
        assert "cron.jobs" in DOTTED_RESOURCE_SHAPES
        assert DOTTED_RESOURCE_SHAPES["cron.jobs"] == "list"


# ---------------------------------------------------------------------------
# Regression tests — live-probe findings (2026-06-18)
# ---------------------------------------------------------------------------


class TestLiveProbeRegressions:
    """Regression tests locking in the live-probe findings.

    The MVC ``cron/settings/getJob`` template uses ``days``/``months``/``weekdays``
    as wire field names (NOT ``mday``/``month``/``wday`` as initially coded).
    ``origin`` is a REQUIRED wire field; OPNsense's ``delJob`` is delete-protected
    for non-``"cron"`` origins.
    """

    def test_to_payload_emits_days_months_weekdays_not_mday(self) -> None:
        """to_payload() must use the real wire keys from the MVC template."""
        cfg = CronJobConfig(
            name="probe-job",
            days="3",
            months="2",
            weekdays="1",
        )
        job = cfg.to_payload()["job"]
        assert job["days"] == "3"
        assert job["months"] == "2"
        assert job["weekdays"] == "1"
        assert "mday" not in job, "old wrong key 'mday' must not appear"
        assert "month" not in job, "old wrong key 'month' must not appear"
        assert "wday" not in job, "old wrong key 'wday' must not appear"

    def test_to_payload_forces_origin_cron_even_when_yaml_has_plugin_origin(self) -> None:
        """to_payload() forces origin='cron' so delJob can delete our managed jobs."""
        cfg = CronJobConfig(name="probe-job", origin="AcmeClient")
        job = cfg.to_payload()["job"]
        assert job["origin"] == "cron", (
            "origin must be forced to 'cron' — delJob is delete-protected for "
            "non-'cron' origins (verified live probe 2026-06-18)"
        )

    def test_row_to_live_reads_days_months_weekdays(self) -> None:
        """_row_to_live must read schedule fields from the correct wire keys."""
        row = {
            "uuid": "u1",
            "description": "[infrafoundry:probe-job]",
            "enabled": "1",
            "minutes": "5",
            "hours": "3",
            "days": "15",
            "months": "6",
            "weekdays": "2",
            "who": "root",
            "command": "probe",
            "parameters": "",
            "origin": "cron",
        }
        live = _row_to_live(row)
        # raw is stored verbatim; the export layer reads from raw
        assert live.raw["days"] == "15"
        assert live.raw["months"] == "6"
        assert live.raw["weekdays"] == "2"

    def test_no_drift_when_origin_differs_between_yaml_and_live(self) -> None:
        """origin mismatch must NOT produce a spurious update.

        InfraFoundry writes origin='cron'; a live job may carry a plugin origin
        (e.g. 'AcmeClient') if it was created by a plugin before InfraFoundry
        adopted it.  Comparing origin would cause perpetual updates.
        """
        desired = CronJobConfig(
            name="acme-job",
            minutes="0",
            hours="2",
            days="*",
            months="*",
            weekdays="*",
            who="root",
            command="acmeclient cron-auto-renew",
            origin="AcmeClient",  # operator sets this in YAML
        )
        live_raw = {
            "uuid": "u1",
            "description": "[infrafoundry:acme-job]",
            "enabled": "1",
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "acmeclient cron-auto-renew",
            "parameters": "",
            "origin": "cron",  # InfraFoundry wrote 'cron' on last apply
        }
        live = LiveCronJob(
            uuid="u1",
            managed_name="acme-job",
            description="",
            origin="cron",
            raw=live_raw,
        )
        diff = compute_diff([desired], [live])
        assert diff.is_empty, (
            "origin diff ('AcmeClient' in YAML vs 'cron' on wire) must NOT "
            "produce a spurious update — origin is excluded from drift detection"
        )

    def test_export_origin_always_cron_not_plugin_origin(self) -> None:
        """_live_to_export_config emits origin: cron regardless of live record's origin."""
        row = {
            "uuid": "u1",
            "description": "[infrafoundry:acme-job]",
            "enabled": "1",
            "minutes": "0",
            "hours": "2",
            "days": "*",
            "months": "*",
            "weekdays": "*",
            "who": "root",
            "command": "acmeclient cron-auto-renew",
            "parameters": "",
            "origin": "AcmeClient",  # live box has plugin origin
        }
        service = CronJobsService(_make_client(search_rows=[row]))
        yaml_text = service.export_to_yaml()
        parsed = _round_trip(yaml_text, "cron_jobs.yaml")
        assert parsed[0].config["origin"] == "cron", (
            "export must emit origin: cron so migrated YAML is immediately "
            "consistent with what InfraFoundry will write on the wire"
        )

    def test_export_reads_schedule_from_correct_wire_keys(self) -> None:
        """export_to_yaml must read days/months/weekdays (not mday/month/wday) from raw."""
        row = {
            "uuid": "u1",
            "description": "[infrafoundry:sched-job]",
            "enabled": "1",
            "minutes": "10",
            "hours": "4",
            "days": "15",
            "months": "6",
            "weekdays": "3",
            "who": "root",
            "command": "sched-cmd",
            "parameters": "",
            "origin": "cron",
        }
        service = CronJobsService(_make_client(search_rows=[row]))
        yaml_text = service.export_to_yaml()
        parsed = _round_trip(yaml_text, "cron_jobs.yaml")
        cfg = parsed[0].config
        assert cfg["days"] == "15", "days field must be read from 'days' wire key"
        assert cfg["months"] == "6", "months field must be read from 'months' wire key"
        assert cfg["weekdays"] == "3", "weekdays field must be read from 'weekdays' wire key"
