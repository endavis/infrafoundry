"""``foundry certs``: issue and inspect per-device Let's Encrypt certificates (ADR-0040)."""

from __future__ import annotations

import click

from .issue import issue
from .renew import renew
from .status import status


@click.group()
def certs() -> None:
    """Issue and inspect ACME certificates declared as certificate resources."""


certs.add_command(status)
certs.add_command(issue)
certs.add_command(renew)

__all__ = ["certs"]
