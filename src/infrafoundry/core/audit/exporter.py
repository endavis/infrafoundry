"""Audit trail exporter for compliance reporting."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, ClassVar

from infrafoundry.core.audit.models import AuditEntry
from infrafoundry.core.base_manager import BaseManager


class AuditExporter(BaseManager):
    """Exports audit logs for compliance and reporting.

    Supports exporting to JSON and CSV formats with filtering options.
    """

    # Fields to include in CSV export (order matters)
    CSV_FIELDS: ClassVar[list[str]] = [
        "id",
        "timestamp",
        "event_type",
        "user_identifier",
        "environment",
        "command",
        "provider",
        "resource_name",
        "resource_type",
        "action",
        "status",
        "message",
        "ip_address",
        "checksum",
    ]

    def __init__(self) -> None:
        """Initialize audit exporter."""
        super().__init__()
        self._log_debug("AuditExporter initialized")

    def export_json(
        self,
        entries: list[AuditEntry],
        output_path: Path,
        pretty: bool = True,
    ) -> str:
        """Export audit entries to JSON file.

        Args:
            entries: List of audit entries to export
            output_path: Path to output JSON file
            pretty: If True, format JSON with indentation

        Returns:
            Path to created file as string
        """
        data = {
            "export_metadata": {
                "total_entries": len(entries),
                "export_format": "json",
            },
            "audit_entries": [entry.to_dict() for entry in entries],
        }

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as f:
            if pretty:
                json.dump(data, f, indent=2, default=str)
            else:
                json.dump(data, f, default=str)

        self._log_info(f"Exported {len(entries)} entries to {output_path}")
        return str(output_path)

    def export_csv(
        self,
        entries: list[AuditEntry],
        output_path: Path,
    ) -> str:
        """Export audit entries to CSV file.

        Args:
            entries: List of audit entries to export
            output_path: Path to output CSV file

        Returns:
            Path to created file as string
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_FIELDS)
            writer.writeheader()

            for entry in entries:
                row = self._entry_to_csv_row(entry)
                writer.writerow(row)

        self._log_info(f"Exported {len(entries)} entries to {output_path}")
        return str(output_path)

    def _entry_to_csv_row(self, entry: AuditEntry) -> dict[str, Any]:
        """Convert an audit entry to a CSV row dict.

        Args:
            entry: Audit entry to convert

        Returns:
            Dictionary with CSV field values
        """
        entry_dict = entry.to_dict()
        row = {}
        for field in self.CSV_FIELDS:
            value = entry_dict.get(field)
            # Convert complex types to string for CSV
            if isinstance(value, dict | list):
                value = json.dumps(value)
            row[field] = value
        return row

    def cleanup(self) -> None:
        """Cleanup resources (required by BaseManager)."""
        self._log_debug("AuditExporter cleanup complete")
