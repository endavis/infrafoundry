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
from types import SimpleNamespace
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

    def test_singletons_selected_by_dotted_name(self) -> None:
        """Singletons carry their dotted type as name, so ``-r`` selects one (#1237)."""
        resources = [
            ResourceConfig(name=t, type=t, provider="opnsense", config={})
            for t in ("system.tuning", "system.firmware")
        ]
        result = OPNsenseDirectRunner._filter_by_type(resources, "system.tuning", ["system.tuning"])
        assert [r.name for r in result] == ["system.tuning"]
        assert OPNsenseDirectRunner._filter_by_type(resources, "system.tuning", ["settings"]) == []


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


EXAMPLE_ENVS = Path(__file__).resolve().parents[4] / "example-config" / "envs"


class TestLoadProviderResources:
    """The runner sees every opnsense resource in the env, wherever it is declared (#1128)."""

    def _load(self) -> list[ResourceConfig]:
        provider = SimpleNamespace(
            name="opnsense", config_dir=EXAMPLE_ENVS, _current_environment="dev"
        )
        return OPNsenseDirectRunner._load_provider_resources(provider)  # type: ignore[arg-type]

    def test_includes_reservations_from_proxmox_packages(self) -> None:
        """example-config dev has no opnsense/ directory; its reservations live in
        proxmox blueprint packages, which the old per-directory load missed."""
        names = {r.name for r in self._load() if r.type == "kea.dhcp4.reservations"}

        assert {"k3s-dev-server-dhcp", "k3s-dev-agent-1-dhcp", "aiqum"} <= names

    def test_keeps_only_opnsense_resources(self) -> None:
        assert {r.provider for r in self._load()} == {"opnsense"}


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
        assert result.get("has_changes") is False
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
        assert result.get("has_changes") is False

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
        assert result.get("has_changes") is True
        assert "changes_summary" in result
        assert "1 to add" in result["changes_summary"]
        assert "add-only mode" in result["changes_summary"]

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
        assert "error" in result
        assert "boom" in result["error"]


class TestFilteredRunsNeverDelete:
    """A filtered run reaches the managers with only its targets, so it must not
    delete live resources outside the filter (#1128)."""

    def _setup(self, provider: MagicMock) -> tuple[MagicMock, list[ResourceConfig]]:
        resources = [_vlan_resource("v1", "igb0", 10), _vlan_resource("v2", "igb0", 20)]
        manager_mock = MagicMock()
        manager_mock.plan.return_value = Diff()
        manager_mock.apply.return_value = {
            "success": True,
            "resources_created": 0,
            "resources_updated": 0,
            "resources_deleted": 0,
            "resource_outcomes": [],
        }
        provider.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": MagicMock(return_value=manager_mock)
        }
        return manager_mock, resources

    def test_filtered_plan_is_add_only(self, provider_with_env: MagicMock) -> None:
        manager_mock, resources = self._setup(provider_with_env)

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            OPNsenseDirectRunner().plan(provider_with_env, target_resources=["v1"])

        manager_mock.plan.assert_called_once_with("test-env", [resources[0]], add_only=True)

    def test_filtered_apply_is_add_only(self, provider_with_env: MagicMock) -> None:
        manager_mock, resources = self._setup(provider_with_env)

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            OPNsenseDirectRunner().apply(provider_with_env, target_resources=["v1"])

        manager_mock.apply.assert_called_once_with(
            "test-env", [resources[0]], auto_approve=True, add_only=True
        )

    def test_unfiltered_plan_still_reconciles(self, provider_with_env: MagicMock) -> None:
        manager_mock, resources = self._setup(provider_with_env)

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            OPNsenseDirectRunner().plan(provider_with_env)

        manager_mock.plan.assert_called_once_with("test-env", resources, add_only=False)


