"""Blueprint management command group."""

import click

from .validate import validate


@click.group()
def blueprint() -> None:
    """Blueprint management (validate, etc.)."""
    pass


# Register subcommands
blueprint.add_command(validate)

__all__ = ["blueprint"]
