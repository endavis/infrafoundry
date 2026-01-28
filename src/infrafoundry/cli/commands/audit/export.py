"""Export audit entries command."""

from datetime import datetime
from pathlib import Path

import click

from infrafoundry.core.audit import AuditExporter, AuditLogger
from infrafoundry.core.state import StateManager

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


@click.command(name="export")
@click.option(
    "--format",
    "-f",
    "export_format",
    type=click.Choice(["json", "csv"]),
    default="json",
    help="Export format (default: json)",
)
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    help="Output file path",
)
@click.option("--env", "-e", help="Filter by environment")
@click.option("--user", "-u", help="Filter by user")
@click.option("--action", "-a", help="Filter by action")
@click.option("--since", help="Start date (YYYY-MM-DD)")
@click.option("--until", help="End date (YYYY-MM-DD)")
@click.pass_context
def export_audit(
    ctx: click.Context,
    export_format: str,
    output: Path,
    env: str | None,
    user: str | None,
    action: str | None,
    since: str | None,
    until: str | None,
) -> None:
    """Export audit entries to JSON or CSV for compliance reporting.

    Examples:

        infra audit export --format json -o audit.json

        infra audit export --format csv -o report.csv --env prod

        infra audit export -o audit.json --since 2024-01-01 --until 2024-12-31
    """
    try:
        # Initialize state manager and audit logger
        state_manager = StateManager()
        state_manager.initialize()
        audit_logger = AuditLogger(session_factory=state_manager.SessionLocal)
        exporter = AuditExporter()

        # Parse dates
        start_date = _parse_date(since)
        end_date = _parse_date(until)

        # Query entries (no limit for export)
        entries = audit_logger.query(
            start_date=start_date,
            end_date=end_date,
            user=user,
            env=env,
            action=action,
            limit=100000,  # Effectively no limit
        )

        if not entries:
            console.warning("No audit entries found matching the criteria")
            return

        # Export based on format
        if export_format == "json":
            exporter.export_json(entries, output)
        else:
            exporter.export_csv(entries, output)

        console.success(f"Exported {len(entries)} audit entries to {output}")

    except click.ClickException:
        raise
    except Exception as exc:
        raise_cli_error("Failed to export audit entries", exc)
