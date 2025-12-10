"""Unit tests for runner interface segregation."""

from infrafoundry.core.protocols import (
    Applyable,
    Destroyable,
    DriftDetectable,
    Plannable,
    StateAware,
)
from infrafoundry.core.runners.ansible_runner import AnsibleRunner
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.runners.pyinfra_runner import PyInfraRunner
from infrafoundry.core.runners.terraform_runner import TerraformRunner


class TestTerraformRunnerInterfaces:
    """Test TerraformRunner protocol compliance."""

    def test_implements_all_protocols(self):
        """TerraformRunner should implement all runner protocols."""
        runner = TerraformRunner()
        assert isinstance(runner, Plannable)
        assert isinstance(runner, Applyable)
        assert isinstance(runner, Destroyable)
        assert isinstance(runner, StateAware)
        assert isinstance(runner, DriftDetectable)


class TestAnsibleRunnerInterfaces:
    """Test AnsibleRunner protocol compliance."""

    def test_implements_core_protocols(self):
        """AnsibleRunner should implement core operations."""
        runner = AnsibleRunner()
        assert isinstance(runner, Plannable)  # via check mode
        assert isinstance(runner, Applyable)

    def test_does_not_implement_unsupported_protocols(self):
        """AnsibleRunner should NOT implement unsupported operations."""
        runner = AnsibleRunner()
        assert not isinstance(runner, Destroyable)
        assert not isinstance(runner, StateAware)
        assert not isinstance(runner, DriftDetectable)


class TestPyInfraRunnerInterfaces:
    """Test PyInfraRunner protocol compliance."""

    def test_implements_core_protocols(self):
        """PyInfraRunner should implement core operations."""
        runner = PyInfraRunner()
        assert isinstance(runner, Plannable)  # via dry-run
        assert isinstance(runner, Applyable)

    def test_does_not_implement_unsupported_protocols(self):
        """PyInfraRunner should NOT implement unsupported operations."""
        runner = PyInfraRunner()
        assert not isinstance(runner, Destroyable)
        assert not isinstance(runner, StateAware)
        assert not isinstance(runner, DriftDetectable)


class TestBaseRunnerInterfaces:
    """Test BaseRunner protocol compliance (should be minimal)."""

    def test_base_runner_does_not_implement_optional_protocols(self):
        """BaseRunner should not implement optional protocols by default."""

        class ConcreteRunner(BaseRunner):
            def tool_name(self):
                return "test"

            def is_available(self):
                return True

            def initialize(self, wd, **kw):
                return {}

            def run(self, p, c, a=False):
                return {}

        runner = ConcreteRunner()

        assert not isinstance(runner, Plannable)
        assert not isinstance(runner, Applyable)
        assert not isinstance(runner, Destroyable)
        assert not isinstance(runner, StateAware)
        assert not isinstance(runner, DriftDetectable)
