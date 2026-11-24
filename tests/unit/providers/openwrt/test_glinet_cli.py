"""``foundry provider openwrt upgrade`` with fake deps and a fake orchestrator (#1655)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner, Result

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import LockAcquisitionError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.openwrt import register_cli
from infrafoundry.providers.openwrt.glinet import cli as glinet_cli
from infrafoundry.providers.openwrt.glinet.firmware import FIRMWARE_TYPE, FirmwareUpgradeError
from infrafoundry.providers.openwrt.glinet.settings import GlinetWebSettings

pytestmark = pytest.mark.unit

PASSWORD = "cli-password-example"
SID = "sid-cli-example"
ADDRESSES = {"openwrt": "192.0.2.2", "openwrt@travel": "198.51.100.2"}
DEVICES = {
    "primary": "office",
    "devices": {
        "office": {"address": "192.0.2.2"},
        "travel": {"address": "198.51.100.2"},
    },
}


def _firmware(provider: str) -> ResourceConfig:
    return ResourceConfig(name="fw", type=FIRMWARE_TYPE, provider=provider, config={})


class FakeClient:
    def __init__(self, address: str, offers: dict[str, str | None]) -> None:
        self.address = address
        self.offers = offers

    @contextmanager
    def session(self) -> Iterator[str]:
        yield SID

    def call(self, sid: str, module: str, method: str, params: Any = None) -> Any:
        reply: dict[str, Any] = {"current_version": "4.8.7"}
        offer = self.offers.get(self.address)
        if offer:
            reply["version_new"] = offer
        return reply

    def probe_tls(self) -> None:
        return None


class Harness:
    def __init__(
        self,
        settings: dict[str, Any],
        resources: list[ResourceConfig],
        offers: dict[str, str | None],
    ) -> None:
        self.events: list[str] = []
        self.upgrade_calls: list[str] = []
        self.fail_on: set[str] = set()
        self.offers = offers
        env = EnvironmentConfig(name="dev", provider_settings={"openwrt": settings})
        self.orchestrator = MagicMock()
        manager = self.orchestrator.config_manager
        manager.base_dir = Path("/unused-config-dir")
        manager.load_environment.return_value = env
        manager.get_all_resources_all_providers.return_value = resources
        self.lock_error: Exception | None = None

        @contextmanager
        def lock(env_name: str, *, timeout: int = 0) -> Iterator[None]:
            if self.lock_error:
                raise self.lock_error
            self.events.append(f"lock:{timeout}")
            try:
                yield
            finally:
                self.events.append("unlock")

        self.orchestrator.environment_lock.side_effect = lock
        self.orchestrator.plan.side_effect = lambda *a, **k: self.events.append("plan")

    def load_web(self, config_dir: Path, env: str, pid: str) -> GlinetWebSettings:
        return GlinetWebSettings(address=ADDRESSES[pid], password=PASSWORD, fingerprint="ab" * 32)

    def client(self, web: GlinetWebSettings) -> FakeClient:
        self.events.append(f"check:{web.address}")
        return FakeClient(web.address, self.offers)

    def run(self, *args: str, input: str | None = None) -> Result:
        harness = self
        deps = glinet_cli._UpgradeDeps(
            load_web=self.load_web,
            client=self.client,
            host_key_probe=lambda *_a: lambda: None,
        )

        class Upgrader:
            def __init__(self, client: FakeClient, *, host_key_probe: Callable[[], None]) -> None:
                self.address = client.address

            def upgrade(self, expected: str, timeout: int) -> None:
                harness.events.append(f"upgrade:{self.address}")
                harness.upgrade_calls.append(self.address)
                if self.address in harness.fail_on:
                    raise FirmwareUpgradeError("upgrade failed")

        with (
            patch.object(glinet_cli, "_DEPS", deps),
            patch.object(glinet_cli, "FirmwareUpgrader", Upgrader),
            patch("infrafoundry.cli.main._get_orchestrator", return_value=self.orchestrator),
            patch("infrafoundry.cli.main._load_env_credentials"),
        ):
            return CliRunner().invoke(
                glinet_cli.openwrt, ["upgrade", "--env", "dev", *args], input=input
            )


def _two(offers: dict[str, str | None] | None = None) -> Harness:
    return Harness(
        DEVICES,
        [_firmware("openwrt"), _firmware("openwrt@travel")],
        offers if offers is not None else {"192.0.2.2": "4.8.8", "198.51.100.2": "4.8.8"},
    )


def test_register_cli_lists_upgrade() -> None:
    group = click.Group("openwrt")
    register_cli(group)
    assert "upgrade" in group.commands


def test_no_firmware_resources() -> None:
    harness = Harness({"address": "192.0.2.2"}, [], {})
    result = harness.run()
    assert result.exit_code == 0 and "nothing to do" in result.output
    assert harness.events == []


def test_all_up_to_date_does_not_prompt() -> None:
    harness = _two({})
    result = harness.run()
    assert result.exit_code == 0 and "up to date" in result.output
    assert harness.upgrade_calls == []
    assert harness.events[0] == "lock:0" and harness.events[-1] == "unlock"


def test_declined_prompt_upgrades_nothing() -> None:
    harness = _two()
    result = harness.run(input="n\n")
    assert result.exit_code == 0 and "Aborted" in result.output
    assert harness.upgrade_calls == []
    assert "plan" not in harness.events


def test_yes_upgrades_in_order_and_replans_inside_the_lock() -> None:
    harness = _two()
    result = harness.run("--yes", "--lock-timeout", "5")
    assert result.exit_code == 0, result.output
    assert harness.upgrade_calls == ["192.0.2.2", "198.51.100.2"]
    assert harness.events[0] == "lock:5"
    assert harness.events[-2:] == ["plan", "unlock"]
    harness.orchestrator.plan.assert_called_once_with(
        "dev", provider_filter=["openwrt", "openwrt@travel"]
    )


def test_confirmed_prompt_upgrades() -> None:
    harness = _two({"192.0.2.2": "4.8.8"})
    result = harness.run(input="y\n")
    assert result.exit_code == 0 and harness.upgrade_calls == ["192.0.2.2"]
    harness.orchestrator.plan.assert_called_once_with("dev", provider_filter=["openwrt"])


def test_first_failure_stops_the_run() -> None:
    harness = _two()
    harness.fail_on = {"192.0.2.2"}
    result = harness.run("--yes")
    assert result.exit_code != 0
    assert harness.upgrade_calls == ["192.0.2.2"]
    assert "not attempted: travel" in result.output
    assert "failed: office" in result.output
    harness.orchestrator.plan.assert_not_called()


def test_a_check_failure_aborts_before_the_prompt() -> None:
    harness = _two()
    original = harness.client

    def failing(web: GlinetWebSettings) -> FakeClient:
        if web.address == "198.51.100.2":
            raise FirmwareUpgradeError("check failed")
        return original(web)

    harness.client = failing  # type: ignore[method-assign]
    result = harness.run("--yes")
    assert result.exit_code != 0
    assert harness.upgrade_calls == []


def test_replan_failure_after_upgrade_is_nonzero_and_says_so() -> None:
    harness = _two({"192.0.2.2": "4.8.8"})
    harness.orchestrator.plan.side_effect = RuntimeError("plan broke")
    result = harness.run("--yes")
    assert result.exit_code != 0
    assert "firmware was upgraded" in result.output


def test_device_narrows_the_run() -> None:
    harness = _two()
    result = harness.run("--yes", "--device", "travel")
    assert result.exit_code == 0 and harness.upgrade_calls == ["198.51.100.2"]
    harness.orchestrator.plan.assert_called_once_with("dev", provider_filter=["openwrt@travel"])


def test_device_errors() -> None:
    assert "not declared" in _two().run("--device", "lab").output
    only_office = Harness(DEVICES, [_firmware("openwrt")], {})
    assert "has no glinet.firmware resource" in only_office.run("--device", "travel").output
    flat = Harness({"address": "192.0.2.2"}, [_firmware("openwrt")], {})
    result = flat.run("--device", "x")
    assert result.exit_code != 0 and "flat" in result.output


def test_a_held_lock_surfaces() -> None:
    harness = _two()
    harness.lock_error = LockAcquisitionError("dev", "someone", "now", "later")
    result = harness.run("--yes")
    assert result.exit_code != 0
    assert harness.upgrade_calls == []


def test_output_never_contains_the_password_or_sid() -> None:
    harness = _two()
    result = harness.run("--yes")
    assert PASSWORD not in result.output and SID not in result.output


def _probe(returncode: int) -> list[list[str]]:
    import subprocess

    from infrafoundry.providers.openwrt.settings import OpenWrtSettings

    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kw: Any) -> Any:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, returncode, "", "Host key verification failed.")

    with (
        patch.object(glinet_cli, "load_settings", return_value=OpenWrtSettings("192.0.2.2")),
        patch.object(glinet_cli.subprocess, "run", fake_run),
    ):
        glinet_cli._ssh_host_key_probe(Path("."), "dev", "openwrt")()
    return calls


def test_host_key_probe_checks_strictly_under_the_address_alias() -> None:
    [argv] = _probe(0)
    assert "StrictHostKeyChecking=yes" in argv and "HostKeyAlias=192.0.2.2" in argv


def test_host_key_probe_failure_raises() -> None:
    with pytest.raises(FirmwareUpgradeError, match="ssh exited 255"):
        _probe(255)


def _probe_with(returncode: int, stderr: str) -> list[str]:
    import subprocess

    from infrafoundry.providers.openwrt.settings import OpenWrtSettings

    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kw: Any) -> Any:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, returncode, "", stderr)

    settings = OpenWrtSettings("192.0.2.2", ssh_private_key_file="/keys/id")
    with (
        patch.object(glinet_cli, "load_settings", return_value=settings),
        patch.object(glinet_cli.subprocess, "run", fake_run),
    ):
        glinet_cli._ssh_host_key_probe(Path("."), "dev", "openwrt")()
    return calls[0]


def test_host_key_probe_uses_no_authentication() -> None:
    argv = _probe_with(0, "")
    for option in (
        "PreferredAuthentications=none",
        "StrictHostKeyChecking=yes",
        "HostKeyAlias=192.0.2.2",
        "BatchMode=yes",
    ):
        assert option in argv
    assert "-i" not in argv


def test_host_key_probe_passes_on_permission_denied() -> None:
    _probe_with(255, "root@192.0.2.2: Permission denied (publickey,password).")


@pytest.mark.parametrize(
    "stderr",
    [
        "Host key verification failed.",
        "@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@",
        "No ED25519 host key is known for 192.0.2.2 and you have requested strict checking.",
    ],
)
def test_host_key_probe_fails_on_host_key_failure(stderr: str) -> None:
    with pytest.raises(FirmwareUpgradeError, match="host-key check failed"):
        _probe_with(255, stderr)


def test_host_key_probe_host_key_failure_wins_over_permission_denied() -> None:
    with pytest.raises(FirmwareUpgradeError, match="host-key check failed"):
        _probe_with(255, "Host key verification failed.\nPermission denied")


def test_host_key_probe_fails_on_connection_refused() -> None:
    with pytest.raises(FirmwareUpgradeError, match="ssh exited 255"):
        _probe_with(255, "ssh: connect to host 192.0.2.2 port 22: Connection refused")
