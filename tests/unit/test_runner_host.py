"""Tests for HostRunner."""

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.runners.host_runner import AUTH_ENV_VAR, HostRunner
from infrafoundry.providers.host import HostProvider
from tests.unit.providers.host.conftest import (
    AUTH_REF,
    SECRET_VALUE,
    host,
    make_env,
    tailscale_block,
)

PATCH_RUN = "infrafoundry.core.runners.host_runner.subprocess.run"


@pytest.fixture
def runner() -> HostRunner:
    return HostRunner()


@pytest.fixture
def provider(tmp_path: Path) -> HostProvider:
    (tmp_path / "envs").mkdir()
    (tmp_path / "playbooks").mkdir()
    (tmp_path / "playbooks" / "base.yml").write_text("---\n")
    p = HostProvider(tmp_path / "envs", tmp_path / "output")
    p.set_environment("test")
    return p


def _generate(provider: HostProvider, *resources: ResourceConfig) -> None:
    provider.generate_host_ansible(list(resources))


def _ok() -> MagicMock:
    return MagicMock(returncode=0)


@pytest.fixture(autouse=True)
def _ansible_present() -> Any:
    with patch("shutil.which", return_value="/usr/bin/ansible-playbook"):
        yield


def test_runner_identity(runner: HostRunner) -> None:
    assert runner.tool_name == "host_ansible"
    assert runner.is_iac_runner
    assert runner.initialize(Path("."))["success"]


def test_non_host_provider_is_skipped_without_subprocess(runner: HostRunner) -> None:
    other = MagicMock()
    other.name = "aws"
    with patch(PATCH_RUN) as run:
        assert runner.plan(other)["has_changes"] is False
        applied = runner.apply(other)
        assert applied["success"] and applied["resource_outcomes"] == []
        assert runner.destroy(other, resource_names=["x"])["resources_destroyed"] == 0
    run.assert_not_called()


def test_plan_runs_no_subprocess(runner: HostRunner, provider: HostProvider) -> None:
    _generate(provider, host("a"), host("b"))
    with patch(PATCH_RUN) as run:
        result = runner.plan(provider)
    run.assert_not_called()
    assert result["has_changes"] is True
    assert "2 existing host(s)" in result["changes_summary"]


def test_plan_without_hosts(runner: HostRunner, provider: HostProvider) -> None:
    assert runner.plan(provider)["has_changes"] is False


def test_apply_argv_cwd_and_create_outcome(runner: HostRunner, provider: HostProvider) -> None:
    _generate(provider, host("a", ansible={"playbooks": ["playbooks/base.yml"]}))
    with patch(PATCH_RUN, return_value=_ok()) as run:
        result = runner.apply(provider)
    argv = run.call_args.args[0]
    assert argv == [
        "/usr/bin/ansible-playbook",
        "-i",
        "inventory.yml",
        "--limit",
        "a",
        str((provider.repo_root / "playbooks" / "base.yml").resolve()),
    ]
    assert run.call_args.kwargs["cwd"] == provider.ansible_dir
    assert run.call_args.kwargs["env"] is None
    assert result["resources_created"] == 1
    outcome = result["resource_outcomes"][0]
    assert (outcome.address, outcome.action, outcome.resource_name) == ("host.a", "create", "a")


def test_apply_reports_update_for_a_managed_host(
    runner: HostRunner, provider: HostProvider
) -> None:
    _generate(provider, host("a"), host("b"))
    managed = {"host": [ResourceConfig(name="a", type="host", provider="host", config={})]}
    result = runner.apply(provider, managed_resources=managed)
    actions = {o.resource_name: o.action for o in result["resource_outcomes"]}
    assert actions == {"a": "update", "b": "create"}
    assert result["resources_updated"] == 1
    assert result["resources_created"] == 1


def test_apply_target_filter(runner: HostRunner, provider: HostProvider) -> None:
    _generate(provider, host("a", ansible={"playbooks": ["playbooks/base.yml"]}), host("b"))
    with patch(PATCH_RUN, return_value=_ok()) as run:
        result = runner.apply(provider, target_resources=["a"], resource_names=["a", "b"])
    assert run.call_count == 1
    assert [o.resource_name for o in result["resource_outcomes"]] == ["a"]


