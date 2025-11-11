"""Refactored state manager - thin coordinator delegating to repositories."""

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infrafoundry.core.base_manager import BaseManager
from infrafoundry.core.state.deployment_repository import DeploymentRepository
from infrafoundry.core.state.models import (
    Base,
    Deployment,
    DeploymentStatus,
    Resource,
    ResourceState,
)
from infrafoundry.core.state.resource_repository import ResourceRepository


class StateManager(BaseManager):
    """Manages infrastructure state and deployment history.

    Coordinates between DeploymentRepository and ResourceRepository.
    Thin wrapper that delegates most operations to specialized repositories.
    """

    def __init__(self, connection_string: str | None = None):
        """Initialize state manager.

        Args:
            connection_string: Database connection string. If None, uses SQLite in default location.
        """
        # Initialize base manager with logging
        super().__init__()

        if connection_string is None:
            state_dir = Path.home() / ".infrafoundry"
            state_dir.mkdir(parents=True, exist_ok=True)
            connection_string = f"sqlite:///{state_dir / 'state.db'}"

        self._log_debug(f"Initializing StateManager with connection: {connection_string}")
        self.engine = create_engine(connection_string)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Initialize repositories
        self.deployments = DeploymentRepository(self.SessionLocal)
        self.resources = ResourceRepository(self.SessionLocal)
        self._log_debug("StateManager initialized successfully")

    def initialize(self) -> None:
        """Initialize database schema."""
        self._log_debug("Initializing database schema")
        Base.metadata.create_all(self.engine)
        self._log_info("Database schema initialized")

    # Deployment operations - delegate to DeploymentRepository
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
        return self.deployments.create(
            environment=environment,
            command=command,
            user=user,
            commit_sha=commit_sha,
            dry_run=dry_run,
            metadata=metadata,
        )

    def update_deployment_status(
        self, deployment_id: int, status: DeploymentStatus, error_message: str | None = None
    ) -> None:
        """Update deployment status.

        Args:
            deployment_id: ID of deployment to update
            status: New status
            error_message: Error message if failed
        """
        self.deployments.update_status(deployment_id, status, error_message)

    def update_deployment_rollback_data(
        self, deployment_id: int, rollback_data: dict[str, Any]
    ) -> None:
        """Update deployment with rollback data.

        Args:
            deployment_id: Deployment ID
            rollback_data: Configuration snapshot for rollback
        """
        self.deployments.update_rollback_data(deployment_id, rollback_data)

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
        return self.deployments.get_history(
            environment=environment,
            command=command,
            status=status,
            limit=limit,
            exclude_dry_run=exclude_dry_run,
        )

    def get_rollback_points(self, environment: str, limit: int = 10) -> list[Deployment]:
        """Get available rollback points for an environment.

        Args:
            environment: Environment name
            limit: Maximum number of rollback points

        Returns:
            List of successful apply deployments with rollback data
        """
        return self.deployments.get_rollback_points(environment, limit)

    def get_deployment_by_id(self, deployment_id: int) -> Deployment | None:
        """Get deployment by ID.

        Args:
            deployment_id: Deployment ID

        Returns:
            Deployment object or None
        """
        return self.deployments.get_by_id(deployment_id)

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
        self.deployments.log_event(deployment_id, event_type, message, resource_name, metadata)

    # Resource operations - delegate to ResourceRepository
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
        return self.resources.track(
            deployment_id=deployment_id,
            environment=environment,
            provider=provider,
            resource_type=resource_type,
            name=name,
            state=state,
            config=config,
            terraform_id=terraform_id,
            metadata=metadata,
        )

    def update_resource_state(
        self, resource_id: int, state: ResourceState, terraform_id: str | None = None
    ) -> None:
        """Update resource state.

        Args:
            resource_id: Resource ID to update
            state: New state
            terraform_id: Updated Terraform ID
        """
        self.resources.update_state(resource_id, state, terraform_id)

    def update_resource(self, resource_id: int, terraform_id: str) -> None:
        """Update resource with Terraform ID.

        Args:
            resource_id: Resource ID to update
            terraform_id: Terraform resource address
        """
        self.resources.update(resource_id, terraform_id)

    def add_resource_dependency(
        self, resource_id: int, depends_on_id: int, dependency_type: str = "explicit"
    ) -> None:
        """Add a dependency between resources.

        Args:
            resource_id: Resource that depends on another
            depends_on_id: Resource that is depended upon
            dependency_type: Type of dependency
        """
        self.resources.add_dependency(resource_id, depends_on_id, dependency_type)

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
        return self.resources.get_all(environment, provider, resource_type, state)

    def get_resource_by_name(self, environment: str, provider: str, name: str) -> Resource | None:
        """Get a resource by its unique identifiers.

        Args:
            environment: Environment name
            provider: Provider name
            name: Resource name

        Returns:
            Resource object or None
        """
        return self.resources.get_by_name(environment, provider, name)

    def cleanup(self) -> None:
        """Cleanup database resources (required by BaseManager).

        Closes database engine and releases connections.
        """
        if hasattr(self, "engine"):
            self._log_debug("Disposing database engine")
            self.engine.dispose()
            self._log_debug("StateManager cleanup complete")
