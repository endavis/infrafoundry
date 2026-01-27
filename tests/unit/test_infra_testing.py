"""Unit tests for infrastructure testing framework."""

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.testing import (
    InfraTestResult,
    InfraTestRunner,
    InfraTestSuite,
    TestStatus,
    assert_config_has_key,
    assert_config_matches,
    assert_no_duplicate_names,
    assert_references_exist,
    assert_resource_count,
    assert_resource_exists,
)
from infrafoundry.core.testing.framework import FunctionalTest


class TestTestStatus:
    """Tests for TestStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert TestStatus.PASSED.value == "passed"
        assert TestStatus.FAILED.value == "failed"
        assert TestStatus.SKIPPED.value == "skipped"
        assert TestStatus.ERROR.value == "error"


class TestInfraTestResult:
    """Tests for InfraTestResult dataclass."""

    def test_create_result(self):
        """Test creating a test result."""
        result = InfraTestResult(
            test_name="my_test",
            status=TestStatus.PASSED,
            message="Test passed",
            duration_seconds=1.5,
        )
        assert result.test_name == "my_test"
        assert result.passed is True
        assert result.duration_seconds == 1.5

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = InfraTestResult(
            test_name="test1",
            status=TestStatus.FAILED,
            message="Something failed",
            details={"error": "details"},
        )
        d = result.to_dict()
        assert d["test_name"] == "test1"
        assert d["status"] == "failed"
        assert d["details"]["error"] == "details"


class TestInfraTestSuite:
    """Tests for InfraTestSuite class."""

    def test_create_suite(self):
        """Test creating a test suite."""
        suite = InfraTestSuite(name="my_suite", description="Test suite")
        assert suite.name == "my_suite"
        assert len(suite.tests) == 0

    def test_add_test(self):
        """Test adding tests to suite."""
        suite = InfraTestSuite(name="suite")
        suite.add_test(assert_no_duplicate_names())
        assert len(suite.tests) == 1

    def test_add_functional_test(self):
        """Test adding functional test to suite."""
        suite = InfraTestSuite(name="suite")

        def my_test(resources: list[ResourceConfig], env: dict[str, Any]) -> tuple[bool, str]:
            return True, "Passed"

        suite.add_functional_test("func_test", "A functional test", my_test)
        assert len(suite.tests) == 1
        assert suite.tests[0].name == "func_test"


class TestFunctionalTest:
    """Tests for FunctionalTest class."""

    def test_passing_functional_test(self):
        """Test functional test that passes."""

        def test_func(resources: list[ResourceConfig], env: dict[str, Any]) -> tuple[bool, str]:
            return True, "All good"

        test = FunctionalTest("my_test", "Test description", test_func)
        result = test.run([], {})
        assert result.passed is True
        assert result.message == "All good"

    def test_failing_functional_test(self):
        """Test functional test that fails."""

        def test_func(resources: list[ResourceConfig], env: dict[str, Any]) -> tuple[bool, str]:
            return False, "Something wrong"

        test = FunctionalTest("my_test", "Test description", test_func)
        result = test.run([], {})
        assert result.passed is False
        assert result.message == "Something wrong"

    def test_error_in_functional_test(self):
        """Test functional test that raises exception."""

        def test_func(resources: list[ResourceConfig], env: dict[str, Any]) -> tuple[bool, str]:
            raise ValueError("Test error")

        test = FunctionalTest("my_test", "Test description", test_func)
        result = test.run([], {})
        assert result.status == TestStatus.ERROR
        assert "Test error" in result.message


class TestInfraTestRunner:
    """Tests for InfraTestRunner class."""

    def test_runner_init(self):
        """Test runner initialization."""
        runner = InfraTestRunner()
        assert len(runner.suites) == 0
        assert len(runner._builtin_tests) == 0

    def test_runner_add_suite(self):
        """Test adding suite to runner."""
        runner = InfraTestRunner()
        suite = InfraTestSuite(name="test_suite")
        runner.add_suite(suite)
        assert len(runner.suites) == 1

    def test_runner_run_empty(self):
        """Test running with no tests."""
        runner = InfraTestRunner()
        results = runner.run([], {})
        assert results["passed"] is True
        assert results["summary"]["total"] == 0

    def test_runner_run_with_tests(self):
        """Test running tests."""
        runner = InfraTestRunner()
        runner.add_test(assert_no_duplicate_names())

        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={}),
            ResourceConfig(provider="test", type="vm", name="vm2", config={}),
        ]

        results = runner.run(resources, {})
        assert results["passed"] is True
        assert results["summary"]["passed"] == 1

    def test_runner_filter_tests(self):
        """Test filtering tests by name."""
        runner = InfraTestRunner()
        runner.add_test(assert_no_duplicate_names())
        runner.add_test(assert_resource_count(min_count=1))

        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={}),
        ]

        # Run only the duplicate names test
        results = runner.run(resources, {}, test_filter=["no_duplicate_names"])
        assert results["summary"]["total"] == 1

    def test_runner_cleanup(self):
        """Test cleanup method."""
        runner = InfraTestRunner()
        runner.cleanup()  # Should not raise


class TestAssertResourceExists:
    """Tests for assert_resource_exists."""

    def test_resource_found(self):
        """Test when resource exists."""
        test = assert_resource_exists("my_vm")
        resources = [
            ResourceConfig(provider="test", type="vm", name="my_vm", config={}),
        ]
        result = test.run(resources, {})
        assert result.passed is True

    def test_resource_not_found(self):
        """Test when resource doesn't exist."""
        test = assert_resource_exists("missing_vm")
        resources = [
            ResourceConfig(provider="test", type="vm", name="my_vm", config={}),
        ]
        result = test.run(resources, {})
        assert result.passed is False

    def test_resource_with_type_filter(self):
        """Test filtering by resource type."""
        test = assert_resource_exists("my_vm", resource_type="vm")
        resources = [
            ResourceConfig(provider="test", type="network", name="my_vm", config={}),
        ]
        result = test.run(resources, {})
        assert result.passed is False  # Wrong type


