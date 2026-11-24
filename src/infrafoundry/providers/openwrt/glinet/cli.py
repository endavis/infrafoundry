"""``foundry provider openwrt upgrade``: install the vendor's latest GL.iNet firmware (ADR-0036).

The command holds the environment lock for its whole run, checks every selected device
read-only, asks once, then upgrades the devices one at a time. The first failure stops
the run: a failure is evidence of API drift, a bad release or a network problem that
would probably repeat on the next router, and a flash cannot be rolled back
automatically. After the upgrades it re-plans the upgraded devices.
"""

from __future__ import annotations

import subprocess  # nosec B404  # required for the read-only ssh host-key probe
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console
from rich.table import Table

from infrafoundry.cli.decorators import with_orchestrator
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider_instances import (
    declared_instances,
    instance_provider_id,
    split_provider_id,
)
from infrafoundry.core.ssh_options import host_key_hint
from infrafoundry.providers.openwrt.devices import BASE_PROVIDER, device_label, devices_declared
from infrafoundry.providers.openwrt.glinet.firmware import (
    FIRMWARE_TYPE,
    FirmwareStatus,
    FirmwareUpgradeError,
    FirmwareUpgrader,
    RpcClient,
    check_firmware,
)
from infrafoundry.providers.openwrt.glinet.rpc import GlinetRpcClient
from infrafoundry.providers.openwrt.glinet.settings import GlinetWebSettings, load_web_settings
from infrafoundry.providers.openwrt.settings import load_settings
from infrafoundry.providers.openwrt.validator import ssh_argv

if TYPE_CHECKING:
    from infrafoundry.core.orchestrator import Orchestrator

SSH_PROBE_COMMAND = "true"
_HOST_KEY_FAILURE_MARKERS = (
    "Host key verification failed",
    "REMOTE HOST IDENTIFICATION HAS CHANGED",
    "host key is known for",
    "has changed and you have requested strict checking",
)


def _ssh_host_key_probe(config_dir: Path, env: str, provider_id: str) -> Callable[[], None]:
    """Return a probe that fails unless the device presents its pinned SSH host key.

    The key is verified during the key exchange, before authentication, so the probe
    uses no credential: exit 0 or a ``Permission denied`` both prove the key matched. A
    host-key failure, or any other failure such as a refused connection, raises.
    """

    def probe() -> None:
        settings = load_settings(config_dir, env, provider_id)
        argv = ssh_argv(settings, SSH_PROBE_COMMAND, host_key_alias=settings.address, no_auth=True)
        result = subprocess.run(  # list argv, no shell
            argv, capture_output=True, text=True, check=False, timeout=60
        )
        if result.returncode == 0:
            return
        stderr = result.stderr
        if any(marker in stderr for marker in _HOST_KEY_FAILURE_MARKERS):
            hint = host_key_hint(stderr, settings.address) or (
                f"The host key for {settings.address} did not match the pinned key."
            )
            raise FirmwareUpgradeError(
                f"ssh exited {result.returncode}: host-key check failed: {hint}"
            )
        if "Permission denied" in stderr:
            return
        raise FirmwareUpgradeError(f"ssh exited {result.returncode}: {stderr.strip()[:200]}")

    return probe


@dataclass(frozen=True)
class _UpgradeDeps:
    """The seams tests replace: how clients and host-key probes are built."""

    load_web: Callable[[Path, str, str], GlinetWebSettings] = load_web_settings
    client: Callable[[GlinetWebSettings], RpcClient] = GlinetRpcClient
    host_key_probe: Callable[[Path, str, str], Callable[[], None]] = _ssh_host_key_probe


_DEPS = _UpgradeDeps()


@dataclass(frozen=True)
class _Row:
    provider_id: str
    label: str
    web: GlinetWebSettings
    status: FirmwareStatus


def _firmware_provider_ids(
    orchestrator: Orchestrator, env: str
) -> tuple[list[str], dict[str, Any]]:
    """Return the provider ids with a ``glinet.firmware`` resource, in declaration order."""
    manager = orchestrator.config_manager
    env_config = manager.load_environment(env)
    settings = env_config.provider_settings if env_config else {}
    have = {
        r.provider
        for r in manager.get_all_resources_all_providers(env)
        if r.type == FIRMWARE_TYPE and split_provider_id(r.provider)[0] == BASE_PROVIDER
    }
    order = [
        instance_provider_id(BASE_PROVIDER, name, settings)
        for name in declared_instances(BASE_PROVIDER, settings)
    ] or [BASE_PROVIDER]
    ids = [pid for pid in order if pid in have]
    ids += sorted(have - set(ids))
    return ids, settings


