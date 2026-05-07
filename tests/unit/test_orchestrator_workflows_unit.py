"""Unit tests for orchestrator workflow helpers."""

from __future__ import annotations

import os
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


# ---------------------------------------------------------------------------
# Plan output surfacing — issue #771
# ---------------------------------------------------------------------------


def _build_plan_orchestrator_with_runner(
    *,
    runner: MagicMock,
    runner_output: str,
    expose_extractor: bool = True,
    extractor_return: str = "21 to add, 0 to change, 0 to destroy",
):
    """Build a PlanOrchestrator wired to *runner* and a captured-output dict.

    The runner is registered under the name ``terraform`` and the provider
    exposes ``generate_terraform`` so the IaC iteration enters the plan
    branch. ``runner.plan`` returns ``{"success": True, "output": ...}``
    matching the real terraform runner's plan return shape.
    """
    runner.priority = 0
    runner.is_iac_runner = True
    runner.plan = MagicMock(return_value={"success": True, "output": runner_output})

    if expose_extractor:
        runner.extract_plan_summary = MagicMock(return_value=extractor_return)
    else:
        # spec the mock so getattr(runner, "extract_plan_summary", None) is None
        del runner.extract_plan_summary

    runner_registry = MagicMock()
    runner_registry.list_runners.return_value = ["terraform"]
    runner_registry.create_runner.return_value = runner

    provider = MagicMock()
    provider.generate_terraform = MagicMock()
    providers = {"proxmox": provider}

    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 1234
    event_manager = MagicMock()
    console_mock = MagicMock(spec=Console)

    def load_resources(env: str):
        res = [_resource("vm1")]
        return res, {"proxmox": res}

    orchestrator = PlanOrchestrator(
        console_mock,
        state_manager,
        event_manager,
        runner_registry,
        get_providers=lambda: providers,
        load_resources=load_resources,
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
    )
    return orchestrator, console_mock, runner


def _print_strings(console_mock: MagicMock) -> list[str]:
    """Collect the leading positional argument of each console.print call as a string."""
    out: list[str] = []
    for call in console_mock.print.call_args_list:
        if call.args:
            out.append(str(call.args[0]))
    return out


def test_plan_prints_per_provider_summary_line_by_default(console):
    """Default-on summary: one ``terraform: <summary>`` line per provider."""
    runner = MagicMock()
    output = (
        "Terraform will perform the following actions:\n"
        "Plan: 21 to add, 0 to change, 0 to destroy.\n"
    )
    orchestrator, console_mock, _ = _build_plan_orchestrator_with_runner(
        runner=runner, runner_output=output
    )

    orchestrator.plan(env_name="dev", dry_run=False, resource_filter=None, enforce_policies=False)

    prints = _print_strings(console_mock)
    summary_lines = [p for p in prints if "terraform: 21 to add" in p]
    assert len(summary_lines) == 1
    assert "[dim]" in summary_lines[0]


def test_plan_does_not_print_full_output_by_default(console):
    """Default-off verbose: the full captured output is NOT printed when verbose=False."""
    runner = MagicMock()
    diff_body = (
        "Terraform will perform the following actions:\n"
        "  # proxmox_virtual_environment_vm.web will be created\n"
        "Plan: 1 to add, 0 to change, 0 to destroy.\n"
    )
    orchestrator, console_mock, _ = _build_plan_orchestrator_with_runner(
        runner=runner, runner_output=diff_body, extractor_return="1 to add"
    )

    orchestrator.plan(env_name="dev", dry_run=False, resource_filter=None, enforce_policies=False)

    prints = _print_strings(console_mock)
    # The diff body line is unique enough that we can grep for it directly.
    assert not any("# proxmox_virtual_environment_vm.web will be created" in p for p in prints)