class TestAssertResourceCount:
    """Tests for assert_resource_count."""

    def test_exact_count_match(self):
        """Test exact count matching."""
        test = assert_resource_count(exact_count=2)
        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={}),
            ResourceConfig(provider="test", type="vm", name="vm2", config={}),
        ]
        result = test.run(resources, {})
        assert result.passed is True

    def test_exact_count_mismatch(self):
        """Test exact count not matching."""
        test = assert_resource_count(exact_count=3)
        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={}),
            ResourceConfig(provider="test", type="vm", name="vm2", config={}),
        ]
        result = test.run(resources, {})
        assert result.passed is False

    def test_min_count(self):
        """Test minimum count."""
        test = assert_resource_count(min_count=1)
        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={}),
        ]
        result = test.run(resources, {})
        assert result.passed is True

    def test_max_count_exceeded(self):
        """Test maximum count exceeded."""
        test = assert_resource_count(max_count=1)
        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={}),
            ResourceConfig(provider="test", type="vm", name="vm2", config={}),
        ]
        result = test.run(resources, {})
        assert result.passed is False


class TestAssertNoDuplicateNames:
    """Tests for assert_no_duplicate_names."""

    def test_no_duplicates(self):
        """Test with no duplicates."""
        test = assert_no_duplicate_names()
        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={}),
            ResourceConfig(provider="test", type="vm", name="vm2", config={}),
        ]
        result = test.run(resources, {})
        assert result.passed is True

    def test_with_duplicates(self):
        """Test with duplicate names."""
        test = assert_no_duplicate_names()
        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={}),
            ResourceConfig(provider="test", type="vm", name="vm1", config={}),
        ]
        result = test.run(resources, {})
        assert result.passed is False
        assert "duplicates" in result.details


class TestAssertReferencesExist:
    """Tests for assert_references_exist."""

    def test_valid_references(self):
        """Test when all references exist."""
        test = assert_references_exist("network", "networks")
        resources = [
            ResourceConfig(provider="test", type="networks", name="my_net", config={}),
            ResourceConfig(provider="test", type="vm", name="vm1", config={"network": "my_net"}),
        ]
        result = test.run(resources, {})
        assert result.passed is True

    def test_missing_reference(self):
        """Test when reference doesn't exist."""
        test = assert_references_exist("network", "networks")
        resources = [
            ResourceConfig(
                provider="test", type="vm", name="vm1", config={"network": "missing_net"}
            ),
        ]
        result = test.run(resources, {})
        assert result.passed is False


class TestAssertConfigHasKey:
    """Tests for assert_config_has_key."""

    def test_key_exists(self):
        """Test when config key exists."""
        test = assert_config_has_key("memory")
        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={"memory": 1024}),
        ]
        result = test.run(resources, {})
        assert result.passed is True

    def test_key_missing(self):
        """Test when config key is missing."""
        test = assert_config_has_key("memory")
        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={"cpu": 2}),
        ]
        result = test.run(resources, {})
        assert result.passed is False


class TestAssertConfigMatches:
    """Tests for assert_config_matches."""

    def test_exact_value_match(self):
        """Test matching exact value."""
        test = assert_config_matches("memory", expected_value=1024)
        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={"memory": 1024}),
        ]
        result = test.run(resources, {})
        assert result.passed is True

    def test_pattern_match(self):
        """Test matching regex pattern."""
        test = assert_config_matches("name", pattern=r"^prod-.*")
        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={"name": "prod-server"}),
        ]
        result = test.run(resources, {})
        assert result.passed is True

    def test_pattern_mismatch(self):
        """Test pattern not matching."""
        test = assert_config_matches("name", pattern=r"^prod-.*")
        resources = [
            ResourceConfig(provider="test", type="vm", name="vm1", config={"name": "dev-server"}),
        ]
        result = test.run(resources, {})
        assert result.passed is False
