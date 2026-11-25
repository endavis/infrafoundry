"""``foundry provider mikrotik upgrade`` with a fake device and a fake orchestrator."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner, Result

from infrafoundry.core.exceptions import LockAcquisitionError
from infrafoundry.providers.mikrotik import cli as mikrotik_cli
from infrafoundry.providers.mikrotik import register_cli
from infrafoundry.providers.mikrotik.client import RouterOSAPIError
from infrafoundry.providers.mikrotik.components.update import UPDATE_TYPE, RouterOSUpgrader
from infrafoundry.providers.mikrotik.settings import MikroTikSettings

from .conftest import resource
from .update_fake import FakeClock, FakeUpdateDevice

pytestmark = pytest.mark.unit

SETTINGS = MikroTikSettings("https://192.0.2.2", "admin", "pw-example", upgrade_timeout=600)


class Harness:
    def __init__(
        self, device: FakeUpdateDevice, resources: list[Any] | None = None, **config: Any
    ) -> None:
        self.device = device
        self.events: list[str] = []
        self.lock_error: Exception | None = None
        self.upgrade_timeouts: list[int] = []
        found = [resource(UPDATE_TYPE, "ros", **config)] if resources is None else resources
        self.orchestrator = MagicMock()
        manager = self.orchestrator.config_manager
        manager.base_dir = Path("/unused-config-dir")
        manager.get_all_resources_all_providers.return_value = found

        @contextmanager
        def lock(env_name: str, *, timeout: int = 0) -> Iterator[None]:
            if self.lock_error:
                raise self.lock_error
            self.events.append(f"lock:{timeout}")
            yield
            self.events.append("unlock")

        self.orchestrator.environment_lock.side_effect = lock
        self.orchestrator.plan.side_effect = lambda *a, **k: self.events.append("plan")

    def upgrader(self, client: Any) -> RouterOSUpgrader:
        clock = FakeClock()
        inner = RouterOSUpgrader(client, sleep=clock.sleep, clock=clock.clock)
        real = inner.upgrade

        def upgrade(expected: str | None, timeout: int) -> Any:
            self.upgrade_timeouts.append(timeout)
            return real(expected, timeout)

        inner.upgrade = upgrade  # type: ignore[method-assign, assignment]
        return inner

    def run(self, *args: str, input: str | None = None) -> Result:
        deps = mikrotik_cli._UpgradeDeps(
            load_settings=lambda config_dir, env: SETTINGS,
            client=lambda settings: self.device,
            upgrader=self.upgrader,
        )
        with (
            patch.object(mikrotik_cli, "_DEPS", deps),
            patch("infrafoundry.cli.main._get_orchestrator", return_value=self.orchestrator),
            patch("infrafoundry.cli.main._load_env_credentials"),
        ):
            return CliRunner().invoke(
                mikrotik_cli.mikrotik, ["upgrade", "--env", "dev", *args], input=input
            )


def test_register_cli_lists_upgrade() -> None:
    group = click.Group("mikrotik")
    register_cli(group)
    assert "upgrade" in group.commands


def test_no_resource_takes_no_lock() -> None:
    harness = Harness(FakeUpdateDevice(), resources=[])
    result = harness.run()
    assert result.exit_code == 0 and "nothing to do" in result.output
    assert harness.events == [] and harness.device.posts == []


def test_up_to_date_does_not_prompt_or_replan() -> None:
    harness = Harness(FakeUpdateDevice(latest="7.24"))
    result = harness.run()
    assert result.exit_code == 0 and "up to date" in result.output
    assert harness.events == ["lock:0", "unlock"]
    assert harness.device.paths() == ["system/package/update/check-for-updates"]


def test_declined_prompt_writes_nothing() -> None:
    harness = Harness(FakeUpdateDevice())
    result = harness.run(input="n\n")
    assert result.exit_code == 0 and "Aborted; nothing was changed" in result.output
    assert harness.device.paths() == ["system/package/update/check-for-updates"]
    assert "plan" not in harness.events


def test_yes_upgrades_then_replans_inside_the_lock() -> None:
    harness = Harness(FakeUpdateDevice(upgrade_fw="7.25"))
    result = harness.run("--yes", "--lock-timeout", "5")
    assert result.exit_code == 0, result.output
    assert harness.device.installed == "7.25" and harness.device.current_fw == "7.25"
    assert harness.events == ["lock:5", "plan", "unlock"]
    assert harness.upgrade_timeouts == [600]
    harness.orchestrator.plan.assert_called_once_with("dev", provider_filter=["mikrotik"])


def test_lock_failure_surfaces() -> None:
    harness = Harness(FakeUpdateDevice())
    harness.lock_error = LockAcquisitionError("dev", "someone", "now", "later")
    result = harness.run("--yes")
    assert result.exit_code != 0 and harness.device.posts == []


def test_failure_names_step_and_versions() -> None:
    device = FakeUpdateDevice()
    device.version_after = "7.24"
    result = Harness(device).run("--yes")
    assert result.exit_code != 0
    assert "step 'verify-routeros'" in result.output and "RouterOS 7.24" in result.output
    assert "rolled back" in result.output


def test_channel_mismatch_writes_nothing_before_the_prompt() -> None:
    device = FakeUpdateDevice(channel="long-term")
    harness = Harness(device)
    result = harness.run(input="n\n")
    assert "Aborted; nothing was changed" in result.output and "long-term" in result.output
    assert device.posts == []


def test_channel_mismatch_confirmed_sets_then_checks_then_upgrades() -> None:
    device = FakeUpdateDevice(channel="long-term")
    harness = Harness(device)
    result = harness.run(input="y\n")
    assert result.exit_code == 0, result.output
    paths = device.paths()
    assert paths[0] == "system/package/update/set"
    assert paths[1] == "system/package/update/check-for-updates"
    assert "system/package/update/install" in paths and device.channel == "stable"
    assert "plan" in harness.events


def test_channel_mismatch_with_nothing_offered_reports_up_to_date() -> None:
    device = FakeUpdateDevice(channel="long-term", latest="7.24")
    harness = Harness(device)
    result = harness.run("--yes")
    assert result.exit_code == 0 and "Channel switched" in result.output
    assert "system/package/update/install" not in device.paths()


def test_replan_failure_says_upgrade_succeeded() -> None:
    harness = Harness(FakeUpdateDevice())
    harness.orchestrator.plan.side_effect = RuntimeError("plan broke")
    result = harness.run("--yes")
    assert (
        result.exit_code != 0 and "the upgrade succeeded, but the re-plan failed" in result.output
    )


def test_check_error_is_reported() -> None:
    device = FakeUpdateDevice()
    device.errors["system/package/update/check-for-updates"] = RouterOSAPIError("nope", 500)
    result = Harness(device).run("--yes")
    assert result.exit_code != 0
