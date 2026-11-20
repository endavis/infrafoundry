"""Unit tests for DeploymentExecutor apply flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.config.models import IaCTool
from infrafoundry.core.deployment_executor import DeploymentExecutor, default_max_workers
from infrafoundry.core.events import EventAbortedError, EventType
from infrafoundry.core.events.context import EventResult
from infrafoundry.core.exceptions import ResourceFilterError, TerraformError
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.state import ResourceState
from infrafoundry.core.types import ResourceOutcome


def _resource(name: str, provider: str = "proxmox", type_: str = "vm") -> MagicMock:
    res = MagicMock()
    res.name = name
    res.provider = provider
    res.type = type_
    res.config = {"id": name}
    return res


def test_apply_serial_orders_providers_and_tracks_states() -> None:
    """Serial apply honors provider order and updates resource state transitions."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]
    tf_runner = MagicMock()
    tf_runner.priority = 0

    # Set protocol methods with return values
    tf_runner.apply = MagicMock(return_value={"success": True})
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock(return_value={"vm1": "proxmox_vm.vm1"})

    runner_registry.create_runner.return_value = tf_runner

    state_manager = MagicMock()
    state_manager.track_resource.side_effect = [
        MagicMock(id=1, terraform_id=None),
        MagicMock(id=2, terraform_id=None),
    ]
    event_manager = MagicMock()

    providers: dict[str, ProviderBase] = {
        "opnsense": MagicMock(),
        "proxmox": MagicMock(),
    }

    resources_by_provider: dict[str, list[ResourceConfig]] = {
        "opnsense": [_resource("fw")],
        "proxmox": [_resource("vm1")],
    }

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
        runner_priorities={"terraform": 0},
    )

    results = executor.apply_serial(
        env_name="dev",
        deployment_id=10,
        resources_by_provider=resources_by_provider,
        resource_filter=None,
        auto_approve=True,
    )

    # Provider order: opnsense first, then proxmox
    assert list(results.keys()) == ["opnsense", "proxmox"]
    # Resource states updated to ACTIVE
    state_manager.update_resource_state.assert_any_call(resource_id=1, state=ResourceState.ACTIVE)
    state_manager.update_resource_state.assert_any_call(resource_id=2, state=ResourceState.ACTIVE)
    # Terraform IDs applied
    state_manager.update_resource.assert_called_with(resource_id=2, terraform_id="proxmox_vm.vm1")
    # Resource creating/created events emitted
    event_manager.emit_event.assert_any_call(
        EventType.RESOURCE_CREATING,
        "dev",
        {
            "resource_id": 1,
            "provider": "opnsense",
            "name": "fw",
            "terraform_id": None,
        },
        target_resources=None,
        package_filter=None,
    )
    assert any(
        call_args[0][0] == EventType.RESOURCE_CREATED
        for call_args in event_manager.emit_event.call_args_list
    )


def test_apply_parallel_uses_executor_and_handles_runner_errors() -> None:
    """Parallel apply aggregates results and captures runner exceptions."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]
    tf_runner = MagicMock()
    tf_runner.priority = 0
    # Ensure protocol checks pass
    tf_runner.apply = MagicMock()
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock()

    def create_runner(name: Any, console: Any = None) -> Any:
        return tf_runner

    runner_registry.create_runner.side_effect = create_runner

    state_manager = MagicMock()
    event_manager = MagicMock()

    provider_ok = MagicMock()
    provider_err = MagicMock()
    providers: dict[str, ProviderBase] = {"proxmox": provider_ok, "opnsense": provider_err}

    resources_by_provider: dict[str, list[ResourceConfig]] = {
        "proxmox": [_resource("vm1", provider="proxmox")],
        "opnsense": [_resource("fw1", provider="opnsense")],
    }

    def runner_apply(provider: Any, auto_approve: Any = True, **kwargs: Any) -> dict[str, Any]:
        if provider is provider_err:
            raise RuntimeError("boom")
        return {"success": True}

    tf_runner.apply.side_effect = runner_apply

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    results = executor.apply_parallel(
        env_name="dev",
        deployment_id=20,
        resources_by_provider=resources_by_provider,
        resource_filter=None,
        auto_approve=True,
        max_workers=2,
    )

    # Successful provider returns runner results
    assert results["proxmox"]["terraform"]["success"] is True
    assert results["opnsense"]["error"] == "boom"


def test_apply_single_provider_tracks_resources_and_emits_events() -> None:
    """Single provider apply tracks each resource through state transitions."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform", "ansible"]

    tf_runner = MagicMock()
    tf_runner.priority = 0

    # Set protocol methods with return values
    tf_runner.apply = MagicMock(return_value={"success": True})
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock(
        return_value={"vm1": "proxmox_vm.vm1", "vm2": "proxmox_vm.vm2"}
    )

    ansible_runner = MagicMock()
    ansible_runner.priority = 50
    # Ansible supports apply/plan but not destroy/state
    ansible_runner.apply = MagicMock(return_value={"success": True})
    ansible_runner.plan = MagicMock()
    # Not setting get_resource_ids/destroy for ansible_runner

    def create_runner(name: Any, console: Any = None) -> Any:
        return tf_runner if name == "terraform" else ansible_runner

    runner_registry.create_runner.side_effect = create_runner

    state_manager = MagicMock()
    # Mock track_resource to return tracked resources with IDs
    state_manager.track_resource.side_effect = [
        MagicMock(id=101, terraform_id=None),
        MagicMock(id=102, terraform_id=None),
    ]
    event_manager = MagicMock()

    provider = MagicMock()
    providers: dict[str, ProviderBase] = {"proxmox": provider}

    resources: list[ResourceConfig] = [
        _resource("vm1", provider="proxmox"),
        _resource("vm2", provider="proxmox"),
    ]

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    results = executor.apply_single_provider(
        env_name="dev",
        deployment_id=5,
        provider_name="proxmox",
        provider=provider,
        resources=resources,
        auto_approve=True,
    )

    # Both runners executed
    assert "terraform" in results
    assert "ansible" in results
    assert results["terraform"]["success"] is True
    assert results["ansible"]["success"] is True

    # Resources tracked with CREATING state
    assert state_manager.track_resource.call_count == 2
    state_manager.track_resource.assert_any_call(
        deployment_id=5,
        environment="dev",
        provider="proxmox",
        resource_type="vm",
        name="vm1",
        state=ResourceState.CREATING,
        config={"id": "vm1"},
    )

    # Terraform IDs updated
    state_manager.update_resource.assert_any_call(resource_id=101, terraform_id="proxmox_vm.vm1")
    state_manager.update_resource.assert_any_call(resource_id=102, terraform_id="proxmox_vm.vm2")

    # Resources marked ACTIVE
    state_manager.update_resource_state.assert_any_call(resource_id=101, state=ResourceState.ACTIVE)
    state_manager.update_resource_state.assert_any_call(resource_id=102, state=ResourceState.ACTIVE)

    # Events emitted for each resource
    creating_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RESOURCE_CREATING
    ]
    created_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RESOURCE_CREATED
    ]
    assert len(creating_calls) == 2
    assert len(created_calls) == 2


