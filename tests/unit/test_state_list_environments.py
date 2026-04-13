"""Unit tests for list_environments on repositories and StateManager."""

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infrafoundry.core.state import (
    ResourceState,
    StateManager,
)
from infrafoundry.core.state.deployment_repository import DeploymentRepository
from infrafoundry.core.state.models import Base
from infrafoundry.core.state.resource_repository import ResourceRepository


@pytest.fixture
def temp_db():
    """Create a temporary database connection string."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_state.db"
        yield f"sqlite:///{db_path}"


@pytest.fixture
def session_factory(temp_db):
    """Create a session factory with initialized schema."""
    engine = create_engine(temp_db)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def resource_repo(session_factory) -> ResourceRepository:
    """Create a ResourceRepository."""
    return ResourceRepository(session_factory)


@pytest.fixture
def deployment_repo(session_factory) -> DeploymentRepository:
    """Create a DeploymentRepository."""
    return DeploymentRepository(session_factory)


@pytest.fixture
def state_manager(temp_db) -> StateManager:
    """Create and initialize a StateManager."""
    mgr = StateManager(connection_string=temp_db)
    mgr.initialize()
    return mgr


class TestResourceRepositoryListEnvironments:
    """Tests for ResourceRepository.list_environments."""

    def test_empty_db_returns_empty(self, resource_repo: ResourceRepository) -> None:
        """Empty DB returns empty list."""
        assert resource_repo.list_environments() == []

    def test_returns_distinct_sorted(
        self, resource_repo: ResourceRepository, deployment_repo: DeploymentRepository
    ) -> None:
        """Returns distinct, sorted environment names."""
        dep_id = deployment_repo.create("dev", "apply")
        resource_repo.track(dep_id, "prod", "proxmox", "vm", "a", ResourceState.ACTIVE)
        resource_repo.track(dep_id, "dev", "proxmox", "vm", "b", ResourceState.ACTIVE)
        resource_repo.track(dep_id, "prod", "proxmox", "vm", "c", ResourceState.ACTIVE)

        assert resource_repo.list_environments() == ["dev", "prod"]

    def test_count_by_environment(
        self, resource_repo: ResourceRepository, deployment_repo: DeploymentRepository
    ) -> None:
        """count_by_environment returns correct count."""
        dep_id = deployment_repo.create("dev", "apply")
        resource_repo.track(dep_id, "dev", "proxmox", "vm", "a", ResourceState.ACTIVE)
        resource_repo.track(dep_id, "dev", "proxmox", "vm", "b", ResourceState.ACTIVE)
        resource_repo.track(dep_id, "prod", "proxmox", "vm", "c", ResourceState.ACTIVE)

        assert resource_repo.count_by_environment("dev") == 2
        assert resource_repo.count_by_environment("prod") == 1
        assert resource_repo.count_by_environment("staging") == 0


class TestDeploymentRepositoryListEnvironments:
    """Tests for DeploymentRepository.list_environments."""

    def test_empty_db_returns_empty(self, deployment_repo: DeploymentRepository) -> None:
        """Empty DB returns empty list."""
        assert deployment_repo.list_environments() == []

    def test_returns_distinct_sorted(self, deployment_repo: DeploymentRepository) -> None:
        """Returns distinct, sorted environment names from deployments."""
        deployment_repo.create("prod", "apply")
        deployment_repo.create("dev", "plan")
        deployment_repo.create("prod", "plan")

        assert deployment_repo.list_environments() == ["dev", "prod"]


class TestStateManagerListEnvironments:
    """Tests for StateManager.list_environments."""

    def test_empty_db_returns_empty(self, state_manager: StateManager) -> None:
        """Empty DB returns empty list."""
        assert state_manager.list_environments() == []

    def test_resources_only_envs(self, state_manager: StateManager) -> None:
        """Environments from resources only are returned."""
        dep_id = state_manager.create_deployment("alpha", "apply")
        state_manager.track_resource(dep_id, "beta", "prov", "vm", "r1", ResourceState.ACTIVE)
        # "alpha" from deployment, "beta" from resource
        envs = state_manager.list_environments()
        assert "beta" in envs

    def test_deployments_only_envs(self, state_manager: StateManager) -> None:
        """Environments from deployments only are returned."""
        state_manager.create_deployment("gamma", "plan")
        assert "gamma" in state_manager.list_environments()

    def test_union_deduped_sorted(self, state_manager: StateManager) -> None:
        """Union of both sources is deduped and sorted."""
        dep_id = state_manager.create_deployment("dev", "apply")
        state_manager.track_resource(dep_id, "dev", "prov", "vm", "r1", ResourceState.ACTIVE)
        state_manager.create_deployment("prod", "plan")
        state_manager.track_resource(dep_id, "staging", "prov", "vm", "r2", ResourceState.ACTIVE)

        assert state_manager.list_environments() == ["dev", "prod", "staging"]

    def test_count_resources(self, state_manager: StateManager) -> None:
        """count_resources delegates correctly."""
        dep_id = state_manager.create_deployment("dev", "apply")
        state_manager.track_resource(dep_id, "dev", "prov", "vm", "r1", ResourceState.ACTIVE)
        state_manager.track_resource(dep_id, "dev", "prov", "vm", "r2", ResourceState.ACTIVE)

        assert state_manager.count_resources("dev") == 2
        assert state_manager.count_resources("nonexistent") == 0
