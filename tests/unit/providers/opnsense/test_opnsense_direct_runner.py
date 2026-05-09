"""Unit tests for OPNsenseDirectRunner.

Coverage:
    - Protocol conformance against ADR-0010 protocols.
    - Tool metadata (name, priority, IaC flag, availability).
    - Initialize is a no-op.
    - Resource filtering (per-type and legacy VLAN-specific helper).
    - Plan/apply/destroy iterate the dispatch table and delegate.
    - get_resource_ids surface for StateAware integration.
    - Aggregation across multiple registered components.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.protocols import (
    Applyable,
    Destroyable,
    Plannable,
    StateAware,
)
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.runners.opnsense_direct_runner import OPNsenseDirectRunner
from infrafoundry.core.types import ResourceOutcome
from infrafoundry.providers.opnsense.services.vlan import Diff, VlanConfig

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """OPNsenseDirectRunner implements the ADR-0010 protocols it claims."""

    def test_implements_plannable(self) -> None:
        runner = OPNsenseDirectRunner()
        assert isinstance(runner, Plannable)

    def test_implements_applyable(self) -> None:
        runner = OPNsenseDirectRunner()
        assert isinstance(runner, Applyable)

    def test_implements_destroyable(self) -> None:
        runner = OPNsenseDirectRunner()
        assert isinstance(runner, Destroyable)

    def test_implements_stateaware(self) -> None:
        runner = OPNsenseDirectRunner()
        assert isinstance(runner, StateAware)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestRunnerMetadata:
    """Tool name, priority, IaC flag — all wired correctly."""

    def test_tool_name_uses_underscore(self) -> None:
        # ``getattr(provider, "generate_<tool_name>", None)`` requires a
        # Python identifier — the issue body's "opnsense-direct" would have
        # broken dispatch.
        runner = OPNsenseDirectRunner()
        assert runner.tool_name == "opnsense_direct"

    def test_priority_runs_before_terraform(self) -> None:
        # Terraform = 0, OPNsense direct = -10 so VLAN apply happens first.
        runner = OPNsenseDirectRunner()
        assert runner.priority == -10

    def test_is_iac_runner(self) -> None:
        runner = OPNsenseDirectRunner()
        assert runner.is_iac_runner is True

    def test_is_available_when_opnsense_openapi_imports(self) -> None:
        # opnsense_openapi is a project dependency; it should always import
        # in CI. The branch covers the negative case via ImportError.
        runner = OPNsenseDirectRunner()
        assert runner.is_available() is True


# ---------------------------------------------------------------------------
# Initialize
# ---------------------------------------------------------------------------


class TestInitialize:
    """No-op initialization since direct API has nothing to provision."""

    def test_initialize_returns_success(self, tmp_path: Path) -> None:
        runner = OPNsenseDirectRunner()
        result = runner.initialize(tmp_path)
        assert result == {"success": True, "output": "no init required"}


# ---------------------------------------------------------------------------
# Helper logic
# ---------------------------------------------------------------------------


def _vlan_resource(name: str, device: str, tag: int) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="interfaces.vlans",
        provider="opnsense",
        config={
            "device": device,
            "tag": tag,
            "description": "test",
            "priority": 0,
        },
    )


def _alias_resource(name: str) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="firewall.aliases",
        provider="opnsense",
        config={"name": name},
    )


class TestFilterVlans:
    """``_filter_vlans`` picks out only ``type='interfaces.vlans'`` resources."""

    def test_picks_only_vlan_resources(self) -> None:
        resources = [
            _vlan_resource("v1", "igb0", 10),
            _alias_resource("a1"),
            _vlan_resource("v2", "igb0", 20),
        ]
        result = OPNsenseDirectRunner._filter_vlans(resources, target_resources=None)
        assert len(result) == 2
        assert {r.name for r in result} == {"v1", "v2"}

    def test_target_resources_filters_by_name(self) -> None:
        resources = [
            _vlan_resource("v1", "igb0", 10),
            _vlan_resource("v2", "igb0", 20),
        ]
        result = OPNsenseDirectRunner._filter_vlans(resources, target_resources=["v1"])
        assert len(result) == 1
        assert result[0].name == "v1"

    def test_no_target_returns_all_vlans(self) -> None:
        resources = [_vlan_resource("v1", "igb0", 10), _vlan_resource("v2", "igb0", 20)]
        result = OPNsenseDirectRunner._filter_vlans(resources, target_resources=None)
        assert len(result) == 2


class TestFilterByType:
    """``_filter_by_type`` is the generic dispatch-table primitive."""

    def test_picks_resources_by_type_name(self) -> None:
        resources = [
            _vlan_resource("v1", "igb0", 10),
            _alias_resource("a1"),
            _vlan_resource("v2", "igb0", 20),
        ]
        vlans = OPNsenseDirectRunner._filter_by_type(
            resources, "interfaces.vlans", target_resources=None
        )
        assert {r.name for r in vlans} == {"v1", "v2"}
        aliases = OPNsenseDirectRunner._filter_by_type(
            resources, "firewall.aliases", target_resources=None
        )
        assert {r.name for r in aliases} == {"a1"}

    def test_unknown_type_returns_empty(self) -> None:
        resources = [_vlan_resource("v1", "igb0", 10)]
        result = OPNsenseDirectRunner._filter_by_type(resources, "nonexistent", None)
        assert result == []

    def test_target_resources_scopes_within_type(self) -> None:
        resources = [
            _vlan_resource("v1", "igb0", 10),
            _vlan_resource("v2", "igb0", 20),
            _alias_resource("v1"),  # same name, different type
        ]
        result = OPNsenseDirectRunner._filter_by_type(resources, "interfaces.vlans", ["v1"])
        assert [r.type for r in result] == ["interfaces.vlans"]
        assert [r.name for r in result] == ["v1"]


class TestResolveDispatchTable:
    """``_resolve_dispatch_table`` survives providers that don't expose the hook."""

    def test_returns_provider_table_when_callable(self) -> None:
        provider = MagicMock()
        provider.get_direct_api_resource_types.return_value = {"interfaces.vlans": object}
        table = OPNsenseDirectRunner._resolve_dispatch_table(provider)
        assert table == {"interfaces.vlans": object}

    def test_returns_empty_when_attribute_missing(self) -> None:
        class _Bare:
            pass

        table = OPNsenseDirectRunner._resolve_dispatch_table(_Bare())  # type: ignore[arg-type]
        assert table == {}

    def test_returns_empty_when_attribute_not_callable(self) -> None:
        provider = MagicMock()
        provider.get_direct_api_resource_types = "not callable"
        table = OPNsenseDirectRunner._resolve_dispatch_table(provider)
        assert table == {}

    def test_returns_empty_when_table_not_a_dict(self) -> None:
        provider = MagicMock()
        provider.get_direct_api_resource_types.return_value = ["not", "a", "dict"]
        table = OPNsenseDirectRunner._resolve_dispatch_table(provider)
        assert table == {}