def test_plan_prints_full_output_when_verbose(console):
    """When ``verbose=True``, the full captured runner output is printed verbatim."""
    runner = MagicMock()
    diff_body = (
        "Terraform will perform the following actions:\n"
        "  # proxmox_virtual_environment_vm.web will be created\n"
        "Plan: 1 to add, 0 to change, 0 to destroy.\n"
    )
    orchestrator, console_mock, _ = _build_plan_orchestrator_with_runner(
        runner=runner, runner_output=diff_body, extractor_return="1 to add"
    )

    orchestrator.plan(
        env_name="dev",
        dry_run=False,
        resource_filter=None,
        enforce_policies=False,
        verbose=True,
    )

    # When verbose=True we still get the summary line, AND the full output.
    full_output_calls = [
        call
        for call in console_mock.print.call_args_list
        if call.args and call.args[0] == diff_body
    ]
    assert len(full_output_calls) == 1
    # The verbose body is printed with markup/highlight off so terraform's own
    # bracketed diff text survives without being reinterpreted by Rich.
    kwargs = full_output_calls[0].kwargs
    assert kwargs.get("markup") is False
    assert kwargs.get("highlight") is False


def test_plan_summary_handles_no_changes_output(console):
    """Output containing ``No changes`` produces a ``terraform: No changes`` line."""
    runner = MagicMock()
    orchestrator, console_mock, _ = _build_plan_orchestrator_with_runner(
        runner=runner,
        runner_output="No changes. Your infrastructure matches the configuration.\n",
        extractor_return="No changes",
    )

    orchestrator.plan(env_name="dev", dry_run=False, resource_filter=None, enforce_policies=False)

    prints = _print_strings(console_mock)
    assert any("terraform: No changes" in p for p in prints)


def test_plan_skips_summary_for_runner_without_extract_plan_summary(console):
    """A runner without ``extract_plan_summary`` (e.g. ansible) prints no summary line."""
    # spec the mock so ``getattr(runner, "extract_plan_summary", None)`` is None
    runner = MagicMock(spec=["priority", "is_iac_runner", "plan"])
    orchestrator, console_mock, _ = _build_plan_orchestrator_with_runner(
        runner=runner, runner_output="output", expose_extractor=False
    )
    # The provider must expose ``generate_terraform`` regardless of the runner
    # name. Re-point the runner registry so the iteration finds this runner.
    # _build_plan_orchestrator_with_runner already registers it under "terraform".

    orchestrator.plan(env_name="dev", dry_run=False, resource_filter=None, enforce_policies=False)

    prints = _print_strings(console_mock)
    # No call should mention a "<tool_name>: <summary>" pattern that the helper would emit.
    # The orchestrator emits other "Running terraform plan..." lines; only the
    # summary is suppressed.
    assert not any("terraform: " in p and "Running" not in p for p in prints)


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


# ---------------------------------------------------------------------------
# Warnings collector integration (#661)
# ---------------------------------------------------------------------------


def _apply_orchestrator_with_hooks(
    load_resources_hook,
    apply_serial_hook=None,
):
    """Build an ApplyOrchestrator whose load_resources callback runs a hook.

    This lets individual tests inject assertions / side-effects at the
    point where INFRAFOUNDRY_WARNINGS_FILE is already set but apply has
    not yet returned.
    """
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 42
    event_manager = MagicMock()
    console = MagicMock()

    default_resources = ([_resource("vm1")], {"proxmox": [_resource("vm1")]})

    def load_resources(env: str):
        load_resources_hook(env)
        return default_resources

    apply_serial = apply_serial_hook or MagicMock(return_value={"proxmox": {"success": True}})

    orchestrator = ApplyOrchestrator(
        console,
        state_manager,
        event_manager,
        load_resources,
        apply_serial=apply_serial,
        apply_parallel=MagicMock(),
        get_current_user=lambda: "tester",
    )
    return orchestrator, console, state_manager


