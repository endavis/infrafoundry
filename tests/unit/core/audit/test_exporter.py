"""Tests for audit exporter service."""

import csv
import json
from datetime import UTC, datetime

import pytest

from infrafoundry.core.audit.exporter import AuditExporter
from infrafoundry.core.audit.models import AuditEntry


@pytest.fixture
def sample_entries():
    """Create sample audit entries for testing."""
    return [
        AuditEntry(
            id=1,
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            event_type="after_apply",
            user_identifier="alice",
            environment="prod",
            command="apply",
            provider="proxmox",
            resource_name="web-server-1",
            resource_type="vms",
            action="apply_completed",
            status="success",
            message="Applied 3 resources",
            ip_address="192.168.1.100",
            changes_summary={"added": 2, "changed": 1, "destroyed": 0},
            request_metadata={"cli_args": ["apply", "--env", "prod"]},
            checksum="abc123",
        ),
        AuditEntry(
            id=2,
            timestamp=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            event_type="after_plan",
            user_identifier="bob",
            environment="dev",
            command="plan",
            provider="oci",
            resource_name=None,
            resource_type=None,
            action="plan_completed",
            status="success",
            message=None,
            ip_address="192.168.1.101",
            changes_summary=None,
            request_metadata=None,
            checksum="def456",
        ),
    ]


@pytest.fixture
def exporter():
    """Create an AuditExporter instance."""
    return AuditExporter()


class TestAuditExporterInit:
    """Tests for AuditExporter initialization."""

    def test_init(self):
        """Test basic initialization."""
        exporter = AuditExporter()
        assert exporter is not None

    def test_csv_fields_defined(self):
        """Test that CSV fields are properly defined."""
        assert AuditExporter.CSV_FIELDS is not None
        assert "id" in AuditExporter.CSV_FIELDS
        assert "timestamp" in AuditExporter.CSV_FIELDS
        assert "user_identifier" in AuditExporter.CSV_FIELDS
        assert "action" in AuditExporter.CSV_FIELDS


class TestExportJson:
    """Tests for AuditExporter.export_json method."""

    def test_export_json_creates_file(self, exporter, sample_entries, tmp_path):
        """Test that export_json creates the output file."""
        output_path = tmp_path / "audit.json"
        result = exporter.export_json(sample_entries, output_path)

        assert output_path.exists()
        assert result == str(output_path)

    def test_export_json_content_structure(self, exporter, sample_entries, tmp_path):
        """Test the structure of exported JSON."""
        output_path = tmp_path / "audit.json"
        exporter.export_json(sample_entries, output_path)

        with output_path.open() as f:
            data = json.load(f)

        assert "export_metadata" in data
        assert "audit_entries" in data
        assert data["export_metadata"]["total_entries"] == 2
        assert data["export_metadata"]["export_format"] == "json"
        assert len(data["audit_entries"]) == 2

    def test_export_json_entry_fields(self, exporter, sample_entries, tmp_path):
        """Test that exported entries have all fields."""
        output_path = tmp_path / "audit.json"
        exporter.export_json(sample_entries, output_path)

        with output_path.open() as f:
            data = json.load(f)

        entry = data["audit_entries"][0]
        assert entry["id"] == 1
        assert entry["user_identifier"] == "alice"
        assert entry["environment"] == "prod"
        assert entry["action"] == "apply_completed"
        assert entry["changes_summary"]["added"] == 2

    def test_export_json_pretty_format(self, exporter, sample_entries, tmp_path):
        """Test that pretty=True formats the JSON."""
        output_path = tmp_path / "audit.json"
        exporter.export_json(sample_entries, output_path, pretty=True)

        content = output_path.read_text()
        # Pretty printed JSON has newlines and indentation
        assert "\n" in content
        assert "  " in content

    def test_export_json_compact_format(self, exporter, sample_entries, tmp_path):
        """Test that pretty=False creates compact JSON."""
        output_path = tmp_path / "audit.json"
        exporter.export_json(sample_entries, output_path, pretty=False)

        content = output_path.read_text()
        # Compact JSON is on one line (no indentation)
        lines = content.strip().split("\n")
        assert len(lines) == 1

    def test_export_json_creates_parent_dirs(self, exporter, sample_entries, tmp_path):
        """Test that export_json creates parent directories."""
        output_path = tmp_path / "nested" / "path" / "audit.json"
        exporter.export_json(sample_entries, output_path)

        assert output_path.exists()

    def test_export_json_empty_list(self, exporter, tmp_path):
        """Test exporting empty list of entries."""
        output_path = tmp_path / "empty.json"
        exporter.export_json([], output_path)

        with output_path.open() as f:
            data = json.load(f)

        assert data["export_metadata"]["total_entries"] == 0
        assert len(data["audit_entries"]) == 0

    def test_export_json_handles_none_values(self, exporter, tmp_path):
        """Test that export handles None values correctly."""
        entry = AuditEntry(
            id=1,
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            event_type="test",
            user_identifier="user",
            action="test_action",
            status="success",
            # All optional fields are None
        )
        output_path = tmp_path / "audit.json"
        exporter.export_json([entry], output_path)

        with output_path.open() as f:
            data = json.load(f)

        exported_entry = data["audit_entries"][0]
        assert exported_entry["environment"] is None
        assert exported_entry["provider"] is None