class TestResolveEnvName:
    """``_resolve_env_name`` reads ``provider._current_environment``."""

    def test_returns_env_name(self) -> None:
        provider = MagicMock()
        provider._current_environment = "prod"
        assert OPNsenseDirectRunner._resolve_env_name(provider) == "prod"

    def test_raises_when_env_not_set(self) -> None:
        provider = MagicMock()
        provider._current_environment = None
        with pytest.raises(RuntimeError, match="set_environment"):
            OPNsenseDirectRunner._resolve_env_name(provider)


# ---------------------------------------------------------------------------
# Plan / apply / destroy delegation
# ---------------------------------------------------------------------------


@pytest.fixture
def provider_with_env(tmp_path: Path) -> MagicMock:
    """Provider whose dispatch table only registers ``vlans``.

    Most legacy tests assume a single-component dispatch; new tests
    cover multi-component aggregation explicitly via dedicated fixtures.
    """
    provider = MagicMock()
    provider._current_environment = "test-env"
    provider.config_dir = tmp_path
    provider.name = "opnsense"
    # Default to an empty dispatch; tests configure as needed.
    provider.get_direct_api_resource_types.return_value = {}
    return provider


class TestPlanDelegation:
    """``runner.plan`` iterates the dispatch table and delegates to each manager."""

    def test_returns_no_changes_when_no_vlans(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        # Even with VLAN registered, an empty resource list means no dispatch.
        manager_cls = MagicMock()
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            result = runner.plan(provider_with_env)
        assert result["success"] is True
        assert result["has_changes"] is False  # type: ignore[typeddict-item]
        manager_cls.assert_not_called()

    def test_returns_no_changes_when_dispatch_empty(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        # Dispatch table empty: nothing to plan even if resources exist.
        with patch.object(
            OPNsenseDirectRunner,
            "_load_provider_resources",
            return_value=[_vlan_resource("v1", "igb0", 10)],
        ):
            result = runner.plan(provider_with_env)
        assert result["success"] is True
        assert result["has_changes"] is False  # type: ignore[typeddict-item]

    def test_calls_manager_plan_with_add_only(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        diff = Diff(adds=[VlanConfig("v1", "igb0", 10, "test", 0)])

        manager_mock = MagicMock()
        manager_mock.plan.return_value = diff
        manager_cls = MagicMock(return_value=manager_mock)

        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.plan(provider_with_env, add_only=True)

        manager_cls.assert_called_once_with(provider_with_env.config_dir)
        manager_mock.plan.assert_called_once_with("test-env", resources, add_only=True)
        assert result["success"] is True
        assert result["has_changes"] is True  # type: ignore[typeddict-item]
        assert "1 to add" in result["changes_summary"]  # type: ignore[typeddict-item]
        assert "add-only mode" in result["changes_summary"]  # type: ignore[typeddict-item]

    def test_plan_failure_returns_error(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]

        manager_mock = MagicMock()
        manager_mock.plan.side_effect = RuntimeError("boom")
        manager_cls = MagicMock(return_value=manager_mock)

        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.plan(provider_with_env)

        assert result["success"] is False
        assert "boom" in result["error"]  # type: ignore[typeddict-item]


class TestApplyDelegation:
    """``runner.apply`` iterates the dispatch table and threads ``add_only``."""

    def test_no_vlans_returns_zero_counts(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        manager_cls = MagicMock()
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            result = runner.apply(provider_with_env)
        assert result["success"] is True
        assert result["resources_created"] == 0  # type: ignore[typeddict-item]
        assert result["resources_updated"] == 0  # type: ignore[typeddict-item]
        assert result["resources_deleted"] == 0  # type: ignore[typeddict-item]
        assert result["resource_outcomes"] == []  # type: ignore[typeddict-item]
        manager_cls.assert_not_called()

    def test_outcomes_returned(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        outcome = ResourceOutcome(address="opnsense_vlan.v1", action="add", resource_name="v1")
        manager_mock = MagicMock()
        manager_mock.apply.return_value = {
            "success": True,
            "resources_created": 1,
            "resources_updated": 0,
            "resources_deleted": 0,
            "resource_outcomes": [outcome],
        }
        manager_cls = MagicMock(return_value=manager_mock)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.apply(provider_with_env, auto_approve=True, add_only=False)

        manager_mock.apply.assert_called_once_with(
            "test-env", resources, auto_approve=True, add_only=False
        )
        assert result["resources_created"] == 1  # type: ignore[typeddict-item]
        assert result["resource_outcomes"] == [outcome]  # type: ignore[typeddict-item]

    def test_apply_threads_add_only(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_mock = MagicMock()
        manager_mock.apply.return_value = {
            "success": True,
            "resources_created": 1,
            "resources_updated": 0,
            "resources_deleted": 0,
            "resource_outcomes": [],
        }
        manager_cls = MagicMock(return_value=manager_mock)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.apply(provider_with_env, add_only=True)
        # add_only kwarg propagated.
        assert manager_mock.apply.call_args.kwargs["add_only"] is True

    def test_apply_failure_returns_error(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_mock = MagicMock()
        manager_mock.apply.side_effect = RuntimeError("api down")
        manager_cls = MagicMock(return_value=manager_mock)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.apply(provider_with_env)
        assert result["success"] is False
        assert "api down" in result["error"]  # type: ignore[typeddict-item]


class TestDestroyDelegation:
    """``runner.destroy`` iterates the dispatch table and aggregates counts."""

    def test_no_vlans_returns_zero(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        manager_cls = MagicMock()
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            result = runner.destroy(provider_with_env)
        assert result["success"] is True
        assert result["resources_destroyed"] == 0  # type: ignore[typeddict-item]

    def test_calls_manager_destroy(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_mock = MagicMock()
        manager_mock.destroy.return_value = {
            "success": True,
            "resources_destroyed": 1,
            "locked_skipped": 0,
        }
        manager_cls = MagicMock(return_value=manager_mock)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.destroy(provider_with_env, auto_approve=True)
        assert result["resources_destroyed"] == 1  # type: ignore[typeddict-item]
        manager_mock.destroy.assert_called_once_with("test-env", resources, auto_approve=True)


class TestGetResourceIds:
    """``get_resource_ids`` merges UUID maps across all registered components."""

    def test_returns_uuid_map(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_mock = MagicMock()
        manager_mock.get_resource_ids.return_value = {"v1": "uuid-1"}
        manager_cls = MagicMock(return_value=manager_mock)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            ids = runner.get_resource_ids(provider_with_env)
        assert ids == {"v1": "uuid-1"}

    def test_empty_when_no_vlans(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        manager_cls = MagicMock()
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            ids = runner.get_resource_ids(provider_with_env)
        assert ids == {}

    def test_swallows_errors(self, provider_with_env: MagicMock) -> None:
        # Failures here are non-fatal — we don't want a state-lookup blip
        # to abort an apply that already succeeded. Per-component failures
        # are skipped so other components can still report their IDs.
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_mock = MagicMock()
        manager_mock.get_resource_ids.side_effect = RuntimeError("transient")
        manager_cls = MagicMock(return_value=manager_mock)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            ids = runner.get_resource_ids(provider_with_env)
        assert ids == {}


# ---------------------------------------------------------------------------
# Multi-component dispatch
# ---------------------------------------------------------------------------


def _ifa_resource(name: str) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="interfaces.assignments",
        provider="opnsense",
        config={"device": "igb0", "description": name},
    )


class TestMultiComponentDispatch:
    """Runner aggregates plan/apply/destroy/IDs across every registered type."""

    def test_plan_aggregates_summaries_across_types(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10), _ifa_resource("lan")]

        vlan_manager = MagicMock()
        vlan_manager.plan.return_value = Diff(adds=[VlanConfig("v1", "igb0", 10, "x", 0)])

        # Simulate a read-only manager: a Diff-shaped value with read_only=True
        # and a message attribute. The runner must surface the message and
        # NOT count the result toward has_changes.
        readonly_diff = Diff()
        readonly_diff.read_only = True  # type: ignore[attr-defined]
        readonly_diff.message = "interface_assignments are read-only on this OPNsense version"  # type: ignore[attr-defined]
        ifa_manager = MagicMock()
        ifa_manager.plan.return_value = readonly_diff

        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": MagicMock(return_value=vlan_manager),
            "interfaces.assignments": MagicMock(return_value=ifa_manager),
        }

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.plan(provider_with_env)

        assert result["success"] is True
        # vlans diff has an add → has_changes is True overall.
        assert result["has_changes"] is True  # type: ignore[typeddict-item]
        summary = result["changes_summary"]  # type: ignore[typeddict-item]
        assert "interfaces.vlans:" in summary
        assert "interfaces.assignments:" in summary
        assert "read-only" in summary

    def test_apply_aggregates_counts_and_outcomes(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10), _ifa_resource("lan")]

        outcome = ResourceOutcome(address="opnsense_vlan.v1", action="add", resource_name="v1")
        vlan_manager = MagicMock()
        vlan_manager.apply.return_value = {
            "success": True,
            "resources_created": 1,
            "resources_updated": 0,
            "resources_deleted": 0,
            "resource_outcomes": [outcome],
        }

        ifa_manager = MagicMock()
        ifa_manager.apply.return_value = {
            "success": True,
            "resources_created": 0,
            "resources_updated": 0,
            "resources_deleted": 0,
            "resource_outcomes": [],
            "message": "1 assignment described, manual GUI configuration required",
        }

        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": MagicMock(return_value=vlan_manager),
            "interfaces.assignments": MagicMock(return_value=ifa_manager),
        }

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.apply(provider_with_env)

        assert result["resources_created"] == 1  # type: ignore[typeddict-item]
        assert result["resource_outcomes"] == [outcome]  # type: ignore[typeddict-item]
        # Each manager dispatched exactly once.
        vlan_manager.apply.assert_called_once()
        ifa_manager.apply.assert_called_once()

    def test_destroy_sums_destroyed_counts(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10), _ifa_resource("lan")]

        vlan_manager = MagicMock()
        vlan_manager.destroy.return_value = {
            "success": True,
            "resources_destroyed": 1,
            "locked_skipped": 0,
        }
        ifa_manager = MagicMock()
        ifa_manager.destroy.return_value = {
            "success": True,
            "resources_destroyed": 0,
            "message": "interface_assignments are read-only; nothing destroyed",
        }

        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": MagicMock(return_value=vlan_manager),
            "interfaces.assignments": MagicMock(return_value=ifa_manager),
        }

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.destroy(provider_with_env)

        assert result["resources_destroyed"] == 1  # type: ignore[typeddict-item]

    def test_get_resource_ids_merges_across_components(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10), _ifa_resource("lan")]

        vlan_manager = MagicMock()
        vlan_manager.get_resource_ids.return_value = {"v1": "uuid-vlan"}
        ifa_manager = MagicMock()
        ifa_manager.get_resource_ids.return_value = {"lan": "lan"}

        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": MagicMock(return_value=vlan_manager),
            "interfaces.assignments": MagicMock(return_value=ifa_manager),
        }

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            ids = runner.get_resource_ids(provider_with_env)
        assert ids == {"v1": "uuid-vlan", "lan": "lan"}

    def test_unregistered_resource_types_ignored(self, provider_with_env: MagicMock) -> None:
        # A resource type missing from the dispatch table is silently
        # ignored — terraform/other paths still see it; the direct-API
        # runner just doesn't dispatch it.
        runner = OPNsenseDirectRunner()
        resources = [
            _alias_resource(
                "a1"
            ),  # "firewall.aliases" is intentionally absent from THIS test's mock dispatch
            _vlan_resource("v1", "igb0", 10),
        ]
        vlan_manager = MagicMock()
        vlan_manager.plan.return_value = Diff()
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": MagicMock(return_value=vlan_manager),
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.plan(provider_with_env)
        assert result["success"] is True
        # vlan_manager.plan called with only the VLAN resource, never the alias.
        vlan_manager.plan.assert_called_once()
        passed_resources = vlan_manager.plan.call_args.args[1]
        assert all(r.type == "interfaces.vlans" for r in passed_resources)


# ---------------------------------------------------------------------------
# Finalization-hook plumbing (#758)
# ---------------------------------------------------------------------------


def _hook_manager(
    *,
    hook_key: str | None,
    created: int = 0,
    updated: int = 0,
    deleted: int = 0,
) -> tuple[MagicMock, MagicMock]:
    """Build a manager_cls + manager_instance pair with a configurable hook key.

    The first element is the dispatch-table value (a callable returning the
    instance); the second is the manager instance. Tests assert on the
    instance's apply-call shape and on the runner's hook firing.
    """
    instance = MagicMock()
    instance.apply.return_value = {
        "success": True,
        "resources_created": created,
        "resources_updated": updated,
        "resources_deleted": deleted,
        "resource_outcomes": [],
    }

    cls = MagicMock(return_value=instance)
    if hook_key is not None:
        cls.FINALIZATION_HOOK = hook_key
    else:
        # Manager class explicitly without the attribute.
        if hasattr(cls, "FINALIZATION_HOOK"):
            del cls.FINALIZATION_HOOK
    return cls, instance


class TestFinalizationHookPlumbing:
    """Apply collects ``FINALIZATION_HOOK`` keys from changed managers and fires them once."""

    def test_hook_fires_when_manager_had_changes(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_cls, _ = _hook_manager(hook_key="my_hook", created=1)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        hook = MagicMock()
        provider_with_env.get_finalization_hooks.return_value = {"my_hook": hook}
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.apply(provider_with_env)
        hook.assert_called_once_with("test-env")

    def test_hook_skipped_when_manager_had_no_changes(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_cls, _ = _hook_manager(hook_key="my_hook", created=0)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        hook = MagicMock()
        provider_with_env.get_finalization_hooks.return_value = {"my_hook": hook}
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.apply(provider_with_env)
        hook.assert_not_called()

    def test_shared_hook_key_fires_once(self, provider_with_env: MagicMock) -> None:
        # Two different manager classes both declare the same FINALIZATION_HOOK
        # key — the runner must dedupe and call the hook exactly once.
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10), _ifa_resource("lan")]

        cls_a, _ = _hook_manager(hook_key="shared_hook", created=1)
        cls_b, _ = _hook_manager(hook_key="shared_hook", updated=1)

        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": cls_a,
            "interfaces.assignments": cls_b,
        }
        hook = MagicMock()
        provider_with_env.get_finalization_hooks.return_value = {"shared_hook": hook}

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.apply(provider_with_env)

        hook.assert_called_once_with("test-env")

    def test_distinct_hook_keys_fire_each_once(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10), _ifa_resource("lan")]

        cls_a, _ = _hook_manager(hook_key="hook_a", created=1)
        cls_b, _ = _hook_manager(hook_key="hook_b", deleted=1)

        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": cls_a,
            "interfaces.assignments": cls_b,
        }
        hook_a = MagicMock()
        hook_b = MagicMock()
        provider_with_env.get_finalization_hooks.return_value = {
            "hook_a": hook_a,
            "hook_b": hook_b,
        }

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.apply(provider_with_env)

        hook_a.assert_called_once_with("test-env")
        hook_b.assert_called_once_with("test-env")

    def test_manager_without_hook_key_does_not_trigger(self, provider_with_env: MagicMock) -> None:
        # A manager that simply doesn't declare ``FINALIZATION_HOOK`` is
        # unaffected — the runner skips it without touching ``hooks``.
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_cls, _ = _hook_manager(hook_key=None, created=1)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        # Provider exposes a hooks dict — but the manager didn't trigger any key.
        hook = MagicMock()
        provider_with_env.get_finalization_hooks.return_value = {"unrelated": hook}
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.apply(provider_with_env)
        hook.assert_not_called()

    def test_provider_without_get_finalization_hooks_is_graceful_noop(self) -> None:
        # When the provider doesn't expose ``get_finalization_hooks`` at all,
        # the runner must continue without raising. We construct a bare object
        # to avoid MagicMock auto-attributes.
        runner = OPNsenseDirectRunner()
        manager_cls, _ = _hook_manager(hook_key="my_hook", created=1)

        class _BareProvider:
            name = "opnsense"
            _current_environment = "test-env"
            config_dir = Path("/tmp")

            def generate_opnsense_direct(self, resources: Any) -> None:
                pass

            def get_direct_api_resource_types(self) -> dict[str, Any]:
                return {"interfaces.vlans": manager_cls}

        provider = _BareProvider()
        resources = [_vlan_resource("v1", "igb0", 10)]
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.apply(provider)  # type: ignore[arg-type]
        # No hooks dict, no error.
        assert result["success"] is True  # type: ignore[typeddict-item]

    def test_hook_error_propagates_and_fails_apply(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_cls, _ = _hook_manager(hook_key="my_hook", created=1)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }

        def _boom(_env: str) -> None:
            raise RuntimeError("reconfigure failed")

        provider_with_env.get_finalization_hooks.return_value = {"my_hook": _boom}

        with (
            patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources),
            pytest.raises(RuntimeError, match="reconfigure failed"),
        ):
            runner.apply(provider_with_env)

    def test_unregistered_hook_key_is_skipped(self, provider_with_env: MagicMock) -> None:
        # A manager declares a key the provider's hooks dict doesn't carry.
        # Runner logs and continues — does NOT raise.
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_cls, _ = _hook_manager(hook_key="missing_hook", created=1)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        provider_with_env.get_finalization_hooks.return_value = {}

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.apply(provider_with_env)
        assert result["success"] is True  # type: ignore[typeddict-item]

    def test_hooks_skip_on_destroy(self, provider_with_env: MagicMock) -> None:
        # Destroy must NOT fire finalization hooks — the contract is
        # apply-only.
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_cls, instance = _hook_manager(hook_key="my_hook", deleted=1)
        instance.destroy.return_value = {
            "success": True,
            "resources_destroyed": 1,
            "locked_skipped": 0,
        }
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        hook = MagicMock()
        provider_with_env.get_finalization_hooks.return_value = {"my_hook": hook}
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.destroy(provider_with_env)
        hook.assert_not_called()

    def test_hooks_skip_on_plan(self, provider_with_env: MagicMock) -> None:
        # Plan must NOT fire finalization hooks — plan never mutates.
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_cls, instance = _hook_manager(hook_key="my_hook", created=1)
        instance.plan.return_value = Diff(adds=[VlanConfig("v1", "igb0", 10, "x", 0)])
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls
        }
        hook = MagicMock()
        provider_with_env.get_finalization_hooks.return_value = {"my_hook": hook}
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.plan(provider_with_env)
        hook.assert_not_called()