def test_apply_single_provider_runs_runners_in_priority_order() -> None:
    """Single provider apply respects runner priority ordering."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["ansible", "terraform"]

    execution_order = []

    tf_runner = MagicMock()
    tf_runner.priority = 0

    # Set protocol methods with side effects for execution tracking
    def tf_apply(provider: Any, auto_approve: Any = True, **kwargs: Any) -> dict[str, Any]:
        execution_order.append("terraform")
        return {"success": True}

    tf_runner.apply = MagicMock(side_effect=tf_apply)
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock(return_value={})

    ansible_runner = MagicMock()
    ansible_runner.priority = 50

    def ansible_apply(provider: Any, auto_approve: Any = True, **kwargs: Any) -> dict[str, Any]:
        execution_order.append("ansible")
        return {"success": True}

    # Ansible supports apply/plan
    ansible_runner.apply = MagicMock(side_effect=ansible_apply)
    ansible_runner.plan = MagicMock()

    def create_runner(name: Any, console: Any = None) -> Any:
        return tf_runner if name == "terraform" else ansible_runner

    runner_registry.create_runner.side_effect = create_runner

    state_manager = MagicMock()
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    provider = MagicMock()
    providers: dict[str, ProviderBase] = {"proxmox": provider}
    resources: list[ResourceConfig] = [_resource("vm1")]

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    executor.apply_single_provider(
        env_name="dev",
        deployment_id=1,
        provider_name="proxmox",
        provider=provider,
        resources=resources,
        auto_approve=True,
    )

    # Terraform (priority 0) should run before ansible (priority 50)
    assert execution_order == ["terraform", "ansible"]


def test_get_sorted_runners_respects_priority_overrides() -> None:
    """Runner sorting uses priority overrides from environment config."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform", "ansible", "pyinfra"]

    tf_runner = MagicMock()
    tf_runner.priority = 0

    ansible_runner = MagicMock()
    ansible_runner.priority = 50

    pyinfra_runner = MagicMock()
    pyinfra_runner.priority = 50

    def create_runner(name: Any, console: Any = None) -> Any:
        if name == "terraform":
            return tf_runner
        elif name == "ansible":
            return ansible_runner
        else:
            return pyinfra_runner

    runner_registry.create_runner.side_effect = create_runner

    state_manager = MagicMock()
    event_manager = MagicMock()
    providers: dict[str, ProviderBase] = {}

    # Override terraform to run last
    runner_priorities = {"terraform": 100}

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
        runner_priorities=runner_priorities,
    )

    sorted_runners = executor._get_sorted_runners()
    names = [name for name, _ in sorted_runners]

    # Ansible and pyinfra (priority 50) should come before terraform (overridden to 100)
    assert names.index("terraform") > names.index("ansible")
    assert names.index("terraform") > names.index("pyinfra")


def test_apply_serial_with_empty_resources() -> None:
    """Serial apply handles empty resource list gracefully."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = []
    state_manager = MagicMock()
    event_manager = MagicMock()
    providers: dict[str, ProviderBase] = {}

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    results = executor.apply_serial(
        env_name="dev",
        deployment_id=1,
        resources_by_provider={},
        resource_filter=None,
        auto_approve=True,
    )

    # Should return empty results without errors
    assert results == {}
    assert state_manager.track_resource.call_count == 0


def test_apply_parallel_with_all_providers_failing() -> None:
    """Parallel apply captures all provider failures."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    tf_runner = MagicMock()
    tf_runner.priority = 0
    # Set protocol methods - apply raises error
    tf_runner.apply = MagicMock(side_effect=RuntimeError("Connection timeout"))
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock()

    runner_registry.create_runner.return_value = tf_runner

    state_manager = MagicMock()
    event_manager = MagicMock()

    providers: dict[str, ProviderBase] = {
        "proxmox": MagicMock(),
        "opnsense": MagicMock(),
    }

    resources_by_provider: dict[str, list[ResourceConfig]] = {
        "proxmox": [_resource("vm1")],
        "opnsense": [_resource("fw1")],
    }

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    results = executor.apply_parallel(
        env_name="dev",
        deployment_id=1,
        resources_by_provider=resources_by_provider,
        resource_filter=None,
        auto_approve=True,
        max_workers=2,
    )

    # Both providers should have error entries
    assert "error" in results["proxmox"]
    assert "Connection timeout" in results["proxmox"]["error"]
    assert "error" in results["opnsense"]
    assert "Connection timeout" in results["opnsense"]["error"]


def test_apply_single_provider_handles_multiple_resources() -> None:
    """Single provider apply processes multiple resources correctly."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    tf_runner = MagicMock()
    tf_runner.priority = 0
    # Set protocol methods with return values
    tf_runner.apply = MagicMock(return_value={"success": True})
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock(return_value={})

    runner_registry.create_runner.return_value = tf_runner

    state_manager = MagicMock()
    state_manager.track_resource.side_effect = [
        MagicMock(id=1, terraform_id=None),
        MagicMock(id=2, terraform_id=None),
        MagicMock(id=3, terraform_id=None),
    ]
    event_manager = MagicMock()

    provider = MagicMock()
    providers: dict[str, ProviderBase] = {"proxmox": provider}

    # Multiple resources
    resources: list[ResourceConfig] = [
        _resource("vm1"),
        _resource("vm2"),
        _resource("net1", type_="network"),
    ]

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    results = executor.apply_single_provider(
        env_name="dev",
        deployment_id=1,
        provider_name="proxmox",
        provider=provider,
        resources=resources,
        auto_approve=True,
    )

    # Should process all 3 resources
    assert state_manager.track_resource.call_count == 3
    assert state_manager.update_resource_state.call_count == 3
    assert results["terraform"]["success"] is True
    # Every resource name reaches the runner, even with no filter, so prefixed
    # terraform addresses map back to their names (#1099).
    assert tf_runner.apply.call_args.kwargs["resource_names"] == ["vm1", "vm2", "net1"]
    assert tf_runner.apply.call_args.kwargs["target_resources"] is None


def test_apply_single_provider_tracks_state_for_opentofu_runner() -> None:
    """StateAware check works for opentofu runner (not just terraform)."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["opentofu"]

    tofu_runner = MagicMock()
    tofu_runner.priority = 0

    # Set protocol methods with return values
    tofu_runner.apply = MagicMock(return_value={"success": True})
    tofu_runner.plan = MagicMock()
    tofu_runner.destroy = MagicMock()
    tofu_runner.get_resource_ids = MagicMock(return_value={"vm1": "proxmox_vm.vm1"})

    runner_registry.create_runner.return_value = tofu_runner

    state_manager = MagicMock()
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    provider = MagicMock()
    providers: dict[str, ProviderBase] = {"proxmox": provider}

    resources: list[ResourceConfig] = [_resource("vm1")]

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )
    executor.iac_tool = IaCTool.OPENTOFU

    results = executor.apply_single_provider(
        env_name="dev",
        deployment_id=1,
        provider_name="proxmox",
        provider=provider,
        resources=resources,
        auto_approve=True,
    )

    # OpenTofu runner should also trigger state tracking via StateAware
    assert "opentofu" in results
    assert results["opentofu"]["success"] is True
    state_manager.update_resource.assert_called_with(resource_id=1, terraform_id="proxmox_vm.vm1")


