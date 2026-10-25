"""Unit tests for runner interface segregation."""

from pathlib import Path
from typing import Any, cast

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

    def test_implements_all_protocols(self) -> None:
        """TerraformRunner should implement all runner protocols."""
        runner = TerraformRunner()
        assert isinstance(cast(object, runner), Plannable)
        assert isinstance(cast(object, runner), Applyable)
        assert isinstance(cast(object, runner), Destroyable)
        assert isinstance(cast(object, runner), StateAware)
        assert isinstance(cast(object, runner), DriftDetectable)


class TestAnsibleRunnerInterfaces:
    """Test AnsibleRunner protocol compliance."""

    def test_implements_core_protocols(self) -> None:
        """AnsibleRunner should implement core operations."""
        runner = AnsibleRunner()
        assert isinstance(cast(object, runner), Plannable)  # via check mode
        assert isinstance(cast(object, runner), Applyable)

    def test_does_not_implement_unsupported_protocols(self) -> None:
        """AnsibleRunner should NOT implement unsupported operations."""
        runner = AnsibleRunner()
        assert not isinstance(cast(object, runner), Destroyable)
        assert not isinstance(cast(object, runner), StateAware)
        assert not isinstance(cast(object, runner), DriftDetectable)


class TestPyInfraRunnerInterfaces:
    """Test PyInfraRunner protocol compliance."""

    def test_implements_core_protocols(self) -> None:
        """PyInfraRunner should implement core operations."""
        runner = PyInfraRunner()
        assert isinstance(cast(object, runner), Plannable)  # via dry-run
        assert isinstance(cast(object, runner), Applyable)

    def test_does_not_implement_unsupported_protocols(self) -> None:
        """PyInfraRunner should NOT implement unsupported operations."""
        runner = PyInfraRunner()
        assert not isinstance(cast(object, runner), Destroyable)
        assert not isinstance(cast(object, runner), StateAware)
        assert not isinstance(cast(object, runner), DriftDetectable)


class TestBaseRunnerInterfaces:
    """Test BaseRunner protocol compliance (should be minimal)."""

    def test_base_runner_does_not_implement_optional_protocols(self) -> None:
        """BaseRunner should not implement optional protocols by default."""

        class ConcreteRunner(BaseRunner):
            @property
            def tool_name(self) -> str:
                return "test"

            def is_available(self) -> bool:
                return True

            def initialize(self, working_dir: Path, **kwargs: Any) -> dict[str, Any]:
                return {}

            def run(self, p: Any, c: Any, a: Any = False) -> dict[str, Any]:
                return {}

        runner = ConcreteRunner()

        assert not isinstance(cast(object, runner), Plannable)
        assert not isinstance(cast(object, runner), Applyable)
        assert not isinstance(cast(object, runner), Destroyable)
        assert not isinstance(cast(object, runner), StateAware)
        assert not isinstance(cast(object, runner), DriftDetectable)
