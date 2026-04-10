"""Unit tests for DeploymentExecutor apply flows."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.config.models import IaCTool
from infrafoundry.core.deployment_executor import DeploymentExecutor
from infrafoundry.core.events import EventAbortedError, EventType
from infrafoundry.core.events.context import EventResult
from infrafoundry.core.exceptions import ResourceFilterError, TerraformError
from infrafoundry.core.state import ResourceState
from infrafoundry.core.types import ResourceOutcome


def _resource(name: str, provider: str = "proxmox", type_: str = "vm"):
    res = MagicMock()
    res.name = name
    res.provider = provider
    res.type = type_
    res.config = {"id": name}
    return res


def test_apply_serial_orders_providers_and_tracks_states():
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

    providers = {
        "opnsense": MagicMock(),
        "proxmox": MagicMock(),
    }

    resources_by_provider = {
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


def test_apply_parallel_uses_executor_and_handles_runner_errors():
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

    def create_runner(name, console=None):
        return tf_runner

    runner_registry.create_runner.side_effect = create_runner

    state_manager = MagicMock()
    event_manager = MagicMock()

    provider_ok = MagicMock()
    provider_err = MagicMock()
    providers = {"proxmox": provider_ok, "opnsense": provider_err}

    resources_by_provider = {
        "proxmox": [_resource("vm1", provider="proxmox")],
        "opnsense": [_resource("fw1", provider="opnsense")],
    }

    def runner_apply(provider, auto_approve=True, **kwargs):
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


def test_apply_single_provider_tracks_resources_and_emits_events():
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

    def create_runner(name, console=None):
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
    providers = {"proxmox": provider}

    resources = [
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


def test_apply_single_provider_runs_runners_in_priority_order():
    """Single provider apply respects runner priority ordering."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["ansible", "terraform"]

    execution_order = []

    tf_runner = MagicMock()
    tf_runner.priority = 0

    # Set protocol methods with side effects for execution tracking
    def tf_apply(provider, auto_approve=True, **kwargs):
        execution_order.append("terraform")
        return {"success": True}

    tf_runner.apply = MagicMock(side_effect=tf_apply)
    tf_runner.plan = MagicMock()
    tf_runner.destroy = MagicMock()
    tf_runner.get_resource_ids = MagicMock(return_value={})

    ansible_runner = MagicMock()
    ansible_runner.priority = 50

    def ansible_apply(provider, auto_approve=True, **kwargs):
        execution_order.append("ansible")
        return {"success": True}

    # Ansible supports apply/plan
    ansible_runner.apply = MagicMock(side_effect=ansible_apply)
    ansible_runner.plan = MagicMock()

    def create_runner(name, console=None):
        return tf_runner if name == "terraform" else ansible_runner

    runner_registry.create_runner.side_effect = create_runner

    state_manager = MagicMock()
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    provider = MagicMock()
    providers = {"proxmox": provider}
    resources = [_resource("vm1")]

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


def test_get_sorted_runners_respects_priority_overrides():
    """Runner sorting uses priority overrides from environment config."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform", "ansible", "pyinfra"]

    tf_runner = MagicMock()
    tf_runner.priority = 0

    ansible_runner = MagicMock()
    ansible_runner.priority = 50

    pyinfra_runner = MagicMock()
    pyinfra_runner.priority = 50

    def create_runner(name, console=None):
        if name == "terraform":
            return tf_runner
        elif name == "ansible":
            return ansible_runner
        else:
            return pyinfra_runner

    runner_registry.create_runner.side_effect = create_runner

    state_manager = MagicMock()
    event_manager = MagicMock()
    providers = {}

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


def test_apply_serial_with_empty_resources():
    """Serial apply handles empty resource list gracefully."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = []
    state_manager = MagicMock()
    event_manager = MagicMock()
    providers = {}

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