class TestTypeWithNoYamlEntriesIsSkippedWithoutManagedSet:
    """A type with no YAML entries is not dispatched when no managed set is given (#1252).

    Without ``managed_resources`` the runner cannot tell managed objects from
    unmanaged ones, so reconciling the type would delete unmanaged live objects.
    With a managed set the type is dispatched only for its managed rows (#1256);
    see ``TestTypeWithNoYamlEntriesDispatchedWhenManaged``.
    """

    def _setup(self, provider: MagicMock) -> tuple[MagicMock, MagicMock, MagicMock]:
        vlan_manager = MagicMock()
        vlan_manager.plan.return_value = Diff()
        vlan_manager.apply.return_value = {
            "success": True,
            "resources_created": 0,
            "resources_updated": 0,
            "resources_deleted": 0,
            "resource_outcomes": [],
        }
        ifa_manager = MagicMock()
        # Live objects exist on the box; a reconcile would delete them.
        ifa_manager.plan.return_value = Diff(deletes=[MagicMock()])
        provider.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": MagicMock(return_value=vlan_manager),
            "interfaces.assignments": MagicMock(return_value=ifa_manager),
        }
        return vlan_manager, ifa_manager, provider

    def test_plan_skips_type_without_yaml_entries(self, provider_with_env: MagicMock) -> None:
        vlan_manager, ifa_manager, _ = self._setup(provider_with_env)
        resources = [_vlan_resource("v1", "igb0", 10)]

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            OPNsenseDirectRunner().plan(provider_with_env)

        vlan_manager.plan.assert_called_once()
        ifa_manager.plan.assert_not_called()

    def test_apply_skips_type_without_yaml_entries(self, provider_with_env: MagicMock) -> None:
        vlan_manager, ifa_manager, _ = self._setup(provider_with_env)
        resources = [_vlan_resource("v1", "igb0", 10)]

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            OPNsenseDirectRunner().apply(provider_with_env, auto_approve=True)

        vlan_manager.apply.assert_called_once()
        ifa_manager.apply.assert_not_called()


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
        assert result.get("resources_created") == 0
        assert result.get("resources_updated") == 0
        assert result.get("resources_deleted") == 0
        assert result.get("resource_outcomes") == []
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
        assert result.get("resources_created") == 1
        assert result.get("resource_outcomes") == [outcome]

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
        assert "error" in result
        assert "api down" in result["error"]


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
        assert result.get("resources_destroyed") == 0

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
        assert result.get("resources_destroyed") == 1
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
        assert result.get("has_changes") is True
        assert "changes_summary" in result
        summary = result["changes_summary"]
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

        assert result.get("resources_created") == 1
        assert result.get("resource_outcomes") == [outcome]
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

        assert result.get("resources_destroyed") == 1

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
        assert result["success"] is True

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
        assert result["success"] is True

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
        config={"server": "172.21.0.53"},
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

    def test_forwards_and_advanced_both_changing_fire_hook_once(
        self, provider_with_env: MagicMock
    ) -> None:
        runner = OPNsenseDirectRunner()
        resources = [
            _ufwd_resource("forward-1"),
            ResourceConfig(
                name="unbound.advanced",
                type="unbound.advanced",
                provider="opnsense",
                config={"private_domains": ["a.example"]},
            ),
        ]
        cls_ufwd, _ = _hook_manager(hook_key="unbound_reconfigure", created=1)
        cls_uadv, _ = _hook_manager(hook_key="unbound_reconfigure", updated=1)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "unbound.forwards": cls_ufwd,
            "unbound.advanced": cls_uadv,
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


