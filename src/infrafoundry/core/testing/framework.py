"""Infrastructure testing framework core classes."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, override

from infrafoundry.core.base_manager import BaseManager
from infrafoundry.core.provider import ResourceConfig


class TestStatus(StrEnum):
    """Status of a test execution."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class InfraTestResult:
    """Result of a single infrastructure test."""

    test_name: str
    status: TestStatus
    message: str
    duration_seconds: float = 0.0
    details: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        """Check if test passed."""
        return self.status == TestStatus.PASSED

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "test_name": self.test_name,
            "status": self.status.value,
            "message": self.message,
            "duration_seconds": self.duration_seconds,
            "details": self.details,
        }


class InfraTest(ABC):
    """Base class for infrastructure tests.

    Subclass this to create custom infrastructure tests.

    Example:
        class MyTest(InfraTest):
            def __init__(self):
                super().__init__("my_test", "Check something important")

            def run(self, resources, env_config):
                # Your test logic here
                if condition:
                    return self.pass_test("Everything is good")
                return self.fail_test("Something is wrong")
    """

    def __init__(self, name: str, description: str) -> None:
        """Initialize test.

        Args:
            name: Unique test name
            description: Human-readable description
        """
        self.name = name
        self.description = description

    @abstractmethod
    def run(
        self,
        resources: list[ResourceConfig],
        env_config: dict[str, Any],
    ) -> InfraTestResult:
        """Run the test against resources.

        Args:
            resources: List of resource configurations
            env_config: Environment configuration dict

        Returns:
            InfraTestResult with pass/fail status
        """
        ...

    def pass_test(self, message: str, details: dict[str, Any] | None = None) -> InfraTestResult:
        """Create a passing test result."""
        return InfraTestResult(
            test_name=self.name,
            status=TestStatus.PASSED,
            message=message,
            details=details,
        )

    def fail_test(self, message: str, details: dict[str, Any] | None = None) -> InfraTestResult:
        """Create a failing test result."""
        return InfraTestResult(
            test_name=self.name,
            status=TestStatus.FAILED,
            message=message,
            details=details,
        )

    def skip_test(self, message: str) -> InfraTestResult:
        """Create a skipped test result."""
        return InfraTestResult(
            test_name=self.name,
            status=TestStatus.SKIPPED,
            message=message,
        )

    def error_test(self, message: str, details: dict[str, Any] | None = None) -> InfraTestResult:
        """Create an error test result."""
        return InfraTestResult(
            test_name=self.name,
            status=TestStatus.ERROR,
            message=message,
            details=details,
        )


class FunctionalTest(InfraTest):
    """Test that runs a function for validation.

    Allows creating tests from simple functions without subclassing.

    Example:
        def check_naming(resources, env_config):
            for r in resources:
                if not r.name.startswith("prod-"):
                    return False, f"Resource {r.name} doesn't follow naming convention"
            return True, "All resources follow naming convention"

        test = FunctionalTest("naming_convention", "Check naming", check_naming)
    """

    def __init__(
        self,
        name: str,
        description: str,
        test_func: Callable[[list[ResourceConfig], dict[str, Any]], tuple[bool, str]],
    ) -> None:
        """Initialize functional test.

        Args:
            name: Unique test name
            description: Human-readable description
            test_func: Function that takes (resources, env_config) and returns (passed, message)
        """
        super().__init__(name, description)
        self.test_func = test_func

    @override
    def run(
        self,
        resources: list[ResourceConfig],
        env_config: dict[str, Any],
    ) -> InfraTestResult:
        """Run the test function."""
        try:
            passed, message = self.test_func(resources, env_config)
            if passed:
                return self.pass_test(message)
            return self.fail_test(message)
        except Exception as exc:
            return self.error_test(f"Test error: {exc}")


@dataclass
class InfraTestSuite:
    """Collection of infrastructure tests.

    Example:
        suite = InfraTestSuite("production_checks")
        suite.add_test(NamingConventionTest())
        suite.add_test(ResourceLimitTest(max_vms=100))
    """

    name: str
    tests: list[InfraTest] = field(default_factory=list)
    description: str = ""

    def add_test(self, test: InfraTest) -> None:
        """Add a test to the suite."""
        self.tests.append(test)

    def add_functional_test(
        self,
        name: str,
        description: str,
        test_func: Callable[[list[ResourceConfig], dict[str, Any]], tuple[bool, str]],
    ) -> None:
        """Add a functional test to the suite."""
        self.tests.append(FunctionalTest(name, description, test_func))


class InfraTestRunner(BaseManager):
    """Runs infrastructure tests against configurations.

    Example:
        runner = InfraTestRunner()
        runner.add_suite(my_suite)
        results = runner.run(resources, env_config)
    """

    def __init__(self) -> None:
        """Initialize test runner."""
        super().__init__()
        self.suites: list[InfraTestSuite] = []
        self._builtin_tests: list[InfraTest] = []

    @override
    def cleanup(self) -> None:
        """Clean up test runner resources."""
        pass

    def add_suite(self, suite: InfraTestSuite) -> None:
        """Add a test suite to run."""
        self.suites.append(suite)

    def add_test(self, test: InfraTest) -> None:
        """Add a standalone test."""
        self._builtin_tests.append(test)

    def run(
        self,
        resources: list[ResourceConfig],
        env_config: dict[str, Any],
        test_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run all tests against the provided resources.

        Args:
            resources: List of resource configurations to test
            env_config: Environment configuration dict
            test_filter: Optional list of test names to run (runs all if None)

        Returns:
            Dict with test results and summary
        """
        all_results: list[InfraTestResult] = []
        start_time = time.time()

        # Collect all tests
        all_tests: list[InfraTest] = list(self._builtin_tests)
        for suite in self.suites:
            all_tests.extend(suite.tests)

        # Filter tests if specified
        if test_filter:
            all_tests = [t for t in all_tests if t.name in test_filter]

        # Run each test
        for test in all_tests:
            self._log_debug(f"Running test: {test.name}")
            test_start = time.time()

            try:
                result = test.run(resources, env_config)
                result.duration_seconds = time.time() - test_start
                all_results.append(result)

                if result.passed:
                    self._log_debug(f"  PASSED: {result.message}")
                else:
                    self._log_warning(f"  {result.status.value.upper()}: {result.message}")

            except Exception as exc:
                self._log_error(f"Test {test.name} raised exception: {exc}")
                all_results.append(
                    InfraTestResult(
                        test_name=test.name,
                        status=TestStatus.ERROR,
                        message=f"Exception: {exc}",
                        duration_seconds=time.time() - test_start,
                    )
                )

        total_duration = time.time() - start_time

        # Calculate summary
        passed = sum(1 for r in all_results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in all_results if r.status == TestStatus.FAILED)
        skipped = sum(1 for r in all_results if r.status == TestStatus.SKIPPED)
        errors = sum(1 for r in all_results if r.status == TestStatus.ERROR)

        return {
            "passed": failed == 0 and errors == 0,
            "results": [r.to_dict() for r in all_results],
            "summary": {
                "total": len(all_results),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "errors": errors,
            },
            "duration_seconds": total_duration,
        }
