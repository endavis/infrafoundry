"""Tests for audit logger service."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infrafoundry.core.audit.logger import AuditLogger
from infrafoundry.core.audit.models import AuditEntry, AuditStatus
from infrafoundry.core.events import Event, EventContext, EventType
from infrafoundry.core.state.models import Base


@pytest.fixture
def db_session_factory():
    """Create an in-memory SQLite database session factory."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    yield session_local
    engine.dispose()


@pytest.fixture
def audit_logger(db_session_factory):
    """Create an AuditLogger instance for testing."""
    return AuditLogger(
        session_factory=db_session_factory,
        get_current_user=lambda: "testuser",
    )


class TestAuditLoggerInit:
    """Tests for AuditLogger initialization."""

    def test_init_with_defaults(self, db_session_factory):
        """Test initializing audit logger with default user getter."""
        logger = AuditLogger(session_factory=db_session_factory)
        assert logger is not None

    def test_init_with_custom_user_getter(self, db_session_factory):
        """Test initializing with custom user getter."""
        logger = AuditLogger(
            session_factory=db_session_factory,
            get_current_user=lambda: "custom_user",
        )
        entry = logger.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
        )
        assert entry.user_identifier == "custom_user"

    def test_init_with_event_bus(self, db_session_factory):
        """Test initializing with event bus subscribes to events."""
        mock_event_bus = MagicMock()
        logger = AuditLogger(
            session_factory=db_session_factory,
            event_bus=mock_event_bus,
        )
        # Should have subscribed to all AUDITED_EVENTS
        assert mock_event_bus.subscribe.call_count == len(logger.AUDITED_EVENTS)


class TestAuditLoggerLog:
    """Tests for AuditLogger.log method."""

    def test_log_basic_entry(self, audit_logger):
        """Test logging a basic audit entry."""
        entry = audit_logger.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
        )

        assert entry.id is not None
        assert entry.event_type == "after_plan"
        assert entry.action == "plan_completed"
        assert entry.status == "success"
        assert entry.user_identifier == "testuser"
        assert entry.checksum is not None

    def test_log_with_all_fields(self, audit_logger):
        """Test logging with all optional fields."""
        entry = audit_logger.log(
            event_type=EventType.AFTER_APPLY,
            action="apply_completed",
            status=AuditStatus.SUCCESS,
            environment="prod",
            command="apply",
            provider="proxmox",
            resource_name="web-server",
            resource_type="vms",
            message="Applied successfully",
            changes_summary={"added": 1},
            request_metadata={"args": ["--env", "prod"]},
        )

        assert entry.environment == "prod"
        assert entry.provider == "proxmox"
        assert entry.resource_name == "web-server"
        assert entry.message == "Applied successfully"

    def test_log_derives_command_from_action(self, audit_logger):
        """Test that command is derived from action if not provided."""
        for action, expected_cmd in [
            ("plan_started", "plan"),
            ("apply_completed", "apply"),
            ("destroy_failed", "destroy"),
            ("drift_detected", "drift"),
        ]:
            entry = audit_logger.log(
                event_type=EventType.AFTER_PLAN,
                action=action,
                status=AuditStatus.SUCCESS,
            )
            assert entry.command == expected_cmd

    def test_log_creates_checksum(self, audit_logger):
        """Test that logging creates a valid checksum."""
        entry = audit_logger.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
            environment="dev",
        )

        assert entry.checksum is not None
        assert len(entry.checksum) == 64  # SHA-256 hex length


