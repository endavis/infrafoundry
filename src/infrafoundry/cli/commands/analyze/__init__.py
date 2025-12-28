"""Analysis and visualization command group."""

import click

from .dependencies import dependencies
from .graph import graph
from .impact import impact


@click.group()
def analyze() -> None:
    """Analysis and visualization (dependencies, impact, graph)."""
    pass


# Register all subcommands
analyze.add_command(dependencies)
analyze.add_command(impact)
analyze.add_command(graph)


__all__ = ["analyze"]