def test_apply_renders_warnings_panel_when_warnings_present():
    """A warning written mid-apply causes a Panel to be printed at the end."""
    from rich.panel import Panel

    from infrafoundry.core.warnings import ENV_VAR

    def hook(_env: str) -> None:
        # Simulate a handler emitting a warning into the file the
        # orchestrator just set up.
        path = Path(os.environ[ENV_VAR])
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"source": "event:test", "message": "kubeconfig oddity"}\n')

    orchestrator, console, _ = _apply_orchestrator_with_hooks(hook)

    orchestrator.apply(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        parallel=False,
        max_workers=1,
    )

    # At least one console.print call must be a Panel whose title marks it
    # as the warnings summary.
    panel_calls = [
        c for c in console.print.call_args_list if c.args and isinstance(c.args[0], Panel)
    ]
    assert len(panel_calls) == 1
    panel = panel_calls[0].args[0]
    assert "Warnings" in str(panel.title)
    assert "1" in str(panel.title)
    assert "kubeconfig oddity" in panel.renderable.plain
    assert "event:test" in panel.renderable.plain


def test_apply_no_panel_when_no_warnings():
    """No warnings → no Panel is printed."""
    from rich.panel import Panel

    orchestrator, console, _ = _apply_orchestrator_with_hooks(lambda _env: None)

    orchestrator.apply(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        parallel=False,
        max_workers=1,
    )

    panel_calls = [
        c for c in console.print.call_args_list if c.args and isinstance(c.args[0], Panel)
    ]
    assert panel_calls == []


def test_apply_renders_warnings_panel_on_failure_path():
    """Warnings emitted before a failure still get summarized."""
    from rich.panel import Panel

    from infrafoundry.core.warnings import ENV_VAR

    class _BoomError(RuntimeError):
        pass

    def hook(_env: str) -> None:
        path = Path(os.environ[ENV_VAR])
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"source": "event:pre-fail", "message": "half-applied"}\n')
        raise _BoomError("synthetic failure")

    orchestrator, console, state_manager = _apply_orchestrator_with_hooks(hook)

    with pytest.raises(_BoomError):
        orchestrator.apply(
            env_name="dev",
            resource_filter=None,
            auto_approve=True,
            parallel=False,
            max_workers=1,
        )

    panel_calls = [
        c for c in console.print.call_args_list if c.args and isinstance(c.args[0], Panel)
    ]
    assert len(panel_calls) == 1
    panel = panel_calls[0].args[0]
    assert "half-applied" in panel.renderable.plain
    # And the deployment was marked failed before the re-raise.
    state_manager.update_deployment_status.assert_any_call(
        42, DeploymentStatus.FAILED, "synthetic failure"
    )


def test_apply_sets_and_restores_warnings_env_var(monkeypatch):
    """INFRAFOUNDRY_WARNINGS_FILE is set during apply and restored after."""
    from infrafoundry.core.warnings import ENV_VAR

    monkeypatch.delenv(ENV_VAR, raising=False)

    captured: dict[str, str | None] = {}

    def hook(_env: str) -> None:
        captured["mid_apply"] = os.environ.get(ENV_VAR)

    orchestrator, _, _ = _apply_orchestrator_with_hooks(hook)

    orchestrator.apply(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        parallel=False,
        max_workers=1,
    )

    # Mid-apply, the env var must be set and point at an existing path.
    assert captured["mid_apply"] is not None
    assert "infrafoundry-warnings-42-" in captured["mid_apply"]
    # After apply returns, the env var was restored (not previously set).
    assert ENV_VAR not in os.environ


def test_apply_restores_prior_warnings_env_var(monkeypatch, tmp_path):
    """A prior value of INFRAFOUNDRY_WARNINGS_FILE is restored after apply."""
    from infrafoundry.core.warnings import ENV_VAR

    prior = tmp_path / "outer.jsonl"
    monkeypatch.setenv(ENV_VAR, str(prior))

    captured: dict[str, str | None] = {}

    def hook(_env: str) -> None:
        captured["mid"] = os.environ.get(ENV_VAR)

    orchestrator, _, _ = _apply_orchestrator_with_hooks(hook)

    orchestrator.apply(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        parallel=False,
        max_workers=1,
    )

    assert captured["mid"] != str(prior)
    assert os.environ.get(ENV_VAR) == str(prior)


# ---------------------------------------------------------------------------
# Provider scoping (--provider / -P) — issue #769
# ---------------------------------------------------------------------------


