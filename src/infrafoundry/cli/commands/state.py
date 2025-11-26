"""Manage InfraFoundry state database operations."""

import datetime
import shutil
from pathlib import Path

import click
from rich.console import Console

from infrafoundry.core.orchestrator import Orchestrator

from ..decorators import with_orchestrator
from ..utils import raise_cli_error

console = Console()


@click.group()
def state() -> None:
    """Manage InfraFoundry state database (backup, restore, migrate)."""
    pass


@state.command("backup")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False, dir_okay=True, writable=True),
    default=".",
    help="Directory to save the backup files. Defaults to current directory.",
)
@click.option(
    "--include-generated",
    "-g",
    is_flag=True,
    help="Include the 'generated/' directory in the backup (tar.gz archive).",
)
@with_orchestrator("State backup failed", require_env=False, load_credentials=False)
def state_backup(
    _ctx: click.Context,
    orchestrator: Orchestrator,
    output_dir: str,
    include_generated: bool,
) -> None:
    """Create a timestamped backup of the InfraFoundry state database.

    Optionally includes the 'generated/' directory.
    """
    try:
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        # Determine state.db location
        # This is a bit tricky, StateManager._determine_state_dir is private.
        # For now, let's assume it's in orchestrator.state_manager._state_dir
        # Or, we can use the default ~/.infrafoundry/state.db or .infrafoundry/state.db
        # Let's use the explicit connection string if it's sqlite, or fallback to default path logic

        state_db_path = None
        # Try to infer from StateManager's connection_string
        if orchestrator.state_manager.engine.url.drivername == "sqlite":
            # Ensure database path is treated as string, as Path() expects str or PathLike
            db_path_str = str(orchestrator.state_manager.engine.url.database)
            state_db_path = Path(db_path_str)
        else:
            # If not SQLite, it's likely a remote DB, so backup is not a file copy.
            console.print(
                "[yellow]InfraFoundry state is not a local SQLite database. "
                "Skipping file backup.[/yellow]"
            )
            return

        if not state_db_path or not state_db_path.exists():
            console.print("[red]InfraFoundry state database file not found.[/red]")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        db_backup_name = f"infrafoundry_state_{timestamp}.db"
        db_backup_path = output_path / db_backup_name

        shutil.copy2(state_db_path, db_backup_path)
        console.print(f"[green]✓ State database backed up to: {db_backup_path}[/green]")

        if include_generated:
            generated_dir = (
                Path.cwd() / "generated"
            )  # Assume generated is in current working directory
            if generated_dir.exists():
                generated_backup_name = f"infrafoundry_generated_{timestamp}.tar.gz"
                generated_backup_path = output_path / generated_backup_name

                # Create a tar.gz archive of the generated directory
                shutil.make_archive(
                    base_name=str(generated_backup_path.with_suffix("")),  # remove .tar.gz
                    format="gztar",
                    root_dir=str(generated_dir.parent),  # Parent directory
                    base_dir=generated_dir.name,  # The directory itself
                )
                console.print(
                    f"[green]✓ 'generated/' directory archived to: {generated_backup_path}[/green]"
                )
            else:
                console.print(
                    "[yellow]'generated/' directory not found. Skipping archive.[/yellow]"
                )

    except Exception as exc:
        raise_cli_error("State backup failed", exc)