class TestAuditLoggerQuery:
    """Tests for AuditLogger.query method."""

    def test_query_returns_entries(self, audit_logger):
        """Test basic query returns entries."""
        # Create some entries
        for _ in range(5):
            audit_logger.log(
                event_type=EventType.AFTER_PLAN,
                action="plan_completed",
                status=AuditStatus.SUCCESS,
            )

        entries = audit_logger.query()
        assert len(entries) == 5

    def test_query_with_limit(self, audit_logger):
        """Test query respects limit parameter."""
        for _ in range(10):
            audit_logger.log(
                event_type=EventType.AFTER_PLAN,
                action="plan_completed",
                status=AuditStatus.SUCCESS,
            )

        entries = audit_logger.query(limit=5)
        assert len(entries) == 5

    def test_query_by_environment(self, audit_logger):
        """Test filtering query by environment."""
        audit_logger.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
            environment="dev",
        )
        audit_logger.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
            environment="prod",
        )

        dev_entries = audit_logger.query(env="dev")
        assert len(dev_entries) == 1
        assert dev_entries[0].environment == "dev"

    def test_query_by_user(self, db_session_factory):
        """Test filtering query by user."""
        logger1 = AuditLogger(
            session_factory=db_session_factory,
            get_current_user=lambda: "alice",
        )
        logger2 = AuditLogger(
            session_factory=db_session_factory,
            get_current_user=lambda: "bob",
        )

        logger1.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
        )
        logger2.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
        )

        alice_entries = logger1.query(user="alice")
        assert len(alice_entries) == 1
        assert alice_entries[0].user_identifier == "alice"

    def test_query_by_action(self, audit_logger):
        """Test filtering query by action."""
        audit_logger.log(
            event_type=EventType.BEFORE_PLAN,
            action="plan_started",
            status=AuditStatus.IN_PROGRESS,
        )
        audit_logger.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
        )

        entries = audit_logger.query(action="plan_completed")
        assert len(entries) == 1
        assert entries[0].action == "plan_completed"

    def test_query_by_date_range(self, audit_logger):
        """Test filtering query by date range."""
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        audit_logger.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
        )

        # Query with date range that includes now
        entries = audit_logger.query(start_date=yesterday, end_date=tomorrow)
        assert len(entries) == 1

        # Query with date range in the past
        past_entries = audit_logger.query(
            start_date=yesterday - timedelta(days=10),
            end_date=yesterday,
        )
        assert len(past_entries) == 0

    def test_query_with_offset(self, audit_logger):
        """Test query with offset for pagination."""
        for i in range(5):
            audit_logger.log(
                event_type=EventType.AFTER_PLAN,
                action=f"action_{i}",
                status=AuditStatus.SUCCESS,
            )

        entries = audit_logger.query(limit=2, offset=2)
        assert len(entries) == 2

    def test_query_returns_ordered_by_timestamp_desc(self, audit_logger):
        """Test that query returns entries ordered by timestamp descending."""
        for i in range(3):
            audit_logger.log(
                event_type=EventType.AFTER_PLAN,
                action=f"action_{i}",
                status=AuditStatus.SUCCESS,
            )

        entries = audit_logger.query()
        # Most recent should be first
        assert entries[0].action == "action_2"


class TestAuditLoggerGetById:
    """Tests for AuditLogger.get_by_id method."""

    def test_get_by_id_returns_entry(self, audit_logger):
        """Test getting an entry by ID."""
        created = audit_logger.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
        )

        fetched = audit_logger.get_by_id(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_by_id_returns_none_for_nonexistent(self, audit_logger):
        """Test that get_by_id returns None for nonexistent ID."""
        result = audit_logger.get_by_id(99999)
        assert result is None


class TestAuditLoggerVerifyIntegrity:
    """Tests for AuditLogger.verify_integrity method."""

    def test_verify_integrity_valid_entry(self, audit_logger):
        """Test verifying integrity of a valid entry."""
        entry = audit_logger.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
            environment="dev",
        )

        assert audit_logger.verify_integrity(entry.id) is True

    def test_verify_integrity_tampered_entry(self, audit_logger, db_session_factory):
        """Test detecting tampered entry."""
        entry = audit_logger.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
            environment="dev",
        )

        # Tamper with the entry directly in DB
        with db_session_factory() as session:
            db_entry = session.query(AuditEntry).filter(AuditEntry.id == entry.id).first()
            db_entry.environment = "prod"  # Change environment
            session.commit()

        # Integrity check should fail
        assert audit_logger.verify_integrity(entry.id) is False

    def test_verify_integrity_nonexistent_entry(self, audit_logger):
        """Test verifying nonexistent entry returns False."""
        assert audit_logger.verify_integrity(99999) is False

    def test_verify_integrity_entry_without_checksum(self, audit_logger, db_session_factory):
        """Test verifying entry without checksum returns False."""
        entry = audit_logger.log(
            event_type=EventType.AFTER_PLAN,
            action="plan_completed",
            status=AuditStatus.SUCCESS,
        )

        # Remove checksum directly in DB
        with db_session_factory() as session:
            db_entry = session.query(AuditEntry).filter(AuditEntry.id == entry.id).first()
            db_entry.checksum = None
            session.commit()

        assert audit_logger.verify_integrity(entry.id) is False


