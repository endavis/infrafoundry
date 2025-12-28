"""Proxmox provider-specific command group."""

import click

from .export_proxmox import export_proxmox as export_cmd


@click.group()
def proxmox() -> None:
    """Proxmox provider-specific commands."""
    pass


# Register subcommands
proxmox.add_command(export_cmd, name="export")


__all__ = ["proxmox"]