class TestPlanEndpointSupport:
    """``plan`` asks the provider whether the box's version serves the endpoints (#1239)."""

    def _run(
        self, provider: MagicMock, hook_result: Any
    ) -> tuple[Any, MagicMock, MagicMock, list[ResourceConfig]]:
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_mock = MagicMock()
        manager_mock.plan.return_value = Diff()
        manager_cls = MagicMock(return_value=manager_mock)
        provider.get_direct_api_resource_types.return_value = {"interfaces.vlans": manager_cls}
        provider.check_endpoint_support.return_value = hook_result
        runner = OPNsenseDirectRunner()
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            result = runner.plan(provider)
        return result, manager_mock, provider.check_endpoint_support, resources

    def test_errors_fail_plan_before_any_manager(self, provider_with_env: MagicMock) -> None:
        result, manager, _, _ = self._run(
            provider_with_env, {"errors": ["boom: needs X"], "warnings": []}
        )
        assert result["success"] is False
        assert "boom: needs X" in result["error"]
        manager.plan.assert_not_called()

    def test_warnings_are_printed_and_plan_proceeds(
        self, provider_with_env: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result, manager, _, _ = self._run(
            provider_with_env, {"errors": [], "warnings": ["version unknown"]}
        )
        assert result["success"] is True
        manager.plan.assert_called_once()
        assert "version unknown" in capsys.readouterr().out

    def test_hook_receives_only_types_with_resources(self, provider_with_env: MagicMock) -> None:
        _, _, hook, _ = self._run(provider_with_env, {"errors": [], "warnings": []})
        hook.assert_called_once_with("test-env", ["interfaces.vlans"])

    def test_hook_not_called_without_resources(self, provider_with_env: MagicMock) -> None:
        provider_with_env.get_direct_api_resource_types.return_value = {
            "interfaces.vlans": MagicMock()
        }
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            OPNsenseDirectRunner().plan(provider_with_env)
        provider_with_env.check_endpoint_support.assert_not_called()

    def test_non_dict_hook_result_is_ignored(self, provider_with_env: MagicMock) -> None:
        result, manager, _, _ = self._run(provider_with_env, MagicMock())
        assert result["success"] is True
        manager.plan.assert_called_once()


# ---------------------------------------------------------------------------
# Managed-set deletes (#1256, ADR-0018)
# ---------------------------------------------------------------------------


def _scoped_manager(
    scope: str | None, *, sibling_type: str | None = None, diff: Any = None
) -> tuple[Any, MagicMock]:
    """Build a manager class with the given ``DELETE_SCOPE`` and a mock instance."""
    instance = MagicMock()
    instance.plan.return_value = diff if diff is not None else Diff()
    instance.apply.return_value = {
        "success": True,
        "resources_created": 0,
        "resources_updated": 0,
        "resources_deleted": 1,
        "resource_outcomes": [],
    }
    attrs: dict[str, Any] = {}
    if scope is not None:
        attrs["DELETE_SCOPE"] = scope
    if sibling_type is not None:
        attrs["SIBLING_RESOURCE_TYPE"] = sibling_type
    cls = MagicMock(return_value=instance, **{})
    for key, value in attrs.items():
        setattr(cls, key, value)
    return cls, instance


def _managed(*pairs: tuple[str, str]) -> dict[str, list[ResourceConfig]]:
    """Build a managed-resources mapping from ``(type, name)`` pairs."""
    out: dict[str, list[ResourceConfig]] = {}
    for type_name, name in pairs:
        out.setdefault(type_name, []).append(
            ResourceConfig(name=name, type=type_name, provider="opnsense", config={"name": name})
        )
    return out


class TestTypeWithNoYamlEntriesDispatchedWhenManaged:
    """A type with no YAML entries is dispatched for its managed rows only (#1256)."""

    def test_plan_dispatches_scoped_type_with_managed_rows(
        self, provider_with_env: MagicMock
    ) -> None:
        cls, instance = _scoped_manager("managed_set", diff=Diff(deletes=[MagicMock()]))
        provider_with_env.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}
        managed = _managed(("unbound.forwards", "f1"))

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            result = OPNsenseDirectRunner().plan(provider_with_env, managed_resources=managed)

        instance.plan.assert_called_once()
        assert instance.plan.call_args.args[1] == []
        assert result["has_changes"] is True
        assert "unbound.forwards: 0 to add, 0 to update, 1 to delete" in result["changes_summary"]

    def test_empty_managed_list_is_not_dispatched(self, provider_with_env: MagicMock) -> None:
        cls, instance = _scoped_manager("managed_set")
        provider_with_env.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            OPNsenseDirectRunner().plan(provider_with_env, managed_resources={})

        instance.plan.assert_not_called()

    def test_unscoped_manager_is_never_dispatched_without_yaml(
        self, provider_with_env: MagicMock
    ) -> None:
        cls, instance = _scoped_manager(None)
        provider_with_env.get_direct_api_resource_types.return_value = {"system.tuning": cls}
        managed = _managed(("system.tuning", "t1"))

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            OPNsenseDirectRunner().plan(provider_with_env, managed_resources=managed)
            OPNsenseDirectRunner().apply(provider_with_env, managed_resources=managed)

        instance.plan.assert_not_called()
        instance.apply.assert_not_called()

    def test_plain_magicmock_class_is_not_scoped(self, provider_with_env: MagicMock) -> None:
        instance = MagicMock()
        provider_with_env.get_direct_api_resource_types.return_value = {
            "unbound.forwards": MagicMock(return_value=instance)
        }
        managed = _managed(("unbound.forwards", "f1"))

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            OPNsenseDirectRunner().plan(provider_with_env, managed_resources=managed)

        instance.plan.assert_not_called()

    def test_add_only_and_filtered_runs_never_dispatch_without_yaml(
        self, provider_with_env: MagicMock
    ) -> None:
        cls, instance = _scoped_manager("managed_set")
        provider_with_env.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}
        managed = _managed(("unbound.forwards", "f1"))

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            OPNsenseDirectRunner().plan(provider_with_env, managed_resources=managed, add_only=True)
            OPNsenseDirectRunner().apply(
                provider_with_env, managed_resources=managed, target_resources=["x"]
            )

        instance.plan.assert_not_called()
        instance.apply.assert_not_called()

    def test_no_managed_set_keeps_legacy_skip(self, provider_with_env: MagicMock) -> None:
        cls, instance = _scoped_manager("managed_set")
        provider_with_env.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            OPNsenseDirectRunner().plan(provider_with_env)

        instance.plan.assert_not_called()

    def test_endpoint_check_includes_types_dispatched_without_yaml(
        self, provider_with_env: MagicMock
    ) -> None:
        cls, _ = _scoped_manager("managed_set")
        provider_with_env.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}
        provider_with_env.check_endpoint_support.return_value = {"errors": [], "warnings": []}
        managed = _managed(("unbound.forwards", "f1"))

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            OPNsenseDirectRunner().plan(provider_with_env, managed_resources=managed)

        provider_with_env.check_endpoint_support.assert_called_once_with(
            "test-env", ["unbound.forwards"]
        )

    def test_apply_dispatches_scoped_type_with_managed_rows(
        self, provider_with_env: MagicMock
    ) -> None:
        cls, instance = _scoped_manager("marker")
        provider_with_env.get_direct_api_resource_types.return_value = {"cron.jobs": cls}
        managed = _managed(("cron.jobs", "j1"))

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            result = OPNsenseDirectRunner().apply(provider_with_env, managed_resources=managed)

        instance.apply.assert_called_once()
        assert result["resources_deleted"] == 1


