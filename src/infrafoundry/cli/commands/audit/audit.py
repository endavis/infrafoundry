"""Audit command group for InfraFoundry."""

import click


@click.group()
def audit() -> None:
    """View and export audit trail for compliance.

    The audit trail records all infrastructure operations (plan, apply, destroy)
    with user identity, timestamps, and operation details.
    """
    pass
