"""Audit trail module for InfraFoundry.

This module provides immutable audit logging for compliance and security:
- Tracks all infrastructure operations (plan, apply, destroy)
- Records user identity, timestamps, and operation details
- Supports tamper detection via SHA-256 checksums
- Exports to JSON/CSV for compliance reporting

Example usage:
    from infrafoundry.core.audit import AuditLogger, AuditExporter

    # Create audit logger (typically done by orchestrator)
    logger = AuditLogger(session_factory, event_bus, get_current_user)

    # Query audit entries
    entries = logger.query(
        start_date=datetime(2024, 1, 1),
        env="prod",
        action="apply_completed",
    )

    # Export for compliance
    exporter = AuditExporter()
    exporter.export_json(entries, Path("audit_report.json"))
"""

from infrafoundry.core.audit.exporter import AuditExporter
from infrafoundry.core.audit.logger import AuditLogger
from infrafoundry.core.audit.models import AuditEntry, AuditStatus

__all__ = [
    "AuditEntry",
    "AuditExporter",
    "AuditLogger",
    "AuditStatus",
]