def test_get_sorted_runners_filters_inactive_iac_tool() -> None:
    """Only the configured IaC runner is included; the other is skipped."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform", "opentofu", "ansible"]

    tf_runner = MagicMock()
    tf_runner.priority = 0

    tofu_runner = MagicMock()
    tofu_runner.priority = 0

    ansible_runner = MagicMock()
    ansible_runner.priority = 50

    def create_runner(name: Any, console: Any = None) -> Any:
        if name == "terraform":
            return tf_runner
        elif name == "opentofu":
            return tofu_runner
        else:
            return ansible_runner

    runner_registry.create_runner.side_effect = create_runner

    state_manager = MagicMock()
    event_manager = MagicMock()
    providers: dict[str, ProviderBase] = {}

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    # Default: terraform
    executor.iac_tool = IaCTool.TERRAFORM
    names = [name for name, _ in executor._get_sorted_runners()]
    assert "terraform" in names
    assert "opentofu" not in names
    assert "ansible" in names

    # Switch to opentofu
    executor.iac_tool = IaCTool.OPENTOFU
    names = [name for name, _ in executor._get_sorted_runners()]
    assert "opentofu" in names
    assert "terraform" not in names
    assert "ansible" in names


def test_apply_emits_runner_starting_and_completed() -> None:
    """Runner events are emitted around each runner.apply() call."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.apply = MagicMock(return_value={"success": True})
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock(return_value={})

    runner_registry.create_runner.return_value = tf_runner

    state_manager = MagicMock()
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    provider = MagicMock()
    providers: dict[str, ProviderBase] = {"proxmox": provider}
    resources: list[ResourceConfig] = [_resource("vm1")]

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    executor.apply_single_provider(
        env_name="dev",
        deployment_id=1,
        provider_name="proxmox",
        provider=provider,
        resources=resources,
        auto_approve=True,
    )

    # Extract runner event calls
    starting_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RUNNER_STARTING
    ]
    completed_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RUNNER_COMPLETED
    ]

    assert len(starting_calls) == 1
    assert len(completed_calls) == 1

    # Verify data and kwargs
    assert starting_calls[0][0][2] == {
        "provider": "proxmox",
        "runner": "terraform",
        "phase": "apply",
    }
    assert starting_calls[0][1] == {
        "provider": "proxmox",
        "runner": "terraform",
        "target_resources": None,
        "package_filter": None,
    }

    assert completed_calls[0][0][2] == {
        "provider": "proxmox",
        "runner": "terraform",
        "phase": "apply",
        "success": True,
    }
    assert completed_calls[0][1] == {
        "provider": "proxmox",
        "runner": "terraform",
        "target_resources": None,
        "package_filter": None,
    }

    # Verify ordering: STARTING before apply, COMPLETED after
    all_call_types = [call[0][0] for call in event_manager.emit_event.call_args_list]
    starting_idx = all_call_types.index(EventType.RUNNER_STARTING)
    completed_idx = all_call_types.index(EventType.RUNNER_COMPLETED)
    assert starting_idx < completed_idx


def test_apply_emits_runner_failed_on_exception() -> None:
    """RUNNER_FAILED is emitted when runner.apply() raises, and exception propagates."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.apply = MagicMock(side_effect=RuntimeError("terraform crashed"))
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock(return_value={})

    runner_registry.create_runner.return_value = tf_runner

    state_manager = MagicMock()
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    provider = MagicMock()
    providers: dict[str, ProviderBase] = {"proxmox": provider}
    resources: list[ResourceConfig] = [_resource("vm1")]

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    with pytest.raises(RuntimeError, match="terraform crashed"):
        executor.apply_single_provider(
            env_name="dev",
            deployment_id=1,
            provider_name="proxmox",
            provider=provider,
            resources=resources,
            auto_approve=True,
        )

    # RUNNER_STARTING should have been emitted
    starting_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RUNNER_STARTING
    ]
    assert len(starting_calls) == 1

    # RUNNER_FAILED should have been emitted with error details
    failed_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RUNNER_FAILED
    ]
    assert len(failed_calls) == 1
    assert failed_calls[0][0][2] == {
        "provider": "proxmox",
        "runner": "terraform",
        "phase": "apply",
        "error": "terraform crashed",
    }
    assert failed_calls[0][1] == {
        "provider": "proxmox",
        "runner": "terraform",
        "target_resources": None,
        "package_filter": None,
    }

    # RUNNER_COMPLETED should NOT have been emitted
    completed_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RUNNER_COMPLETED
    ]
    assert len(completed_calls) == 0


def test_apply_single_provider_raises_on_runner_failure() -> None:
    """When runner.apply returns success=False the executor raises TerraformError.

    The RUNNER_FAILED event must be emitted (via the existing except handler)
    and RUNNER_COMPLETED must NOT be emitted.
    """
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.apply = MagicMock(
        return_value={
            "success": False,
            "exit_code": 1,
            "error": "boom",
            "stderr": "boom stderr",
            "resource_outcomes": [],
        }
    )
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock(return_value={})

    runner_registry.create_runner.return_value = tf_runner

    state_manager = MagicMock()
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    provider = MagicMock()
    providers: dict[str, ProviderBase] = {"proxmox": provider}
    resources: list[ResourceConfig] = [_resource("vm1")]

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    with pytest.raises(TerraformError, match="boom"):
        executor.apply_single_provider(
            env_name="dev",
            deployment_id=1,
            provider_name="proxmox",
            provider=provider,
            resources=resources,
            auto_approve=True,
        )

    # RUNNER_FAILED should have been emitted exactly once
    failed_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RUNNER_FAILED
    ]
    assert len(failed_calls) == 1
    assert failed_calls[0][0][2]["phase"] == "apply"
    assert failed_calls[0][0][2]["provider"] == "proxmox"

    # RUNNER_COMPLETED must NOT have been emitted
    completed_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RUNNER_COMPLETED
    ]
    assert len(completed_calls) == 0


def _make_executor(providers: Any = None) -> DeploymentExecutor:
    """Create a minimal DeploymentExecutor for resource filter tests."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = []
    state_manager = MagicMock()
    event_manager = MagicMock()

    return DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers or {},
    )


