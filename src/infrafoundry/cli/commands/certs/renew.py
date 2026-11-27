"""``foundry certs renew``: the unattended run, for a timer or cron.

It processes what ``issue`` would without ``--force``: certificates that are due, never
issued, declared differently from what is stored, or stored but not installed. It differs
from ``issue`` on purpose: there is no ``--force``, nothing is printed and no lock is taken
when nothing is due, and ``--dry-run`` reports the plan without any lock or network call.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import click

from infrafoundry.cli.decorators import with_orchestrator
from infrafoundry.core.certs.models import CertificateError
from infrafoundry.core.certs.service import certificate_resources
from infrafoundry.core.exceptions import LockAcquisitionError

from . import _common
from .issue import EXIT_FAILED, EXIT_LOCKED, LOCK_TTL

if TYPE_CHECKING:
    from infrafoundry.core.orchestrator import Orchestrator


@click.command("renew")
@click.option("--env", "-e", required=True, help="Environment name")
@click.argument("names", nargs=-1)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Report what would be done; take no lock and contact no CA, DNS or target",
)
@click.option(
    "--lock-timeout",
    type=int,
    default=0,
    show_default=True,
    help="Seconds to wait for the environment lock (0 fails fast)",
)
@with_orchestrator("Certificate renewal failed")
def renew(
    ctx: click.Context,
    orchestrator: Orchestrator,
    env: str,
    names: tuple[str, ...],
    dry_run: bool,
    lock_timeout: int,
) -> None:
    """Renew the certificates that are due, never issued or not yet installed.

    Meant for a systemd timer or cron: it prints nothing and exits 0 when nothing is due.
    Without NAMES every declared certificate is checked. A failure does not stop the
    others. Exit codes: 0 ok, 1 a certificate failed, 2 usage error, 75 the environment
    lock is held (retry on the next run). The certificate store is a SOPS file in the
    config repo: commit it afterwards.
    """
    deps = _common.DEPS
    resources = orchestrator.config_manager.get_all_resources_all_providers(env)
    if not certificate_resources(resources):
        if dry_run:
            click.echo(f"No certificate resources in environment '{env}'; nothing to do.")
        return
    env_config = _common.load_environment(orchestrator, env)
    settings = _common.load_settings(env_config)
    service = _common.build_service(
        orchestrator,
        env,
        deps,
        settings.renew_before_days,
        record=not dry_run,
        command="certs renew",
    )
    try:
        plans = service.plan(resources, directory=settings.directory, only=names)
    except CertificateError as exc:
        raise click.UsageError(str(exc)) from None
    if dry_run:
        for plan in plans:
            verb = {"issue": "would issue", "install": "would install"}.get(plan.action, "invalid")
            click.echo(f"{verb:<12} {plan.name}: {plan.reason}")
        if not plans:
            click.echo("Nothing is due.")
        if any(p.action == "error" for p in plans):
            sys.exit(EXIT_FAILED)
        return
    if not plans:
        return
    account = _common.stored_account(env_config, settings)
    issuer = _common.build_issuer(settings, deps)
    try:
        with orchestrator.environment_lock(env, timeout=lock_timeout, ttl=LOCK_TTL):
            outcomes = service.renew(
                resources,
                issuer,
                account,
                directory=settings.directory,
                directory_id=settings.directory_id,
                only=names,
            )
    except LockAcquisitionError as exc:
        click.echo(f"Environment '{env}' is locked by {exc.locked_by}; try again later.", err=True)
        sys.exit(EXIT_LOCKED)
    for outcome in outcomes:
        if outcome.action != "skipped":
            click.echo(f"{outcome.action:<10} {outcome.name}: {outcome.message}")
    if any(o.action in ("issued", "installed") for o in outcomes):
        click.echo("Commit the config repo: the encrypted certificate store changed.")
    if any(o.action == "failed" for o in outcomes):
        sys.exit(EXIT_FAILED)