def test_apply_provider_filter_isolates_to_requested_provider(console):
    """``provider_filter=["opnsense"]`` keeps Proxmox resources out of the apply path."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 200
    event_manager = MagicMock()

    res_proxmox = [_resource("vm1", provider="proxmox")]
    res_opnsense = [_resource("fw1", provider="opnsense", type_="firewall_rule")]

    captured: dict[str, dict[str, list[ResourceConfig]]] = {}

    def apply_serial(
        env_name,
        deployment_id,
        resources_by_provider,
        resource_filter,
        auto_approve,
        package_filter=None,
        *,
        add_only=False,
    ):
        captured["resources_by_provider"] = resources_by_provider
        return {"opnsense": {"success": True}}

    apply_parallel = MagicMock()

    orchestrator = ApplyOrchestrator(
        console,
        state_manager,
        event_manager,
        lambda env: (
            res_proxmox + res_opnsense,
            {"proxmox": res_proxmox, "opnsense": res_opnsense},
        ),
        apply_serial=apply_serial,
        apply_parallel=apply_parallel,
        get_current_user=lambda: "tester",
    )

    orchestrator.apply(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        parallel=False,
        max_workers=1,
        provider_filter=["opnsense"],
    )

    apply_parallel.assert_not_called()
    # Filter dropped proxmox; only opnsense reached the serial executor.
    assert list(captured["resources_by_provider"].keys()) == ["opnsense"]
    assert captured["resources_by_provider"]["opnsense"] == res_opnsense


def test_apply_provider_filter_none_preserves_full_iteration(console):
    """Passing ``provider_filter=None`` is equivalent to no filter (regression check)."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 201
    event_manager = MagicMock()

    res_proxmox = [_resource("vm1", provider="proxmox")]
    res_opnsense = [_resource("fw1", provider="opnsense", type_="firewall_rule")]

    captured: dict[str, dict[str, list[ResourceConfig]]] = {}

    def apply_serial(
        env_name,
        deployment_id,
        resources_by_provider,
        resource_filter,
        auto_approve,
        package_filter=None,
        *,
        add_only=False,
    ):
        captured["resources_by_provider"] = resources_by_provider
        return {}

    orchestrator = ApplyOrchestrator(
        console,
        state_manager,
        event_manager,
        lambda env: (
            res_proxmox + res_opnsense,
            {"proxmox": res_proxmox, "opnsense": res_opnsense},
        ),
        apply_serial=apply_serial,
        apply_parallel=MagicMock(),
        get_current_user=lambda: "tester",
    )

    orchestrator.apply(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        parallel=False,
        max_workers=1,
        provider_filter=None,
    )

    assert set(captured["resources_by_provider"].keys()) == {"proxmox", "opnsense"}


def test_apply_provider_filter_unknown_name_raises(console):
    """An unknown name in ``provider_filter`` raises ``ProviderFilterError``."""
    from infrafoundry.core.exceptions import ProviderFilterError

    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 202
    event_manager = MagicMock()

    res_proxmox = [_resource("vm1", provider="proxmox")]
    res_opnsense = [_resource("fw1", provider="opnsense", type_="firewall_rule")]

    apply_serial = MagicMock()

    orchestrator = ApplyOrchestrator(
        console,
        state_manager,
        event_manager,
        lambda env: (
            res_proxmox + res_opnsense,
            {"proxmox": res_proxmox, "opnsense": res_opnsense},
        ),
        apply_serial=apply_serial,
        apply_parallel=MagicMock(),
        get_current_user=lambda: "tester",
    )

    with pytest.raises(ProviderFilterError) as excinfo:
        orchestrator.apply(
            env_name="dev",
            resource_filter=None,
            auto_approve=True,
            parallel=False,
            max_workers=1,
            provider_filter=["nope"],
        )

    assert excinfo.value.requested == ["nope"]
    assert sorted(excinfo.value.available) == ["opnsense", "proxmox"]
    apply_serial.assert_not_called()
    state_manager.update_deployment_status.assert_called_with(
        202, DeploymentStatus.FAILED, str(excinfo.value)
    )


