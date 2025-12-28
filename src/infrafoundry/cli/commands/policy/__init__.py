"""Policy management command group."""

import click

from .policies import policies as list_cmd


@click.group()
def policy() -> None:
    """Policy management (list, validate)."""
    pass


# Register subcommands
policy.add_command(list_cmd, name="list")


__all__ = ["policy"]
