"""Manage InfraFoundry state database operations."""

import datetime
import shutil
from pathlib import Path

import click

from infrafoundry.core.orchestrator import Orchestrator

from ...decorators import with_orchestrator
from ...utils import console, raise_cli_error


def sqlite_db_path(orchestrator: Orchestrator) -> Path | None:
    """Return the state database file for a SQLite backend, or None for other backends."""
    engine_url = orchestrator.state_manager.engine.url
    if engine_url.drivername != "sqlite":
        return None
    # Ensure database path is treated as string, as Path() expects str or PathLike
    return Path(str(engine_url.database))


def copy_state_db(state_db_path: Path, output_path: Path, timestamp: str) -> Path:
    """Copy the SQLite state database to ``output_path`` as a timestamped file.

    Args:
        state_db_path: Existing state database file.
        output_path: Existing directory to place the copy in.
        timestamp: ``%Y%m%d_%H%M%S`` stamp used in the file name.

    An existing backup is never overwritten: if the name is taken, ``-1``, ``-2``, ...
    is appended to the stem and the first free name is used.

    Returns:
        Path of the backup file actually written.
    """
    attempt = 0
    while True:
        suffix = f"-{attempt}" if attempt else ""
        db_backup_path = output_path / f"infrafoundry_state_{timestamp}{suffix}.db"
        try:
            # "xb" reserves the name exclusively, so concurrent runs never share it.
            with db_backup_path.open("xb"):
                pass
        except FileExistsError:
            attempt += 1
            continue
        try:
            shutil.copy2(state_db_path, db_backup_path)
        except BaseException:
            db_backup_path.unlink(missing_ok=True)
            raise
        return db_backup_path


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

        state_db_path = sqlite_db_path(orchestrator)
        if state_db_path is None:
            # Not SQLite, so likely a remote DB: backup is not a file copy.
            console.warning(
                "InfraFoundry state is not a local SQLite database. Skipping file backup."
            )
            return

        if not state_db_path or not state_db_path.exists():
            console.error("InfraFoundry state database file not found.")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        db_backup_path = copy_state_db(state_db_path, output_path, timestamp)
        console.success(f"State database backed up to: {db_backup_path}")

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
                console.success(f"'generated/' directory archived to: {generated_backup_path}")
            else:
                console.warning("'generated/' directory not found. Skipping archive.")

    except Exception as exc:
        raise_cli_error("State backup failed", exc)
