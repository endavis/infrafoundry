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
