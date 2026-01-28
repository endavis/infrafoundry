"""Audit command group for InfraFoundry."""

from .audit import audit
from .export import export_audit
from .list import list_audit
from .verify import verify_audit

# Add subcommands to the audit group
audit.add_command(list_audit, name="list")
audit.add_command(export_audit, name="export")
audit.add_command(verify_audit, name="verify")

__all__ = ["audit"]
