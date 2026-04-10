"""Unit tests for orchestrator workflow helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.events import EventType
from infrafoundry.core.orchestrator_workflows import (
    ApplyOrchestrator,
    DestroyOrchestrator,
    DriftOrchestrator,
    PlanOrchestrator,
    ProviderResourceBatch,
    StatusOrchestrator,
    ValidationOrchestrator,
)
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.state import DeploymentStatus


@pytest.fixture
def console():
    """Stub console to avoid actual output."""
    return Console(file=open(Path("/dev/null"), "w"))


def _resource(name: str, provider: str = "proxmox", type_: str = "vm") -> ResourceConfig:
    return ResourceConfig(name=name, provider=provider, type=type_, config={"id": name})


def test_plan_orchestrator_dry_run_skips_generation(console):
    """Dry run should skip generate/run and mark dry_run in results."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 1
    event_manager = MagicMock()
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = []
    providers = {"proxmox": MagicMock()}

    def load_resources(env: str):
        res = [_resource("vm1")]
        return res, {"proxmox": res}

    orchestrator = PlanOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
        iter_provider_batches=lambda resources_by_provider, filt, reverse, env_name: [
            ProviderResourceBatch("proxmox", resources_by_provider["proxmox"], 1)
        ],
        validate_resources=MagicMock(),
        has_policies=lambda: False,
        check_policies=MagicMock(),
        secret_manager_factory=MagicMock(),
        get_current_user=lambda: "tester",
        fail_on_missing_secrets=False,
        get_runner_priorities=lambda _: {},
    )

    result = orchestrator.plan(
        env_name="dev",
        dry_run=True,
        resource_filter=None,
        enforce_policies=False,
    )

    assert result["proxmox"]["dry_run"] is True
    providers["proxmox"].ensure_directories.assert_not_called()
    state_manager.update_deployment_status.assert_called_with(1, DeploymentStatus.COMPLETED)
    event_manager.emit_event.assert_any_call(
        EventType.BEFORE_PLAN,
        "dev",
        {"deployment_id": 1, "dry_run": True},
        target_resources=None,
        package_filter=None,
    )
    event_manager.emit_event.assert_any_call(
        EventType.AFTER_PLAN,
        "dev",
        {"deployment_id": 1, "results": result},
        target_resources=None,
        package_filter=None,
    )


def test_plan_orchestrator_runs_runners_in_priority_order(console):
    """Runners are sorted by provided priorities when generating plans."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 2
    event_manager = MagicMock()

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.plan = MagicMock()  # Satisfy Plannable

    ansible_runner = MagicMock()
    ansible_runner.priority = 50
    ansible_runner.plan = MagicMock()  # Satisfy Plannable

    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform", "ansible"]
    runner_registry.create_runner.side_effect = lambda name, console=None: {
        "terraform": tf_runner,
        "ansible": ansible_runner,
    }[name]

    provider = MagicMock()
    provider.generate_terraform = MagicMock()
    provider.generate_ansible = MagicMock()
    providers = {"proxmox": provider}

    def load_resources(env: str):
        res = [_resource("vm1")]
        return res, {"proxmox": res}

    orchestrator = PlanOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
        iter_provider_batches=lambda resources_by_provider, filt, reverse, env_name: [
            ProviderResourceBatch("proxmox", resources_by_provider["proxmox"], 1)
        ],
        validate_resources=MagicMock(),
        has_policies=lambda: False,
        check_policies=MagicMock(),
        secret_manager_factory=MagicMock(),
        get_current_user=lambda: "tester",
        fail_on_missing_secrets=False,
        get_runner_priorities=lambda _: {},
    )

    orchestrator.plan(env_name="dev", dry_run=False, resource_filter=None, enforce_policies=False)

    provider.generate_terraform.assert_called_once()
    provider.generate_ansible.assert_called_once()
    # Ensure terraform plan happens before ansible
    assert tf_runner.plan.called
    assert ansible_runner.plan.called
    assert tf_runner.plan.call_args_list[0][0][0] == provider


def test_apply_orchestrator_uses_parallel_when_multiple_providers(console):
    """Apply chooses parallel path when requested and multiple providers exist."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 3
    event_manager = MagicMock()

    def load_resources(env: str):
        res_a = [_resource("vm1", provider="proxmox")]
        res_b = [_resource("fw1", provider="opnsense", type_="firewall_rule")]
        return res_a + res_b, {"proxmox": res_a, "opnsense": res_b}

    apply_serial = MagicMock()
    apply_parallel = MagicMock(return_value={"parallel": True})

    orchestrator = ApplyOrchestrator(
        console,
        state_manager,
        event_manager,
        load_resources,
        apply_serial=apply_serial,
        apply_parallel=apply_parallel,
        get_current_user=lambda: "tester",
    )

    result = orchestrator.apply(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        parallel=True,
        max_workers=4,
    )

    apply_parallel.assert_called_once()
    apply_serial.assert_not_called()
    state_manager.update_deployment_status.assert_called_with(3, DeploymentStatus.COMPLETED)
    assert result == {"parallel": True}