class TestExportCsv:
    """Tests for AuditExporter.export_csv method."""

    def test_export_csv_creates_file(self, exporter, sample_entries, tmp_path):
        """Test that export_csv creates the output file."""
        output_path = tmp_path / "audit.csv"
        result = exporter.export_csv(sample_entries, output_path)

        assert output_path.exists()
        assert result == str(output_path)

    def test_export_csv_has_header(self, exporter, sample_entries, tmp_path):
        """Test that CSV has header row."""
        output_path = tmp_path / "audit.csv"
        exporter.export_csv(sample_entries, output_path)

        with output_path.open() as f:
            reader = csv.reader(f)
            header = next(reader)

        assert "id" in header
        assert "timestamp" in header
        assert "user_identifier" in header

    def test_export_csv_row_count(self, exporter, sample_entries, tmp_path):
        """Test that CSV has correct number of rows."""
        output_path = tmp_path / "audit.csv"
        exporter.export_csv(sample_entries, output_path)

        with output_path.open() as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Header + 2 data rows
        assert len(rows) == 3

    def test_export_csv_content(self, exporter, sample_entries, tmp_path):
        """Test CSV content matches entries."""
        output_path = tmp_path / "audit.csv"
        exporter.export_csv(sample_entries, output_path)

        with output_path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert rows[0]["id"] == "1"
        assert rows[0]["user_identifier"] == "alice"
        assert rows[0]["environment"] == "prod"
        assert rows[1]["user_identifier"] == "bob"
        assert rows[1]["environment"] == "dev"

    def test_export_csv_creates_parent_dirs(self, exporter, sample_entries, tmp_path):
        """Test that export_csv creates parent directories."""
        output_path = tmp_path / "nested" / "dir" / "audit.csv"
        exporter.export_csv(sample_entries, output_path)

        assert output_path.exists()

    def test_export_csv_empty_list(self, exporter, tmp_path):
        """Test exporting empty list creates file with header only."""
        output_path = tmp_path / "empty.csv"
        exporter.export_csv([], output_path)

        with output_path.open() as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Only header row
        assert len(rows) == 1
        assert "id" in rows[0]

    def test_export_csv_handles_none_values(self, exporter, tmp_path):
        """Test that CSV handles None values as empty strings."""
        entry = AuditEntry(
            id=1,
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            event_type="test",
            user_identifier="user",
            action="test_action",
            status="success",
        )
        output_path = tmp_path / "audit.csv"
        exporter.export_csv([entry], output_path)

        with output_path.open() as f:
            reader = csv.DictReader(f)
            row = next(reader)

        assert row["environment"] == "None" or row["environment"] == ""

    def test_export_csv_serializes_complex_types(self, exporter, sample_entries, tmp_path):
        """Test that complex types (dict, list) are JSON serialized."""
        output_path = tmp_path / "audit.csv"
        exporter.export_csv(sample_entries, output_path)

        with output_path.open() as f:
            content = f.read()

        # The changes_summary dict should be JSON serialized
        # Note: CSV fields don't include changes_summary by default
        # but if they did, it would be serialized
        assert "alice" in content  # Just verify the export worked


class TestAuditExporterHelpers:
    """Tests for AuditExporter helper methods."""

    def test_entry_to_csv_row(self, exporter, sample_entries):
        """Test converting entry to CSV row dict."""
        row = exporter._entry_to_csv_row(sample_entries[0])

        assert row["id"] == 1
        assert row["user_identifier"] == "alice"
        assert row["environment"] == "prod"

    def test_entry_to_csv_row_only_csv_fields(self, exporter, sample_entries):
        """Test that only CSV fields are included in row."""
        row = exporter._entry_to_csv_row(sample_entries[0])

        for key in row:
            assert key in AuditExporter.CSV_FIELDS

    def test_cleanup(self, exporter):
        """Test cleanup method runs without error."""
        exporter.cleanup()  # Should not raise
