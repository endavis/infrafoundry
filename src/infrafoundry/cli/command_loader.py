"""Command loader for auto-discovering and registering CLI commands.

This module provides functionality to automatically discover command modules
in the commands/ directory and register them with the main CLI application.

Architecture:
    - One file per command in commands/ directory (e.g., init.py, plan.py, apply.py)
    - Each file should contain a Click command or group
    - Commands are auto-discovered and registered at import time

Example command file (commands/example.py):
    ```python
    import click

    @click.command()
    def example():
        '''Example command description.'''
        click.echo('Hello!')
    ```
"""

import importlib
import logging
import traceback
from pathlib import Path

import click

from infrafoundry.core.exceptions import InfraFoundryError

logger = logging.getLogger(__name__)


class CommandLoader:
    """Auto-discover and load CLI command modules.

    Scans the commands/ directory for Python modules and automatically
    registers any Click commands or groups found in them.

    Example:
        >>> loader = CommandLoader(main_group)
        >>> loader.discover_and_register_all()
        # All commands from commands/*.py are now registered
    """

    def __init__(self, main_group: click.Group) -> None:
        """Initialize command loader.

        Args:
            main_group: The main Click group to register commands to
        """
        self.main_group = main_group
        self._commands_dir = Path(__file__).parent / "commands"

    def discover_and_register_all(self) -> None:
        """Discover and register all command modules.

        Scans the commands/ directory for .py files (excluding __init__.py)
        and attempts to load and register commands from each.
        """
        if not self._commands_dir.exists():
            logger.warning(f"Commands directory not found: {self._commands_dir}")
            return

        for module_file in self._commands_dir.glob("*.py"):
            if module_file.name == "__init__.py":
                continue

            module_name = module_file.stem
            self._discover_and_register_module(module_name)

    def _discover_and_register_module(self, module_name: str) -> None:
        """Discover and register commands from a specific module.

        Args:
            module_name: Name of the module (without .py extension)
        """
        try:
            # Import the module
            module_path = f"infrafoundry.cli.commands.{module_name}"
            module = importlib.import_module(module_path)

            # Look for commands or groups to register
            registered_count = 0

            # Check for a register_commands function (preferred pattern)
            if hasattr(module, "register_commands"):
                module.register_commands(self.main_group)
                logger.debug(f"Registered commands from {module_name} via register_commands()")
                return

            # Fallback: auto-discover Click commands/groups
            for attr_name in dir(module):
                attr = getattr(module, attr_name)

                # Skip private attributes and non-Click objects
                if attr_name.startswith("_"):
                    continue

                # Register Click commands
                if isinstance(attr, (click.Command, click.Group)):
                    # Don't register if it's already attached to a parent
                    if not hasattr(attr, "parent") or attr.parent is None:
                        self.main_group.add_command(attr, name=attr.name or attr_name.lower())
                        registered_count += 1
                        logger.debug(f"Registered command '{attr.name}' from {module_name}")

            if registered_count > 0:
                logger.debug(f"Auto-registered {registered_count} command(s) from {module_name}")

        except ImportError as e:
            logger.error(f"Failed to import command module '{module_name}': {e}")
        except InfraFoundryError as e:
            logger.error(f"InfraFoundry error loading commands from '{module_name}': {e}")
        except Exception as e:
            logger.warning(f"Failed to load command module '{module_name}': {e}")
            logger.debug(traceback.format_exc())  # Log full traceback

    def register_module(self, module_name: str) -> None:
        """Manually register a specific module.

        Useful for testing or selective command loading.

        Args:
            module_name: Name of the module to register
        """
        self._discover_and_register_module(module_name)


def load_commands(main_group: click.Group) -> None:
    """Convenience function to load all commands.

    Args:
        main_group: The main Click group to register commands to

    Example:
        >>> @click.group()
        >>> def main():
        ...     pass
        >>>
        >>> load_commands(main)
    """
    loader = CommandLoader(main_group)
    loader.discover_and_register_all()
