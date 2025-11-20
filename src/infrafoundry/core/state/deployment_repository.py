"""Repository for deployment operations."""

from datetime import datetime

from infrafoundry.core.state.models import Deployment, DeploymentEvent, DeploymentStatus
from infrafoundry.core.types import DeploymentMetadata, ResourceTrackingMetadata, RollbackData


class DeploymentRepository:
    """Handles all deployment-related database operations."""

    def __init__(self, session_factory):
        """Initialize repository with SQLAlchemy session factory.

        Args:
            session_factory: SQLAlchemy sessionmaker instance
        """
        self.SessionLocal = session_factory

    def create(
        self,
        environment: str,
        command: str,
        user: str | None = None,
        commit_sha: str | None = None,
        dry_run: bool = False,
        metadata: DeploymentMetadata | None = None,
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
            return deployment.id

    def update_status(
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

    def update_rollback_data(self, deployment_id: int, rollback_data: RollbackData) -> None:
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

    def get_history(
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

    def get_by_id(self, deployment_id: int) -> Deployment | None:
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

    def log_event(
        self,
        deployment_id: int,
        event_type: str,
        message: str,
        resource_name: str | None = None,
        metadata: ResourceTrackingMetadata | None = None,
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
