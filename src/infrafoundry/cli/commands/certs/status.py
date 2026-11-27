"""``foundry certs status``: show the state of each declared certificate."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from infrafoundry.cli.decorators import with_orchestrator
from infrafoundry.core.certs.models import DEFAULT_RENEW_BEFORE_DAYS, PROVIDER_NAME
from infrafoundry.core.certs.service import certificate_resources

from . import _common

if TYPE_CHECKING:
    from infrafoundry.core.orchestrator import Orchestrator


@click.command("status")
@click.option("--env", "-e", required=True, help="Environment name")
@with_orchestrator("Certificate status failed")
def status(ctx: click.Context, orchestrator: Orchestrator, env: str) -> None:
    """Show each declared certificate: its state, expiry and whether it is installed.

    Reads the encrypted store only; it contacts no CA, DNS host or device.
    """
    deps = _common.DEPS
    resources = orchestrator.config_manager.get_all_resources_all_providers(env)
    if not certificate_resources(resources):
        click.echo(f"No certificate resources in environment '{env}'.")
        return
    env_config = _common.load_environment(orchestrator, env)
    raw = env_config.provider_settings.get(PROVIDER_NAME) or {}
    renew = int(raw.get("renew_before_days", DEFAULT_RENEW_BEFORE_DAYS))
    service = _common.build_service(orchestrator, env, deps, renew, record=False)
    for item in service.status(resources):
        expiry = (
            f"{item.not_after:%Y-%m-%d} ({item.days_left}d)" if item.not_after is not None else "-"
        )
        click.echo(
            f"{item.name:<24} {item.state:<14} {expiry:<22} "
            f"installed={'yes' if item.installed else 'no'}  package={item.package}  "
            f"names={','.join(item.names)}"
        )
