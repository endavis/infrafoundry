"""Tests for runner execution order priorities."""

from unittest.mock import Mock

import pytest
from rich.console import Console

from infrafoundry.core.deployment_executor import DeploymentExecutor
from infrafoundry.core.runners import BaseRunner


class MockTerraformRunner(BaseRunner):
    tool_name = "terraform"
    priority = 0

    def is_available(self):
        return True

    def initialize(self, *args, **kwargs):
        return {}

    def plan(self, *args, **kwargs):
        return {}

    def apply(self, *args, **kwargs):
        return {}

    def destroy(self, *args, **kwargs):
        return {}

    def run(self, *args, **kwargs):
        return {"success": True}

    def get_resource_ids(self, *args, **kwargs):
        return {}

    def parse_plan_for_drift(self, *args, **kwargs):
        return {}


class MockAnsibleRunner(BaseRunner):
    tool_name = "ansible"
    priority = 50

    def is_available(self):
        return True

    def initialize(self, *args, **kwargs):
        return {}

    def plan(self, *args, **kwargs):
        return {}

    def apply(self, *args, **kwargs):
        return {}

    def destroy(self, *args, **kwargs):
        return {}

    def run(self, *args, **kwargs):
        return {"success": True}

    def get_resource_ids(self, *args, **kwargs):
        return {}

    def parse_plan_for_drift(self, *args, **kwargs):
        return {}


class MockPyInfraRunner(BaseRunner):
    tool_name = "pyinfra"
    priority = 50

    def is_available(self):
        return True

    def initialize(self, *args, **kwargs):
        return {}

    def plan(self, *args, **kwargs):
        return {}

    def apply(self, *args, **kwargs):
        return {}

    def destroy(self, *args, **kwargs):
        return {}

    def run(self, *args, **kwargs):
        return {"success": True}

    def get_resource_ids(self, *args, **kwargs):
        return {}

    def parse_plan_for_drift(self, *args, **kwargs):
        return {}


@pytest.fixture
def executor():
    runner_registry = Mock()
    runner_registry.list_runners.return_value = ["terraform", "ansible", "pyinfra"]

    # Mock create_runner to return instances of our mock classes
    def create_runner(name, **kwargs):
        if name == "terraform":
            return MockTerraformRunner()
        if name == "ansible":
            return MockAnsibleRunner()
        if name == "pyinfra":
            return MockPyInfraRunner()
        return None

    runner_registry.create_runner.side_effect = create_runner

    return DeploymentExecutor(
        runner_registry=runner_registry,
        state_manager=Mock(),
        event_manager=Mock(),
        providers={},
        console=Console(quiet=True),
    )


def test_default_priority_order(executor):
    """Test default order: Terraform(0) -> Ansible(50) -> PyInfra(50)."""
    sorted_runners = executor._get_sorted_runners()

    # Extract names
    names = [name for name, _ in sorted_runners]

    assert names[0] == "terraform"
    # Stability check: Ansible and PyInfra have same priority, should preserve registration order
    # Registration order was ["terraform", "ansible", "pyinfra"]
    assert names[1] == "ansible"
    assert names[2] == "pyinfra"


def test_priority_override(executor):
    """Test overriding priorities via config."""
    # Set priorities: PyInfra(40) -> Ansible(60) -> Terraform(0)
    # Order should be: Terraform(0) -> PyInfra(40) -> Ansible(60)
    executor.runner_priorities = {"pyinfra": 40, "ansible": 60}

    sorted_runners = executor._get_sorted_runners()
    names = [name for name, _ in sorted_runners]

    assert names[0] == "terraform"  # 0 (default)
    assert names[1] == "pyinfra"  # 40
    assert names[2] == "ansible"  # 60


def test_priority_override_terraform_last(executor):
    """Test forcing Terraform last (unlikely but possible)."""
    executor.runner_priorities = {"terraform": 100}

    sorted_runners = executor._get_sorted_runners()
    names = [name for name, _ in sorted_runners]

    # Ansible(50), PyInfra(50), Terraform(100)
    assert names[0] == "ansible"
    assert names[1] == "pyinfra"
    assert names[2] == "terraform"