def test_apply_without_playbooks_still_reports_the_host(
    runner: HostRunner, provider: HostProvider
) -> None:
    _generate(provider, host("a"))
    with patch(PATCH_RUN) as run:
        result = runner.apply(provider)
    run.assert_not_called()
    assert result["resource_outcomes"][0].action == "create"


def test_secret_env_var_only_on_the_enrollment_run(
    runner: HostRunner, provider: HostProvider
) -> None:
    _generate(
        provider,
        host("a", tailscale=tailscale_block(), ansible={"playbooks": ["playbooks/base.yml"]}),
    )
    env = make_env({"tailscale": {"oauth_client_secret": SECRET_VALUE}})
    with (
        patch.object(HostProvider, "_load_environment_config", return_value=env),
        patch(PATCH_RUN, return_value=_ok()) as run,
    ):
        runner.apply(provider)
    first, second = run.call_args_list
    assert first.kwargs["env"][AUTH_ENV_VAR] == SECRET_VALUE
    assert first.args[0][-1].endswith("tailscale.yml")
    assert second.kwargs["env"] is None
    assert SECRET_VALUE not in " ".join(first.args[0] + second.args[0])


def test_failure_message_has_no_secret(runner: HostRunner, provider: HostProvider) -> None:
    _generate(provider, host("a", tailscale=tailscale_block()))
    env = make_env({"tailscale": {"oauth_client_secret": SECRET_VALUE}})
    with (
        patch.object(HostProvider, "_load_environment_config", return_value=env),
        patch(PATCH_RUN, return_value=MagicMock(returncode=2)),
    ):
        result = runner.apply(provider)
    assert result["success"] is False
    assert "host 'a'" in result["error"]
    assert "exit 2" in result["error"]
    assert SECRET_VALUE not in result["error"]


def test_unresolvable_secret_fails_without_running(
    runner: HostRunner, provider: HostProvider
) -> None:
    _generate(provider, host("a", tailscale=tailscale_block()))
    env = make_env({})
    with (
        patch.object(HostProvider, "_load_environment_config", return_value=env),
        patch(PATCH_RUN) as run,
    ):
        result = runner.apply(provider)
    run.assert_not_called()
    assert result["success"] is False
    assert AUTH_REF in result["error"]


def test_failure_stops_before_later_hosts(runner: HostRunner, provider: HostProvider) -> None:
    pb = {"playbooks": ["playbooks/base.yml"]}
    _generate(provider, host("a", ansible=pb), host("b", ansible=pb))
    with patch(PATCH_RUN, return_value=MagicMock(returncode=1)) as run:
        result = runner.apply(provider)
    assert run.call_count == 1
    assert result["success"] is False


def test_missing_ansible_playbook(runner: HostRunner, provider: HostProvider) -> None:
    _generate(provider, host("a"))
    with patch("shutil.which", return_value=None):
        result = runner.apply(provider)
    assert result["success"] is False
    assert "not found" in result["error"]


def test_ansible_vanishing_between_check_and_run(
    runner: HostRunner, provider: HostProvider
) -> None:
    _generate(provider, host("a", ansible={"playbooks": ["playbooks/base.yml"]}))
    with patch(PATCH_RUN, side_effect=FileNotFoundError):
        result = runner.apply(provider)
    assert result["success"] is False


def test_destroy_reports_delete_outcomes_and_never_runs_anything(
    runner: HostRunner, provider: HostProvider
) -> None:
    with patch(PATCH_RUN) as run, patch.object(subprocess, "Popen") as popen:
        result = runner.destroy(provider, resource_names=["a", "b"], target_resources=None)
    run.assert_not_called()
    popen.assert_not_called()
    assert result["resources_destroyed"] == 2
    assert [(o.address, o.action) for o in result["resource_outcomes"]] == [
        ("host.a", "delete"),
        ("host.b", "delete"),
    ]


def test_destroy_prefers_targets(runner: HostRunner, provider: HostProvider) -> None:
    result = runner.destroy(provider, resource_names=["a", "b"], target_resources=["b"])
    assert [o.resource_name for o in result["resource_outcomes"]] == ["b"]