# ---------------------------------------------------------------------------
# Unbound reconfigure coalescing (#776)
# ---------------------------------------------------------------------------


def _uho_resource(name: str) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="unbound.host_overrides",
        provider="opnsense",
        config={"hostname": "web", "domain": "example.com", "server": "192.168.1.10"},
    )


def _uha_resource(name: str) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="unbound.host_aliases",
        provider="opnsense",
        config={"host": "web", "hostname": "alias", "domain": "example.com"},
    )


def _ufwd_resource(name: str) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="unbound.forwards",
        provider="opnsense",
        config={"server": "10.0.0.53"},
    )


class TestUnboundReconfigureCoalescing:
    """All three unbound managers (host_override / host_alias / forward)
    declare ``FINALIZATION_HOOK = "unbound_reconfigure"`` (#776). The runner
    must coalesce the hook firing across them so a multi-unbound apply
    produces exactly one ``unbound/service/reconfigure`` call.

    These tests use the same ``unbound_reconfigure`` hook key as the
    production code so they verify the contract end-to-end through the
    runner's hook plumbing.
    """

    def test_apply_touching_all_three_unbound_types_fires_hook_once(
        self, provider_with_env: MagicMock
    ) -> None:
        runner = OPNsenseDirectRunner()
        resources = [
            _uho_resource("override-1"),
            _uha_resource("alias-1"),
            _ufwd_resource("forward-1"),
        ]
        # All three managers declare the same hook key and report changes.
        cls_uho, _ = _hook_manager(hook_key="unbound_reconfigure", created=1)
        cls_uha, _ = _hook_manager(hook_key="unbound_reconfigure", updated=1)
        cls_ufwd, _ = _hook_manager(hook_key="unbound_reconfigure", deleted=1)

        provider_with_env.get_direct_api_resource_types.return_value = {
            "unbound.host_overrides": cls_uho,
            "unbound.host_aliases": cls_uha,
            "unbound.forwards": cls_ufwd,
        }
        hook = MagicMock()
        provider_with_env.get_finalization_hooks.return_value = {"unbound_reconfigure": hook}

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.apply(provider_with_env)

        hook.assert_called_once_with("test-env")

    def test_apply_touching_only_one_unbound_type_fires_hook_once(
        self, provider_with_env: MagicMock
    ) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_uho_resource("override-1")]
        cls_uho, _ = _hook_manager(hook_key="unbound_reconfigure", created=1)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "unbound.host_overrides": cls_uho,
        }
        hook = MagicMock()
        provider_with_env.get_finalization_hooks.return_value = {"unbound_reconfigure": hook}

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.apply(provider_with_env)

        hook.assert_called_once_with("test-env")

    def test_apply_touching_none_fires_hook_zero_times(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        # Manager registered for the type but no resources of that type.
        # The dispatch table is iterated but no manager is instantiated.
        resources: list[ResourceConfig] = [_vlan_resource("v1", "igb0", 10)]
        cls_uho, _ = _hook_manager(hook_key="unbound_reconfigure", created=1)
        # Register a vlan manager that returns zero changes — apply walks
        # the dispatch table but no unbound manager fires.
        cls_vlan, _ = _hook_manager(hook_key=None, created=0)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": cls_vlan,
            "unbound.host_overrides": cls_uho,
        }
        hook = MagicMock()
        provider_with_env.get_finalization_hooks.return_value = {"unbound_reconfigure": hook}

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.apply(provider_with_env)

        hook.assert_not_called()

    def test_apply_with_unbound_changes_but_no_change_only_unbound_skips_hook(
        self, provider_with_env: MagicMock
    ) -> None:
        # If the unbound manager runs but reports no changes, the hook
        # must not fire (the runner only adds the key when the manager
        # actually mutated state).
        runner = OPNsenseDirectRunner()
        resources = [_uho_resource("override-1")]
        cls_uho, _ = _hook_manager(hook_key="unbound_reconfigure", created=0)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "unbound.host_overrides": cls_uho,
        }
        hook = MagicMock()
        provider_with_env.get_finalization_hooks.return_value = {"unbound_reconfigure": hook}

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.apply(provider_with_env)

        hook.assert_not_called()


