"""``foundry provider mikrotik upgrade``: install the latest RouterOS of the declared channel.

ADR-0037. The command holds the environment lock for its whole run and checks the device
read-only. Nothing is written before the confirmation: when the device follows another
channel than the resource declares, the channel is switched only after the user said yes.
It then runs the two upgrade stages (RouterOS, then RouterBOARD firmware) and re-plans.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.table import Table

from infrafoundry.cli.decorators import with_orchestrator
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ResourceConfig

from .client import RouterOSClient
from .components.update import (
    UPDATE_TYPE,
    DeviceUpdateState,
    RouterOSUpgrader,
    UpdateClient,
    check_update,
    current_versions,
    declared_channel,
    set_channel,
)
from .settings import PROVIDER_NAME, MikroTikSettings, load_settings

if TYPE_CHECKING:
    from infrafoundry.core.orchestrator import Orchestrator


@dataclass(frozen=True)
class _UpgradeDeps:
    """The seams tests replace: how settings, clients and upgraders are built."""

    load_settings: Callable[[Path, str], MikroTikSettings] = load_settings
    client: Callable[[MikroTikSettings], UpdateClient] = RouterOSClient
    upgrader: Callable[[UpdateClient], RouterOSUpgrader] = RouterOSUpgrader


_DEPS = _UpgradeDeps()


def _update_resource(orchestrator: Orchestrator, env: str) -> ResourceConfig | None:
    """Return the environment's ``system.package.update`` resource, if any."""
    for resource in orchestrator.config_manager.get_all_resources_all_providers(env):
        if resource.provider == PROVIDER_NAME and resource.type == UPDATE_TYPE:
            return resource
    return None


def _print_table(state: DeviceUpdateState, declared: str) -> None:
    table = Table(title="MikroTik RouterOS")
    for column in ("Channel", "Current", "Available", "RouterBOARD firmware"):
        table.add_column(column)
    rb = state.routerboard
    firmware = "-"
    if rb.present:
        firmware = (
            f"{rb.current_firmware} → {rb.upgrade_firmware}"
            if rb.lags
            else str(rb.current_firmware)
        )
    if state.channel_mismatch is not None:
        device, _ = state.channel_mismatch
        table.add_row(
            f"{device} (declared: {declared})",
            state.update.installed_version,
            "checked after confirmation",
            firmware,
        )
    else:
        latest = state.update.latest_version if state.update.update_available else "-"
        table.add_row(declared, state.update.installed_version, latest or "-", firmware)
    Console().print(table)


def _failure_message(step: str, error: Exception, versions: str) -> str:
    return (
        f"RouterOS upgrade failed at step '{step}': {error}\n"
        f"The device now reports: {versions}.\n"
        "An installed package or flashed firmware cannot be rolled back automatically."
    )


@click.group()
def mikrotik() -> None:
    """MikroTik provider commands."""


@mikrotik.command(name="upgrade")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--yes", "-y", is_flag=True, help="Do not ask before upgrading")
@click.option(
    "--lock-timeout",
    type=int,
    default=0,
    show_default=True,
    help="Seconds to wait for the environment lock (0 fails fast)",
)
@with_orchestrator("MikroTik RouterOS upgrade failed")
def upgrade(
    ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    yes: bool,
    lock_timeout: int,
) -> None:
    """Install the latest RouterOS of the declared channel, then lagging RouterBOARD firmware.

    Checks the device read-only, asks once (unless --yes), then installs and reboots.
    The device reboots once or twice and its traffic is interrupted each time.
    """
    resource = _update_resource(orchestrator, env)
    if resource is None:
        click.echo(f"No {UPDATE_TYPE} resource in environment '{env}'; nothing to do.")
        return
    channel = declared_channel(resource)
    config_dir = orchestrator.config_manager.base_dir
    with orchestrator.environment_lock(env, timeout=lock_timeout):
        settings = _DEPS.load_settings(config_dir, env)
        client = _DEPS.client(settings)
        state = check_update(client, channel)
        _print_table(state, channel)
        mismatch = state.channel_mismatch
        pending = mismatch is not None or state.update.update_available or state.routerboard.lags
        if not pending:
            click.echo("The device is up to date.")
            return
        question = (
            "Install the pending RouterOS release and RouterBOARD firmware? "
            "The device reboots once or twice and its traffic is interrupted each time. "
            "An upgrade cannot be rolled back automatically."
        )
        if mismatch is not None:
            question = (
                f"Switch the update channel from '{mismatch[0]}' to '{mismatch[1]}' first, "
                "then install the latest release of that channel and any pending "
                "RouterBOARD firmware? " + question.split("? ", 1)[1]
            )
        if not yes and not click.confirm(question, default=False):
            click.echo("Aborted; nothing was changed.")
            return
        try:
            if mismatch is not None:
                set_channel(client, channel)
                state = check_update(client, channel)
            expected = state.update.latest_version if state.update.update_available else None
            if expected is None and not state.routerboard.lags:
                click.echo(f"Channel switched to '{channel}'; the device is up to date.")
                return
            click.echo(f"Upgrading{f' to RouterOS {expected}' if expected else ''} ...")
            report = _DEPS.upgrader(client).upgrade(expected, settings.upgrade_timeout)
        except (InfraFoundryError, OSError) as exc:
            step = getattr(exc, "step", "check")
            raise click.ClickException(
                _failure_message(step, exc, current_versions(client))
            ) from exc
        if report.routeros_version:
            click.echo(f"RouterOS is now {report.routeros_version}.")
        if report.firmware_version:
            click.echo(f"RouterBOARD firmware is now {report.firmware_version}.")
        if report.routerboard_skipped:
            click.echo(f"RouterBOARD stage skipped: {report.routerboard_skipped}.")
        try:
            orchestrator.plan(env, provider_filter=[PROVIDER_NAME])
        except Exception as exc:
            raise click.ClickException(
                f"the upgrade succeeded, but the re-plan failed: {exc}"
            ) from exc
