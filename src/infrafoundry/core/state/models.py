"""Database models for state management."""

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


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

    id = Column(Integer, primary_key=True)
    environment = Column(String(100), nullable=False, index=True)
    command = Column(String(50), nullable=False)  # plan, apply, destroy
    status = Column(SQLEnum(DeploymentStatus), nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime)
    user = Column(String(100))
    commit_sha = Column(String(40))  # Git commit
    dry_run = Column(Boolean, default=False, nullable=False)  # Whether this was a dry run
    error_message = Column(Text)
    extra_data = Column(JSON)  # Renamed from metadata to avoid SQLAlchemy reserved word
    rollback_data = Column(JSON)  # Configuration snapshot for rollback

    # Relationships
    resources = relationship("Resource", back_populates="deployment")
    events = relationship("DeploymentEvent", back_populates="deployment")


class Resource(Base):
    """Tracked resource in infrastructure."""

    __tablename__ = "resources"

    id = Column(Integer, primary_key=True)
    deployment_id = Column(Integer, ForeignKey("deployments.id"), nullable=False)
    environment = Column(String(100), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    resource_type = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False, index=True)
    state = Column(SQLEnum(ResourceState), nullable=False)
    config = Column(JSON)  # Full resource configuration
    terraform_id = Column(String(500))  # Terraform resource ID
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime)
    extra_data = Column(JSON)  # Additional context

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

    id = Column(Integer, primary_key=True)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False)
    depends_on_id = Column(Integer, ForeignKey("resources.id"), nullable=False)
    dependency_type = Column(String(50))  # implicit, explicit, data

    # Relationships
    resource = relationship("Resource", foreign_keys=[resource_id], back_populates="dependencies")
    depends_on_resource = relationship(
        "Resource", foreign_keys=[depends_on_id], back_populates="dependents"
    )


class DeploymentEvent(Base):
    """Event that occurred during a deployment."""

    __tablename__ = "deployment_events"

    id = Column(Integer, primary_key=True)
    deployment_id = Column(Integer, ForeignKey("deployments.id"), nullable=False)
    event_type = Column(String(50), nullable=False)  # resource_created, validation_failed, etc.
    resource_name = Column(String(200))
    message = Column(Text)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    extra_data = Column(JSON)  # Additional context

    # Relationships
    deployment = relationship("Deployment", back_populates="events")
