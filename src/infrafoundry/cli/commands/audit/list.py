"""List audit entries command."""

from datetime import datetime
from typing import Any

import click
from rich.table import Table

from infrafoundry.core.audit import AuditLogger
from infrafoundry.core.state import StateManager

from ...output import output_data
from ...utils import console, raise_cli_error


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse date string to datetime.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        Parsed datetime or None
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise click.BadParameter(f"Invalid date format: {date_str}. Use YYYY-MM-DD.") from e


@click.command(name="list")
@click.option("--env", "-e", help="Filter by environment")
@click.option("--user", "-u", help="Filter by user")
@click.option("--action", "-a", help="Filter by action (e.g., apply_completed)")
@click.option("--since", help="Start date (YYYY-MM-DD)")
@click.option("--until", help="End date (YYYY-MM-DD)")
@click.option("--limit", "-n", default=50, help="Maximum entries to display (default: 50)")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
@click.pass_context
def list_audit(
    ctx: click.Context,
    env: str | None,
    user: str | None,
    action: str | None,
    since: str | None,
    until: str | None,
    limit: int,
    output_format: str,
) -> None:
    """List audit entries with optional filters.

    Examples:

        infra audit list --env prod

        infra audit list --user admin --since 2024-01-01

        infra audit list --action apply_completed --limit 100

        infra audit list --format json
    """
    try:
        # Initialize state manager and audit logger
        state_manager = StateManager()
        state_manager.initialize()
        audit_logger = AuditLogger(session_factory=state_manager.SessionLocal)

        # Parse dates
        start_date = _parse_date(since)
        end_date = _parse_date(until)

        # Query entries
        entries = audit_logger.query(
            start_date=start_date,
            end_date=end_date,
            user=user,
            env=env,
            action=action,
            limit=limit,
        )

        if not entries:
            if output_format == "json":
                output_data({"entries": [], "total": 0}, output_format)
            else:
                console.warning("No audit entries found matching the criteria")
            return

        # Build data structure
        entry_data: list[dict[str, Any]] = []
        for entry in entries:
            entry_data.append(
                {
                    "id": entry.id,
                    "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                    "user": entry.user_identifier or "",
                    "environment": entry.environment or "",
                    "action": entry.action or "",
                    "status": entry.status,
                    "provider": entry.provider or "",
                    "message": entry.message or "",
                }
            )

        if output_format == "json":
            output_data({"entries": entry_data, "total": len(entry_data)}, output_format)
        else:
            # Build and display table
            table = Table(title=f"Audit Trail ({len(entries)} entries)")
            table.add_column("ID", style="dim")
            table.add_column("Timestamp", style="cyan")
            table.add_column("User", style="green")
            table.add_column("Env", style="yellow")
            table.add_column("Action", style="magenta")
            table.add_column("Status")
            table.add_column("Provider")
            table.add_column("Message", max_width=40)

            for entry in entries:
                status_style = {
                    "success": "green",
                    "failed": "red",
                    "in_progress": "yellow",
                }.get(entry.status, "")

                table.add_row(
                    str(entry.id),
                    entry.timestamp.strftime("%Y-%m-%d %H:%M:%S") if entry.timestamp else "",
                    entry.user_identifier or "",
                    entry.environment or "",
                    entry.action or "",
                    f"[{status_style}]{entry.status}[/{status_style}]"
                    if status_style
                    else entry.status,
                    entry.provider or "",
                    (entry.message[:37] + "...")
                    if entry.message and len(entry.message) > 40
                    else (entry.message or ""),
                )

            console.print(table)

    except click.ClickException:
        raise
    except Exception as exc:
        raise_cli_error("Failed to list audit entries", exc)
