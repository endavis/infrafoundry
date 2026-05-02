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
        type="vlans",
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
        type="aliases",
        provider="opnsense",
        config={"name": name},
    )


class TestFilterVlans:
    """``_filter_vlans`` picks out only ``type='vlans'`` resources."""

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
        vlans = OPNsenseDirectRunner._filter_by_type(resources, "vlans", target_resources=None)
        assert {r.name for r in vlans} == {"v1", "v2"}
        aliases = OPNsenseDirectRunner._filter_by_type(resources, "aliases", target_resources=None)
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
        result = OPNsenseDirectRunner._filter_by_type(resources, "vlans", ["v1"])
        assert [r.type for r in result] == ["vlans"]
        assert [r.name for r in result] == ["v1"]


class TestResolveDispatchTable:
    """``_resolve_dispatch_table`` survives providers that don't expose the hook."""

    def test_returns_provider_table_when_callable(self) -> None:
        provider = MagicMock()
        provider.get_direct_api_resource_types.return_value = {"vlans": object}
        table = OPNsenseDirectRunner._resolve_dispatch_table(provider)
        assert table == {"vlans": object}

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
        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}
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

        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}

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

        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.plan(provider_with_env)

        assert result["success"] is False
        assert "boom" in result["error"]  # type: ignore[typeddict-item]


class TestApplyDelegation:
    """``runner.apply`` iterates the dispatch table and threads ``add_only``."""

    def test_no_vlans_returns_zero_counts(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        manager_cls = MagicMock()
        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}
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
        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}

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
        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}
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
        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.apply(provider_with_env)
        assert result["success"] is False
        assert "api down" in result["error"]  # type: ignore[typeddict-item]


class TestDestroyDelegation:
    """``runner.destroy`` iterates the dispatch table and aggregates counts."""

    def test_no_vlans_returns_zero(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        manager_cls = MagicMock()
        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}
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
        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}
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
        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            ids = runner.get_resource_ids(provider_with_env)
        assert ids == {"v1": "uuid-1"}

    def test_empty_when_no_vlans(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        manager_cls = MagicMock()
        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}
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
        provider_with_env.get_direct_api_resource_types.return_value = {"vlans": manager_cls}
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            ids = runner.get_resource_ids(provider_with_env)
        assert ids == {}


# ---------------------------------------------------------------------------
# Multi-component dispatch
# ---------------------------------------------------------------------------


def _ifa_resource(name: str) -> ResourceConfig:
    return ResourceConfig(
        name=name,
        type="interface_assignments",
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
            "vlans": MagicMock(return_value=vlan_manager),
            "interface_assignments": MagicMock(return_value=ifa_manager),
        }

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.plan(provider_with_env)

        assert result["success"] is True
        # vlans diff has an add → has_changes is True overall.
        assert result["has_changes"] is True  # type: ignore[typeddict-item]
        summary = result["changes_summary"]  # type: ignore[typeddict-item]
        assert "vlans:" in summary
        assert "interface_assignments:" in summary
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
            "vlans": MagicMock(return_value=vlan_manager),
            "interface_assignments": MagicMock(return_value=ifa_manager),
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
            "vlans": MagicMock(return_value=vlan_manager),
            "interface_assignments": MagicMock(return_value=ifa_manager),
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
            "vlans": MagicMock(return_value=vlan_manager),
            "interface_assignments": MagicMock(return_value=ifa_manager),
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
            _alias_resource("a1"),  # type "aliases" is NOT in the dispatch table
            _vlan_resource("v1", "igb0", 10),
        ]
        vlan_manager = MagicMock()
        vlan_manager.plan.return_value = Diff()
        provider_with_env.get_direct_api_resource_types.return_value = {
            "vlans": MagicMock(return_value=vlan_manager),
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.plan(provider_with_env)
        assert result["success"] is True
        # vlan_manager.plan called with only the VLAN resource, never the alias.
        vlan_manager.plan.assert_called_once()
        passed_resources = vlan_manager.plan.call_args.args[1]
        assert all(r.type == "vlans" for r in passed_resources)