class TestManagedResourcesThreading:
    """``managed_resources`` reaches only ``managed_set`` managers (#1256)."""

    def test_only_managed_set_managers_receive_managed_resources(
        self, provider_with_env: MagicMock
    ) -> None:
        set_cls, set_inst = _scoped_manager("managed_set")
        marker_cls, marker_inst = _scoped_manager("marker")
        bare_cls, bare_inst = _scoped_manager(None)
        provider_with_env.get_direct_api_resource_types.return_value = {
            "unbound.forwards": set_cls,
            "cron.jobs": marker_cls,
            "system.tuning": bare_cls,
        }
        managed = _managed(("unbound.forwards", "f1"))
        resources = [
            ResourceConfig(name="j", type="cron.jobs", provider="opnsense", config={}),
            ResourceConfig(name="t", type="system.tuning", provider="opnsense", config={}),
        ]

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            OPNsenseDirectRunner().plan(provider_with_env, managed_resources=managed)

        assert [r.name for r in set_inst.plan.call_args.kwargs["managed_resources"]] == ["f1"]
        assert "managed_resources" not in marker_inst.plan.call_args.kwargs
        assert "managed_resources" not in bare_inst.plan.call_args.kwargs

    def test_apply_threads_managed_resources(self, provider_with_env: MagicMock) -> None:
        cls, inst = _scoped_manager("managed_set")
        provider_with_env.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}
        managed = _managed(("unbound.forwards", "f1"))

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            OPNsenseDirectRunner().apply(provider_with_env, managed_resources=managed)

        assert [r.name for r in inst.apply.call_args.kwargs["managed_resources"]] == ["f1"]

    def test_no_managed_resources_kwarg_when_runner_got_none(
        self, provider_with_env: MagicMock
    ) -> None:
        cls, inst = _scoped_manager("managed_set")
        provider_with_env.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}
        resources = [
            ResourceConfig(name="f", type="unbound.forwards", provider="opnsense", config={})
        ]

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            OPNsenseDirectRunner().plan(provider_with_env)

        assert "managed_resources" not in inst.plan.call_args.kwargs


