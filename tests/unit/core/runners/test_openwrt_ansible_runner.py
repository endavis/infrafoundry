"""Tests for OpenWrtAnsibleRunner (ADR-0028)."""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from rich.console import Console

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_registry_service import ProviderRegistryService
from infrafoundry.core.runners.openwrt_ansible_runner import OpenWrtAnsibleRunner
from infrafoundry.providers.openwrt import OpenWrtProvider
from infrafoundry.providers.openwrt.settings import OpenWrtSettings
from tests.unit.providers.openwrt.conftest import (
    doc,
    fixture_text,
    lan,
    printer,
    task,
    web,
)

SETTINGS = OpenWrtSettings(address="192.0.2.2")
ANSIBLE = "/usr/bin/ansible-playbook"


class FakeAnsible:
    """Stands in for ``_run``: returns queued stdout documents and records the calls."""

    def __init__(self, *outputs: str, returncode: int = 0, stderr: str = "") -> None:
        self.outputs = list(outputs)
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[tuple[list[str], Path, dict[str, str]]] = []

    def __call__(
        self, argv: list[str], cwd: Path, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((argv, cwd, env))
        stdout = self.outputs.pop(0) if self.outputs else ""
        return subprocess.CompletedProcess(argv, self.returncode, stdout, self.stderr)


def _provider(tmp_path: Path) -> OpenWrtProvider:
    provider = OpenWrtProvider(tmp_path, tmp_path / "generated")
    provider.set_environment("test")
    return provider


def _go(
    action: str,
    provider: OpenWrtProvider,
    fake: FakeAnsible,
    resources: list[ResourceConfig],
    *,
    which: str | None = ANSIBLE,
    settings: OpenWrtSettings = SETTINGS,
    **kwargs: Any,
) -> Any:
    runner = OpenWrtAnsibleRunner(Console(quiet=True))
    with (
        patch("infrafoundry.core.runners.openwrt_ansible_runner._run", fake),
        patch("infrafoundry.core.runners.openwrt_ansible_runner.shutil.which", return_value=which),
        patch("infrafoundry.providers.openwrt.load_settings", return_value=settings),
        patch("infrafoundry.providers.openwrt.components.management.resolve_ipv4", lambda h: h),
        patch.object(OpenWrtAnsibleRunner, "_load_resources", return_value=resources),
    ):
        return getattr(runner, action)(provider, **kwargs)


def test_runner_properties() -> None:
    runner = OpenWrtAnsibleRunner()
    assert (runner.tool_name, runner.is_iac_runner, runner.priority) == (
        "openwrt_ansible",
        True,
        -10,
    )
    assert runner.initialize(Path("."))["success"]
    assert runner.get_resource_ids(SimpleNamespace(name="openwrt")) == {}  # type: ignore[arg-type]


def test_availability_follows_the_binary_on_path() -> None:
    runner = OpenWrtAnsibleRunner()
    with patch("infrafoundry.core.runners.openwrt_ansible_runner.shutil.which", return_value=None):
        assert not runner.is_available()
        with pytest.raises(FileNotFoundError, match="ansible-playbook"):
            _ = runner.tool_path
    with patch("infrafoundry.core.runners.openwrt_ansible_runner.shutil.which", return_value="/x"):
        assert runner.is_available()
        assert runner.tool_path == "/x"


def test_registered_with_the_default_runners(tmp_path: Path) -> None:
    service = ProviderRegistryService(
        base_output_dir=tmp_path,
        config_manager=SimpleNamespace(),  # type: ignore[arg-type]
    )
    assert "openwrt_ansible" in service.runner_registry.list_runners()


def test_other_providers_are_skipped() -> None:
    runner = OpenWrtAnsibleRunner()
    other = SimpleNamespace(name="mikrotik")
    expected = {"success": True, "has_changes": False, "changes_summary": "No changes"}
    assert runner.plan(other, env_name="x") == expected  # type: ignore[arg-type]
    assert runner.apply(other)["success"]  # type: ignore[arg-type]
    assert runner.destroy(other)["success"]  # type: ignore[arg-type]
    assert not runner.needs_managed_dispatch(other, {"dhcp.host": [printer()]})  # type: ignore[arg-type]


def test_plan_runs_check_and_diff_with_the_json_callback(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    fake = FakeAnsible(fixture_text("check_clean"))
    result = _go("plan", provider, fake, [lan(), printer(), web()])
    assert result["success"]
    assert not result["has_changes"]
    argv, cwd, env = fake.calls[0]
    assert argv == [ANSIBLE, "-i", "inventory.yml", "openwrt.yml", "--check", "--diff"]
    assert cwd == provider.ansible_dir
    assert env["ANSIBLE_STDOUT_CALLBACK"] == "ansible.posix.json"


def test_host_key_checking_is_forced_on_over_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANSIBLE_HOST_KEY_CHECKING", "False")
    fake = FakeAnsible(fixture_text("check_clean"))
    _go("plan", _provider(tmp_path), fake, [lan()])
    _argv, _cwd, env = fake.calls[0]
    assert env["ANSIBLE_HOST_KEY_CHECKING"] == "True"


def test_plan_reports_changes_and_counts(tmp_path: Path) -> None:
    fake = FakeAnsible(fixture_text("check_changed"))
    result = _go("plan", _provider(tmp_path), fake, [lan(), printer(), web()])
    assert result["has_changes"]
    assert "create: 2" in result["changes_summary"]
    assert '"create": 2' in result["output"]


def test_plan_with_targets_passes_tags(tmp_path: Path) -> None:
    fake = FakeAnsible(fixture_text("check_clean"))
    _go("plan", _provider(tmp_path), fake, [lan(), printer(), web()], target_resources=["web"])
    argv = fake.calls[0][0]
    assert argv[argv.index("--tags") + 1] == "web"


def test_a_refused_plan_fails_with_the_refusal_list(tmp_path: Path) -> None:
    fake = FakeAnsible(fixture_text("check_management"))
    result = _go("plan", _provider(tmp_path), fake, [lan(ipaddr="198.51.100.1")])
    assert not result["success"]
    assert "refused" in result["error"]
    assert "confirm_management_change" in result["error"]


def test_a_failed_check_is_reported(tmp_path: Path) -> None:
    fake = FakeAnsible(fixture_text("lease_duplicate"))
    result = _go("plan", _provider(tmp_path), fake, [printer()])
    assert not result["success"]
    assert "more than one dhcp host section" in result["error"]


def test_a_missing_binary_gives_a_clean_error(tmp_path: Path) -> None:
    fake = FakeAnsible()
    result = _go("plan", _provider(tmp_path), fake, [lan()], which=None)
    assert not result["success"]
    assert "ansible-playbook not found on PATH" in result["error"]
    assert fake.calls == []


def test_no_output_gives_an_error_with_the_stderr_tail(tmp_path: Path) -> None:
    fake = FakeAnsible("", returncode=4, stderr="ERROR! the collection is missing")
    result = _go("plan", _provider(tmp_path), fake, [lan()])
    assert not result["success"]
    assert "exited 4 with no output" in result["error"]
    assert "collection is missing" in result["error"]


def test_malformed_output_is_a_failure_not_an_exception(tmp_path: Path) -> None:
    result = _go("plan", _provider(tmp_path), FakeAnsible("not json"), [lan()])
    assert not result["success"]
    assert "JSON" in result["error"]


def test_invalid_resources_are_a_failure(tmp_path: Path) -> None:
    result = _go("plan", _provider(tmp_path), FakeAnsible(), [lan(bogus=1)])
    assert not result["success"]
    assert "unknown field" in result["error"]


def test_plan_without_an_environment_fails_cleanly(tmp_path: Path) -> None:
    provider = OpenWrtProvider(tmp_path, tmp_path / "generated")
    result = _go("plan", provider, FakeAnsible(), [lan()])
    assert not result["success"]
    assert "set_environment" in result["error"]


def test_apply_checks_first_then_runs_for_real(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    fake = FakeAnsible(fixture_text("check_changed"), fixture_text("apply_ok"))
    result = _go("apply", provider, fake, [lan(), printer(), web()])
    assert result["success"]
    assert result["resources_created"] == 2
    check_argv, real_argv = fake.calls[0][0], fake.calls[1][0]
    assert "--check" in check_argv and "--diff" in check_argv
    assert "--check" not in real_argv
    assert real_argv[:4] == [ANSIBLE, "-i", "inventory.yml", "openwrt.yml"]
    assert "infrafoundry_reconnect_host" not in " ".join(real_argv)


def test_apply_outcomes_cover_changed_and_adopted_resources(tmp_path: Path) -> None:
    fake = FakeAnsible(fixture_text("check_changed"), fixture_text("apply_ok"))
    result = _go("apply", _provider(tmp_path), fake, [lan(), printer(), web()])
    assert {(o.resource_name, o.action) for o in result["resource_outcomes"]} == {
        ("lan", "create"),
        ("printer", "create"),
        ("web", "create"),
    }
    assert result["resource_outcomes_summary"][0]["address"] == "openwrt_network_interface.lan"


def test_apply_stops_on_refusal_before_the_real_run(tmp_path: Path) -> None:
    fake = FakeAnsible(fixture_text("check_management"), fixture_text("apply_ok"))
    result = _go("apply", _provider(tmp_path), fake, [lan(ipaddr="198.51.100.1")])
    assert not result["success"]
    assert "refused" in result["error"]
    assert len(fake.calls) == 1


def test_apply_passes_the_new_address_to_reconnect(tmp_path: Path) -> None:
    settings = OpenWrtSettings(address="192.0.2.1")
    fake = FakeAnsible(fixture_text("check_management"), doc())
    _go(
        "apply",
        _provider(tmp_path),
        fake,
        [lan(ipaddr="198.51.100.1", confirm_management_change=True)],
        settings=settings,
    )
    real = fake.calls[1][0]
    assert real[real.index("-e") + 1] == "infrafoundry_reconnect_host=198.51.100.1"


def test_a_failed_check_stops_apply(tmp_path: Path) -> None:
    fake = FakeAnsible(fixture_text("lease_duplicate"), doc())
    result = _go("apply", _provider(tmp_path), fake, [printer()])
    assert not result["success"]
    assert len(fake.calls) == 1


def test_a_rollback_failure_mentions_the_automatic_revert(tmp_path: Path) -> None:
    fake = FakeAnsible(fixture_text("check_changed"), fixture_text("apply_rollback"))
    result = _go("apply", _provider(tmp_path), fake, [printer()])
    assert not result["success"]
    assert "reverts it by itself" in result["error"]
    assert "released_resources" not in result


def test_apply_releases_managed_rows_it_deleted(tmp_path: Path) -> None:
    managed = {"dhcp.host": [printer()]}
    check = doc(task("infrafoundry|absent|dhcp.host|printer", changed=True))
    real = doc(task("infrafoundry|absent|dhcp.host|printer", changed=True))
    fake = FakeAnsible(check, real)
    result = _go("apply", _provider(tmp_path), fake, [web()], managed_resources=managed)
    assert result["success"]
    assert result["resources_deleted"] == 1
    assert result["released_resources"] == [{"resource_type": "dhcp.host", "name": "printer"}]


def test_apply_with_targets_never_deletes(tmp_path: Path) -> None:
    managed = {"dhcp.host": [printer()]}
    fake = FakeAnsible(doc(), doc())
    provider = _provider(tmp_path)
    _go("apply", provider, fake, [web()], managed_resources=managed, target_resources=["web"])
    playbook = (provider.ansible_dir / "openwrt.yml").read_text()
    assert "absent" not in playbook


def test_destroy_returns_delete_outcomes(tmp_path: Path) -> None:
    out = doc(
        task("infrafoundry|absent|dhcp.host|printer", changed=True),
        task("infrafoundry|absent|firewall.redirect|web", changed=True),
    )
    fake = FakeAnsible(out)
    result = _go("destroy", _provider(tmp_path), fake, [lan(), printer(), web()])
    assert result["success"]
    assert result["resources_destroyed"] == 3
    assert {(o.resource_name, o.action) for o in result["resource_outcomes"]} == {
        ("printer", "delete"),
        ("web", "delete"),
        ("lan", "delete"),
    }
    assert "--check" not in fake.calls[0][0]


def test_destroy_failure_is_reported(tmp_path: Path) -> None:
    result = _go(
        "destroy", _provider(tmp_path), FakeAnsible(fixture_text("apply_rollback")), [printer()]
    )
    assert not result["success"]
    assert "reverts it by itself" in result["error"]


def test_needs_managed_dispatch_only_for_managed_deletable_rows(tmp_path: Path) -> None:
    runner = OpenWrtAnsibleRunner()
    provider = _provider(tmp_path)
    assert runner.needs_managed_dispatch(provider, {"dhcp.host": [printer()]})
    assert runner.needs_managed_dispatch(provider, {"firewall.redirect": [web()]})
    assert not runner.needs_managed_dispatch(provider, {"network.interface": [lan()]})
    assert not runner.needs_managed_dispatch(provider, {"dhcp.host": []})


def test_parse_plan_for_drift_counts(tmp_path: Path) -> None:
    fake = FakeAnsible(fixture_text("check_changed"))
    runner = OpenWrtAnsibleRunner(Console(quiet=True))
    plan = _go("plan", _provider(tmp_path), fake, [lan(), printer(), web()])
    info = runner.parse_plan_for_drift(plan)
    assert (info["to_add"], info["to_change"], info["to_destroy"]) == (2, 0, 0)
    assert info["has_changes"]


def test_parse_plan_for_drift_handles_failures_and_bad_output() -> None:
    runner = OpenWrtAnsibleRunner()
    failed = runner.parse_plan_for_drift({"success": False, "error": "boom"})
    assert (failed["has_changes"], failed["summary"]) == (False, "boom")
    broken = runner.parse_plan_for_drift({"success": True, "output": "{"})
    assert not broken["has_changes"]


def test_load_resources_reads_only_this_providers_resources(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    mine, theirs = lan(), ResourceConfig(name="v", type="vm", provider="proxmox", config={})
    with patch("infrafoundry.core.config.ConfigManager") as manager:
        manager.return_value.load_environment.return_value = object()
        manager.return_value.get_all_resources_all_providers.return_value = [mine, theirs]
        assert OpenWrtAnsibleRunner._load_resources(provider, "test") == [mine]
        manager.return_value.load_environment.return_value = None
        assert OpenWrtAnsibleRunner._load_resources(provider, "test") == []
    assert OpenWrtAnsibleRunner._load_resources(SimpleNamespace(name="openwrt"), "t") == []  # type: ignore[arg-type]
