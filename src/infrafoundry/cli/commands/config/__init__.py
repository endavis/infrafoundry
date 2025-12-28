"""Configuration management command group."""

import click

from .diff import diff
from .envs import envs
from .migrate import migrate
from .new import new
from .validate import validate


@click.group()
def config() -> None:
    """Configuration management (envs, diff, validate, etc.)."""
    pass


# Register all subcommands
config.add_command(envs)
config.add_command(diff)
config.add_command(validate)
config.add_command(new)
config.add_command(migrate)


__all__ = ["config"]
