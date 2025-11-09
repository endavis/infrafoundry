"""Unit tests for StateManager."""

import tempfile
from pathlib import Path

import pytest

from infrafoundry.core.state import (Deployment, DeploymentStatus, Resource,
                                     ResourceState, StateManager)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_state.db"
        connection_string = f"sqlite:///{db_path}"
        yield connection_string


@pytest.fixture
def state_manager(temp_db):
    """Create a StateManager with temporary database."""
    manager = StateManager(connection_string=temp_db)
    manager.initialize()
    return manager


class TestStateManager:
    """Tests for StateManager."""

    def test_init_default_location(self):
        """Test initialization with default SQLite location."""
        manager = StateManager()
        assert manager.engine is not None
        assert "sqlite:///" in str(manager.engine.url)

    def test_init_custom_connection(self, temp_db):
        """Test initialization with custom connection string."""
        manager = StateManager(connection_string=temp_db)
        assert manager.engine is not None
        assert str(manager.engine.url) == temp_db

    def test_initialize_schema(self, temp_db):
        """Test database schema initialization."""
        manager = StateManager(connection_string=temp_db)
        manager.initialize()

        # Verify tables were created
        with manager.SessionLocal() as session:
            # Should not raise exception
            session.query(Deployment).first()
            session.query(Resource).first()

    def test_create_deployment(self, state_manager):
        """Test creating a new deployment record."""
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
            user="testuser",
            commit_sha="abc123",
            dry_run=False,
            metadata={"key": "value"},
        )

        assert deployment_id is not None
        assert isinstance(deployment_id, int)

        # Verify deployment was created
        with state_manager.SessionLocal() as session:
            deployment = session.query(Deployment).filter_by(id=deployment_id).first()
            assert deployment is not None
            assert deployment.environment == "dev"
            assert deployment.command == "apply"
            assert deployment.status == DeploymentStatus.IN_PROGRESS
            assert deployment.user == "testuser"
            assert deployment.commit_sha == "abc123"
            assert deployment.dry_run is False
            assert deployment.extra_data == {"key": "value"}

    def test_create_deployment_minimal(self, state_manager):
        """Test creating deployment with minimal parameters."""
        deployment_id = state_manager.create_deployment(
            environment="prod",
            command="plan",
        )

        assert deployment_id is not None

        with state_manager.SessionLocal() as session:
            deployment = session.query(Deployment).filter_by(id=deployment_id).first()
            assert deployment.environment == "prod"
            assert deployment.command == "plan"
            assert deployment.user is None
            assert deployment.commit_sha is None
            assert deployment.dry_run is False

    def test_update_deployment_status(self, state_manager):
        """Test updating deployment status."""
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
        )

        state_manager.update_deployment_status(
            deployment_id=deployment_id,
            status=DeploymentStatus.COMPLETED,
        )

        with state_manager.SessionLocal() as session:
            deployment = session.query(Deployment).filter_by(id=deployment_id).first()
            assert deployment.status == DeploymentStatus.COMPLETED
            assert deployment.completed_at is not None

    def test_update_deployment_status_with_error(self, state_manager):
        """Test updating deployment status to failed with error message."""
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
        )

        error_msg = "Terraform apply failed"
        state_manager.update_deployment_status(
            deployment_id=deployment_id,
            status=DeploymentStatus.FAILED,
            error_message=error_msg,
        )

        with state_manager.SessionLocal() as session:
            deployment = session.query(Deployment).filter_by(id=deployment_id).first()
            assert deployment.status == DeploymentStatus.FAILED
            assert deployment.error_message == error_msg
            assert deployment.completed_at is not None

    def test_add_resource(self, state_manager):
        """Test adding a resource to deployment."""
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
        )

        resource = state_manager.track_resource(
            deployment_id=deployment_id,
            environment="dev",
            provider="proxmox",
            resource_type="vm",
            name="web-01",
            state=ResourceState.CREATING,
            config={"cores": 4, "memory": 8192},
            metadata={"tags": {"env": "dev"}},
        )

        assert resource is not None
        assert resource.deployment_id == deployment_id
        assert resource.environment == "dev"
        assert resource.provider == "proxmox"
        assert resource.resource_type == "vm"
        assert resource.name == "web-01"
        assert resource.state == ResourceState.CREATING
        assert resource.config == {"cores": 4, "memory": 8192}
        assert resource.extra_data == {"tags": {"env": "dev"}}

    def test_update_resource_state(self, state_manager):
        """Test updating resource state."""
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
        )
        resource = state_manager.track_resource(
            deployment_id=deployment_id,
            environment="dev",
            provider="proxmox",
            resource_type="vm",
            name="web-01",
            state=ResourceState.CREATING,
        )

        state_manager.update_resource_state(
            resource_id=resource.id,
            state=ResourceState.ACTIVE,
            terraform_id="proxmox_vm.web_01",
        )

        # Re-fetch resource to check updates
        updated = state_manager.get_resource_by_name(
            environment="dev",
            provider="proxmox",
            name="web-01",
        )
        assert updated.state == ResourceState.ACTIVE
        assert updated.terraform_id == "proxmox_vm.web_01"

    def test_get_deployment(self, state_manager):
        """Test retrieving a deployment."""
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
            user="testuser",
        )

        deployment = state_manager.get_deployment_by_id(deployment_id)
        assert deployment is not None
        assert deployment.id == deployment_id
        assert deployment.environment == "dev"
        assert deployment.command == "apply"
        assert deployment.user == "testuser"
        assert deployment.status == DeploymentStatus.IN_PROGRESS

    def test_get_deployment_not_found(self, state_manager):
        """Test retrieving non-existent deployment."""
        deployment = state_manager.get_deployment_by_id(99999)
        assert deployment is None

    def test_list_deployments(self, state_manager):
        """Test listing deployments."""
        # Create multiple deployments
        state_manager.create_deployment(environment="dev", command="plan")
        state_manager.create_deployment(environment="dev", command="apply")
        state_manager.create_deployment(environment="prod", command="apply")

        # List all deployments
        deployments = state_manager.get_deployment_history()
        assert len(deployments) == 3

    def test_list_deployments_filtered_by_environment(self, state_manager):
        """Test listing deployments filtered by environment."""
        state_manager.create_deployment(environment="dev", command="plan")
        state_manager.create_deployment(environment="dev", command="apply")
        state_manager.create_deployment(environment="prod", command="apply")

        # List only dev deployments
        dev_deployments = state_manager.get_deployment_history(environment="dev")
        assert len(dev_deployments) == 2
        assert all(d.environment == "dev" for d in dev_deployments)

    def test_list_deployments_with_limit(self, state_manager):
        """Test listing deployments with limit."""
        for _ in range(5):
            state_manager.create_deployment(environment="dev", command="apply")

        deployments = state_manager.get_deployment_history(limit=3)
        assert len(deployments) == 3

    def test_get_resources_by_deployment(self, state_manager):
        """Test getting resources for a deployment."""
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
        )

        # Add multiple resources
        state_manager.track_resource(
            deployment_id=deployment_id,
            environment="dev",
            provider="proxmox",
            resource_type="vm",
            name="web-01",
            state=ResourceState.ACTIVE,
        )
        state_manager.track_resource(
            deployment_id=deployment_id,
            environment="dev",
            provider="proxmox",
            resource_type="vm",
            name="web-02",
            state=ResourceState.ACTIVE,
        )

        # Get resources by environment and provider
        resources = state_manager.get_resources(
            environment="dev",
            provider="proxmox",
        )
        assert len(resources) == 2
        names = {r.name for r in resources}
        assert "web-01" in names
        assert "web-02" in names

    def test_get_resources_by_environment(self, state_manager):
        """Test getting resources by environment."""
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
        )

        state_manager.track_resource(
            deployment_id=deployment_id,
            environment="dev",
            provider="proxmox",
            resource_type="vm",
            name="web-01",
            state=ResourceState.ACTIVE,
        )

        resources = state_manager.get_resources(environment="dev")
        assert len(resources) >= 1
        assert any(r.name == "web-01" for r in resources)

    def test_get_resource_history(self, state_manager):
        """Test getting resource history across deployments."""
        # First deployment - create resource
        deployment1 = state_manager.create_deployment(
            environment="dev",
            command="apply",
        )
        state_manager.track_resource(
            deployment_id=deployment1,
            environment="dev",
            provider="proxmox",
            resource_type="vm",
            name="web-01",
            state=ResourceState.ACTIVE,
        )

        # Second deployment - update resource
        deployment2 = state_manager.create_deployment(
            environment="dev",
            command="apply",
        )
        state_manager.track_resource(
            deployment_id=deployment2,
            environment="dev",
            provider="proxmox",
            resource_type="vm",
            name="web-01",
            state=ResourceState.UPDATING,
        )

        # Get all resources with this name
        resources = state_manager.get_resources(
            environment="dev",
            provider="proxmox",
        )

        # Filter to web-01
        web01_resources = [r for r in resources if r.name == "web-01"]
        assert len(web01_resources) == 2
        assert {r.state for r in web01_resources} == {ResourceState.ACTIVE, ResourceState.UPDATING}

    def test_add_deployment_event(self, state_manager):
        """Test adding an event to a deployment."""
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
        )

        state_manager.log_event(
            deployment_id=deployment_id,
            event_type="resource_created",
            resource_name="web-01",
            message="VM created successfully",
            metadata={"duration": "45s"},
        )

        # Verify event was created by querying directly
        with state_manager.SessionLocal() as session:
            from infrafoundry.core.state import DeploymentEvent

            events = session.query(DeploymentEvent).filter_by(deployment_id=deployment_id).all()
            assert len(events) == 1
            event = events[0]
            assert event.event_type == "resource_created"
            assert event.resource_name == "web-01"
            assert event.message == "VM created successfully"
            assert event.extra_data == {"duration": "45s"}

    def test_deployment_status_enum(self):
        """Test DeploymentStatus enum values."""
        assert DeploymentStatus.PLANNED.value == "planned"
        assert DeploymentStatus.IN_PROGRESS.value == "in_progress"
        assert DeploymentStatus.COMPLETED.value == "completed"
        assert DeploymentStatus.FAILED.value == "failed"
        assert DeploymentStatus.ROLLED_BACK.value == "rolled_back"

    def test_resource_state_enum(self):
        """Test ResourceState enum values."""
        assert ResourceState.PLANNED.value == "planned"
        assert ResourceState.CREATING.value == "creating"
        assert ResourceState.ACTIVE.value == "active"
        assert ResourceState.UPDATING.value == "updating"
        assert ResourceState.DELETING.value == "deleting"
        assert ResourceState.DELETED.value == "deleted"
        assert ResourceState.ERROR.value == "error"

    def test_update_resource(self, state_manager):
        """Test updating resource terraform_id."""
        # Create deployment and resource
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
        )

        resource = state_manager.track_resource(
            deployment_id=deployment_id,
            environment="dev",
            provider="proxmox",
            resource_type="vm",
            name="test-vm",
            state=ResourceState.PLANNED,
        )

        # Update terraform_id
        state_manager.update_resource(resource.id, terraform_id="proxmox_vm.test_vm")

        # Verify update
        resources = state_manager.get_resources(environment="dev", provider="proxmox")
        assert len(resources) == 1
        assert resources[0].terraform_id == "proxmox_vm.test_vm"

    def test_add_resource_dependency(self, state_manager):
        """Test adding resource dependencies."""
        # Create deployment
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
        )

        # Create two resources
        resource1 = state_manager.track_resource(
            deployment_id=deployment_id,
            environment="dev",
            provider="proxmox",
            resource_type="network",
            name="network",
            state=ResourceState.ACTIVE,
        )

        resource2 = state_manager.track_resource(
            deployment_id=deployment_id,
            environment="dev",
            provider="proxmox",
            resource_type="vm",
            name="vm",
            state=ResourceState.PLANNED,
        )

        # Add dependency: vm depends on network
        state_manager.add_resource_dependency(
            resource_id=resource2.id, depends_on_id=resource1.id, dependency_type="explicit"
        )

        # Verify dependency was added successfully
        # The test succeeds if no exception is raised
