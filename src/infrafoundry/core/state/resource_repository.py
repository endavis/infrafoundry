"""Repository for resource operations."""

from typing import Any

from infrafoundry.core.state.models import Resource, ResourceDependency, ResourceState
from infrafoundry.core.types import ResourceTrackingMetadata


class ResourceRepository:
    """Handles all resource-related database operations."""

    def __init__(self, session_factory):
        """Initialize repository with SQLAlchemy session factory.

        Args:
            session_factory: SQLAlchemy sessionmaker instance
        """
        self.SessionLocal = session_factory

    def track(
        self,
        deployment_id: int,
        environment: str,
        provider: str,
        resource_type: str,
        name: str,
        state: ResourceState,
        config: dict[str, Any] | None = None,
        terraform_id: str | None = None,
        metadata: ResourceTrackingMetadata | None = None,
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

    def update_state(
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

    def update(self, resource_id: int, terraform_id: str) -> None:
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

    def add_dependency(
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

    def get_all(
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

    def get_by_name(self, environment: str, provider: str, name: str) -> Resource | None:
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
