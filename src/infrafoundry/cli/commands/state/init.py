"""Init command - Initialize InfraFoundry state database."""

import os
from pathlib import Path

import click

from infrafoundry.core.exceptions import InfraFoundryError, StateError

from ...utils import console, raise_cli_error


@click.command()
def init() -> None:
    """Initialize InfraFoundry state database."""
    from infrafoundry.core.state import StateManager

    try:
        console.info("Initializing InfraFoundry state database...")

        # Get state backend configuration
        state_backend = os.getenv("INFRAFOUNDRY_STATE_BACKEND", "sqlite")
        connection_string = os.getenv("INFRAFOUNDRY_STATE_CONNECTION")

        if state_backend == "sqlite" and not connection_string:
            state_dir = Path.home() / ".infrafoundry"
            state_dir.mkdir(parents=True, exist_ok=True)
            db_path = state_dir / "state.db"
            console.info(f"Using SQLite database at: {db_path}")

        state_manager = StateManager(connection_string)
        state_manager.initialize()

        console.success("State database initialized successfully!")

        if state_backend == "sqlite" and not connection_string:
            state_dir = Path.home() / ".infrafoundry"
            db_path = state_dir / "state.db"
            console.info(f"Database location: {db_path}")

        console.header("State tracking is now enabled.")
        console.info("Deployment history and resource state will be recorded.")

    except click.ClickException:
        raise
    except StateError as exc:
        raise_cli_error("Init command failed", exc)
    except InfraFoundryError as exc:
        raise_cli_error("Init command failed", exc)
    except Exception as exc:
        raise_cli_error("Init command failed", exc)