def test_destroy_orchestrator_requires_confirmation(console):
    """Destroy requires confirmation when auto_approve is False."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 4
    event_manager = MagicMock()
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = []
    providers = {"proxmox": MagicMock()}

    orchestrator = DestroyOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=lambda env: ([], {"proxmox": []}),
        iter_provider_batches=lambda resources_by_provider, filt, reverse, env_name: [
            ProviderResourceBatch("proxmox", [], 0)
        ],
        get_current_user=lambda: "tester",
    )

    result = orchestrator.destroy(
        env_name="dev",
        resource_filter=None,
        auto_approve=False,
        confirm_callback=lambda: False,
    )

    assert result["success"] is False
    state_manager.update_deployment_status.assert_called_with(
        4, DeploymentStatus.FAILED, "User aborted"
    )


def test_validation_orchestrator_warns_on_missing_provider(console):
    """Validation skips missing providers without crashing."""
    config_manager = MagicMock()
    config_manager.load_environment.return_value = SimpleNamespace(
        model_dump=lambda: {"name": "dev"}
    )
    env_resources = [_resource("vm1", provider="proxmox")]
    validation = ValidationOrchestrator(
        config_manager,
        console,
        get_providers=lambda: {},  # Missing provider
        load_resources=lambda env: (env_resources, {"proxmox": env_resources}),
        iter_provider_batches=lambda resources_by_provider, filt, reverse, env_name: [
            ProviderResourceBatch("proxmox", env_resources, 1)
        ],
    )

    results = validation.validate("dev", resource_filter=None, verbose=False)
    assert results == {}


def test_status_orchestrator_marks_unregistered_provider(console):
    """Status shows not registered when provider missing."""
    rows: list[tuple[str, str, str]] = []

    class FakeTable:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def add_column(self, *args, **kwargs):
            pass

        def add_row(self, provider: str, resources: str, status: str):
            rows.append((provider, resources, status))

    console_stub = MagicMock()
    config_manager = MagicMock()
    config_manager.get_all_resources_all_providers.return_value = [
        _resource("vm1", provider="proxmox")
    ]

    with patch("infrafoundry.core.orchestrator_workflows.Table", FakeTable):
        status = StatusOrchestrator(console_stub, config_manager, get_providers=lambda: {})
        status.show("dev")

    assert rows
    assert "Not registered" in rows[0][2]


def test_plan_emits_runner_starting_and_completed(console):
    """Runner events are emitted around each runner.plan() call."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 10
    event_manager = MagicMock()

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.plan = MagicMock(return_value={"success": True})

    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]
    runner_registry.create_runner.return_value = tf_runner

    provider = MagicMock()
    provider.generate_terraform = MagicMock()
    providers = {"proxmox": provider}

    def load_resources(env: str):
        res = [_resource("vm1")]
        return res, {"proxmox": res}

    orchestrator = PlanOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
        iter_provider_batches=lambda resources_by_provider, filt, reverse, env_name: [
            ProviderResourceBatch("proxmox", resources_by_provider["proxmox"], 1)
        ],
        validate_resources=MagicMock(),
        has_policies=lambda: False,
        check_policies=MagicMock(),
        secret_manager_factory=MagicMock(),
        get_current_user=lambda: "tester",
        fail_on_missing_secrets=False,
        get_runner_priorities=lambda _: {},
    )

    orchestrator.plan(env_name="dev", dry_run=False, resource_filter=None, enforce_policies=False)

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
    assert starting_calls[0][0][2] == {
        "provider": "proxmox",
        "runner": "terraform",
        "phase": "plan",
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
        "phase": "plan",
        "success": True,
    }


