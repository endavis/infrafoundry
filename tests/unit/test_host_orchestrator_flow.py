"""Plan and apply of a host through the orchestrator reach the host runner (#1411)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from rich.console import Console

from infrafoundry.core.deployment_executor import DeploymentExecutor
from infrafoundry.core.orchestrator_workflows import (
    PlanOrchestrator,
    ProviderResourceBatch,
    _regenerate_iac_configs,
)
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners.host_runner import HostRunner
from infrafoundry.providers.host import HostProvider
from tests.unit.providers.host.conftest import host

PATCH_RUN = "infrafoundry.core.runners.host_runner.subprocess.run"


@pytest.fixture
def provider(tmp_path: Path) -> HostProvider:
    (tmp_path / "envs").mkdir()
    (tmp_path / "playbooks").mkdir()
    (tmp_path / "playbooks" / "base.yml").write_text("---\n")
    p = HostProvider(tmp_path / "envs", tmp_path / "output")
    p.set_environment("test")
    return p


@pytest.fixture(autouse=True)
def _ansible_present() -> Any:
    with patch("shutil.which", return_value="/usr/bin/ansible-playbook"):
        yield


def _registry() -> MagicMock:
    registry = MagicMock()
    registry.list_runners.return_value = ["host"]
    registry.create_runner.side_effect = lambda name, console=None: HostRunner()
    return registry


def test_plan_generates_inventory_through_orchestrator(provider: HostProvider) -> None:
    resources = [host(ansible={"playbooks": ["playbooks/base.yml"]})]
    providers: dict[str, ProviderBase] = {"host": provider}
    orchestrator = PlanOrchestrator(
        Console(file=MagicMock()),
        MagicMock(),
        MagicMock(),
        _registry(),
        get_providers=lambda: providers,
        load_resources=lambda env: (resources, {"host": resources}),
        iter_provider_batches=lambda rbp, filt, rev, env: [
            ProviderResourceBatch("host", rbp["host"], 1)
        ],
        validate_resources=MagicMock(),
        has_policies=lambda: False,
        check_policies=MagicMock(),
        secret_manager_factory=MagicMock(),
        get_current_user=lambda: "tester",
        fail_on_missing_secrets=False,
        get_runner_priorities=lambda _: {},
    )

    orchestrator.plan(env_name="test", dry_run=False, resource_filter=None, enforce_policies=False)

    inventory = yaml.safe_load((provider.ansible_dir / "inventory.yml").read_text())
    assert "vps-01" in inventory["all"]["hosts"]


def test_apply_runs_playbook_through_executor(provider: HostProvider) -> None:
    resources = [host(ansible={"playbooks": ["playbooks/base.yml"]})]
    registry = _registry()
    console = Console(file=MagicMock())
    runner = HostRunner()
    _regenerate_iac_configs(provider, "host", resources, [("host", runner)], console)

    state = MagicMock()
    state.track_resource.return_value = MagicMock(id=1, terraform_id=None)
    state.get_managed_resources.return_value = []
    executor = DeploymentExecutor(
        runner_registry=registry,
        state_manager=state,
        event_manager=MagicMock(),
        providers={"host": provider},
        console=console,
    )
    with patch(PATCH_RUN, return_value=MagicMock(returncode=0)) as run:
        results = executor.apply_single_provider(
            env_name="test",
            deployment_id=1,
            provider_name="host",
            provider=provider,
            resources=resources,
            auto_approve=True,
        )

    assert results["host"]["success"] is True
    argv = run.call_args.args[0]
    assert argv[-1].endswith("playbooks/base.yml")
    assert argv[argv.index("--limit") + 1] == "vps-01"