class TestManagedSiblingThreading:
    """``managed_sibling_resources`` reaches sibling-type managed_set managers (#1256)."""

    def test_sibling_managed_rows_are_threaded(self, provider_with_env: MagicMock) -> None:
        res_cls, res_inst = _scoped_manager("managed_set", sibling_type="kea.dhcp4.subnets")
        plain_cls, plain_inst = _scoped_manager("managed_set")
        provider_with_env.get_direct_api_resource_types.return_value = {
            "kea.dhcp4.reservations": res_cls,
            "unbound.forwards": plain_cls,
        }
        managed = _managed(
            ("kea.dhcp4.reservations", "r1"),
            ("kea.dhcp4.subnets", "s1"),
            ("unbound.forwards", "f1"),
        )

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            OPNsenseDirectRunner().plan(provider_with_env, managed_resources=managed)

        kwargs = res_inst.plan.call_args.kwargs
        assert [r.name for r in kwargs["managed_sibling_resources"]] == ["s1"]
        assert "managed_sibling_resources" not in plain_inst.plan.call_args.kwargs

    def test_sibling_threaded_even_without_managed_subnets(
        self, provider_with_env: MagicMock
    ) -> None:
        res_cls, res_inst = _scoped_manager("managed_set", sibling_type="kea.dhcp4.subnets")
        provider_with_env.get_direct_api_resource_types.return_value = {
            "kea.dhcp4.reservations": res_cls
        }
        managed = _managed(("kea.dhcp4.reservations", "r1"))

        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            OPNsenseDirectRunner().apply(provider_with_env, managed_resources=managed)

        assert res_inst.apply.call_args.kwargs["managed_sibling_resources"] == []


class TestReleasedResources:
    """Managed names that left YAML are reported as released after a full apply (#1256)."""

    def _apply(
        self,
        provider: MagicMock,
        managed: dict[str, list[ResourceConfig]],
        resources: list[ResourceConfig],
        scope: str | None = "managed_set",
        **kwargs: Any,
    ) -> Any:
        cls, _ = _scoped_manager(scope)
        provider.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources):
            return OPNsenseDirectRunner().apply(provider, managed_resources=managed, **kwargs)

    def _yaml(self, *names: str) -> list[ResourceConfig]:
        return [
            ResourceConfig(name=n, type="unbound.forwards", provider="opnsense", config={})
            for n in names
        ]

    def test_released_is_managed_minus_yaml(self, provider_with_env: MagicMock) -> None:
        managed = _managed(("unbound.forwards", "f1"), ("unbound.forwards", "f2"))
        result = self._apply(provider_with_env, managed, self._yaml("f2"))
        assert result["released_resources"] == [{"resource_type": "unbound.forwards", "name": "f1"}]

    def test_released_when_last_entry_removed(self, provider_with_env: MagicMock) -> None:
        managed = _managed(("unbound.forwards", "f1"))
        result = self._apply(provider_with_env, managed, [])
        assert result["released_resources"] == [{"resource_type": "unbound.forwards", "name": "f1"}]

    def test_nothing_released_when_all_still_in_yaml(self, provider_with_env: MagicMock) -> None:
        managed = _managed(("unbound.forwards", "f1"))
        result = self._apply(provider_with_env, managed, self._yaml("f1"))
        assert "released_resources" not in result

    def test_no_release_in_add_only_or_filtered_mode(self, provider_with_env: MagicMock) -> None:
        managed = _managed(("unbound.forwards", "f1"), ("unbound.forwards", "f2"))
        add_only = self._apply(provider_with_env, managed, self._yaml("f2"), add_only=True)
        filtered = self._apply(
            provider_with_env, managed, self._yaml("f2"), target_resources=["f2"]
        )
        assert "released_resources" not in add_only
        assert "released_resources" not in filtered

    def test_no_release_for_unscoped_manager(self, provider_with_env: MagicMock) -> None:
        managed = _managed(("unbound.forwards", "f1"))
        result = self._apply(provider_with_env, managed, self._yaml("f2"), scope=None)
        assert "released_resources" not in result

    def test_no_release_on_failure(self, provider_with_env: MagicMock) -> None:
        cls, inst = _scoped_manager("managed_set")
        inst.apply.side_effect = RuntimeError("boom")
        provider_with_env.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}
        managed = _managed(("unbound.forwards", "f1"))
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            result = OPNsenseDirectRunner().apply(provider_with_env, managed_resources=managed)
        assert result["success"] is False
        assert "released_resources" not in result


