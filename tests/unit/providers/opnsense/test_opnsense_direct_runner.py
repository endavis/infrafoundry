"""Unit tests for OPNsenseDirectRunner.

Coverage:
    - Protocol conformance against ADR-0010 protocols.
    - Tool metadata (name, priority, IaC flag, availability).
    - Initialize is a no-op.
    - Resource filtering.
    - Plan/apply/destroy delegate to the VLAN manager.
    - get_resource_ids surface for StateAware integration.
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
    provider = MagicMock()
    provider._current_environment = "test-env"
    provider.config_dir = tmp_path
    provider.name = "opnsense"
    return provider


class TestPlanDelegation:
    """``runner.plan`` delegates to ``VlanManager.plan``."""

    def test_returns_no_changes_when_no_vlans(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            result = runner.plan(provider_with_env)
        assert result["success"] is True
        assert result["has_changes"] is False  # type: ignore[typeddict-item]

    def test_calls_manager_plan_with_add_only(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        diff = Diff(adds=[VlanConfig("v1", "igb0", 10, "test", 0)])

        manager_mock = MagicMock()
        manager_mock.plan.return_value = diff

        with (
            patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources),
            patch(
                "infrafoundry.providers.opnsense.components.vlan.VlanManager",
                return_value=manager_mock,
            ),
        ):
            result = runner.plan(provider_with_env, add_only=True)

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

        with (
            patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources),
            patch(
                "infrafoundry.providers.opnsense.components.vlan.VlanManager",
                return_value=manager_mock,
            ),
        ):
            result = runner.plan(provider_with_env)

        assert result["success"] is False
        assert "boom" in result["error"]  # type: ignore[typeddict-item]


class TestApplyDelegation:
    """``runner.apply`` delegates to ``VlanManager.apply`` and threads ``add_only``."""

    def test_no_vlans_returns_zero_counts(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            result = runner.apply(provider_with_env)
        assert result["success"] is True
        assert result["resources_created"] == 0  # type: ignore[typeddict-item]
        assert result["resources_updated"] == 0  # type: ignore[typeddict-item]
        assert result["resources_deleted"] == 0  # type: ignore[typeddict-item]
        assert result["resource_outcomes"] == []  # type: ignore[typeddict-item]

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

        with (
            patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources),
            patch(
                "infrafoundry.providers.opnsense.components.vlan.VlanManager",
                return_value=manager_mock,
            ),
        ):
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
        with (
            patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources),
            patch(
                "infrafoundry.providers.opnsense.components.vlan.VlanManager",
                return_value=manager_mock,
            ),
        ):
            runner.apply(provider_with_env, add_only=True)
        # add_only kwarg propagated.
        assert manager_mock.apply.call_args.kwargs["add_only"] is True

    def test_apply_failure_returns_error(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_mock = MagicMock()
        manager_mock.apply.side_effect = RuntimeError("api down")
        with (
            patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources),
            patch(
                "infrafoundry.providers.opnsense.components.vlan.VlanManager",
                return_value=manager_mock,
            ),
        ):
            result = runner.apply(provider_with_env)
        assert result["success"] is False
        assert "api down" in result["error"]  # type: ignore[typeddict-item]


class TestDestroyDelegation:
    """``runner.destroy`` delegates to ``VlanManager.destroy``."""

    def test_no_vlans_returns_zero(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
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
        with (
            patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources),
            patch(
                "infrafoundry.providers.opnsense.components.vlan.VlanManager",
                return_value=manager_mock,
            ),
        ):
            result = runner.destroy(provider_with_env, auto_approve=True)
        assert result["resources_destroyed"] == 1  # type: ignore[typeddict-item]
        manager_mock.destroy.assert_called_once_with("test-env", resources, auto_approve=True)


class TestGetResourceIds:
    """``get_resource_ids`` returns the live UUID map."""

    def test_returns_uuid_map(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_mock = MagicMock()
        manager_mock.get_resource_ids.return_value = {"v1": "uuid-1"}
        with (
            patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources),
            patch(
                "infrafoundry.providers.opnsense.components.vlan.VlanManager",
                return_value=manager_mock,
            ),
        ):
            ids = runner.get_resource_ids(provider_with_env)
        assert ids == {"v1": "uuid-1"}

    def test_empty_when_no_vlans(self, provider_with_env: MagicMock) -> None:
        runner = OPNsenseDirectRunner()
        with patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=[]):
            ids = runner.get_resource_ids(provider_with_env)
        assert ids == {}

    def test_swallows_errors(self, provider_with_env: MagicMock) -> None:
        # Failures here are non-fatal — we don't want a state-lookup blip
        # to abort an apply that already succeeded.
        runner = OPNsenseDirectRunner()
        resources = [_vlan_resource("v1", "igb0", 10)]
        manager_mock = MagicMock()
        manager_mock.get_resource_ids.side_effect = RuntimeError("transient")
        with (
            patch.object(OPNsenseDirectRunner, "_load_provider_resources", return_value=resources),
            patch(
                "infrafoundry.providers.opnsense.components.vlan.VlanManager",
                return_value=manager_mock,
            ),
        ):
            ids = runner.get_resource_ids(provider_with_env)
        assert ids == {}