def _select(ids: list[str], settings: dict[str, Any], device: str | None) -> list[str]:
    if device is None:
        return ids
    raw = settings.get(BASE_PROVIDER)
    if not devices_declared(raw):
        raise click.ClickException(
            "--device needs provider_settings.openwrt.devices; this configuration is flat"
        )
    if device not in declared_instances(BASE_PROVIDER, settings):
        raise click.ClickException(f"device '{device}' is not declared under openwrt devices")
    chosen = instance_provider_id(BASE_PROVIDER, device, settings)
    if chosen not in ids:
        raise click.ClickException(f"device '{device}' has no {FIRMWARE_TYPE} resource")
    return [chosen]


def _print_table(rows: list[_Row]) -> None:
    table = Table(title="GL.iNet firmware")
    for column in ("Device", "Address", "Current", "Available"):
        table.add_column(column)
    for row in rows:
        table.add_row(
            row.label, row.web.address, row.status.current_version, row.status.version_new or "-"
        )
    Console().print(table)


def _failure_message(failed: _Row, error: Exception, done: list[_Row], rest: list[_Row]) -> str:
    def names(rows: list[_Row]) -> str:
        return ", ".join(r.label for r in rows) or "none"

    return (
        f"firmware upgrade of '{failed.label}' failed: {error}\n"
        f"upgraded: {names(done)}; failed: {failed.label}; not attempted: {names(rest)}.\n"
        "The run stopped at the first failure; a flash cannot be rolled back automatically."
    )


@click.group()
def openwrt() -> None:
    """OpenWrt provider commands."""


@openwrt.command(name="upgrade")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--device", default=None, help="Only this device (needs a devices: map)")
@click.option("--yes", "-y", is_flag=True, help="Do not ask before flashing")
@click.option(
    "--lock-timeout",
    type=int,
    default=0,
    show_default=True,
    help="Seconds to wait for the environment lock (0 fails fast)",
)
@with_orchestrator("OpenWrt firmware upgrade failed")
def upgrade(
    ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    device: str | None,
    yes: bool,
    lock_timeout: int,
) -> None:
    """Install the vendor's latest firmware on GL.iNet devices with a glinet.firmware resource.

    Checks every selected device read-only, asks once (unless --yes), upgrades the devices
    one at a time keeping their configuration, and stops at the first failure.
    """
    ids, settings = _firmware_provider_ids(orchestrator, env)
    if not ids:
        click.echo(f"No {FIRMWARE_TYPE} resources in environment '{env}'; nothing to do.")
        return
    selected = _select(ids, settings, device)
    config_dir = orchestrator.config_manager.base_dir
    env_config = orchestrator.config_manager.load_environment(env)
    with orchestrator.environment_lock(env, timeout=lock_timeout):
        rows: list[_Row] = []
        for pid in selected:
            web = _DEPS.load_web(config_dir, env, pid)
            status = check_firmware(_DEPS.client(web))
            rows.append(_Row(pid, device_label(env_config, pid) or BASE_PROVIDER, web, status))
        _print_table(rows)
        todo = [r for r in rows if r.status.update_available]
        if not todo:
            click.echo("All selected devices are up to date.")
            return
        if not yes and not click.confirm(
            f"Flash the latest firmware on {len(todo)} device(s)? "
            "A flash cannot be rolled back automatically.",
            default=False,
        ):
            click.echo("Aborted; nothing was changed.")
            return
        done: list[_Row] = []
        for index, row in enumerate(todo):
            upgrader = FirmwareUpgrader(
                _DEPS.client(row.web),
                host_key_probe=_DEPS.host_key_probe(config_dir, env, row.provider_id),
            )
            click.echo(f"Upgrading '{row.label}' to {row.status.version_new} ...")
            try:
                upgrader.upgrade(str(row.status.version_new), row.web.upgrade_timeout)
            except (InfraFoundryError, OSError) as exc:
                raise click.ClickException(
                    _failure_message(row, exc, done, todo[index + 1 :])
                ) from exc
            done.append(row)
            click.echo(f"'{row.label}' is now on {row.status.version_new}.")
        try:
            orchestrator.plan(env, provider_filter=[r.provider_id for r in done])
        except Exception as exc:
            raise click.ClickException(
                f"the firmware was upgraded, but the re-plan failed: {exc}"
            ) from exc
