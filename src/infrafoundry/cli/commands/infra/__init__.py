"""Infrastructure operations command group."""

import click

from .apply import apply
from .deployed import deployed
from .destroy import destroy
from .drift import drift
from .history import history
from .list_packages import list_packages
from .move_package import move_package
from .plan import plan
from .reset import reset
from .rollback import rollback
from .security import security
from .status import status
from .test import test
from .unlock import unlock


@click.group()
def infra() -> None:
    """Infrastructure operations (plan, apply, destroy, drift, etc.)."""
    pass


# Register all subcommands
infra.add_command(plan)
infra.add_command(apply)
infra.add_command(deployed)
infra.add_command(destroy)
infra.add_command(drift)
infra.add_command(rollback)
infra.add_command(reset)
infra.add_command(security)
infra.add_command(status)
infra.add_command(test)
infra.add_command(history)
infra.add_command(list_packages)
infra.add_command(move_package)
infra.add_command(unlock)


__all__ = ["infra"]
