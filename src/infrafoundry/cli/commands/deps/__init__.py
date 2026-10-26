"""Blueprint requirement commands (check, sync)."""

import click

from .check import check
from .sync import sync


@click.group()
def deps() -> None:
    """Blueprint requirements (check, sync)."""
    pass


# Register subcommands
deps.add_command(check)
deps.add_command(sync)


__all__ = ["deps"]
