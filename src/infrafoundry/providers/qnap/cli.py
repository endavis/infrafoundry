"""``foundry provider qnap upgrade``: install the vendor's latest firmware on a QNAP switch.

ADR-0038. The command holds the environment lock for its whole run and checks the switch
read-only. Nothing is written before the confirmation. It then installs, waits for the
reboot, verifies the version and re-plans. A switch cannot be rolled back automatically.
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

from .client import QnapClient
from .components.firmware import (
    FIRMWARE_TYPE,
    FirmwareClient,
    FirmwareState,
    QnapFirmwareUpgrader,
    check_firmware,
    current_version,
)
from .settings import PROVIDER_NAME, QnapSettings, load_settings

if TYPE_CHECKING:
    from infrafoundry.core.orchestrator import Orchestrator


@dataclass(frozen=True)
class _UpgradeDeps:
    """The seams tests replace: how settings, clients and upgraders are built."""

    load_settings: Callable[[Path, str], QnapSettings] = load_settings
    client: Callable[[QnapSettings], FirmwareClient] = QnapClient
    upgrader: Callable[[FirmwareClient], QnapFirmwareUpgrader] = QnapFirmwareUpgrader


_DEPS = _UpgradeDeps()


def _firmware_resource(orchestrator: Orchestrator, env: str) -> ResourceConfig | None:
    """Return the environment's ``firmware.update`` resource, if any."""
    for resource in orchestrator.config_manager.get_all_resources_all_providers(env):
        if resource.provider == PROVIDER_NAME and resource.type == FIRMWARE_TYPE:
            return resource
    return None


def _print_table(state: FirmwareState) -> None:
    table = Table(title="QNAP switch firmware")
    for column in ("Current", "Available"):
        table.add_column(column)
    offer = state.offer
    available = offer.version if offer is not None and offer.newer and offer.version else "-"
    table.add_row(state.current.version, available)
    Console().print(table)


def _failure_message(step: str, error: Exception, version: str) -> str:
    return (
        f"QNAP firmware upgrade failed at step '{step}': {error}\n"
        f"The switch now reports: {version}.\n"
        "An installed firmware cannot be rolled back automatically."
    )


@click.group()
def qnap() -> None:
    """QNAP provider commands."""


@qnap.command(name="upgrade")
@click.option("--env", "-e", required=True, help="Environment name")
@click.option("--yes", "-y", is_flag=True, help="Do not ask before upgrading")
@click.option(
    "--lock-timeout",
    type=int,
    default=0,
    show_default=True,
    help="Seconds to wait for the environment lock (0 fails fast)",
)
@with_orchestrator("QNAP firmware upgrade failed")
def upgrade(
    ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    yes: bool,
    lock_timeout: int,
) -> None:
    """Install the vendor's latest firmware on the switch.

    Checks the switch read-only, asks once (unless --yes), then installs and reboots.
    The switch's traffic is interrupted while it reboots. Run this from a path that does
    not cross the switch.
    """
    if _firmware_resource(orchestrator, env) is None:
        click.echo(f"No {FIRMWARE_TYPE} resource in environment '{env}'; nothing to do.")
        return
    config_dir = orchestrator.config_manager.base_dir
    with orchestrator.environment_lock(env, timeout=lock_timeout):
        settings = _DEPS.load_settings(config_dir, env)
        client = _DEPS.client(settings)
        with client.session():
            try:
                state = check_firmware(client, settings.check_timeout)
            except (InfraFoundryError, OSError) as exc:
                raise click.ClickException(f"the update check failed: {exc}") from exc
            _print_table(state)
            if state.skipped_reason is not None:
                raise click.ClickException(f"the update check was skipped: {state.skipped_reason}")
            offer = state.offer
            if offer is None or not offer.newer or not offer.version:
                click.echo("The switch is up to date.")
                return
            question = (
                f"Install firmware {offer.version}? The switch reboots and its traffic is "
                "interrupted. An upgrade cannot be rolled back automatically."
            )
            if not yes and not click.confirm(question, default=False):
                click.echo("Aborted; nothing was changed.")
                return
            click.echo(f"Upgrading to {offer.version} ...")
            try:
                installed = _DEPS.upgrader(client).upgrade(offer.version, settings.upgrade_timeout)
            except (InfraFoundryError, OSError) as exc:
                step = getattr(exc, "step", "check")
                version = (
                    "unknown (the login failed, so it was not read again)"
                    if step == "login"
                    else current_version(client)
                )
                raise click.ClickException(_failure_message(step, exc, version)) from exc
        click.echo(f"The switch now runs firmware {installed}.")
        try:
            orchestrator.plan(env, provider_filter=[PROVIDER_NAME])
        except Exception as exc:
            raise click.ClickException(
                f"the upgrade succeeded, but the re-plan failed: {exc}"
            ) from exc