def test_validate_resource_filter_zero_matches_raises() -> None:
    """Zero resource filter matches raises ResourceFilterError."""
    executor = _make_executor()
    resources_by_provider: dict[str, list[ResourceConfig]] = {
        "proxmox": [_resource("vm1"), _resource("vm2")],
    }

    with pytest.raises(ResourceFilterError, match="No resources matched filter"):
        executor._validate_resource_filter(resources_by_provider, {"nonexistent"})


def test_validate_resource_filter_error_includes_names() -> None:
    """Error message includes unmatched filter names and available resource names."""
    executor = _make_executor()
    resources_by_provider: dict[str, list[ResourceConfig]] = {
        "proxmox": [_resource("vm1"), _resource("vm2")],
    }

    with pytest.raises(ResourceFilterError) as exc_info:
        executor._validate_resource_filter(resources_by_provider, {"nonexistent"})

    error_msg = str(exc_info.value)
    assert "nonexistent" in error_msg
    assert "vm1" in error_msg
    assert "vm2" in error_msg


def test_validate_resource_filter_legacy_settings_name_lists_new_names() -> None:
    """``-r settings`` no longer matches OPNsense singletons; the error lists dotted names."""
    executor = _make_executor()
    resources_by_provider: dict[str, list[ResourceConfig]] = {
        "opnsense": [
            _resource("system.tuning", "opnsense", "system.tuning"),
            _resource("system.firmware", "opnsense", "system.firmware"),
        ],
    }

    with pytest.raises(ResourceFilterError) as exc_info:
        executor._validate_resource_filter(resources_by_provider, {"settings"})

    assert "system.tuning" in str(exc_info.value)
    assert "system.firmware" in str(exc_info.value)


def test_validate_resource_filter_partial_match_warns() -> None:
    """Partial match warns but does not raise."""
    executor = _make_executor()
    resources_by_provider: dict[str, list[ResourceConfig]] = {
        "proxmox": [_resource("vm1"), _resource("vm2")],
    }

    # Should not raise
    executor._validate_resource_filter(resources_by_provider, {"vm1", "nonexistent"})


def test_validate_resource_filter_full_match_succeeds() -> None:
    """Full match does not raise or warn."""
    executor = _make_executor()
    resources_by_provider: dict[str, list[ResourceConfig]] = {
        "proxmox": [_resource("vm1"), _resource("vm2")],
    }

    # Should not raise
    executor._validate_resource_filter(resources_by_provider, {"vm1", "vm2"})


def test_apply_serial_raises_on_zero_filter_matches() -> None:
    """apply_serial raises ResourceFilterError when filter matches nothing."""
    providers: dict[str, ProviderBase] = {"proxmox": MagicMock()}
    executor = _make_executor(providers=providers)
    resources_by_provider: dict[str, list[ResourceConfig]] = {
        "proxmox": [_resource("vm1")],
    }

    with pytest.raises(ResourceFilterError, match="No resources matched filter"):
        executor.apply_serial(
            env_name="dev",
            deployment_id=1,
            resources_by_provider=resources_by_provider,
            resource_filter=["nonexistent"],
            auto_approve=True,
        )


def test_apply_parallel_raises_on_zero_filter_matches() -> None:
    """apply_parallel raises ResourceFilterError when filter matches nothing."""
    providers: dict[str, ProviderBase] = {"proxmox": MagicMock()}
    executor = _make_executor(providers=providers)
    resources_by_provider: dict[str, list[ResourceConfig]] = {
        "proxmox": [_resource("vm1")],
    }

    with pytest.raises(ResourceFilterError, match="No resources matched filter"):
        executor.apply_parallel(
            env_name="dev",
            deployment_id=1,
            resources_by_provider=resources_by_provider,
            resource_filter=["nonexistent"],
            auto_approve=True,
            max_workers=2,
        )


# ---------------------------------------------------------------------------
# Event handler failure propagation tests
# ---------------------------------------------------------------------------