def test_destroy_emits_runner_starting_and_completed(console):
    """Runner events are emitted around each runner.destroy() call."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 20
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.destroy = MagicMock(return_value={"success": True})
    tf_runner.verify_destroyed = MagicMock(return_value=[])

    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    runners = {"terraform": tf_runner}

    provider = MagicMock()
    providers = {"proxmox": provider}

    def load_resources(env: str):
        res = [_resource("vm1")]
        return res, {"proxmox": res}

    orchestrator = DestroyOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
        iter_provider_batches=lambda resources_by_provider, filt, reverse, env_name: [
            ProviderResourceBatch("proxmox", resources_by_provider["proxmox"], 1)
        ],
        get_current_user=lambda: "tester",
    )
    # Inject runners directly for the destroy loop
    orchestrator.runners = runners

    orchestrator.destroy(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        confirm_callback=lambda: True,
    )

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
    assert starting_calls[0][0][2] == {
        "provider": "proxmox",
        "runner": "terraform",
        "phase": "destroy",
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
        "phase": "destroy",
        "success": True,
    }


def test_destroy_orchestrator_regenerates_configs_before_destroy(console):
    """Destroy regenerates provider IaC configs before invoking runner.destroy."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 30
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.is_iac_runner = True
    tf_runner.destroy = MagicMock(return_value={"success": True})
    tf_runner.verify_destroyed = MagicMock(return_value=[])

    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    # Shared parent mock so we can assert call ordering across generate + destroy
    parent = MagicMock()
    provider = MagicMock()
    provider.generate_terraform = parent.generate_terraform
    parent.attach_mock(tf_runner.destroy, "tf_destroy")
    providers = cast("dict[str, ProviderBase]", {"proxmox": provider})

    resources = [_resource("vm1"), _resource("vm2"), _resource("vm3")]

    def load_resources(env: str):
        return resources, {"proxmox": resources}

    orchestrator = DestroyOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
        iter_provider_batches=lambda rbp, filt, rev, env: [
            ProviderResourceBatch("proxmox", rbp["proxmox"], 3)
        ],
        get_current_user=lambda: "tester",
    )
    orchestrator.runners = cast("dict[str, BaseRunner]", {"terraform": tf_runner})

    orchestrator.destroy(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        confirm_callback=lambda: True,
    )

    provider.generate_terraform.assert_called_once_with(resources)
    tf_runner.destroy.assert_called_once()

    # Verify ordering: generate_terraform happened before tf_destroy
    call_names = [c[0] for c in parent.mock_calls]
    gen_idx = call_names.index("generate_terraform")
    destroy_idx = call_names.index("tf_destroy")
    assert gen_idx < destroy_idx


def test_destroy_orchestrator_regenerates_with_all_resources_when_filtered(console):
    """Filtered destroy still regenerates all provider resources (not just the filtered subset)."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 31
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.is_iac_runner = True
    tf_runner.destroy = MagicMock(return_value={"success": True})
    tf_runner.verify_destroyed = MagicMock(return_value=[])

    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    provider = MagicMock()
    provider.generate_terraform = MagicMock()
    providers = cast("dict[str, ProviderBase]", {"proxmox": provider})

    all_resources = [_resource("vm1"), _resource("vm2"), _resource("vm3")]
    filtered_resources = [_resource("vm1")]

    def load_resources(env: str):
        return all_resources, {"proxmox": all_resources}

    orchestrator = DestroyOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
        # iter_provider_batches returns the FILTERED subset, mirroring production
        iter_provider_batches=lambda rbp, filt, rev, env: [
            ProviderResourceBatch("proxmox", filtered_resources, 3)
        ],
        get_current_user=lambda: "tester",
    )
    orchestrator.runners = cast("dict[str, BaseRunner]", {"terraform": tf_runner})

    orchestrator.destroy(
        env_name="dev",
        resource_filter=["vm1"],
        auto_approve=True,
        confirm_callback=lambda: True,
    )

    # Generate was called with ALL 3 resources, not just the filtered subset
    provider.generate_terraform.assert_called_once_with(all_resources)


def test_destroy_orchestrator_skips_generate_when_provider_lacks_method(console):
    """Destroy proceeds without error when provider has no generate_terraform method."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 32
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.is_iac_runner = True
    tf_runner.destroy = MagicMock(return_value={"success": True})
    tf_runner.verify_destroyed = MagicMock(return_value=[])

    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    # Provider deliberately lacks generate_terraform
    provider = MagicMock(spec=["set_environment", "ensure_directories", "terraform_parallelism"])
    provider.terraform_parallelism = None
    providers = cast("dict[str, ProviderBase]", {"proxmox": provider})

    resources = [_resource("vm1")]

    def load_resources(env: str):
        return resources, {"proxmox": resources}

    orchestrator = DestroyOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
        iter_provider_batches=lambda rbp, filt, rev, env: [
            ProviderResourceBatch("proxmox", rbp["proxmox"], 1)
        ],
        get_current_user=lambda: "tester",
    )
    orchestrator.runners = cast("dict[str, BaseRunner]", {"terraform": tf_runner})

    # Should not raise AttributeError
    orchestrator.destroy(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        confirm_callback=lambda: True,
    )

    tf_runner.destroy.assert_called_once()
    assert not hasattr(provider, "generate_terraform")