# ---------------------------------------------------------------------------
# Sibling-resource threading (#802)
# ---------------------------------------------------------------------------


def _kea_subnet(name: str, *, subnet: str = "10.0.10.0/24") -> ResourceConfig:
    """Helper for ``kea.dhcp4.subnets`` resources."""
    return ResourceConfig(
        name=name,
        type="kea.dhcp4.subnets",
        provider="opnsense",
        config={"subnet": subnet},
    )


def _kea_reservation(name: str) -> ResourceConfig:
    """Helper for ``kea.dhcp4.reservations`` resources."""
    return ResourceConfig(
        name=name,
        type="kea.dhcp4.reservations",
        provider="opnsense",
        config={
            "subnet_ref": "lan-dhcp",
            "hw_address": "aa:bb:cc:dd:ee:01",
            "ip_address": "10.0.10.50",
            "hostname": name,
        },
    )


class TestSiblingResourceThreading:
    """Runner threads ``sibling_resources`` to managers that opt-in via
    ``SIBLING_RESOURCE_TYPE`` (#802). Managers without the attribute keep
    unchanged signatures.
    """

    def test_sibling_resources_for_returns_slice_when_attribute_set(self) -> None:
        # Build a fake manager class that opts in to the kea.dhcp4.subnets slice.
        class _OptedInManager:
            SIBLING_RESOURCE_TYPE = "kea.dhcp4.subnets"

        all_resources = [
            _kea_subnet("lan-dhcp", subnet="10.0.10.0/24"),
            _kea_subnet("guest-dhcp", subnet="10.0.20.0/24"),
            _kea_reservation("server1"),
            _vlan_resource("v1", "igb0", 10),
        ]
        sibling = OPNsenseDirectRunner._sibling_resources_for(_OptedInManager, all_resources)
        assert sibling is not None
        assert len(sibling) == 2
        assert {r.name for r in sibling} == {"lan-dhcp", "guest-dhcp"}

    def test_sibling_resources_for_returns_none_when_attribute_missing(self) -> None:
        class _BareManager:
            pass

        sibling = OPNsenseDirectRunner._sibling_resources_for(
            _BareManager, [_vlan_resource("v1", "igb0", 10)]
        )
        assert sibling is None

    def test_sibling_resources_for_returns_none_when_attribute_is_none(self) -> None:
        class _ExplicitNoneManager:
            SIBLING_RESOURCE_TYPE = None

        sibling = OPNsenseDirectRunner._sibling_resources_for(
            _ExplicitNoneManager, [_vlan_resource("v1", "igb0", 10)]
        )
        assert sibling is None

    def test_dispatch_passes_sibling_resources_to_kea_reservation_managers(
        self, provider_with_env: MagicMock
    ) -> None:
        """The runner threads kea.dhcp4.subnets into the reservation manager."""
        runner = OPNsenseDirectRunner()
        all_resources = [
            _kea_subnet("lan-dhcp", subnet="10.0.10.0/24"),
            _kea_reservation("server1"),
        ]

        # Build a manager class that opts in via SIBLING_RESOURCE_TYPE.
        manager_instance = MagicMock()
        manager_instance.plan.return_value = MagicMock(
            adds=[], updates=[], deletes=[], locked=[], is_empty=True
        )
        manager_cls = MagicMock(return_value=manager_instance)
        manager_cls.SIBLING_RESOURCE_TYPE = "kea.dhcp4.subnets"

        provider_with_env.get_direct_api_resource_types.return_value = {
            "kea.dhcp4.reservations": manager_cls,
        }

        with patch.object(
            OPNsenseDirectRunner, "_load_provider_resources", return_value=all_resources
        ):
            runner.plan(provider_with_env)

        manager_instance.plan.assert_called_once()
        call_kwargs = manager_instance.plan.call_args.kwargs
        # The runner must pass sibling_resources containing the sibling subnet slice.
        assert "sibling_resources" in call_kwargs
        passed_siblings = call_kwargs["sibling_resources"]
        assert len(passed_siblings) == 1
        assert passed_siblings[0].name == "lan-dhcp"
        assert passed_siblings[0].type == "kea.dhcp4.subnets"

    def test_dispatch_does_not_pass_sibling_resources_when_manager_does_not_opt_in(
        self, provider_with_env: MagicMock
    ) -> None:
        """Existing managers (no SIBLING_RESOURCE_TYPE) must keep unchanged kwargs."""
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]

        manager_instance = MagicMock()
        manager_instance.plan.return_value = Diff(adds=[VlanConfig("v1", "igb0", 10, "x", 0)])
        # Bare manager class — no SIBLING_RESOURCE_TYPE attribute.
        manager_cls = MagicMock(spec=["__call__"], return_value=manager_instance)

        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": manager_cls,
        }

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            runner.plan(provider_with_env)

        manager_instance.plan.assert_called_once()
        call_kwargs = manager_instance.plan.call_args.kwargs
        # The runner must NOT pass sibling_resources to managers that don't opt in.
        assert "sibling_resources" not in call_kwargs