def _resource_with_events(
    name: str,
    provider: str = "proxmox",
    type_: str = "vm",
    events: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock resource with event handlers configured."""
    res = MagicMock()
    res.name = name
    res.provider = provider
    res.type = type_
    res.config = {"id": name}
    res.events = events
    res.package_variables = {}
    return res


def _make_executor_with_outcomes(
    outcomes: list[ResourceOutcome],
    emit_results: list[EventResult] | None = None,
) -> Any:
    """Build an executor whose IaC runner returns *outcomes* and whose
    event_manager.emit_event returns *emit_results* for lifecycle events.

    Returns (executor, event_manager) so callers can inspect calls.
    """
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.apply = MagicMock(return_value={"success": True, "resource_outcomes": outcomes})
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock(return_value={})

    runner_registry.create_runner.return_value = tf_runner

    state_manager = MagicMock()
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)

    event_manager = MagicMock()
    # By default, emit_event returns an empty list (no handler results).
    # Callers override this via side_effect for specific event types.
    event_manager.emit_event.return_value = []
    if emit_results is not None:
        # Return handler results only for RESOURCE_CREATED/UPDATED/DELETED calls
        lifecycle_types = {
            EventType.RESOURCE_CREATED,
            EventType.RESOURCE_UPDATED,
            EventType.RESOURCE_DELETED,
        }

        def emit_side_effect(event_type: Any, *args: Any, **kwargs: Any) -> list[Any]:
            if event_type in lifecycle_types:
                return emit_results
            return []

        event_manager.emit_event.side_effect = emit_side_effect

    provider = MagicMock()
    # Map vm type -> proxmox_virtual_environment_vm terraform type
    provider.get_terraform_resource_types.return_value = {
        "vm": ["proxmox_virtual_environment_vm"],
    }

    providers: dict[str, ProviderBase] = {"proxmox": provider}

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    return executor, event_manager, provider


def test_event_handler_failure_abort_raises_from_lifecycle_events() -> None:
    """Handler failure with abort=True raises EventAbortedError."""
    outcomes = [
        ResourceOutcome(
            address="proxmox_virtual_environment_vm.web",
            action="create",
            resource_name="web",
        ),
    ]
    abort_result = EventResult(
        success=False,
        abort=True,
        reason="script timed out",
        handler_name="on_create_script",
    )

    resource = _resource_with_events(
        "web",
        events={"on_create": [{"type": "script", "script": "setup.sh"}]},
    )

    executor, _event_manager, provider = _make_executor_with_outcomes(
        outcomes, emit_results=[abort_result]
    )

    with pytest.raises(EventAbortedError, match="script timed out"):
        executor.apply_single_provider(
            env_name="dev",
            deployment_id=1,
            provider_name="proxmox",
            provider=provider,
            resources=[resource],
            auto_approve=True,
        )


def test_event_handler_failure_continue_on_error_does_not_raise() -> None:
    """Handler failure with abort=False (continue_on_error) does not raise."""
    outcomes = [
        ResourceOutcome(
            address="proxmox_virtual_environment_vm.web",
            action="create",
            resource_name="web",
        ),
    ]
    non_abort_result = EventResult(
        success=False,
        abort=False,
        reason="script failed but continue_on_error is true",
        handler_name="on_create_script",
    )

    resource = _resource_with_events(
        "web",
        events={"on_create": [{"type": "script", "script": "setup.sh"}]},
    )

    executor, _event_manager, provider = _make_executor_with_outcomes(
        outcomes, emit_results=[non_abort_result]
    )

    # Should NOT raise
    result = executor.apply_single_provider(
        env_name="dev",
        deployment_id=1,
        provider_name="proxmox",
        provider=provider,
        resources=[resource],
        auto_approve=True,
    )

    assert "terraform" in result


def test_event_handler_success_does_not_raise() -> None:
    """Successful handler results do not raise."""
    outcomes = [
        ResourceOutcome(
            address="proxmox_virtual_environment_vm.web",
            action="create",
            resource_name="web",
        ),
    ]
    success_result = EventResult(
        success=True,
        abort=False,
        reason="",
        handler_name="on_create_script",
    )

    resource = _resource_with_events(
        "web",
        events={"on_create": [{"type": "script", "script": "setup.sh"}]},
    )

    executor, _event_manager, provider = _make_executor_with_outcomes(
        outcomes, emit_results=[success_result]
    )

    result = executor.apply_single_provider(
        env_name="dev",
        deployment_id=1,
        provider_name="proxmox",
        provider=provider,
        resources=[resource],
        auto_approve=True,
    )

    assert "terraform" in result


def test_aggregate_group_handler_failure_raises_from_apply_serial() -> None:
    """Aggregate RESOURCE_CREATED handler abort raises EventAbortedError."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    tf_runner = MagicMock()
    tf_runner.priority = 0
    outcome = ResourceOutcome(
        address="proxmox_vm.web",
        action="create",
        resource_name="web",
    )
    tf_runner.apply = MagicMock(
        return_value={
            "success": True,
            "resource_outcomes": [outcome],
        }
    )
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock(return_value={})

    runner_registry.create_runner.return_value = tf_runner

    state_manager = MagicMock()
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)

    abort_result = EventResult(
        success=False,
        abort=True,
        reason="group handler failed",
        handler_name="group_setup",
    )

    event_manager = MagicMock()
    call_count = 0

    def emit_side_effect(event_type: Any, *args: Any, **kwargs: Any) -> list[Any]:
        nonlocal call_count
        call_count += 1
        # The aggregate RESOURCE_CREATED call in apply_serial is the one
        # that includes "resources" in data and target_resources as a list
        # of all created resource names. Return abort result for it.
        data = args[1] if len(args) > 1 else kwargs.get("data")
        if (
            event_type == EventType.RESOURCE_CREATED
            and isinstance(data, dict)
            and "resources" in data
        ):
            return [abort_result]
        return []

    event_manager.emit_event.side_effect = emit_side_effect

    provider = MagicMock()
    provider.get_terraform_resource_types.return_value = {}
    providers: dict[str, ProviderBase] = {"proxmox": provider}

    resource = _resource_with_events("web")

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    with pytest.raises(EventAbortedError, match="group handler failed"):
        executor.apply_serial(
            env_name="dev",
            deployment_id=1,
            resources_by_provider={"proxmox": [resource]},
            resource_filter=None,
            auto_approve=True,
        )


# ---------------------------------------------------------------------------
# Aggregate RESOURCE_CREATED grouped by package variables (#1231)
# ---------------------------------------------------------------------------


def _pkg_res(name: str, variables: dict[str, Any] | None) -> MagicMock:
    res = _resource_with_events(name)
    res.package_variables = variables
    return res


def _apply_created(
    names: list[str],
    resources: list[MagicMock],
    emit_results: list[EventResult] | None = None,
) -> tuple[Any, list[Any]]:
    outcomes = [
        ResourceOutcome(address=f"proxmox_vm.{n}", action="create", resource_name=n) for n in names
    ]
    executor, event_manager, _ = _make_executor_with_outcomes(outcomes, emit_results)
    executor.apply_serial(
        env_name="dev",
        deployment_id=1,
        resources_by_provider={"proxmox": resources},
        resource_filter=None,
        auto_approve=True,
        package_filter="pkg",
    )
    aggregates = [
        c
        for c in event_manager.emit_event.call_args_list
        if c.args[0] == EventType.RESOURCE_CREATED and "resources" in c.args[2]
    ]
    return event_manager, aggregates


def test_apply_emits_one_aggregate_per_package_variables_group() -> None:
    resources = [
        _pkg_res("a1", {"x": 1}),
        _pkg_res("b1", {"x": 2}),
        _pkg_res("a2", {"x": 1}),
    ]
    _, aggregates = _apply_created(["a1", "b1", "a2"], resources)

    assert [(c.kwargs["target_resources"], c.kwargs["package_variables"]) for c in aggregates] == [
        (["a1", "a2"], {"x": 1}),
        (["b1"], {"x": 2}),
    ]
    assert all(c.kwargs["package_filter"] == "pkg" for c in aggregates)


def test_apply_single_package_emits_one_aggregate_with_variables() -> None:
    resources = [_pkg_res("a", {"x": 1}), _pkg_res("b", {"x": 1})]
    _, aggregates = _apply_created(["a", "b"], resources)

    assert len(aggregates) == 1
    assert aggregates[0].kwargs["target_resources"] == ["a", "b"]
    assert aggregates[0].kwargs["package_variables"] == {"x": 1}


def test_apply_without_package_variables_still_emits() -> None:
    _, aggregates = _apply_created(["a"], [_pkg_res("a", None)])

    assert len(aggregates) == 1
    assert aggregates[0].kwargs["package_variables"] == {}


def test_apply_aggregate_abort_raises() -> None:
    abort = EventResult(success=False, abort=True, reason="stop", handler_name="h")
    with pytest.raises(EventAbortedError):
        _apply_created(["a"], [_pkg_res("a", {"x": 1})], [abort])


def _opnsense_executor(
    apply_result: dict[str, Any], managed_rows: Any = None
) -> tuple[DeploymentExecutor, MagicMock, MagicMock]:
    """Build an executor with one runner returning ``apply_result``."""
    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.apply = MagicMock(return_value=apply_result)
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock(return_value={})
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]
    runner_registry.create_runner.return_value = tf_runner

    state_manager = MagicMock()
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    state_manager.get_managed_resources.return_value = (
        managed_rows if managed_rows is not None else []
    )
    provider = MagicMock()
    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=MagicMock(),
        providers={"opnsense": provider},
    )
    return executor, tf_runner, state_manager