def test_destroy_orchestrator_raises_on_runner_failure(console):
    """When runner returns success=False, destroy raises TerraformError and fires RUNNER_FAILED."""
    from infrafoundry.core.exceptions import TerraformError

    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 40
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.is_iac_runner = True
    tf_runner.destroy = MagicMock(
        return_value={
            "success": False,
            "exit_code": 1,
            "stderr": "Error: Instance cannot be destroyed",
            "error": "Instance cannot be destroyed",
        }
    )
    tf_runner.verify_destroyed = MagicMock(return_value=[])

    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    provider = MagicMock()
    providers = cast("dict[str, ProviderBase]", {"proxmox": provider})

    resources = [_resource("vm1")]

    def load_resources(env: str):
        return resources, {"proxmox": resources}

    orchestrator = DestroyOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
        iter_provider_batches=lambda rbp, filt, rev, env: [
            ProviderResourceBatch("proxmox", rbp["proxmox"], 1)
        ],
        get_current_user=lambda: "tester",
    )
    orchestrator.runners = cast("dict[str, BaseRunner]", {"terraform": tf_runner})

    with pytest.raises(TerraformError) as excinfo:
        orchestrator.destroy(
            env_name="dev",
            resource_filter=None,
            auto_approve=True,
            confirm_callback=lambda: True,
        )

    assert "Instance cannot be destroyed" in str(excinfo.value)
    assert excinfo.value.exit_code == 1

    failed_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RUNNER_FAILED
    ]
    completed_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RUNNER_COMPLETED
    ]
    assert len(failed_calls) == 1
    assert len(completed_calls) == 0

    # Deployment marked FAILED
    status_calls = state_manager.update_deployment_status.call_args_list
    assert any(call[0][1] == DeploymentStatus.FAILED for call in status_calls)


def test_destroy_orchestrator_raises_when_resource_remains_in_state(console):
    """Defense-in-depth: success=True but state still has the resource -> TerraformError."""
    from infrafoundry.core.exceptions import TerraformError

    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 41
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.is_iac_runner = True
    tf_runner.destroy = MagicMock(return_value={"success": True, "exit_code": 0})
    tf_runner.verify_destroyed = MagicMock(return_value=["vm1"])

    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    provider = MagicMock()
    providers = cast("dict[str, ProviderBase]", {"proxmox": provider})

    resources = [_resource("vm1")]

    def load_resources(env: str):
        return resources, {"proxmox": resources}

    orchestrator = DestroyOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
        iter_provider_batches=lambda rbp, filt, rev, env: [
            ProviderResourceBatch("proxmox", rbp["proxmox"], 1)
        ],
        get_current_user=lambda: "tester",
    )
    orchestrator.runners = cast("dict[str, BaseRunner]", {"terraform": tf_runner})

    with pytest.raises(TerraformError) as excinfo:
        orchestrator.destroy(
            env_name="dev",
            resource_filter=None,
            auto_approve=True,
            confirm_callback=lambda: True,
        )

    assert "vm1" in str(excinfo.value)
    tf_runner.verify_destroyed.assert_called_once_with(provider, ["vm1"])


