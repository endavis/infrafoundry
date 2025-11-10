"""Init command - Initialize InfraFoundry state database."""

import os
import sys
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.command()
def init() -> None:
    """Initialize InfraFoundry state database."""
    from infrafoundry.core.state import StateManager

    try:
        console.print("[cyan]Initializing InfraFoundry state database...[/cyan]")

        # Get state backend configuration
        state_backend = os.getenv("INFRAFOUNDRY_STATE_BACKEND", "sqlite")
        connection_string = os.getenv("INFRAFOUNDRY_STATE_CONNECTION")

        if state_backend == "sqlite" and not connection_string:
            state_dir = Path.home() / ".infrafoundry"
            state_dir.mkdir(parents=True, exist_ok=True)
            db_path = state_dir / "state.db"
            console.print(f"[dim]Using SQLite database at: {db_path}[/dim]")

        state_manager = StateManager(connection_string)
        state_manager.initialize()

        console.print("[bold green]✓ State database initialized successfully![/bold green]")

        if state_backend == "sqlite" and not connection_string:
            state_dir = Path.home() / ".infrafoundry"
            db_path = state_dir / "state.db"
            console.print(f"\n[dim]Database location: {db_path}[/dim]")

        console.print("\n[bold]State tracking is now enabled.[/bold]")
        console.print("Deployment history and resource state will be recorded.")

    except Exception as e:
        console.print(f"[bold red]Error initializing state database:[/bold red] {e}")
        sys.exit(1)
