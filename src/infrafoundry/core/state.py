"""State management for InfraFoundry.

Tracks deployment history, resource state, and metadata across environments.
Supports both SQLite (local) and PostgreSQL (teams) backends.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

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


class StateManager:
    """Manages infrastructure state and deployment history."""

    def __init__(self, connection_string: str | None = None):
        """Initialize state manager.

        Args:
            connection_string: Database connection string. If None, uses SQLite in default location.
        """
        if connection_string is None:
            state_dir = Path.home() / ".infrafoundry"
            state_dir.mkdir(parents=True, exist_ok=True)
            connection_string = f"sqlite:///{state_dir / 'state.db'}"

        self.engine = create_engine(connection_string)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def initialize(self) -> None:
        """Initialize database schema."""
        Base.metadata.create_all(self.engine)

    def create_deployment(
        self,
        environment: str,
        command: str,
        user: str | None = None,
        commit_sha: str | None = None,
        dry_run: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Create a new deployment record.

        Args:
            environment: Environment name
            command: Command being executed (plan, apply, destroy)
            user: User executing the deployment
            commit_sha: Git commit SHA
            dry_run: Whether this is a dry run
            metadata: Additional metadata

        Returns:
            ID of created deployment
        """
        with self.SessionLocal() as session:
            deployment = Deployment(
                environment=environment,
                command=command,
                status=DeploymentStatus.IN_PROGRESS,
                user=user,
                commit_sha=commit_sha,
                dry_run=dry_run,
                extra_data=metadata,
            )
            session.add(deployment)
            session.commit()
            session.refresh(deployment)
            deployment_id = deployment.id
            return deployment_id

    def update_deployment_status(
        self, deployment_id: int, status: DeploymentStatus, error_message: str | None = None
    ) -> None:
        """Update deployment status.

        Args:
            deployment_id: ID of deployment to update
            status: New status
            error_message: Error message if failed
        """
        with self.SessionLocal() as session:
            deployment = session.query(Deployment).filter_by(id=deployment_id).first()
            if deployment:
                deployment.status = status
                deployment.completed_at = datetime.utcnow()
                if error_message:
                    deployment.error_message = error_message
                session.commit()

    def update_deployment_rollback_data(
        self, deployment_id: int, rollback_data: dict[str, Any]
    ) -> None:
        """Update deployment with rollback data.

        Args:
            deployment_id: Deployment ID
            rollback_data: Configuration snapshot for rollback
        """
        with self.SessionLocal() as session:
            deployment = session.query(Deployment).filter_by(id=deployment_id).first()
            if deployment:
                deployment.rollback_data = rollback_data
                session.commit()

    def track_resource(
        self,
        deployment_id: int,
        environment: str,
        provider: str,
        resource_type: str,
        name: str,
        state: ResourceState,
        config: dict[str, Any] | None = None,
        terraform_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Resource:
        """Track a resource.

        Args:
            deployment_id: Associated deployment ID
            environment: Environment name
            provider: Provider name
            resource_type: Type of resource
            name: Resource name
            state: Current state
            config: Resource configuration
            terraform_id: Terraform resource identifier
            metadata: Additional metadata

        Returns:
            Created Resource object
        """
        with self.SessionLocal() as session:
            resource = Resource(
                deployment_id=deployment_id,
                environment=environment,
                provider=provider,
                resource_type=resource_type,
                name=name,
                state=state,
                config=config,
                terraform_id=terraform_id,
                extra_data=metadata,
            )
            session.add(resource)
            session.commit()
            session.refresh(resource)
            return resource

    def update_resource_state(
        self, resource_id: int, state: ResourceState, terraform_id: str | None = None
    ) -> None:
        """Update resource state.

        Args:
            resource_id: Resource ID to update
            state: New state
            terraform_id: Updated Terraform ID
        """
        with self.SessionLocal() as session:
            resource = session.query(Resource).filter_by(id=resource_id).first()
            if resource:
                resource.state = state
                if terraform_id:
                    resource.terraform_id = terraform_id
                session.commit()

    def update_resource(self, resource_id: int, terraform_id: str) -> None:
        """Update resource with Terraform ID.

        Args:
            resource_id: Resource ID to update
            terraform_id: Terraform resource address
        """
        with self.SessionLocal() as session:
            resource = session.query(Resource).filter_by(id=resource_id).first()
            if resource:
                resource.terraform_id = terraform_id
                session.commit()

    def add_resource_dependency(
        self, resource_id: int, depends_on_id: int, dependency_type: str = "explicit"
    ) -> None:
        """Add a dependency between resources.

        Args:
            resource_id: Resource that depends on another
            depends_on_id: Resource that is depended upon
            dependency_type: Type of dependency
        """
        with self.SessionLocal() as session:
            dependency = ResourceDependency(
                resource_id=resource_id,
                depends_on_id=depends_on_id,
                dependency_type=dependency_type,
            )
            session.add(dependency)
            session.commit()

    def log_event(
        self,
        deployment_id: int,
        event_type: str,
        message: str,
        resource_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a deployment event.

        Args:
            deployment_id: Associated deployment ID
            event_type: Type of event
            message: Event message
            resource_name: Related resource name
            metadata: Additional metadata
        """
        with self.SessionLocal() as session:
            event = DeploymentEvent(
                deployment_id=deployment_id,
                event_type=event_type,
                resource_name=resource_name,
                message=message,
                extra_data=metadata,
            )
            session.add(event)
            session.commit()

    def get_deployment_history(
        self,
        environment: str | None = None,
        command: str | None = None,
        status: DeploymentStatus | None = None,
        limit: int = 50,
        exclude_dry_run: bool = False,
    ) -> list[Deployment]:
        """Get deployment history.

        Args:
            environment: Filter by environment (None for all)
            command: Filter by command type (plan, apply, destroy)
            status: Filter by deployment status
            limit: Maximum number of records
            exclude_dry_run: If True, exclude dry-run deployments

        Returns:
            List of Deployment objects
        """
        with self.SessionLocal() as session:
            query = session.query(Deployment)
            if environment:
                query = query.filter_by(environment=environment)
            if command:
                query = query.filter_by(command=command)
            if status:
                query = query.filter_by(status=status)
            if exclude_dry_run:
                query = query.filter_by(dry_run=False)
            deployments = query.order_by(Deployment.started_at.desc()).limit(limit).all()
            # Detach from session
            session.expunge_all()
            return deployments

    def get_rollback_points(self, environment: str, limit: int = 10) -> list[Deployment]:
        """Get available rollback points for an environment.

        Args:
            environment: Environment name
            limit: Maximum number of rollback points

        Returns:
            List of successful apply deployments with rollback data
        """
        with self.SessionLocal() as session:
            query = (
                session.query(Deployment)
                .filter_by(
                    environment=environment,
                    command="apply",
                    status=DeploymentStatus.COMPLETED,
                    dry_run=False,
                )
                .filter(Deployment.rollback_data.isnot(None))
                .order_by(Deployment.completed_at.desc())
                .limit(limit)
            )
            deployments = query.all()
            session.expunge_all()
            return deployments

    def get_deployment_by_id(self, deployment_id: int) -> Deployment | None:
        """Get deployment by ID.

        Args:
            deployment_id: Deployment ID

        Returns:
            Deployment object or None
        """
        with self.SessionLocal() as session:
            deployment = session.query(Deployment).filter_by(id=deployment_id).first()
            if deployment:
                session.expunge(deployment)
            return deployment

    def get_resources(
        self,
        environment: str | None = None,
        provider: str | None = None,
        resource_type: str | None = None,
        state: ResourceState | None = None,
    ) -> list[Resource]:
        """Query resources with filters.

        Args:
            environment: Filter by environment
            provider: Filter by provider
            resource_type: Filter by resource type
            state: Filter by state

        Returns:
            List of Resource objects
        """
        with self.SessionLocal() as session:
            query = session.query(Resource)
            if environment:
                query = query.filter_by(environment=environment)
            if provider:
                query = query.filter_by(provider=provider)
            if resource_type:
                query = query.filter_by(resource_type=resource_type)
            if state:
                query = query.filter_by(state=state)
            resources = query.order_by(Resource.created_at.desc()).all()
            session.expunge_all()
            return resources

    def get_resource_by_name(self, environment: str, provider: str, name: str) -> Resource | None:
        """Get a resource by its unique identifiers.

        Args:
            environment: Environment name
            provider: Provider name
            name: Resource name

        Returns:
            Resource object or None
        """
        with self.SessionLocal() as session:
            resource = (
                session.query(Resource)
                .filter_by(environment=environment, provider=provider, name=name)
                .order_by(Resource.created_at.desc())
                .first()
            )
            if resource:
                session.expunge(resource)
            return resource