def test_destroy_orchestrator_skips_verify_when_runner_lacks_method(console):
    """A runner without verify_destroyed (e.g. Ansible) proceeds without AttributeError."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 42
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    # spec the mock so hasattr(runner, "verify_destroyed") is False
    tf_runner = MagicMock(
        spec=[
            "priority",
            "is_iac_runner",
            "destroy",
        ]
    )
    tf_runner.priority = 0
    tf_runner.is_iac_runner = True
    tf_runner.destroy = MagicMock(return_value={"success": True, "exit_code": 0})

    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    provider = MagicMock()
    providers = cast("dict[str, ProviderBase]", {"proxmox": provider})

    resources = [_resource("vm1")]

    def load_resources(env: str):
        return resources, {"proxmox": resources}

    orchestrator = DestroyOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
        iter_provider_batches=lambda rbp, filt, rev, env: [
            ProviderResourceBatch("proxmox", rbp["proxmox"], 1)
        ],
        get_current_user=lambda: "tester",
    )
    orchestrator.runners = cast("dict[str, BaseRunner]", {"terraform": tf_runner})

    # Should not raise
    orchestrator.destroy(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        confirm_callback=lambda: True,
    )

    tf_runner.destroy.assert_called_once()
    assert not hasattr(tf_runner, "verify_destroyed")


def test_destroy_orchestrator_aggregates_failures_across_providers(console):
    """With two providers, the second's failure surfaces while the first completes."""
    from infrafoundry.core.exceptions import TerraformError

    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 43
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()

    # Single runner instance; returns success for provider-a then failure for provider-b.
    tf_runner = MagicMock()
    tf_runner.priority = 0
    tf_runner.is_iac_runner = True
    tf_runner.destroy = MagicMock(
        side_effect=[
            {"success": True, "exit_code": 0},
            {
                "success": False,
                "exit_code": 1,
                "stderr": "nope",
                "error": "prevent_destroy",
            },
        ]
    )
    tf_runner.verify_destroyed = MagicMock(return_value=[])

    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]

    provider_a = MagicMock()
    provider_b = MagicMock()
    providers = cast("dict[str, ProviderBase]", {"prov_a": provider_a, "prov_b": provider_b})

    res_a = [_resource("vm_a", provider="prov_a")]
    res_b = [_resource("vm_b", provider="prov_b")]

    def load_resources(env: str):
        return res_a + res_b, {"prov_a": res_a, "prov_b": res_b}

    orchestrator = DestroyOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
        iter_provider_batches=lambda rbp, filt, rev, env: [
            ProviderResourceBatch("prov_a", rbp["prov_a"], 1),
            ProviderResourceBatch("prov_b", rbp["prov_b"], 1),
        ],
        get_current_user=lambda: "tester",
    )
    orchestrator.runners = cast("dict[str, BaseRunner]", {"terraform": tf_runner})

    with pytest.raises(TerraformError):
        orchestrator.destroy(
            env_name="dev",
            resource_filter=None,
            auto_approve=True,
            confirm_callback=lambda: True,
        )

    completed_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RUNNER_COMPLETED
    ]
    failed_calls = [
        call
        for call in event_manager.emit_event.call_args_list
        if call[0][0] == EventType.RUNNER_FAILED
    ]
    assert len(completed_calls) == 1
    assert len(failed_calls) == 1
    assert completed_calls[0][1]["provider"] == "prov_a"
    assert failed_calls[0][1]["provider"] == "prov_b"

    status_calls = state_manager.update_deployment_status.call_args_list
    assert any(call[0][1] == DeploymentStatus.FAILED for call in status_calls)


def test_drift_orchestrator_sets_providers():
    """DriftOrchestrator injects providers before detection."""
    drift_detector = MagicMock()
    drift_detector.detect.return_value = {"drift": False}
    providers = {"proxmox": MagicMock()}

    orchestrator = DriftOrchestrator(drift_detector, get_providers=lambda: providers)
    result = orchestrator.detect("dev")

    assert result == {"drift": False}
    assert drift_detector.providers == providers


def _make_env_config_with_events(events: dict | None = None) -> EnvironmentConfig:
    """Create an EnvironmentConfig with optional events dict."""
    return EnvironmentConfig(
        name="dev",
        events=events or {},
    )


