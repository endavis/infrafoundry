"""Unit tests for ``AliasManager``.

Coverage:
    - plan/apply/destroy/get_resource_ids/list/migrate delegate to
      ``AliasService`` correctly.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes
      keyed on the alias ``name`` (the natural-key wire identity).
    - get_resource_ids maps live UUIDs to the operator-facing top-level
      ``ResourceConfig.name`` (which can diverge from ``config.name``
      after an operator renames post-migrate).
    - migrate exports YAML.
    - lock semantics honored on destroy.
    - add_only flag propagated to compute_diff.
    - destroy filters system aliases (no live match for absent records).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.alias import AliasManager
from infrafoundry.providers.opnsense.services.alias import (
    AliasConfig,
    Diff,
    LiveAlias,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(
    name: str,
    *,
    wire_name: str | None = None,
    alias_type: str = "host",
    content: list[str] | None = None,
    lock: bool = False,
) -> ResourceConfig:
    config: dict[str, Any] = {
        "name": wire_name if wire_name is not None else name,
        "type": alias_type,
        "description": f"{name} desc",
        "content": list(content) if content is not None else ["192.0.2.1"],
    }
    if lock:
        config["lock"] = True
    return ResourceConfig(name=name, type="aliases", provider="opnsense", config=config)


def _live(
    uuid: str,
    name: str,
    *,
    alias_type: str = "host",
) -> LiveAlias:
    return LiveAlias(
        uuid=uuid,
        name=name,
        type=alias_type,
        raw={
            "uuid": uuid,
            "name": name,
            "type": alias_type,
            "description": "",
            "content": "",
            "enabled": "1",
        },
    )


def _alias(name: str, **overrides: Any) -> AliasConfig:
    return AliasConfig(
        name=name,
        type=overrides.get("type", "host"),
        description=overrides.get("description", ""),
        content=overrides.get("content", ()),
        enabled=overrides.get("enabled", True),
        lock=overrides.get("lock", False),
    )


SERVICE_PATH = "infrafoundry.providers.opnsense.components.alias.AliasService"


def _make_service_mock(
    *,
    live: list[LiveAlias] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mocked ``AliasService`` with sensible defaults."""
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


class TestPlan:
    def test_returns_diff(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
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
        manager = AliasManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True

    def test_default_add_only_false(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is False

    def test_passes_provider_name_through(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources, provider_name="alt")
        svc_cls.from_environment.assert_called_once_with("test-env", "alt", tmp_path)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_returns_counts(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[_alias("foo")])
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
        manager = AliasManager(tmp_path)
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
        assert outcomes[0].address == "opnsense_firewall_alias.foo"

    def test_apply_emits_update_outcome(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources = [_resource("foo")]
        live = _live("u1", "foo")
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
        assert outcomes[0].address == "opnsense_firewall_alias.foo"

    def test_apply_emits_delete_outcome(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = _live("u1", "stale")
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
        # Identity is the wire ``name`` (no synthetic key needed).
        assert outcomes[0].resource_name == "stale"
        assert outcomes[0].address == "opnsense_firewall_alias.stale"

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True

    def test_apply_emits_outcomes_in_diff_order(self, tmp_path: Path) -> None:
        # Adds first, then updates, then deletes — matches the diff
        # iteration order in ``apply``.
        manager = AliasManager(tmp_path)
        resources = [
            _resource("a"),
            _resource("b"),
        ]
        live_b = _live("uuid-b", "b")
        live_c = _live("uuid-c", "c")
        diff = Diff(
            adds=[_alias("a")],
            updates=[(live_b, _alias("b"))],
            deletes=[live_c],
        )
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 1, "deleted": 1}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert [o.action for o in outcomes] == ["add", "update", "delete"]
        assert [o.resource_name for o in outcomes] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_aliases(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources = [_resource("foo")]
        live = [_live("u1", "foo")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_called_once_with("u1")
        service_mock.reconfigure.assert_called_once()
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0
        assert result["success"] is True

    def test_destroy_skips_when_no_live_match(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(live=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.reconfigure.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources = [_resource("survival", lock=True)]
        live = [_live("u1", "survival")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.reconfigure.assert_not_called()
        assert result["locked_skipped"] == 1
        assert result["resources_destroyed"] == 0

    def test_destroy_matches_by_wire_name(self, tmp_path: Path) -> None:
        # Operator-facing top-level name diverges from the wire name —
        # destroy matches by the wire name (``config.name``).
        manager = AliasManager(tmp_path)
        resources = [_resource("operator-foo", wire_name="wire-foo")]
        live = [
            _live("u1", "wire-foo"),
            _live("u2", "operator-foo"),  # different wire name; should NOT match
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        # Only the wire-foo live alias is deleted.
        service_mock.delete.assert_called_once_with("u1")
        assert result["resources_destroyed"] == 1

    def test_destroy_deletes_multiple(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources = [_resource("a"), _resource("b")]
        live = [_live("u1", "a"), _live("u2", "b")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        assert service_mock.delete.call_count == 2
        service_mock.reconfigure.assert_called_once()
        assert result["resources_destroyed"] == 2


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources = [_resource("foo"), _resource("bar")]
        live = [_live("u1", "foo"), _live("u2", "bar")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1", "bar": "u2"}

    def test_uses_top_level_name_as_key(self, tmp_path: Path) -> None:
        # Operator renamed the top-level name post-migrate; ``config.name``
        # is the wire identity (used to match live), but the dict KEY is
        # the operator-facing top-level name.
        manager = AliasManager(tmp_path)
        resources = [_resource("renamed", wire_name="wire-foo")]
        live = [_live("u1", "wire-foo")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"renamed": "u1"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        resources = [_resource("foo"), _resource("missing")]
        live = [_live("u1", "foo")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}

    def test_empty_resources_returns_empty(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        service_mock = _make_service_mock(live=[_live("u1", "stale")])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", [])
        assert result == {}


# ---------------------------------------------------------------------------
# list / migrate
# ---------------------------------------------------------------------------


class TestListAndMigrate:
    def test_list_returns_live_aliases(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        live = [_live("u1", "a"), _live("u2", "b")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        assert result == live

    def test_migrate_returns_yaml_string(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")
        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once_with()
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)

    def test_migrate_passes_provider_name_through(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.migrate("test-env", provider_name="alt-provider")
        svc_cls.from_environment.assert_called_once_with("test-env", "alt-provider", tmp_path)

    def test_migrate_returns_yaml_verbatim(self, tmp_path: Path) -> None:
        # The manager is a thin pass-through; whatever the service emits
        # is what the operator gets — no transformation.
        manager = AliasManager(tmp_path)
        service_mock = MagicMock()
        payload = "resources:\n- provider: opnsense\n  type: aliases\n  name: web\n"
        service_mock.export_to_yaml.return_value = payload
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("env")
        assert result == payload
