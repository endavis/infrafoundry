"""Proxmox provider CLI commands.

This package hosts the ``click`` subcommands attached to the top-level
``foundry provider proxmox`` group via the provider's ``cli_registration``
hook (see :func:`infrafoundry.providers.proxmox.register`).
"""

from __future__ import annotations

import click

from .dump import dump
from .export import export_proxmox


@click.group()
def proxmox() -> None:
    """Proxmox provider commands."""


proxmox.add_command(export_proxmox, name="export")
proxmox.add_command(dump, name="dump")


__all__ = ["proxmox"]
