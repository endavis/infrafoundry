"""Tests for audit CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infrafoundry.cli.commands.audit import audit
from infrafoundry.core.audit.logger import AuditLogger
from infrafoundry.core.audit.models import AuditEntry, AuditStatus
from infrafoundry.core.events import EventType
from infrafoundry.core.state.models import Base


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def db_session_factory(tmp_path):
    """Create a SQLite database for testing."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    yield session_local
    engine.dispose()


@pytest.fixture
def audit_logger(db_session_factory):
    """Create an AuditLogger with test database."""
    return AuditLogger(
        session_factory=db_session_factory,
        get_current_user=lambda: "testuser",
    )


@pytest.fixture
def populated_logger(audit_logger):
    """Create an AuditLogger with some test entries."""
    # Create various audit entries
    audit_logger.log(
        event_type=EventType.AFTER_PLAN,
        action="plan_completed",
        status=AuditStatus.SUCCESS,
        environment="dev",
        provider="proxmox",
        message="Plan completed successfully",
    )
    audit_logger.log(
        event_type=EventType.AFTER_APPLY,
        action="apply_completed",
        status=AuditStatus.SUCCESS,
        environment="prod",
        provider="oci",
    )
    audit_logger.log(
        event_type=EventType.APPLY_FAILED,
        action="apply_failed",
        status=AuditStatus.FAILED,
        environment="dev",
        message="Connection timeout",
    )
    return audit_logger