class TestUnmanagedSummary:
    """The plan summary reports live objects kept because they are unmanaged (#1256)."""

    def test_summary_appends_unmanaged_count(self) -> None:
        diff = Diff(unmanaged=[MagicMock(), MagicMock()])
        summary = OPNsenseDirectRunner._format_plan_summary(
            "interfaces.vlans", diff, add_only=False
        )
        assert summary == (
            "interfaces.vlans: 0 to add, 0 to update, 0 to delete, 0 locked, 2 unmanaged (kept)."
        )

    def test_summary_unchanged_without_unmanaged(self) -> None:
        summary = OPNsenseDirectRunner._format_plan_summary(
            "interfaces.vlans", Diff(), add_only=False
        )
        assert summary == "interfaces.vlans: 0 to add, 0 to update, 0 to delete, 0 locked."

    def test_unmanaged_does_not_count_as_a_change(self) -> None:
        assert Diff(unmanaged=[MagicMock()]).is_empty is True


class TestUnresolvedManagedRowsAreNotReleased:
    """Managed rows a manager could not resolve stay managed and are retried (#1256)."""

    def _apply(
        self, provider: MagicMock, managed: dict[str, list[ResourceConfig]], unresolved: Any
    ) -> Any:
        cls, inst = _scoped_manager("managed_set")
        inst.apply.return_value = {
            "success": True,
            "resources_created": 0,
            "resources_updated": 0,
            "resources_deleted": 0,
            "resource_outcomes": [],
            "unresolved_managed": unresolved,
        }
        provider.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            return OPNsenseDirectRunner().apply(provider, managed_resources=managed)

    def test_unresolved_name_is_excluded_and_resolved_absent_name_is_released(
        self, provider_with_env: MagicMock
    ) -> None:
        managed = _managed(("unbound.forwards", "stuck"), ("unbound.forwards", "gone"))
        result = self._apply(provider_with_env, managed, ["stuck"])
        assert result["released_resources"] == [
            {"resource_type": "unbound.forwards", "name": "gone"}
        ]

    def test_nothing_released_when_every_name_is_unresolved(
        self, provider_with_env: MagicMock
    ) -> None:
        managed = _managed(("unbound.forwards", "stuck"))
        result = self._apply(provider_with_env, managed, ["stuck"])
        assert "released_resources" not in result

    def test_missing_or_malformed_report_releases_as_before(
        self, provider_with_env: MagicMock
    ) -> None:
        managed = _managed(("unbound.forwards", "gone"))
        result = self._apply(provider_with_env, managed, MagicMock())
        assert [r["name"] for r in result["released_resources"]] == ["gone"]


class TestNeedsManagedDispatch:
    """``needs_managed_dispatch`` tells the orchestrator to run with no YAML (#1260)."""

    def test_true_for_scoped_type_with_managed_rows(self, provider_with_env: MagicMock) -> None:
        cls, _ = _scoped_manager("managed_set")
        provider_with_env.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}

        managed = _managed(("unbound.forwards", "f1"))

        assert OPNsenseDirectRunner().needs_managed_dispatch(provider_with_env, managed) is True

    def test_false_for_type_without_delete_scope(self, provider_with_env: MagicMock) -> None:
        cls, _ = _scoped_manager(None)
        provider_with_env.get_direct_api_resource_types.return_value = {"system.tuning": cls}

        managed = _managed(("system.tuning", "t1"))

        assert OPNsenseDirectRunner().needs_managed_dispatch(provider_with_env, managed) is False

    def test_false_for_other_provider(self, provider_with_env: MagicMock) -> None:
        cls, _ = _scoped_manager("managed_set")
        provider_with_env.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}
        provider_with_env.name = "proxmox"

        managed = _managed(("unbound.forwards", "f1"))

        assert OPNsenseDirectRunner().needs_managed_dispatch(provider_with_env, managed) is False

    def test_false_for_empty_mapping(self, provider_with_env: MagicMock) -> None:
        cls, _ = _scoped_manager("managed_set")
        provider_with_env.get_direct_api_resource_types.return_value = {"unbound.forwards": cls}

        assert OPNsenseDirectRunner().needs_managed_dispatch(provider_with_env, {}) is False
