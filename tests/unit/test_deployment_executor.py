"""Unit tests for DeploymentExecutor apply flows."""

from __future__ import annotations

from unittest.mock import MagicMock

from infrafoundry.core.deployment_executor import DeploymentExecutor
from infrafoundry.core.events import EventType
from infrafoundry.core.state import ResourceState


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
    tf_runner.run.return_value = {"success": True}
    tf_runner.get_resource_ids.return_value = {"vm1": "proxmox_vm.vm1"}
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

    def runner_run(provider, command, auto_approve):
        if provider is provider_err:
            raise RuntimeError("boom")
        return {"success": True}

    tf_runner.run.side_effect = runner_run

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
    tf_runner.run.return_value = {"success": True}
    tf_runner.get_resource_ids.return_value = {"vm1": "proxmox_vm.vm1", "vm2": "proxmox_vm.vm2"}

    ansible_runner = MagicMock()
    ansible_runner.priority = 50
    ansible_runner.run.return_value = {"success": True}

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

    def tf_run(provider, command, auto_approve):
        execution_order.append("terraform")
        return {"success": True}

    tf_runner.run.side_effect = tf_run
    tf_runner.get_resource_ids.return_value = {}

    ansible_runner = MagicMock()
    ansible_runner.priority = 50

    def ansible_run(provider, command, auto_approve):
        execution_order.append("ansible")
        return {"success": True}

    ansible_runner.run.side_effect = ansible_run

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
    tf_runner.run.side_effect = RuntimeError("Connection timeout")

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
    tf_runner.run.return_value = {"success": True}
    tf_runner.get_resource_ids.return_value = {}

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