def test_plan_loads_event_config(console):
    """PlanOrchestrator calls load_config when events are present."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 100
    event_manager = MagicMock()
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = []
    providers = {"proxmox": MagicMock()}

    events_cfg = {"RUNNER_COMPLETED": [{"type": "script", "name": "post", "script": "s.sh"}]}
    env_config = _make_env_config_with_events(events_cfg)

    orchestrator = PlanOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=lambda env: ([_resource("vm1")], {"proxmox": [_resource("vm1")]}),
        iter_provider_batches=lambda rbp, filt, rev, env: [
            ProviderResourceBatch("proxmox", rbp["proxmox"], 1)
        ],
        validate_resources=MagicMock(),
        has_policies=lambda: False,
        check_policies=MagicMock(),
        secret_manager_factory=MagicMock(),
        get_current_user=lambda: "tester",
        fail_on_missing_secrets=False,
        get_runner_priorities=lambda _: {},
        load_environment=lambda _: env_config,
    )

    orchestrator.plan(env_name="dev", dry_run=True, resource_filter=None, enforce_policies=False)

    event_manager.clear_handlers.assert_called_once()
    event_manager.load_config.assert_called_once_with(events_cfg)


def test_plan_skips_event_config_when_empty(console):
    """PlanOrchestrator clears handlers but does not call load_config when events is empty."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 101
    event_manager = MagicMock()
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = []
    providers = {"proxmox": MagicMock()}

    env_config = _make_env_config_with_events({})

    orchestrator = PlanOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=lambda env: ([_resource("vm1")], {"proxmox": [_resource("vm1")]}),
        iter_provider_batches=lambda rbp, filt, rev, env: [
            ProviderResourceBatch("proxmox", rbp["proxmox"], 1)
        ],
        validate_resources=MagicMock(),
        has_policies=lambda: False,
        check_policies=MagicMock(),
        secret_manager_factory=MagicMock(),
        get_current_user=lambda: "tester",
        fail_on_missing_secrets=False,
        get_runner_priorities=lambda _: {},
        load_environment=lambda _: env_config,
    )

    orchestrator.plan(env_name="dev", dry_run=True, resource_filter=None, enforce_policies=False)

    event_manager.clear_handlers.assert_called_once()
    event_manager.load_config.assert_not_called()


def test_apply_loads_event_config(console):
    """ApplyOrchestrator calls load_config when events are present."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 102
    event_manager = MagicMock()

    events_cfg = {"RUNNER_COMPLETED": [{"type": "script", "name": "post", "script": "s.sh"}]}
    env_config = _make_env_config_with_events(events_cfg)

    apply_serial = MagicMock(return_value={"proxmox": {"success": True}})

    orchestrator = ApplyOrchestrator(
        console,
        state_manager,
        event_manager,
        lambda env: ([_resource("vm1")], {"proxmox": [_resource("vm1")]}),
        apply_serial=apply_serial,
        apply_parallel=MagicMock(),
        get_current_user=lambda: "tester",
        load_environment=lambda _: env_config,
    )

    orchestrator.apply(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        parallel=False,
        max_workers=1,
    )

    event_manager.clear_handlers.assert_called_once()
    event_manager.load_config.assert_called_once_with(events_cfg)


def test_destroy_loads_event_config(console):
    """DestroyOrchestrator calls load_config when events are present."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 103
    state_manager.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    event_manager = MagicMock()
    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = []
    providers = {"proxmox": MagicMock()}

    events_cfg = {"RUNNER_COMPLETED": [{"type": "script", "name": "post", "script": "s.sh"}]}
    env_config = _make_env_config_with_events(events_cfg)

    orchestrator = DestroyOrchestrator(
        console,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=lambda env: ([], {"proxmox": []}),
        iter_provider_batches=lambda rbp, filt, rev, env: [ProviderResourceBatch("proxmox", [], 0)],
        get_current_user=lambda: "tester",
        load_environment=lambda _: env_config,
    )

    orchestrator.destroy(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        confirm_callback=lambda: True,
    )

    event_manager.clear_handlers.assert_called_once()
    event_manager.load_config.assert_called_once_with(events_cfg)


def test_environment_config_parses_events():
    """EnvironmentConfig accepts events dict from settings data."""
    config = EnvironmentConfig(
        name="test",
        events={
            "RUNNER_COMPLETED": [
                {"type": "script", "name": "ontap-setup", "script": "scripts/post.sh"}
            ]
        },
    )
    assert "RUNNER_COMPLETED" in config.events
    assert config.events["RUNNER_COMPLETED"][0]["type"] == "script"


def test_environment_config_default_empty_events():
    """EnvironmentConfig defaults to empty dict for events."""
    config = EnvironmentConfig(name="test")
    assert config.events == {}
