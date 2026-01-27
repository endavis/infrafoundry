"""Infrastructure operations command group."""

import click

from .apply import apply
from .destroy import destroy
from .drift import drift
from .history import history
from .plan import plan
from .reset import reset
from .rollback import rollback
from .security import security
from .status import status


@click.group()
def infra() -> None:
    """Infrastructure operations (plan, apply, destroy, drift, etc.)."""
    pass


# Register all subcommands
infra.add_command(plan)
infra.add_command(apply)
infra.add_command(destroy)
infra.add_command(drift)
infra.add_command(rollback)
infra.add_command(reset)
infra.add_command(security)
infra.add_command(status)
infra.add_command(history)


__all__ = ["infra"]