def _apply_opnsense(executor: DeploymentExecutor, resources: list[Any]) -> dict[str, Any]:
    return executor.apply_single_provider(
        env_name="dev",
        deployment_id=7,
        provider_name="opnsense",
        provider=MagicMock(),
        resources=resources,
        auto_approve=True,
    )


def test_apply_passes_managed_resources_to_runner() -> None:
    """The runner receives the managed rows rebuilt as ResourceConfigs (#1256)."""
    from types import SimpleNamespace

    rows = [SimpleNamespace(resource_type="unbound.forwards", name="f1", config={"server": "x"})]
    executor, runner, state = _opnsense_executor({"success": True}, rows)

    _apply_opnsense(executor, [])

    state.get_managed_resources.assert_called_once_with("dev", "opnsense")
    managed = runner.apply.call_args.kwargs["managed_resources"]
    assert [r.name for r in managed["unbound.forwards"]] == ["f1"]


def test_apply_records_released_resources_as_deleted() -> None:
    """Each released resource becomes a DELETED row carrying the managed config (#1256)."""
    from types import SimpleNamespace

    rows = [SimpleNamespace(resource_type="unbound.forwards", name="f1", config={"server": "x"})]
    result = {
        "success": True,
        "released_resources": [{"resource_type": "unbound.forwards", "name": "f1"}],
    }
    executor, _, state = _opnsense_executor(result, rows)

    _apply_opnsense(executor, [])

    state.track_resource.assert_called_once_with(
        deployment_id=7,
        environment="dev",
        provider="opnsense",
        resource_type="unbound.forwards",
        name="f1",
        state=ResourceState.DELETED,
        config={"server": "x"},
    )


def test_apply_records_nothing_when_runner_fails() -> None:
    """A failed runner releases nothing (#1256)."""
    result = {
        "success": False,
        "error": "boom",
        "released_resources": [{"resource_type": "unbound.forwards", "name": "f1"}],
    }
    executor, _, state = _opnsense_executor(result)

    with pytest.raises(Exception, match="boom"):
        _apply_opnsense(executor, [])

    assert state.track_resource.call_count == 0


def test_apply_with_unreadable_managed_set_passes_empty_mapping() -> None:
    """A MagicMock state manager (non-list rows) yields an empty managed mapping (#1256)."""
    executor, runner, state = _opnsense_executor({"success": True})
    state.get_managed_resources.return_value = MagicMock()

    _apply_opnsense(executor, [])

    assert runner.apply.call_args.kwargs["managed_resources"] == {}


@pytest.mark.parametrize("mode", ["serial", "parallel"])
def test_apply_dispatches_provider_with_empty_resource_list(mode: str) -> None:
    """A managed-only provider (empty list) still reaches its runner (#1260)."""
    executor, runner, _ = _opnsense_executor({"success": True})
    by_provider: dict[str, list[ResourceConfig]] = {"opnsense": []}

    if mode == "serial":
        executor.apply_serial(
            env_name="dev",
            deployment_id=1,
            resources_by_provider=by_provider,
            resource_filter=None,
            auto_approve=True,
        )
    else:
        executor.apply_parallel(
            env_name="dev",
            deployment_id=1,
            resources_by_provider=by_provider,
            resource_filter=None,
            auto_approve=True,
            max_workers=2,
        )

    runner.apply.assert_called_once()


class TestDefaultMaxWorkers:
    """default_max_workers resolves the CPU count with a fallback of 4."""

    def test_uses_cpu_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("infrafoundry.core.deployment_executor.os.cpu_count", lambda: 12)
        assert default_max_workers() == 12

    def test_falls_back_to_four_when_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("infrafoundry.core.deployment_executor.os.cpu_count", lambda: None)
        assert default_max_workers() == 4


def _failed_apply_executor(
    apply_mock: MagicMock, ids: dict[str, int]
) -> tuple[DeploymentExecutor, MagicMock, MagicMock, MagicMock]:
    """Build an executor whose runner uses ``apply_mock`` and tracks ``ids``."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]
    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.apply = apply_mock
    tf_runner.get_resource_ids = MagicMock(return_value={})
    runner_registry.create_runner.return_value = tf_runner

    state_manager = MagicMock()
    state_manager.track_resource.side_effect = [
        MagicMock(id=rid, terraform_id=None) for rid in ids.values()
    ]
    event_manager = MagicMock()
    provider = MagicMock()
    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers={"proxmox": provider},
    )
    return executor, state_manager, event_manager, provider


def _run_failed_apply(executor: DeploymentExecutor, provider: MagicMock, names: list[str]) -> None:
    executor.apply_single_provider(
        env_name="dev",
        deployment_id=1,
        provider_name="proxmox",
        provider=provider,
        resources=[_resource(n) for n in names],
        auto_approve=True,
    )


def _emitted(event_manager: MagicMock, event_type: EventType) -> list[Any]:
    return [c for c in event_manager.emit_event.call_args_list if c[0][0] == event_type]


def test_failed_apply_raise_marks_rows_error() -> None:
    """A raising runner leaves this run's rows ERROR, never ACTIVE (#1414)."""
    executor, state_manager, event_manager, provider = _failed_apply_executor(
        MagicMock(side_effect=RuntimeError("terraform crashed")), {"vm1": 11, "vm2": 12}
    )

    with pytest.raises(RuntimeError, match="terraform crashed"):
        _run_failed_apply(executor, provider, ["vm1", "vm2"])

    calls = state_manager.update_resource_state.call_args_list
    assert sorted((c.kwargs["resource_id"], c.kwargs["state"]) for c in calls) == [
        (11, ResourceState.ERROR),
        (12, ResourceState.ERROR),
    ]
    failed = _emitted(event_manager, EventType.RESOURCE_FAILED)
    assert sorted(c[0][2]["name"] for c in failed) == ["vm1", "vm2"]
    assert _emitted(event_manager, EventType.RESOURCE_CREATED) == []
    # RUNNER_FAILED is emitted before the rows are marked failed.
    types = [c[0][0] for c in event_manager.emit_event.call_args_list]
    assert types.index(EventType.RUNNER_FAILED) < types.index(EventType.RESOURCE_FAILED)


def test_failed_apply_success_false_marks_rows_error() -> None:
    """A success=False result raises TerraformError and never reaches the ACTIVE loop."""
    executor, state_manager, event_manager, provider = _failed_apply_executor(
        MagicMock(return_value={"success": False, "error": "boom", "resource_outcomes": []}),
        {"vm1": 11},
    )

    with pytest.raises(TerraformError):
        _run_failed_apply(executor, provider, ["vm1"])

    states = [c.kwargs["state"] for c in state_manager.update_resource_state.call_args_list]
    assert states == [ResourceState.ERROR]
    assert len(_emitted(event_manager, EventType.RESOURCE_FAILED)) == 1
    assert _emitted(event_manager, EventType.RESOURCE_CREATED) == []


