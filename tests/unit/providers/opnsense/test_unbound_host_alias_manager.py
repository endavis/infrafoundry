"""Unit tests for ``UnboundHostAliasManager``.

Coverage:
    - plan/apply/destroy delegate to UnboundHostAliasService correctly.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes.
    - delete outcomes use the synthesized ``alias-<hostname>-<parent_short>`` name.
    - get_resource_ids maps live UUIDs to operator-facing names by tuple match.
    - migrate exports YAML.
    - lock semantics honored on destroy.
    - add_only flag propagated to compute_diff.
    - host_name → host_uuid resolution against searchHostOverride rows.
    - ReferenceValidationError raised when a host_name does not match.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.unbound_host_alias import (
    UnboundHostAliasManager,
)
from infrafoundry.providers.opnsense.services.unbound_host_alias import (
    Diff,
    LiveUnboundHostAlias,
    UnboundHostAliasConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(
    name: str,
    *,
    host: str = "db-primary",
    hostname: str = "db",
    domain: str = "internal",
    lock: bool = False,
) -> ResourceConfig:
    config: dict[str, Any] = {
        "host": host,
        "hostname": hostname,
        "domain": domain,
        "description": f"{name} desc",
    }
    if lock:
        config["lock"] = True
    return ResourceConfig(
        name=name, type="unbound.host_aliases", provider="opnsense", config=config
    )


def _live(
    uuid: str,
    *,
    host_uuid: str = "parent-uuid",
    hostname: str = "db",
) -> LiveUnboundHostAlias:
    return LiveUnboundHostAlias(
        uuid=uuid,
        host_uuid=host_uuid,
        hostname=hostname,
        raw={
            "uuid": uuid,
            "host": host_uuid,
            "hostname": hostname,
            "domain": "internal",
            "enabled": "1",
            "description": "",
        },
    )


def _alias(name: str, **overrides: Any) -> UnboundHostAliasConfig:
    return UnboundHostAliasConfig(
        name=name,
        host_name=overrides.get("host_name", "db-primary"),
        host_uuid=overrides.get("host_uuid", "parent-uuid"),
        hostname=overrides.get("hostname", "db"),
        domain=overrides.get("domain", "internal"),
        enabled=overrides.get("enabled", True),
    )


SERVICE_PATH = (
    "infrafoundry.providers.opnsense.components.unbound_host_alias.UnboundHostAliasService"
)


def _make_service_mock(
    *,
    live: list[LiveUnboundHostAlias] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
    host_overrides: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mocked ``UnboundHostAliasService`` with sensible defaults."""
    service = MagicMock()
    service.search.return_value = live if live is not None else []
    service.compute_diff.return_value = diff if diff is not None else Diff()
    service.apply_diff.return_value = (
        apply_counts if apply_counts is not None else {"created": 0, "updated": 0, "deleted": 0}
    )
    service.search_host_overrides.return_value = (
        host_overrides
        if host_overrides is not None
        else [
            {"uuid": "parent-uuid", "hostname": "db-primary", "domain": "internal"},
        ]
    )
    return service


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class TestPlan:
    def test_returns_diff(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_alias("foo")])
        service_mock = _make_service_mock(diff=diff)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", resources)
        assert result.adds == diff.adds
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)
        service_mock.compute_diff.assert_called_once()

    def test_threads_add_only(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True

    def test_resolves_host_uuid_from_overrides(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo", host="db-primary")]
        service_mock = _make_service_mock(
            diff=Diff(),
            host_overrides=[
                {"uuid": "parent-uuid", "hostname": "db-primary", "domain": "internal"}
            ],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources)
        # First positional arg to compute_diff is the desired list with
        # host_uuid resolved.
        desired = service_mock.compute_diff.call_args.args[0]
        assert len(desired) == 1
        assert desired[0].host_uuid == "parent-uuid"

    def test_unknown_host_raises(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo", host="missing-host")]
        service_mock = _make_service_mock(
            diff=Diff(),
            host_overrides=[
                {"uuid": "parent-uuid", "hostname": "db-primary", "domain": "internal"}
            ],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            with pytest.raises(ReferenceValidationError, match="missing-host"):
                manager.plan("test-env", resources)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_returns_counts(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_alias("foo")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        assert result["resources_created"] == 1
        assert result["success"] is True

    def test_apply_emits_add_outcome(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_alias("foo")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "add"
        assert outcomes[0].resource_name == "foo"
        assert outcomes[0].address == "opnsense_unbound_host_alias.foo"

    def test_apply_emits_update_outcome(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo")]
        live = _live("u1")
        want = _alias("foo")
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
        assert outcomes[0].resource_name == "foo"
        assert outcomes[0].address == "opnsense_unbound_host_alias.foo"

    def test_apply_emits_delete_outcome_with_synthetic_name(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = _live("u1", host_uuid="parentuuid-1234-5678", hostname="db")
        diff = Diff(deletes=[live])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 0, "deleted": 1}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 1
        assert outcomes[0].action == "delete"
        # Synthetic name: alias-<hostname>-<parent_short>
        assert outcomes[0].resource_name == "alias-db-parentuuid"
        assert outcomes[0].address == "opnsense_unbound_host_alias.alias-db-parentuuid"

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True

    def test_apply_unknown_host_raises(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo", host="missing-host")]
        service_mock = _make_service_mock(
            host_overrides=[
                {"uuid": "parent-uuid", "hostname": "db-primary", "domain": "internal"}
            ],
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            with pytest.raises(ReferenceValidationError, match="missing-host"):
                manager.apply("test-env", resources)


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_aliases(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo")]
        live = [_live("u1")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_called_once_with("u1")
        service_mock.reconfigure.assert_called_once()
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0

    def test_destroy_skips_when_no_live_match(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(live=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.reconfigure.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("survival", lock=True)]
        live = [_live("u1")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        assert result["locked_skipped"] == 1

    def test_destroy_matches_by_natural_key(self, tmp_path: Path) -> None:
        # YAML name is ``foo``, but identity matches by tuple — verify
        # that two tuples that don't match each other don't accidentally
        # collide on names.
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo", hostname="db", host="db-primary")]
        live = [
            _live("u1", host_uuid="parent-uuid", hostname="db"),
            _live("u2", host_uuid="parent-uuid", hostname="other"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        # Only the matching tuple is deleted.
        service_mock.delete.assert_called_once_with("u1")
        assert result["resources_destroyed"] == 1


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids_by_tuple(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [
            _resource("foo", hostname="db"),
            _resource("bar", hostname="other"),
        ]
        live = [
            _live("u1", host_uuid="parent-uuid", hostname="db"),
            _live("u2", host_uuid="parent-uuid", hostname="other"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1", "bar": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [
            _resource("foo", hostname="db"),
            _resource("missing", hostname="absent"),
        ]
        live = [_live("u1", host_uuid="parent-uuid", hostname="db")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}


# ---------------------------------------------------------------------------
# list / migrate
# ---------------------------------------------------------------------------


class TestListAndMigrate:
    def test_list_returns_live_aliases(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        live = [_live("u1"), _live("u2", hostname="other")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        assert result == live

    def test_migrate_returns_yaml_string(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")
        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once()


# ---------------------------------------------------------------------------
# Finalization hook contract (#776)
# ---------------------------------------------------------------------------


class TestFinalizationHook:
    """The manager declares the shared ``unbound_reconfigure`` hook key and
    apply must NOT call ``service.reconfigure`` inline (the runner fires it
    via ``OPNsenseProvider.get_finalization_hooks()`` instead, coalescing
    across host_override / host_alias / forward managers).
    """

    def test_finalization_hook_classvar_declared(self) -> None:
        assert UnboundHostAliasManager.FINALIZATION_HOOK == "unbound_reconfigure"

    def test_apply_does_not_call_reconfigure_inline(self, tmp_path: Path) -> None:
        manager = UnboundHostAliasManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_alias("foo")])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", resources)
        service_mock.reconfigure.assert_not_called()
