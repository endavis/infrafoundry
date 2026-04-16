"""Configuration management command group."""

import click

from ..proxmox.export_proxmox import export_proxmox as export_cmd
from ..schema import schema
from .create import create
from .diff import diff
from .doctor import doctor
from .envs import envs
from .migrate import migrate
from .new import new
from .show import show


@click.group()
def config() -> None:
    """Configuration management (envs, diff, doctor, schema, export, etc.)."""
    pass


# Register all subcommands
config.add_command(doctor)
config.add_command(envs)
config.add_command(diff)
config.add_command(export_cmd, name="export")
config.add_command(create)
config.add_command(schema)
config.add_command(show)
config.add_command(new)
config.add_command(migrate)


__all__ = ["config"]