def test_failed_apply_marking_error_does_not_mask_runner_error() -> None:
    """A state-DB failure while marking ERROR leaves the runner's exception intact."""
    executor, state_manager, _event_manager, provider = _failed_apply_executor(
        MagicMock(side_effect=RuntimeError("terraform crashed")), {"vm1": 11}
    )
    state_manager.update_resource_state.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError, match="terraform crashed"):
        _run_failed_apply(executor, provider, ["vm1"])


def test_successful_apply_never_marks_error() -> None:
    """The success path sets ACTIVE only and emits no RESOURCE_FAILED."""
    executor, state_manager, event_manager, provider = _failed_apply_executor(
        MagicMock(return_value={"success": True, "resource_outcomes": []}), {"vm1": 11}
    )

    _run_failed_apply(executor, provider, ["vm1"])

    states = [c.kwargs["state"] for c in state_manager.update_resource_state.call_args_list]
    assert ResourceState.ERROR not in states
    assert _emitted(event_manager, EventType.RESOURCE_FAILED) == []


# ---------------------------------------------------------------------------
# on_create ledger: handlers survive a failed apply (#1524)
# ---------------------------------------------------------------------------

_ON_CREATE = {"on_create": [{"type": "script", "script": "setup.sh"}]}
_ON_UPDATE = {"on_update": [{"type": "script", "script": "update.sh"}]}


def _create(name: str, prefix: str = "proxmox_virtual_environment_vm") -> ResourceOutcome:
    return ResourceOutcome(address=f"{prefix}.{name}", action="create", resource_name=name)


class _LedgerRig:
    """An executor on a real SQLite ledger with scripted runner and handler results."""

    def __init__(
        self,
        tmp_path: Path,
        apply_results: list[dict[str, Any]],
        providers: dict[str, str] | None = None,
    ) -> None:
        from infrafoundry.core.state import StateManager

        self.state = StateManager(f"sqlite:///{tmp_path / 'state.db'}")
        self.state.initialize()
        self.apply_results = apply_results
        self.abort_for: set[str] = set()
        self.continue_for: set[str] = set()
        runner = MagicMock()
        runner.priority = 0
        runner.apply = MagicMock(side_effect=self._apply)
        runner.plan = MagicMock()
        runner.destroy = MagicMock()
        runner.get_resource_ids = MagicMock(return_value={})
        registry = MagicMock()
        registry.list_runners.return_value = ["terraform"]
        registry.create_runner.return_value = runner
        self.events = MagicMock()
        self.events.emit_event.side_effect = self._emit
        tf_types = providers or {"proxmox": "proxmox_virtual_environment_vm"}
        self.providers: dict[str, Any] = {}
        for name, tf_type in tf_types.items():
            provider = MagicMock()
            provider.get_terraform_resource_types.return_value = {"vm": [tf_type]}
            self.providers[name] = provider
        self.executor = DeploymentExecutor(
            runner_registry=registry,
            state_manager=self.state,
            event_manager=self.events,
            providers=self.providers,
        )

    def _apply(self, *_a: Any, **_k: Any) -> dict[str, Any]:
        return self.apply_results.pop(0)

    def _emit(self, event_type: Any, _env: str, payload: Any, **kwargs: Any) -> list[EventResult]:
        name = kwargs.get("resource")
        if name in self.abort_for:
            return [EventResult(success=False, abort=True, reason="boom", handler_name="h")]
        if name in self.continue_for:
            return [EventResult(success=False, abort=False, reason="soft", handler_name="h")]
        return []

    def deployment(self) -> int:
        return self.state.create_deployment("dev", "apply")

    def apply(self, resources: list[MagicMock], provider: str = "proxmox") -> Any:
        return self.executor.apply_single_provider(
            env_name="dev",
            deployment_id=self.deployment(),
            provider_name=provider,
            provider=self.providers[provider],
            resources=resources,  # type: ignore[arg-type]
            auto_approve=True,
        )

    def apply_serial(self, by_provider: dict[str, list[MagicMock]], **kwargs: Any) -> Any:
        return self.executor.apply_serial(
            env_name="dev",
            deployment_id=self.deployment(),
            resources_by_provider=by_provider,  # type: ignore[arg-type]
            resource_filter=kwargs.get("resource_filter"),
            auto_approve=True,
        )

    def fired(self, event_type: EventType = EventType.RESOURCE_CREATED) -> list[str]:
        """Names of per-resource lifecycle emits of ``event_type``, in order."""
        return [
            c.kwargs["resource"]
            for c in self.events.emit_event.call_args_list
            if c.args[0] == event_type and "resource" in c.kwargs
        ]

    def aggregates(self) -> list[Any]:
        return [
            c
            for c in self.events.emit_event.call_args_list
            if c.args[0] == EventType.RESOURCE_CREATED and "resources" in c.args[2]
        ]

    def pending(self, kind: Any = None) -> list[str]:
        return [p.name for p in self.state.get_pending_on_create("dev", kind=kind)]


@pytest.fixture
def rig_factory(tmp_path: Path) -> Any:
    rigs: list[_LedgerRig] = []

    def make(apply_results: list[dict[str, Any]], **kwargs: Any) -> _LedgerRig:
        rig = _LedgerRig(tmp_path, apply_results, **kwargs)
        rigs.append(rig)
        return rig

    yield make
    for rig in rigs:
        rig.state.cleanup()


def _ok(*outcomes: ResourceOutcome) -> dict[str, Any]:
    return {"success": True, "resource_outcomes": list(outcomes)}


def _failed(*outcomes: ResourceOutcome) -> dict[str, Any]:
    return {"success": False, "resource_outcomes": list(outcomes)}


def test_failed_apply_records_pending_and_no_done(rig_factory: Any) -> None:
    rig = rig_factory([_failed(_create("web"))])
    with pytest.raises(TerraformError):
        rig.apply([_resource_with_events("web", events=_ON_CREATE)])

    assert rig.pending("resource") == ["web"]
    assert rig.fired() == []


def test_aborting_handler_leaves_pending(rig_factory: Any) -> None:
    rig = rig_factory([_ok(_create("web"))])
    rig.abort_for = {"web"}
    with pytest.raises(EventAbortedError):
        rig.apply([_resource_with_events("web", events=_ON_CREATE)])

    assert rig.pending("resource") == ["web"]