class TestAuditCommandGroup:
    """Tests for the audit command group."""

    def test_audit_group_exists(self, cli_runner):
        """Test that audit command group is registered."""
        result = cli_runner.invoke(audit, ["--help"])
        assert result.exit_code == 0
        assert "audit" in result.output.lower() or "View and export" in result.output

    def test_audit_list_subcommand_exists(self, cli_runner):
        """Test that list subcommand exists."""
        result = cli_runner.invoke(audit, ["list", "--help"])
        assert result.exit_code == 0
        assert "entries" in result.output.lower() or "--env" in result.output

    def test_audit_export_subcommand_exists(self, cli_runner):
        """Test that export subcommand exists."""
        result = cli_runner.invoke(audit, ["export", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output or "--output" in result.output

    def test_audit_verify_subcommand_exists(self, cli_runner):
        """Test that verify subcommand exists."""
        result = cli_runner.invoke(audit, ["verify", "--help"])
        assert result.exit_code == 0
        assert "integrity" in result.output.lower() or "ENTRY_ID" in result.output


class TestAuditListCommand:
    """Tests for infra audit list command."""

    def test_list_no_entries(self, cli_runner, db_session_factory):
        """Test list with no audit entries."""
        with patch("infrafoundry.cli.commands.audit.list.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(audit, ["list"])

        assert result.exit_code == 0
        assert "No audit entries found" in result.output

    def test_list_shows_entries(self, cli_runner, db_session_factory, populated_logger):
        """Test list displays audit entries."""
        with patch("infrafoundry.cli.commands.audit.list.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(audit, ["list"])

        assert result.exit_code == 0
        # Should show some entries in table format
        assert "entries" in result.output.lower() or "plan_completed" in result.output

    def test_list_filter_by_env(self, cli_runner, db_session_factory, populated_logger):
        """Test list with environment filter."""
        with patch("infrafoundry.cli.commands.audit.list.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(audit, ["list", "--env", "prod"])

        assert result.exit_code == 0

    def test_list_filter_by_user(self, cli_runner, db_session_factory, populated_logger):
        """Test list with user filter."""
        with patch("infrafoundry.cli.commands.audit.list.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(audit, ["list", "--user", "testuser"])

        assert result.exit_code == 0

    def test_list_filter_by_action(self, cli_runner, db_session_factory, populated_logger):
        """Test list with action filter."""
        with patch("infrafoundry.cli.commands.audit.list.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(audit, ["list", "--action", "apply_completed"])

        assert result.exit_code == 0

    def test_list_with_limit(self, cli_runner, db_session_factory, populated_logger):
        """Test list with limit option."""
        with patch("infrafoundry.cli.commands.audit.list.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(audit, ["list", "--limit", "1"])

        assert result.exit_code == 0

    def test_list_with_date_filter(self, cli_runner, db_session_factory, populated_logger):
        """Test list with date range filter."""
        with patch("infrafoundry.cli.commands.audit.list.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(audit, ["list", "--since", "2020-01-01"])

        assert result.exit_code == 0

    def test_list_invalid_date_format(self, cli_runner, db_session_factory):
        """Test list with invalid date format."""
        with patch("infrafoundry.cli.commands.audit.list.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(audit, ["list", "--since", "invalid-date"])

        assert result.exit_code != 0


class TestAuditExportCommand:
    """Tests for infra audit export command."""

    def test_export_requires_output(self, cli_runner):
        """Test export requires --output option."""
        result = cli_runner.invoke(audit, ["export"])
        assert result.exit_code != 0
        assert "output" in result.output.lower() or "required" in result.output.lower()

    def test_export_json(self, cli_runner, db_session_factory, populated_logger, tmp_path):
        """Test export to JSON format."""
        output_file = tmp_path / "audit.json"

        with patch("infrafoundry.cli.commands.audit.export.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(
                audit, ["export", "--format", "json", "--output", str(output_file)]
            )

        assert result.exit_code == 0
        assert output_file.exists()

    def test_export_csv(self, cli_runner, db_session_factory, populated_logger, tmp_path):
        """Test export to CSV format."""
        output_file = tmp_path / "audit.csv"

        with patch("infrafoundry.cli.commands.audit.export.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(
                audit, ["export", "--format", "csv", "--output", str(output_file)]
            )

        assert result.exit_code == 0
        assert output_file.exists()

    def test_export_with_filters(self, cli_runner, db_session_factory, populated_logger, tmp_path):
        """Test export with filters applied."""
        output_file = tmp_path / "audit.json"

        with patch("infrafoundry.cli.commands.audit.export.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(
                audit,
                [
                    "export",
                    "--output",
                    str(output_file),
                    "--env",
                    "prod",
                    "--since",
                    "2020-01-01",
                ],
            )

        assert result.exit_code == 0

    def test_export_no_entries_warning(self, cli_runner, db_session_factory, tmp_path):
        """Test export with no matching entries shows warning."""
        output_file = tmp_path / "audit.json"

        with patch("infrafoundry.cli.commands.audit.export.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(
                audit, ["export", "--output", str(output_file), "--env", "nonexistent"]
            )

        assert result.exit_code == 0
        assert "No audit entries found" in result.output


class TestAuditVerifyCommand:
    """Tests for infra audit verify command."""

    def test_verify_requires_entry_id(self, cli_runner):
        """Test verify requires entry ID argument."""
        result = cli_runner.invoke(audit, ["verify"])
        assert result.exit_code != 0

    def test_verify_valid_entry(self, cli_runner, db_session_factory, populated_logger):
        """Test verify with valid entry."""
        # Get an entry ID
        entries = populated_logger.query(limit=1)
        entry_id = entries[0].id

        with patch("infrafoundry.cli.commands.audit.verify.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(audit, ["verify", str(entry_id)])

        assert result.exit_code == 0
        assert "PASSED" in result.output or "not been tampered" in result.output

    def test_verify_nonexistent_entry(self, cli_runner, db_session_factory):
        """Test verify with nonexistent entry ID."""
        with patch("infrafoundry.cli.commands.audit.verify.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(audit, ["verify", "99999"])

        assert result.exit_code != 0
        assert "not found" in result.output

    def test_verify_tampered_entry(self, cli_runner, db_session_factory, populated_logger):
        """Test verify detects tampered entry."""
        # Get an entry and tamper with it
        entries = populated_logger.query(limit=1)
        entry_id = entries[0].id

        # Tamper with the entry directly in database
        with db_session_factory() as session:
            entry = session.query(AuditEntry).filter(AuditEntry.id == entry_id).first()
            entry.environment = "tampered"
            session.commit()

        with patch("infrafoundry.cli.commands.audit.verify.StateManager") as mock_sm:
            mock_instance = MagicMock()
            mock_instance.SessionLocal = db_session_factory
            mock_sm.return_value = mock_instance

            result = cli_runner.invoke(audit, ["verify", str(entry_id)])

        assert result.exit_code != 0
        assert "FAILED" in result.output or "modified" in result.output