def test_apply_parallel_with_all_providers_failing():
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

    providers = {
        "proxmox": MagicMock(),
        "opnsense": MagicMock(),
    }

    resources_by_provider = {
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


def test_apply_single_provider_handles_multiple_resources():
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
    providers = {"proxmox": provider}

    # Multiple resources
    resources = [
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


def test_apply_single_provider_tracks_state_for_opentofu_runner():
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
    providers = {"proxmox": provider}

    resources = [_resource("vm1")]

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


def test_get_sorted_runners_filters_inactive_iac_tool():
    """Only the configured IaC runner is included; the other is skipped."""
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform", "opentofu", "ansible"]

    tf_runner = MagicMock()
    tf_runner.priority = 0

    tofu_runner = MagicMock()
    tofu_runner.priority = 0

    ansible_runner = MagicMock()
    ansible_runner.priority = 50

    def create_runner(name, console=None):
        if name == "terraform":
            return tf_runner
        elif name == "opentofu":
            return tofu_runner
        else:
            return ansible_runner

    runner_registry.create_runner.side_effect = create_runner

    state_manager = MagicMock()
    event_manager = MagicMock()
    providers = {}

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


def test_apply_emits_runner_starting_and_completed():
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
    providers = {"proxmox": provider}
    resources = [_resource("vm1")]

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


def test_apply_emits_runner_failed_on_exception():
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
    providers = {"proxmox": provider}
    resources = [_resource("vm1")]

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


def test_apply_single_provider_raises_on_runner_failure():
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
    providers = {"proxmox": provider}
    resources = [_resource("vm1")]

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


def _make_executor(providers=None):
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


def test_validate_resource_filter_zero_matches_raises():
    """Zero resource filter matches raises ResourceFilterError."""
    executor = _make_executor()
    resources_by_provider = {
        "proxmox": [_resource("vm1"), _resource("vm2")],
    }

    with pytest.raises(ResourceFilterError, match="No resources matched filter"):
        executor._validate_resource_filter(resources_by_provider, {"nonexistent"})


def test_validate_resource_filter_error_includes_names():
    """Error message includes unmatched filter names and available resource names."""
    executor = _make_executor()
    resources_by_provider = {
        "proxmox": [_resource("vm1"), _resource("vm2")],
    }

    with pytest.raises(ResourceFilterError) as exc_info:
        executor._validate_resource_filter(resources_by_provider, {"nonexistent"})

    error_msg = str(exc_info.value)
    assert "nonexistent" in error_msg
    assert "vm1" in error_msg
    assert "vm2" in error_msg


def test_validate_resource_filter_partial_match_warns():
    """Partial match warns but does not raise."""
    executor = _make_executor()
    resources_by_provider = {
        "proxmox": [_resource("vm1"), _resource("vm2")],
    }

    # Should not raise
    executor._validate_resource_filter(resources_by_provider, {"vm1", "nonexistent"})


def test_validate_resource_filter_full_match_succeeds():
    """Full match does not raise or warn."""
    executor = _make_executor()
    resources_by_provider = {
        "proxmox": [_resource("vm1"), _resource("vm2")],
    }

    # Should not raise
    executor._validate_resource_filter(resources_by_provider, {"vm1", "vm2"})


def test_apply_serial_raises_on_zero_filter_matches():
    """apply_serial raises ResourceFilterError when filter matches nothing."""
    providers = {"proxmox": MagicMock()}
    executor = _make_executor(providers=providers)
    resources_by_provider = {
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


def test_apply_parallel_raises_on_zero_filter_matches():
    """apply_parallel raises ResourceFilterError when filter matches nothing."""
    providers = {"proxmox": MagicMock()}
    executor = _make_executor(providers=providers)
    resources_by_provider = {
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
    events: dict | None = None,
):
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
):
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

        def emit_side_effect(event_type, *args, **kwargs):
            if event_type in lifecycle_types:
                return emit_results
            return []

        event_manager.emit_event.side_effect = emit_side_effect

    provider = MagicMock()
    # Map vm type -> proxmox_virtual_environment_vm terraform type
    provider.get_terraform_resource_types.return_value = {
        "vm": ["proxmox_virtual_environment_vm"],
    }

    providers = {"proxmox": provider}

    executor = DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=state_manager,
        event_manager=event_manager,
        providers=providers,
    )

    return executor, event_manager, provider


def test_event_handler_failure_abort_raises_from_lifecycle_events():
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


def test_event_handler_failure_continue_on_error_does_not_raise():
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


def test_event_handler_success_does_not_raise():
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


def test_aggregate_group_handler_failure_raises_from_apply_serial():
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

    def emit_side_effect(event_type, *args, **kwargs):
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
    providers = {"proxmox": provider}

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
