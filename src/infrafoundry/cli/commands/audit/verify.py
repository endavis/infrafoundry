"""Verify audit entry integrity command."""

import click

from infrafoundry.core.audit import AuditLogger
from infrafoundry.core.state import StateManager

from ...utils import console, raise_cli_error


@click.command(name="verify")
@click.argument("entry_id", type=int)
@click.pass_context
def verify_audit(ctx: click.Context, entry_id: int) -> None:
    """Verify the integrity of an audit entry by checking its checksum.

    This command recalculates the SHA-256 checksum of the audit entry
    and compares it to the stored value to detect tampering.

    Examples:

        infra audit verify 123
    """
    try:
        # Initialize state manager and audit logger
        state_manager = StateManager()
        state_manager.initialize()
        audit_logger = AuditLogger(session_factory=state_manager.SessionLocal)

        # Get the entry first to show details
        entry = audit_logger.get_by_id(entry_id)
        if not entry:
            console.error(f"Audit entry {entry_id} not found")
            raise SystemExit(1)

        # Display entry details
        console.header(f"Audit Entry #{entry_id}")
        console.info(f"  Timestamp: {entry.timestamp}")
        console.info(f"  User: {entry.user_identifier}")
        console.info(f"  Environment: {entry.environment or 'N/A'}")
        console.info(f"  Action: {entry.action}")
        console.info(f"  Status: {entry.status}")
        console.info(f"  Checksum: {entry.checksum or 'N/A'}")
        console.info("")

        # Verify integrity
        is_valid = audit_logger.verify_integrity(entry_id)

        if is_valid:
            console.success("Integrity check PASSED - entry has not been tampered with")
        else:
            console.error("Integrity check FAILED - entry may have been modified")
            raise SystemExit(1)

    except SystemExit:
        raise
    except click.ClickException:
        raise
    except Exception as exc:
        raise_cli_error("Failed to verify audit entry", exc)
