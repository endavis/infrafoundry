"""Database models for state management."""

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class DeploymentStatus(str, Enum):
    """Status of a deployment."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ResourceState(str, Enum):
    """State of a resource."""

    PLANNED = "planned"
    CREATING = "creating"
    ACTIVE = "active"
    UPDATING = "updating"
    DELETING = "deleting"
    DELETED = "deleted"
    ERROR = "error"


class Deployment(Base):
    """Record of a deployment operation."""

    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    environment: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    command: Mapped[str] = mapped_column(String(50), nullable=False)  # plan, apply, destroy
    status: Mapped[DeploymentStatus] = mapped_column(SQLEnum(DeploymentStatus), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    user: Mapped[str | None] = mapped_column(String(100))
    commit_sha: Mapped[str | None] = mapped_column(String(40))  # Git commit
    dry_run: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # Whether this was a dry run
    error_message: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict | None] = mapped_column(
        JSON
    )  # Renamed from metadata to avoid SQLAlchemy reserved word
    rollback_data: Mapped[dict | None] = mapped_column(JSON)  # Configuration snapshot for rollback

    # Relationships
    resources = relationship("Resource", back_populates="deployment")
    events = relationship("DeploymentEvent", back_populates="deployment")


class Resource(Base):
    """Tracked resource in infrastructure."""

    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deployments.id"), nullable=False
    )
    environment: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    state: Mapped[ResourceState] = mapped_column(SQLEnum(ResourceState), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSON)  # Full resource configuration
    terraform_id: Mapped[str | None] = mapped_column(String(500))  # Terraform resource ID
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    extra_data: Mapped[dict | None] = mapped_column(JSON)  # Additional context

    # Relationships
    deployment = relationship("Deployment", back_populates="resources")
    dependencies = relationship(
        "ResourceDependency",
        foreign_keys="ResourceDependency.resource_id",
        back_populates="resource",
    )
    dependents = relationship(
        "ResourceDependency",
        foreign_keys="ResourceDependency.depends_on_id",
        back_populates="depends_on_resource",
    )


class ResourceDependency(Base):
    """Dependency relationship between resources."""

    __tablename__ = "resource_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_id: Mapped[int] = mapped_column(Integer, ForeignKey("resources.id"), nullable=False)
    depends_on_id: Mapped[int] = mapped_column(Integer, ForeignKey("resources.id"), nullable=False)
    dependency_type: Mapped[str | None] = mapped_column(String(50))  # implicit, explicit, data

    # Relationships
    resource = relationship("Resource", foreign_keys=[resource_id], back_populates="dependencies")
    depends_on_resource = relationship(
        "Resource", foreign_keys=[depends_on_id], back_populates="dependents"
    )


class DeploymentEvent(Base):
    """Event that occurred during a deployment."""

    __tablename__ = "deployment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deployments.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # resource_created, validation_failed, etc.
    resource_name: Mapped[str | None] = mapped_column(String(200))
    message: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    extra_data: Mapped[dict | None] = mapped_column(JSON)  # Additional context

    # Relationships
    deployment = relationship("Deployment", back_populates="events")
