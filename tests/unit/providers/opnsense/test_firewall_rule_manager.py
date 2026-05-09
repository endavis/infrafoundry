"""Unit tests for ``FirewallRuleManager``.

Coverage:
    - ``plan`` returns ``Diff`` and threads ``add_only``.
    - ``apply`` returns counts dict + ``resource_outcomes`` for adds /
      updates / deletes; ``ResourceOutcome.address`` is
      ``opnsense_firewall_rule.<name>``.
    - ``destroy`` deletes managed rules, honors ``lock``, calls
      ``apply_changes`` only when at least one delete happened.
    - ``get_resource_ids`` maps operator names to live UUIDs.
    - ``list`` and ``migrate`` delegate to the service layer correctly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.firewall_rule import FirewallRuleManager
from infrafoundry.providers.opnsense.services.firewall_rule import (
    Diff,
    FirewallRuleConfig,
    LiveFirewallRule,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resource(name: str, *, lock: bool = False, **overrides: Any) -> ResourceConfig:
    config: dict[str, Any] = {
        "interface": "lan",
        "description": f"{name} desc",
    }
    if lock:
        config["lock"] = True
    config.update(overrides)
    return ResourceConfig(name=name, type="firewall.rules", provider="opnsense", config=config)


def _live_managed(uuid: str, name: str) -> LiveFirewallRule:
    return LiveFirewallRule(
        uuid=uuid,
        managed_name=name,
        description="",
        raw={"uuid": uuid, "description": f"[infrafoundry:{name}]"},
    )


SERVICE_PATH = "infrafoundry.providers.opnsense.components.firewall_rule.FirewallRuleService"


def _make_service_mock(
    *,
    live: list[LiveFirewallRule] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mocked ``FirewallRuleService`` with sensible defaults."""
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
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[FirewallRuleConfig(name="foo", interface="lan")])
        service_mock = _make_service_mock(diff=diff)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", resources)
        assert result.adds == diff.adds
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)
        service_mock.compute_diff.assert_called_once()

    def test_threads_add_only(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True

    def test_passes_provider_name(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", [], provider_name="opnsense-prod")
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense-prod", tmp_path)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_returns_counts_dict(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[FirewallRuleConfig(name="foo", interface="lan")])
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
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        diff = Diff(adds=[FirewallRuleConfig(name="foo", interface="lan")])
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
        assert outcomes[0].address == "opnsense_firewall_rule.foo"

    def test_apply_emits_update_outcome(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        live = _live_managed("u1", "foo")
        want = FirewallRuleConfig(name="foo", interface="lan")
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
        assert outcomes[0].address == "opnsense_firewall_rule.foo"

    def test_apply_emits_delete_outcome(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = _live_managed("u1", "stale")
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
        assert outcomes[0].resource_name == "stale"
        assert outcomes[0].address == "opnsense_firewall_rule.stale"

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True

    def test_apply_outcomes_order_adds_updates_deletes(self, tmp_path: Path) -> None:
        # Mixed diff — outcomes list must preserve the
        # adds → updates → deletes ordering used by the manager.
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("a"), _resource("b"), _resource("c")]
        live_b = _live_managed("u-b", "b")
        live_c = _live_managed("u-c", "c")
        diff = Diff(
            adds=[FirewallRuleConfig(name="a", interface="lan")],
            updates=[(live_b, FirewallRuleConfig(name="b", interface="lan"))],
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

    def test_apply_synthesizes_delete_name_from_managed_name(self, tmp_path: Path) -> None:
        # The manager synthesizes the address from ``live.managed_name``;
        # the diff engine guarantees that's non-None for delete entries.
        manager = FirewallRuleManager(tmp_path)
        live = _live_managed("u1", "stale-rule")
        diff = Diff(deletes=[live])
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 0, "updated": 0, "deleted": 1}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", [])
        assert result["resource_outcomes"][0].address == "opnsense_firewall_rule.stale-rule"


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_managed_rules(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        live = [_live_managed("u1", "foo")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_called_once_with("u1")
        service_mock.apply_changes.assert_called_once()
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0
        assert result["success"] is True

    def test_destroy_skips_when_no_live_match(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        service_mock = _make_service_mock(live=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        # Apply must NOT be called when nothing was deleted.
        service_mock.apply_changes.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("wan-survival", lock=True)]
        live = [_live_managed("u1", "wan-survival")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.apply_changes.assert_not_called()
        assert result["locked_skipped"] == 1
        assert result["resources_destroyed"] == 0

    def test_destroy_mixed_locked_and_unlocked(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [
            _resource("locked-one", lock=True),
            _resource("normal-two"),
        ]
        live = [
            _live_managed("u-locked", "locked-one"),
            _live_managed("u-normal", "normal-two"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        # Only the unlocked rule is deleted.
        service_mock.delete.assert_called_once_with("u-normal")
        service_mock.apply_changes.assert_called_once()
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 1


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo"), _resource("bar")]
        live = [_live_managed("u1", "foo"), _live_managed("u2", "bar")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1", "bar": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo"), _resource("missing")]
        live = [_live_managed("u1", "foo")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}

    def test_unmanaged_live_excluded(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        resources = [_resource("foo")]
        # Live list contains an unmanaged row plus the matching managed one.
        live = [
            LiveFirewallRule(
                uuid="u-unmanaged",
                managed_name=None,
                description="manual rule",
                raw={"uuid": "u-unmanaged", "description": "manual rule"},
            ),
            _live_managed("u1", "foo"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}


# ---------------------------------------------------------------------------
# list / migrate
# ---------------------------------------------------------------------------


class TestListAndMigrate:
    def test_list_returns_live_rules(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        live = [_live_managed("u1", "foo")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        assert result == live
        service_mock.search.assert_called_once()

    def test_migrate_returns_yaml_string(self, tmp_path: Path) -> None:
        manager = FirewallRuleManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")
        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once()
