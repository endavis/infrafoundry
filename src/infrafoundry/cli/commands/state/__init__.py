"""State management command group."""

from ..audit import audit
from .backend import _backend as backend
from .init import init
from .list import list_resources as list_cmd
from .resources import resources
from .state import state

# Add subcommands to the state group
state.add_command(audit)
state.add_command(init)
state.add_command(list_cmd, name="list")
state.add_command(resources)
state.add_command(backend)


__all__ = ["state"]
