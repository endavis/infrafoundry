"""Unit tests for ``NATRuleManager``.

Coverage:
    - plan/apply/destroy delegate to NATRuleService correctly.
    - apply emits ``ResourceOutcome`` entries for adds/updates/deletes.
    - get_resource_ids maps live UUIDs to operator-facing names per kind.
    - migrate exports YAML.
    - lock semantics honored on destroy.
    - Per-kind isolation: same name, different kind → independent identities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components.nat_rule import NATRuleManager
from infrafoundry.providers.opnsense.services.nat_rule import (
    Diff,
    LiveNATRule,
    NATRuleConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outbound_resource(name: str, *, lock: bool = False) -> ResourceConfig:
    config: dict[str, Any] = {
        "kind": "outbound",
        "interface": "wan",
        "target": "wanip",
        "description": f"{name} desc",
    }
    if lock:
        config["lock"] = True
    return ResourceConfig(name=name, type="nat_rules", provider="opnsense", config=config)


def _one_to_one_resource(name: str, *, lock: bool = False) -> ResourceConfig:
    config: dict[str, Any] = {
        "kind": "one_to_one",
        "interface": "wan",
        "external": "198.51.100.10",
        "source_net": "10.0.0.10",
    }
    if lock:
        config["lock"] = True
    return ResourceConfig(name=name, type="nat_rules", provider="opnsense", config=config)


def _port_forward_resource(name: str, *, lock: bool = False) -> ResourceConfig:
    config: dict[str, Any] = {
        "kind": "port_forward",
        "interface": "wan",
        "target": "10.0.0.10",
        "local_port": "8080",
        "description": f"{name} desc",
    }
    if lock:
        config["lock"] = True
    return ResourceConfig(name=name, type="nat_rules", provider="opnsense", config=config)


def _live_managed(uuid: str, name: str, kind: str) -> LiveNATRule:
    return LiveNATRule(
        uuid=uuid,
        kind=kind,  # type: ignore[arg-type]
        managed_name=name,
        description="",
        raw={"uuid": uuid, "description": f"[infrafoundry:{name}]"},
    )


SERVICE_PATH = "infrafoundry.providers.opnsense.components.nat_rule.NATRuleService"


def _make_service_mock(
    *,
    live: list[LiveNATRule] | None = None,
    diff: Diff | None = None,
    apply_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a mocked ``NATRuleService`` with sensible defaults."""
    service = MagicMock()
    service.search_all.return_value = live if live is not None else []
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
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo")]
        diff = Diff(
            adds=[NATRuleConfig(name="foo", kind="outbound", interface="wan", target="wanip")]
        )
        service_mock = _make_service_mock(diff=diff)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.plan("test-env", resources)
        assert result.adds == diff.adds
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)
        service_mock.compute_diff.assert_called_once()

    def test_threads_add_only(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.plan("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_returns_counts(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo")]
        diff = Diff(
            adds=[NATRuleConfig(name="foo", kind="outbound", interface="wan", target="wanip")]
        )
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 1, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        assert result["resources_created"] == 1
        assert result["success"] is True

    def test_apply_emits_add_outcome(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo")]
        diff = Diff(
            adds=[NATRuleConfig(name="foo", kind="outbound", interface="wan", target="wanip")]
        )
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
        assert outcomes[0].address == "opnsense_nat_rule.foo"

    def test_apply_emits_update_outcome(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo")]
        live = _live_managed("u1", "foo", "outbound")
        want = NATRuleConfig(name="foo", kind="outbound", interface="wan", target="wanip")
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

    def test_apply_emits_delete_outcome(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        resources: list[ResourceConfig] = []
        live = _live_managed("u1", "stale", "outbound")
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
        # Synthetic name uses managed_name from live.
        assert outcomes[0].resource_name == "stale"

    def test_apply_threads_add_only(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo")]
        service_mock = _make_service_mock(diff=Diff())
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.apply("test-env", resources, add_only=True)
        assert service_mock.compute_diff.call_args.kwargs["add_only"] is True

    def test_apply_emits_port_forward_outcomes(self, tmp_path: Path) -> None:
        # Mixed-kind resource list including a port_forward (#725).
        # Each resource emits its own ResourceOutcome regardless of kind.
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("a"), _port_forward_resource("b")]
        diff = Diff(
            adds=[
                NATRuleConfig(name="a", kind="outbound", interface="wan", target="wanip"),
                NATRuleConfig(
                    name="b",
                    kind="port_forward",
                    interface="wan",
                    target="10.0.0.10",
                    local_port="8080",
                ),
            ]
        )
        service_mock = _make_service_mock(
            diff=diff, apply_counts={"created": 2, "updated": 0, "deleted": 0}
        )
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.apply("test-env", resources)
        outcomes = result["resource_outcomes"]
        assert len(outcomes) == 2
        names = {o.resource_name for o in outcomes}
        assert names == {"a", "b"}
        assert result["resources_created"] == 2


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------


class TestDestroy:
    def test_destroy_deletes_matching_managed_rules(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo")]
        live = [_live_managed("u1", "foo", "outbound")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_called_once_with("u1", "outbound")
        service_mock.apply_changes.assert_called_once_with("outbound")
        assert result["resources_destroyed"] == 1
        assert result["locked_skipped"] == 0

    def test_destroy_skips_when_no_live_match(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo")]
        service_mock = _make_service_mock(live=[])
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        service_mock.apply_changes.assert_not_called()
        assert result["resources_destroyed"] == 0

    def test_destroy_honors_lock(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("wan-survival", lock=True)]
        live = [_live_managed("u1", "wan-survival", "outbound")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        service_mock.delete.assert_not_called()
        assert result["locked_skipped"] == 1

    def test_destroy_per_kind_isolation(self, tmp_path: Path) -> None:
        # Two rules named ``foo``: outbound + 1:1. Destroying only deletes
        # the matching kind for each YAML entry.
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo"), _one_to_one_resource("foo")]
        live = [
            _live_managed("u-out", "foo", "outbound"),
            _live_managed("u-oto", "foo", "one_to_one"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        # Both deleted, each from its own controller.
        delete_calls = service_mock.delete.call_args_list
        assert len(delete_calls) == 2
        called_args = {call.args for call in delete_calls}
        assert ("u-out", "outbound") in called_args
        assert ("u-oto", "one_to_one") in called_args
        # Both kinds had applyChanges called.
        apply_calls = {call.args[0] for call in service_mock.apply_changes.call_args_list}
        assert apply_calls == {"outbound", "one_to_one"}
        assert result["resources_destroyed"] == 2

    def test_destroy_three_kind_isolation(self, tmp_path: Path) -> None:
        # All three kinds named ``foo`` (#725). Destroying deletes one
        # per controller; apply_changes is called per kind that had work.
        manager = NATRuleManager(tmp_path)
        resources = [
            _outbound_resource("foo"),
            _one_to_one_resource("foo"),
            _port_forward_resource("foo"),
        ]
        live = [
            _live_managed("u-out", "foo", "outbound"),
            _live_managed("u-oto", "foo", "one_to_one"),
            _live_managed("u-pf", "foo", "port_forward"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.destroy("test-env", resources)
        delete_calls = service_mock.delete.call_args_list
        assert len(delete_calls) == 3
        called_args = {call.args for call in delete_calls}
        assert ("u-out", "outbound") in called_args
        assert ("u-oto", "one_to_one") in called_args
        assert ("u-pf", "port_forward") in called_args
        apply_calls = {call.args[0] for call in service_mock.apply_changes.call_args_list}
        assert apply_calls == {"outbound", "one_to_one", "port_forward"}
        assert result["resources_destroyed"] == 3


# ---------------------------------------------------------------------------
# get_resource_ids
# ---------------------------------------------------------------------------


class TestGetResourceIds:
    def test_maps_names_to_uuids(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo"), _outbound_resource("bar")]
        live = [_live_managed("u1", "foo", "outbound"), _live_managed("u2", "bar", "outbound")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1", "bar": "u2"}

    def test_omits_resources_with_no_live_match(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo"), _outbound_resource("missing")]
        live = [_live_managed("u1", "foo", "outbound")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u1"}

    def test_per_kind_keys_distinguish_outbound_from_1to1(self, tmp_path: Path) -> None:
        # YAML has only the outbound "foo"; live has both. Only the
        # outbound mapping is returned.
        manager = NATRuleManager(tmp_path)
        resources = [_outbound_resource("foo")]
        live = [
            _live_managed("u-out", "foo", "outbound"),
            _live_managed("u-oto", "foo", "one_to_one"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u-out"}

    def test_per_kind_keys_distinguish_port_forward(self, tmp_path: Path) -> None:
        # YAML has only the port_forward "foo"; live has all three kinds.
        # Only the port_forward mapping is returned (#725).
        manager = NATRuleManager(tmp_path)
        resources = [_port_forward_resource("foo")]
        live = [
            _live_managed("u-out", "foo", "outbound"),
            _live_managed("u-oto", "foo", "one_to_one"),
            _live_managed("u-pf", "foo", "port_forward"),
        ]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.get_resource_ids("test-env", resources)
        assert result == {"foo": "u-pf"}


# ---------------------------------------------------------------------------
# list / migrate
# ---------------------------------------------------------------------------


class TestListAndMigrate:
    def test_list_returns_live_rules(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        live = [_live_managed("u1", "foo", "outbound")]
        service_mock = _make_service_mock(live=live)
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.list("test-env")
        assert result == live

    def test_migrate_returns_yaml_string(self, tmp_path: Path) -> None:
        manager = NATRuleManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")
        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once()
