"""``foundry certs issue``: order, store and install the certificates that need it."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import click

from infrafoundry.cli.decorators import with_orchestrator
from infrafoundry.core.certs.models import CertificateError
from infrafoundry.core.certs.service import certificate_resources
from infrafoundry.core.exceptions import LockAcquisitionError

from . import _common

if TYPE_CHECKING:
    from infrafoundry.core.orchestrator import Orchestrator

EXIT_FAILED = 1
EXIT_LOCKED = 75
LOCK_TTL = 900


@click.command("issue")
@click.option("--env", "-e", required=True, help="Environment name")
@click.argument("names", nargs=-1)
@click.option(
    "--force", is_flag=True, help="Issue again even when the stored certificate is current"
)
@click.option(
    "--lock-timeout",
    type=int,
    default=0,
    show_default=True,
    help="Seconds to wait for the environment lock (0 fails fast)",
)
@with_orchestrator("Certificate issue failed")
def issue(
    ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    names: tuple[str, ...],
    force: bool,
    lock_timeout: int,
) -> None:
    """Issue and install the certificates that are missing, due or not yet installed.

    Without NAMES every declared certificate is checked. Each one is processed in turn
    and a failure does not stop the others. Exit codes: 0 ok, 1 a certificate failed,
    2 usage error, 75 the environment lock is held. The certificate store is a SOPS file in
    the config repo: commit it afterwards.
    """
    deps = _common.DEPS
    resources = orchestrator.config_manager.get_all_resources_all_providers(env)
    if not certificate_resources(resources):
        click.echo(f"No certificate resources in environment '{env}'; nothing to do.")
        return
    env_config = _common.load_environment(orchestrator, env)
    settings = _common.load_settings(env_config)
    account = _common.stored_account(env_config, settings)
    service = _common.build_service(
        orchestrator, env, deps, settings.renew_before_days, record=True
    )
    issuer = _common.build_issuer(settings, deps)
    try:
        with orchestrator.environment_lock(env, timeout=lock_timeout, ttl=LOCK_TTL):
            try:
                outcomes = service.issue(
                    resources,
                    issuer,
                    account,
                    directory=settings.directory,
                    directory_id=settings.directory_id,
                    only=names,
                    force=force,
                )
            except CertificateError as exc:
                raise click.UsageError(str(exc)) from None
    except LockAcquisitionError as exc:
        click.echo(f"Environment '{env}' is locked by {exc.locked_by}; try again later.", err=True)
        sys.exit(EXIT_LOCKED)
    failed = False
    for outcome in outcomes:
        failed = failed or outcome.action == "failed"
        click.echo(f"{outcome.action:<10} {outcome.name}: {outcome.message}")
    if any(o.action in ("issued", "installed") for o in outcomes):
        click.echo("Commit the config repo: the encrypted certificate store changed.")
    if failed:
        sys.exit(EXIT_FAILED)