def test_success_records_pending_then_done(rig_factory: Any) -> None:
    rig = rig_factory([_ok(_create("web"))])
    rig.apply([_resource_with_events("web", events=_ON_CREATE)])

    assert rig.fired() == ["web"]
    assert rig.pending() == []
    with rig.state.SessionLocal() as session:
        from infrafoundry.core.state.models import DeploymentEvent

        types = [e.event_type for e in session.query(DeploymentEvent).order_by(DeploymentEvent.id)]
    assert types == ["on_create_pending", "on_create_done"]


def test_continue_on_error_failure_counts_as_done(rig_factory: Any) -> None:
    rig = rig_factory([_ok(_create("web"))])
    rig.continue_for = {"web"}
    rig.apply([_resource_with_events("web", events=_ON_CREATE)])

    assert rig.pending() == []


def test_resource_without_on_create_handlers_records_nothing(rig_factory: Any) -> None:
    rig = rig_factory([_failed(_create("web"))])
    with pytest.raises(TerraformError):
        rig.apply([_resource_with_events("web", events=None)])

    assert rig.pending("resource") == []


def test_helper_resource_outcome_is_not_recorded(rig_factory: Any) -> None:
    helper = _create("web", prefix="proxmox_virtual_environment_file")
    rig = rig_factory([_failed(helper)])
    with pytest.raises(TerraformError):
        rig.apply([_resource_with_events("web", events=_ON_CREATE)])

    assert rig.pending() == []


def test_retry_fires_pending_on_create_once(rig_factory: Any) -> None:
    rig = rig_factory([_failed(_create("web")), _ok(), _ok()])
    resources = [_resource_with_events("web", events=_ON_CREATE)]
    with pytest.raises(TerraformError):
        rig.apply(resources)

    rig.apply(resources)
    assert rig.fired() == ["web"]
    assert rig.pending() == []

    rig.apply(resources)
    assert rig.fired() == ["web"]


def test_retry_skipped_when_resource_filtered_out(rig_factory: Any) -> None:
    rig = rig_factory([_failed(_create("web")), _ok()])
    with pytest.raises(TerraformError):
        rig.apply([_resource_with_events("web", events=_ON_CREATE)])

    rig.apply([_resource_with_events("other", events=_ON_CREATE)])
    assert rig.fired() == []
    assert rig.pending("resource") == ["web"]


def test_retry_fires_before_update(rig_factory: Any) -> None:
    update = ResourceOutcome(
        address="proxmox_virtual_environment_vm.db", action="update", resource_name="db"
    )
    rig = rig_factory([_failed(_create("web")), _ok(update)])
    resources = [
        _resource_with_events("web", events=_ON_CREATE),
        _resource_with_events("db", events=_ON_UPDATE),
    ]
    with pytest.raises(TerraformError):
        rig.apply(resources)

    rig.apply(resources)
    order = [
        (c.args[0], c.kwargs["resource"])
        for c in rig.events.emit_event.call_args_list
        if "resource" in c.kwargs
    ]
    assert order == [
        (EventType.RESOURCE_CREATED, "web"),
        (EventType.RESOURCE_UPDATED, "db"),
    ]


def test_retry_abort_stays_pending(rig_factory: Any) -> None:
    rig = rig_factory([_failed(_create("web")), _ok()])
    resources = [_resource_with_events("web", events=_ON_CREATE)]
    with pytest.raises(TerraformError):
        rig.apply(resources)

    rig.abort_for = {"web"}
    with pytest.raises(EventAbortedError):
        rig.apply(resources)
    assert rig.pending("resource") == ["web"]


def test_ledger_errors_do_not_break_the_apply(rig_factory: Any) -> None:
    rig = rig_factory([_ok(_create("web"))])
    for attr in ("record_pending_on_create", "record_on_create_done", "get_pending_on_create"):
        setattr(rig.state, attr, MagicMock(side_effect=RuntimeError("db down")))

    rig.apply([_resource_with_events("web", events=_ON_CREATE)])
    assert rig.fired() == ["web"]


def test_ledger_write_error_does_not_mask_the_runner_error(rig_factory: Any) -> None:
    rig = rig_factory([_failed(_create("web"))])
    rig.state.record_pending_on_create = MagicMock(side_effect=RuntimeError("db down"))
    with pytest.raises(TerraformError):
        rig.apply([_resource_with_events("web", events=_ON_CREATE)])


# Package kind --------------------------------------------------------------


def test_package_pending_recorded_and_done_after_aggregate(rig_factory: Any) -> None:
    rig = rig_factory([_ok(_create("web"))])
    rig.apply_serial({"proxmox": [_resource_with_events("web")]})

    assert len(rig.aggregates()) == 1
    assert rig.pending() == []
    assert rig.pending("package") == []


def test_cross_provider_failure_keeps_package_pending(rig_factory: Any) -> None:
    rig = rig_factory(
        [_ok(_create("a")), _failed(_create("b", "proxmox_virtual_environment_vm"))],
        providers={
            "opnsense": "proxmox_virtual_environment_vm",
            "proxmox": "proxmox_virtual_environment_vm",
        },
    )
    by_provider = {
        "opnsense": [_resource_with_events("a", provider="opnsense")],
        "proxmox": [_resource_with_events("b")],
    }
    with pytest.raises(TerraformError):
        rig.apply_serial(by_provider)

    assert rig.aggregates() == []
    assert sorted(rig.pending("package")) == ["a", "b"]


def test_retry_merges_old_and_new_names_into_one_aggregate(rig_factory: Any) -> None:
    rig = rig_factory([_failed(_create("a")), _ok(_create("b"))])
    first = {"proxmox": [_resource_with_events("a")]}
    with pytest.raises(TerraformError):
        rig.apply_serial(first)

    rig.apply_serial({"proxmox": [_resource_with_events("a"), _resource_with_events("b")]})
    aggregates = rig.aggregates()
    assert len(aggregates) == 1
    assert aggregates[0].kwargs["target_resources"] == ["b", "a"]
    assert rig.pending("package") == []


def test_package_abort_stays_pending(rig_factory: Any) -> None:
    rig = rig_factory([_ok(_create("web"))])
    rig.events.emit_event.side_effect = lambda et, env, payload, **kw: (
        [EventResult(success=False, abort=True, reason="stop", handler_name="h")]
        if "resources" in payload
        else []
    )
    with pytest.raises(EventAbortedError):
        rig.apply_serial({"proxmox": [_resource_with_events("web")]})

    assert rig.pending("package") == ["web"]


def test_apply_parallel_records_no_package_pending(rig_factory: Any) -> None:
    rig = rig_factory([_ok(_create("web"))])
    rig.abort_for = {"web"}
    rig.executor.apply_parallel(
        env_name="dev",
        deployment_id=rig.deployment(),
        resources_by_provider={"proxmox": [_resource_with_events("web", events=_ON_CREATE)]},
        resource_filter=None,
        auto_approve=True,
        max_workers=1,
    )

    assert rig.pending("package") == []
    assert rig.pending("resource") == ["web"]
