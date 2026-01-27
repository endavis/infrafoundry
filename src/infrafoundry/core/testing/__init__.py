"""Infrastructure testing framework for validating configurations.

This module provides a testing framework for infrastructure configurations,
including schema validation, test assertions, and mock providers.
"""

from infrafoundry.core.testing.assertions import (
    assert_config_has_key,
    assert_config_matches,
    assert_no_duplicate_names,
    assert_references_exist,
    assert_resource_count,
    assert_resource_exists,
)
from infrafoundry.core.testing.framework import (
    InfraTest,
    InfraTestResult,
    InfraTestRunner,
    InfraTestSuite,
    TestStatus,
)

__all__ = [
    "InfraTest",
    "InfraTestResult",
    "InfraTestRunner",
    "InfraTestSuite",
    "TestStatus",
    "assert_config_has_key",
    "assert_config_matches",
    "assert_no_duplicate_names",
    "assert_references_exist",
    "assert_resource_count",
    "assert_resource_exists",
]
