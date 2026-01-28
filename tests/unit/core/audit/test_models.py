"""Tests for audit trail models."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infrafoundry.core.audit.models import AuditEntry, AuditStatus
from infrafoundry.core.state.models import Base


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    session = session_local()
    yield session
    session.close()
    engine.dispose()


class TestAuditStatus:
    """Tests for AuditStatus enum."""

    def test_status_values(self):
        """Test that all expected status values exist."""
        assert AuditStatus.SUCCESS.value == "success"
        assert AuditStatus.FAILED.value == "failed"
        assert AuditStatus.IN_PROGRESS.value == "in_progress"

    def test_status_is_string_enum(self):
        """Test that AuditStatus is a string enum."""
        assert isinstance(AuditStatus.SUCCESS, str)
        assert AuditStatus.SUCCESS == "success"


class TestAuditEntry:
    """Tests for AuditEntry model."""

    def test_create_audit_entry(self, db_session):
        """Test creating a basic audit entry."""
        entry = AuditEntry(
            timestamp=datetime.now(UTC),
            event_type="before_apply",
            user_identifier="testuser",
            environment="dev",
            command="apply",
            action="apply_started",
            status="in_progress",
        )
        db_session.add(entry)
        db_session.commit()

        assert entry.id is not None
        assert entry.event_type == "before_apply"
        assert entry.user_identifier == "testuser"
        assert entry.environment == "dev"

    def test_create_audit_entry_with_all_fields(self, db_session):
        """Test creating an audit entry with all optional fields."""
        entry = AuditEntry(
            timestamp=datetime.now(UTC),
            event_type="after_apply",
            user_identifier="admin",
            environment="prod",
            command="apply",
            provider="proxmox",
            resource_name="web-server-1",
            resource_type="vms",
            action="apply_completed",
            status="success",
            message="Applied 5 resources successfully",
            ip_address="192.168.1.100",
            changes_summary={"added": 3, "changed": 2, "destroyed": 0},
            request_metadata={"cli_args": ["apply", "--env", "prod"]},
            checksum="abc123def456",
        )
        db_session.add(entry)
        db_session.commit()

        assert entry.provider == "proxmox"
        assert entry.resource_name == "web-server-1"
        assert entry.changes_summary["added"] == 3
        assert entry.request_metadata["cli_args"] == ["apply", "--env", "prod"]

    def test_to_dict(self, db_session):
        """Test converting audit entry to dictionary."""
        timestamp = datetime.now(UTC)
        entry = AuditEntry(
            timestamp=timestamp,
            event_type="after_plan",
            user_identifier="testuser",
            environment="dev",
            action="plan_completed",
            status="success",
        )
        db_session.add(entry)
        db_session.commit()

        entry_dict = entry.to_dict()

        assert entry_dict["id"] == entry.id
        # SQLite stores timestamps without timezone, so compare without timezone
        assert entry_dict["timestamp"].startswith(timestamp.replace(tzinfo=None).isoformat()[:19])
        assert entry_dict["event_type"] == "after_plan"
        assert entry_dict["user_identifier"] == "testuser"
        assert entry_dict["environment"] == "dev"
        assert entry_dict["action"] == "plan_completed"
        assert entry_dict["status"] == "success"

    def test_to_dict_with_none_timestamp(self, db_session):
        """Test to_dict handles None timestamp gracefully."""
        entry = AuditEntry(
            event_type="test",
            user_identifier="testuser",
            action="test_action",
            status="success",
        )
        # Don't set timestamp to test None handling
        entry.timestamp = None  # type: ignore
        entry_dict = entry.to_dict()
        assert entry_dict["timestamp"] is None

    def test_repr(self, db_session):
        """Test audit entry string representation."""
        entry = AuditEntry(
            timestamp=datetime.now(UTC),
            event_type="after_apply",
            user_identifier="admin",
            environment="prod",
            action="apply_completed",
            status="success",
        )
        db_session.add(entry)
        db_session.commit()

        repr_str = repr(entry)
        assert "AuditEntry" in repr_str
        assert "apply_completed" in repr_str
        assert "admin" in repr_str
        assert "prod" in repr_str

    def test_query_by_environment(self, db_session):
        """Test querying audit entries by environment."""
        # Create entries in different environments
        for env in ["dev", "staging", "prod", "dev"]:
            entry = AuditEntry(
                timestamp=datetime.now(UTC),
                event_type="after_apply",
                user_identifier="testuser",
                environment=env,
                action="apply_completed",
                status="success",
            )
            db_session.add(entry)
        db_session.commit()

        dev_entries = db_session.query(AuditEntry).filter(AuditEntry.environment == "dev").all()
        assert len(dev_entries) == 2

    def test_query_by_user(self, db_session):
        """Test querying audit entries by user identifier."""
        for user in ["alice", "bob", "alice"]:
            entry = AuditEntry(
                timestamp=datetime.now(UTC),
                event_type="after_plan",
                user_identifier=user,
                action="plan_completed",
                status="success",
            )
            db_session.add(entry)
        db_session.commit()

        alice_entries = (
            db_session.query(AuditEntry).filter(AuditEntry.user_identifier == "alice").all()
        )
        assert len(alice_entries) == 2

    def test_query_by_action(self, db_session):
        """Test querying audit entries by action."""
        for action in ["plan_started", "plan_completed", "apply_started", "apply_completed"]:
            entry = AuditEntry(
                timestamp=datetime.now(UTC),
                event_type="test",
                user_identifier="testuser",
                action=action,
                status="success",
            )
            db_session.add(entry)
        db_session.commit()

        plan_entries = db_session.query(AuditEntry).filter(AuditEntry.action.like("plan%")).all()
        assert len(plan_entries) == 2

    def test_nullable_fields(self, db_session):
        """Test that optional fields can be null."""
        entry = AuditEntry(
            timestamp=datetime.now(UTC),
            event_type="test",
            user_identifier="testuser",
            action="test_action",
            status="success",
            # All optional fields left as None
        )
        db_session.add(entry)
        db_session.commit()

        assert entry.environment is None
        assert entry.command is None
        assert entry.provider is None
        assert entry.resource_name is None
        assert entry.resource_type is None
        assert entry.message is None
        assert entry.ip_address is None
        assert entry.changes_summary is None
        assert entry.request_metadata is None
        assert entry.checksum is None