class TestAuditLoggerEventHandling:
    """Tests for AuditLogger event handling."""

    def test_handle_event_creates_entry(self, db_session_factory):
        """Test that handling an event creates an audit entry."""
        logger = AuditLogger(
            session_factory=db_session_factory,
            get_current_user=lambda: "testuser",
        )

        event = Event(
            context=EventContext(
                event_type=EventType.AFTER_PLAN,
                environment="dev",
                provider="proxmox",
            )
        )
        logger._handle_event(event)

        entries = logger.query()
        assert len(entries) == 1
        assert entries[0].action == "plan_completed"
        assert entries[0].environment == "dev"
        assert entries[0].status == "success"

    def test_handle_event_sets_status_based_on_event_type(self, db_session_factory):
        """Test that status is correctly set based on event type."""
        logger = AuditLogger(
            session_factory=db_session_factory,
            get_current_user=lambda: "testuser",
        )

        test_cases = [
            (EventType.BEFORE_PLAN, "in_progress"),
            (EventType.AFTER_PLAN, "success"),
            (EventType.PLAN_FAILED, "failed"),
            (EventType.BEFORE_APPLY, "in_progress"),
            (EventType.AFTER_APPLY, "success"),
            (EventType.APPLY_FAILED, "failed"),
        ]

        for event_type, _expected_status in test_cases:
            event = Event(
                context=EventContext(
                    event_type=event_type,
                    environment="dev",
                )
            )
            logger._handle_event(event)

        entries = logger.query(limit=100)
        statuses = {(e.action, e.status) for e in entries}

        assert ("plan_started", "in_progress") in statuses
        assert ("plan_completed", "success") in statuses
        assert ("plan_failed", "failed") in statuses

    def test_handle_event_extracts_message_from_data(self, db_session_factory):
        """Test that message is extracted from event data."""
        logger = AuditLogger(
            session_factory=db_session_factory,
            get_current_user=lambda: "testuser",
        )

        event = Event(
            context=EventContext(
                event_type=EventType.APPLY_FAILED,
                environment="dev",
                data={"error": "Connection timeout"},
            )
        )
        logger._handle_event(event)

        entries = logger.query()
        assert entries[0].message == "Connection timeout"

    def test_handle_event_skips_unaudited_events(self, db_session_factory):
        """Test that unaudited events are skipped."""
        logger = AuditLogger(
            session_factory=db_session_factory,
            get_current_user=lambda: "testuser",
        )

        # RESOURCE_CREATED is not in AUDITED_EVENTS
        event = Event(
            context=EventContext(
                event_type=EventType.RESOURCE_CREATED,
                environment="dev",
            )
        )
        logger._handle_event(event)

        entries = logger.query()
        assert len(entries) == 0


class TestAuditLoggerHelpers:
    """Tests for AuditLogger helper methods."""

    def test_default_get_user(self, db_session_factory):
        """Test default user getter from environment."""
        with patch.dict("os.environ", {"USER": "envuser"}):
            logger = AuditLogger(session_factory=db_session_factory)
            assert logger._default_get_user() == "envuser"

    def test_default_get_user_fallback_username(self, db_session_factory, monkeypatch):
        """Test default user getter fallback to USERNAME."""
        monkeypatch.delenv("USER", raising=False)
        monkeypatch.setenv("USERNAME", "winuser")
        logger = AuditLogger(session_factory=db_session_factory)
        assert logger._default_get_user() == "winuser"

    def test_default_get_user_unknown(self, db_session_factory, monkeypatch):
        """Test default user getter returns unknown when no env vars."""
        monkeypatch.delenv("USER", raising=False)
        monkeypatch.delenv("USERNAME", raising=False)
        logger = AuditLogger(session_factory=db_session_factory)
        assert logger._default_get_user() == "unknown"

    def test_get_ip_address(self, audit_logger):
        """Test getting local IP address."""
        ip = audit_logger._get_ip_address()
        # Should return a valid IP or None
        if ip:
            assert isinstance(ip, str)

    def test_calculate_checksum_deterministic(self, audit_logger):
        """Test that checksum calculation is deterministic."""
        entry = AuditEntry(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            event_type="after_plan",
            user_identifier="testuser",
            environment="dev",
            action="plan_completed",
            status="success",
        )

        checksum1 = audit_logger._calculate_checksum(entry)
        checksum2 = audit_logger._calculate_checksum(entry)

        assert checksum1 == checksum2

    def test_calculate_checksum_different_for_different_data(self, audit_logger):
        """Test that checksum differs for different data."""
        entry1 = AuditEntry(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            event_type="after_plan",
            user_identifier="testuser",
            environment="dev",
            action="plan_completed",
            status="success",
        )
        entry2 = AuditEntry(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            event_type="after_plan",
            user_identifier="testuser",
            environment="prod",  # Different environment
            action="plan_completed",
            status="success",
        )

        assert audit_logger._calculate_checksum(entry1) != audit_logger._calculate_checksum(entry2)

    def test_cleanup(self, audit_logger):
        """Test cleanup method runs without error."""
        audit_logger.cleanup()  # Should not raise