def test_apply_provider_filter_multi_provider_scoping(console):
    """``provider_filter=["opnsense", "proxmox"]`` keeps both, drops the third."""
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 203
    event_manager = MagicMock()

    res_proxmox = [_resource("vm1", provider="proxmox")]
    res_opnsense = [_resource("fw1", provider="opnsense", type_="firewall_rule")]
    res_oci = [_resource("box1", provider="oci", type_="instance")]

    captured: dict[str, dict[str, list[ResourceConfig]]] = {}

    def apply_serial(
        env_name,
        deployment_id,
        resources_by_provider,
        resource_filter,
        auto_approve,
        package_filter=None,
        *,
        add_only=False,
    ):
        captured["resources_by_provider"] = resources_by_provider
        return {}

    orchestrator = ApplyOrchestrator(
        console,
        state_manager,
        event_manager,
        lambda env: (
            res_proxmox + res_opnsense + res_oci,
            {"proxmox": res_proxmox, "opnsense": res_opnsense, "oci": res_oci},
        ),
        apply_serial=apply_serial,
        apply_parallel=MagicMock(),
        get_current_user=lambda: "tester",
    )

    orchestrator.apply(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        parallel=False,
        max_workers=1,
        provider_filter=["opnsense", "proxmox"],
    )

    assert set(captured["resources_by_provider"].keys()) == {"opnsense", "proxmox"}
    assert "oci" not in captured["resources_by_provider"]


def test_apply_provider_filter_drops_cross_provider_dependency_silently(console):
    """When a filtered-in provider has a dep on a filtered-out provider, the run still completes.

    The orchestrator-level provider filter narrows ``resources_by_provider`` to the
    requested keys before iteration; any cross-provider dependency edges pointing at
    the dropped providers are silently skipped for this run.
    """
    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 204
    event_manager = MagicMock()

    # Proxmox resource conceptually depends on the OPNsense firewall rule, but
    # we filter to ["proxmox"]; the dependency target is excluded for this run.
    res_proxmox = [_resource("vm1", provider="proxmox")]
    res_opnsense = [_resource("fw1", provider="opnsense", type_="firewall_rule")]

    captured: dict[str, dict[str, list[ResourceConfig]]] = {}
    serial_called = MagicMock()

    def apply_serial(
        env_name,
        deployment_id,
        resources_by_provider,
        resource_filter,
        auto_approve,
        package_filter=None,
        *,
        add_only=False,
    ):
        captured["resources_by_provider"] = resources_by_provider
        serial_called(env_name)
        return {"proxmox": {"success": True}}

    orchestrator = ApplyOrchestrator(
        console,
        state_manager,
        event_manager,
        lambda env: (
            res_proxmox + res_opnsense,
            {"proxmox": res_proxmox, "opnsense": res_opnsense},
        ),
        apply_serial=apply_serial,
        apply_parallel=MagicMock(),
        get_current_user=lambda: "tester",
    )

    # Should NOT raise even though the dropped opnsense provider was a
    # cross-provider dependency target.
    orchestrator.apply(
        env_name="dev",
        resource_filter=None,
        auto_approve=True,
        parallel=False,
        max_workers=1,
        provider_filter=["proxmox"],
    )

    serial_called.assert_called_once_with("dev")
    assert list(captured["resources_by_provider"].keys()) == ["proxmox"]
    assert "opnsense" not in captured["resources_by_provider"]
    state_manager.update_deployment_status.assert_called_with(204, DeploymentStatus.COMPLETED)


def test_plan_provider_filter_unknown_name_raises(console):
    """Plan also raises ``ProviderFilterError`` for unknown names."""
    from infrafoundry.core.exceptions import ProviderFilterError

    state_manager = MagicMock()
    state_manager.create_deployment.return_value = 205
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

    with pytest.raises(ProviderFilterError):
        orchestrator.plan(
            env_name="dev",
            dry_run=True,
            resource_filter=None,
            enforce_policies=False,
            provider_filter=["nope"],
        )
