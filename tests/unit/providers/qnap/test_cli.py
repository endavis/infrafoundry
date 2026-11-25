"""``foundry provider qnap upgrade`` with a fake switch and a fake orchestrator."""

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
from infrafoundry.providers.qnap import cli as qnap_cli
from infrafoundry.providers.qnap import register_cli
from infrafoundry.providers.qnap.client import QnapTimeoutError
from infrafoundry.providers.qnap.components.firmware import QnapFirmwareUpgrader

from .conftest import SETTINGS, firmware
from .update_fake import FakeClock, FakeQnapSwitch

pytestmark = pytest.mark.unit


class Harness:
    def __init__(self, switch: FakeQnapSwitch, resources: list[Any] | None = None) -> None:
        self.switch = switch
        self.events: list[str] = []
        self.lock_error: Exception | None = None
        found = [firmware()] if resources is None else resources
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

    def upgrader(self, client: Any) -> QnapFirmwareUpgrader:
        clock = FakeClock()
        return QnapFirmwareUpgrader(client, sleep=clock.sleep, clock=clock.clock)

    def run(self, *args: str, input: str | None = None) -> Result:
        deps = qnap_cli._UpgradeDeps(
            load_settings=lambda config_dir, env: SETTINGS,
            client=lambda settings: self.switch,
            upgrader=self.upgrader,
        )
        with (
            patch.object(qnap_cli, "_DEPS", deps),
            patch("infrafoundry.cli.main._get_orchestrator", return_value=self.orchestrator),
            patch("infrafoundry.cli.main._load_env_credentials"),
        ):
            return CliRunner().invoke(
                qnap_cli.qnap, ["upgrade", "--env", "dev", *args], input=input
            )


def test_register_cli_lists_upgrade() -> None:
    group = click.Group("qnap")
    register_cli(group)
    assert "upgrade" in group.commands


def test_no_resource_takes_no_lock() -> None:
    harness = Harness(FakeQnapSwitch(), resources=[])
    result = harness.run()
    assert result.exit_code == 0 and "nothing to do" in result.output
    assert harness.events == [] and harness.switch.requests == []


def test_up_to_date_does_not_prompt_or_replan() -> None:
    harness = Harness(FakeQnapSwitch(offer=None))
    result = harness.run()
    assert result.exit_code == 0 and "up to date" in result.output
    assert harness.events == ["lock:0", "unlock"]
    assert "firmware/update/live" not in harness.switch.paths()


def test_declined_prompt_installs_nothing() -> None:
    harness = Harness(FakeQnapSwitch())
    result = harness.run(input="n\n")
    assert result.exit_code == 0 and "Aborted; nothing was changed" in result.output
    assert "firmware/update/live" not in harness.switch.paths()
    assert "plan" not in harness.events


def test_yes_upgrades_then_replans_inside_the_lock() -> None:
    harness = Harness(FakeQnapSwitch())
    result = harness.run("--yes", "--lock-timeout", "5")
    assert result.exit_code == 0, result.output
    assert harness.switch.version == "2.6.0"
    assert harness.events == ["lock:5", "plan", "unlock"]
    harness.orchestrator.plan.assert_called_once_with("dev", provider_filter=["qnap"])
    assert harness.switch.sessions_closed == 1


def test_lock_failure_surfaces() -> None:
    harness = Harness(FakeQnapSwitch())
    harness.lock_error = LockAcquisitionError("dev", "someone", "now", "later")
    result = harness.run("--yes")
    assert result.exit_code != 0 and harness.switch.requests == []


def test_failure_names_step_and_version() -> None:
    result = Harness(FakeQnapSwitch(version_after="2.5.1")).run("--yes")
    assert result.exit_code != 0
    assert "step 'verify'" in result.output and "firmware 2.5.1" in result.output
    assert "rolled back" in result.output


def test_login_failure_does_not_read_the_version_again() -> None:
    from infrafoundry.providers.qnap.client import QnapAuthError

    switch = FakeQnapSwitch()
    harness = Harness(switch)
    original = switch.login
    calls = {"n": 0}

    def login() -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise QnapAuthError("refused")
        original()

    switch.login = login  # type: ignore[method-assign]
    result = harness.run("--yes")
    assert result.exit_code != 0 and "step 'login'" in result.output
    assert "unknown" in result.output


def test_replan_failure_says_the_upgrade_succeeded() -> None:
    harness = Harness(FakeQnapSwitch())
    harness.orchestrator.plan.side_effect = RuntimeError("plan broke")
    result = harness.run("--yes")
    assert (
        result.exit_code != 0 and "the upgrade succeeded, but the re-plan failed" in result.output
    )


def test_skipped_check_exits_non_zero_with_the_reason() -> None:
    harness = Harness(FakeQnapSwitch(dns=False))
    result = harness.run("--yes")
    assert result.exit_code != 0 and "no DNS server" in result.output
    assert "firmware/update/live" not in harness.switch.paths()


def test_failed_check_exits_non_zero_with_the_reason() -> None:
    switch = FakeQnapSwitch()
    switch.check_error = QnapTimeoutError("the switch did not answer in time")
    result = Harness(switch).run("--yes")
    assert result.exit_code != 0 and "update check failed" in result.output
