"""Built-in test assertions for infrastructure testing."""

from __future__ import annotations

import re
from typing import Any, override

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.testing.framework import InfraTest, InfraTestResult


class AssertResourceExists(InfraTest):
    """Assert that a specific resource exists."""

    def __init__(self, resource_name: str, resource_type: str | None = None) -> None:
        """Initialize assertion.

        Args:
            resource_name: Name of resource to find
            resource_type: Optional type to filter by
        """
        super().__init__(
            f"resource_exists_{resource_name}",
            f"Assert resource '{resource_name}' exists",
        )
        self.resource_name = resource_name
        self.resource_type = resource_type

    @override
    def run(
        self,
        resources: list[ResourceConfig],
        env_config: dict[str, Any],
    ) -> InfraTestResult:
        """Check if resource exists."""
        for resource in resources:
            if resource.name == self.resource_name:
                if self.resource_type and resource.type != self.resource_type:
                    continue
                return self.pass_test(f"Resource '{self.resource_name}' found")

        return self.fail_test(
            f"Resource '{self.resource_name}' not found",
            details={"searched_type": self.resource_type},
        )


class AssertResourceCount(InfraTest):
    """Assert resource count is within expected range."""

    def __init__(
        self,
        resource_type: str | None = None,
        provider: str | None = None,
        min_count: int | None = None,
        max_count: int | None = None,
        exact_count: int | None = None,
    ) -> None:
        """Initialize assertion.

        Args:
            resource_type: Filter by resource type
            provider: Filter by provider
            min_count: Minimum expected count
            max_count: Maximum expected count
            exact_count: Exact expected count (overrides min/max)
        """
        name_parts = ["resource_count"]
        if provider:
            name_parts.append(provider)
        if resource_type:
            name_parts.append(resource_type)

        super().__init__(
            "_".join(name_parts),
            f"Assert resource count for {resource_type or 'all'} resources",
        )
        self.resource_type = resource_type
        self.provider = provider
        self.min_count = min_count
        self.max_count = max_count
        self.exact_count = exact_count

    @override
    def run(
        self,
        resources: list[ResourceConfig],
        env_config: dict[str, Any],
    ) -> InfraTestResult:
        """Check resource count."""
        filtered = resources
        if self.resource_type:
            filtered = [r for r in filtered if r.type == self.resource_type]
        if self.provider:
            filtered = [r for r in filtered if r.provider == self.provider]

        count = len(filtered)

        if self.exact_count is not None:
            if count == self.exact_count:
                return self.pass_test(f"Resource count is {count} (expected {self.exact_count})")
            return self.fail_test(
                f"Resource count is {count}, expected exactly {self.exact_count}",
                details={"actual": count, "expected": self.exact_count},
            )

        if self.min_count is not None and count < self.min_count:
            return self.fail_test(
                f"Resource count {count} is below minimum {self.min_count}",
                details={"actual": count, "minimum": self.min_count},
            )

        if self.max_count is not None and count > self.max_count:
            return self.fail_test(
                f"Resource count {count} exceeds maximum {self.max_count}",
                details={"actual": count, "maximum": self.max_count},
            )

        return self.pass_test(f"Resource count {count} is within expected range")


class AssertNoDuplicateNames(InfraTest):
    """Assert no duplicate resource names exist."""

    def __init__(self, resource_type: str | None = None, provider: str | None = None) -> None:
        """Initialize assertion.

        Args:
            resource_type: Filter by resource type
            provider: Filter by provider
        """
        name_parts = ["no_duplicate_names"]
        if provider:
            name_parts.append(provider)
        if resource_type:
            name_parts.append(resource_type)

        super().__init__(
            "_".join(name_parts),
            f"Assert no duplicate names for {resource_type or 'all'} resources",
        )
        self.resource_type = resource_type
        self.provider = provider

    @override
    def run(
        self,
        resources: list[ResourceConfig],
        env_config: dict[str, Any],
    ) -> InfraTestResult:
        """Check for duplicate names."""
        filtered = resources
        if self.resource_type:
            filtered = [r for r in filtered if r.type == self.resource_type]
        if self.provider:
            filtered = [r for r in filtered if r.provider == self.provider]

        names: dict[str, int] = {}
        for resource in filtered:
            names[resource.name] = names.get(resource.name, 0) + 1

        duplicates = {name: count for name, count in names.items() if count > 1}

        if duplicates:
            return self.fail_test(
                f"Found {len(duplicates)} duplicate resource names",
                details={"duplicates": duplicates},
            )

        return self.pass_test(f"No duplicate names found among {len(filtered)} resources")


class AssertReferencesExist(InfraTest):
    """Assert that all resource references point to existing resources."""

    def __init__(self, reference_field: str, target_type: str) -> None:
        """Initialize assertion.

        Args:
            reference_field: Config field containing the reference
            target_type: Resource type the reference should point to
        """
        super().__init__(
            f"references_exist_{reference_field}_to_{target_type}",
            f"Assert '{reference_field}' references exist as '{target_type}'",
        )
        self.reference_field = reference_field
        self.target_type = target_type

    @override
    def run(
        self,
        resources: list[ResourceConfig],
        env_config: dict[str, Any],
    ) -> InfraTestResult:
        """Check that references point to existing resources."""
        # Collect target resource names
        target_names = {r.name for r in resources if r.type == self.target_type}

        # Find all references
        missing_refs: list[tuple[str, str]] = []
        for resource in resources:
            ref_value = resource.config.get(self.reference_field)
            if ref_value and ref_value not in target_names:
                missing_refs.append((resource.name, ref_value))

        if missing_refs:
            return self.fail_test(
                f"Found {len(missing_refs)} missing references",
                details={
                    "missing": [{"resource": r, "references": ref} for r, ref in missing_refs],
                    "available_targets": list(target_names),
                },
            )

        return self.pass_test("All references point to existing resources")


class AssertConfigHasKey(InfraTest):
    """Assert that resources have a required config key."""

    def __init__(
        self,
        config_key: str,
        resource_type: str | None = None,
        provider: str | None = None,
    ) -> None:
        """Initialize assertion.

        Args:
            config_key: Config key that must be present
            resource_type: Filter by resource type
            provider: Filter by provider
        """
        name_parts = ["config_has_key", config_key]
        if provider:
            name_parts.append(provider)
        if resource_type:
            name_parts.append(resource_type)

        super().__init__(
            "_".join(name_parts),
            f"Assert config key '{config_key}' exists",
        )
        self.config_key = config_key
        self.resource_type = resource_type
        self.provider = provider

    @override
    def run(
        self,
        resources: list[ResourceConfig],
        env_config: dict[str, Any],
    ) -> InfraTestResult:
        """Check that config key exists."""
        filtered = resources
        if self.resource_type:
            filtered = [r for r in filtered if r.type == self.resource_type]
        if self.provider:
            filtered = [r for r in filtered if r.provider == self.provider]

        missing: list[str] = []
        for resource in filtered:
            if self.config_key not in resource.config:
                missing.append(resource.name)

        if missing:
            return self.fail_test(
                f"{len(missing)} resources missing config key '{self.config_key}'",
                details={"missing_in": missing},
            )

        return self.pass_test(f"All {len(filtered)} resources have config key '{self.config_key}'")


class AssertConfigMatches(InfraTest):
    """Assert that config values match a pattern or value."""

    def __init__(
        self,
        config_key: str,
        pattern: str | None = None,
        expected_value: Any = None,
        resource_type: str | None = None,
        provider: str | None = None,
    ) -> None:
        """Initialize assertion.

        Args:
            config_key: Config key to check
            pattern: Regex pattern to match (if checking string)
            expected_value: Exact value to match (takes precedence over pattern)
            resource_type: Filter by resource type
            provider: Filter by provider
        """
        name_parts = ["config_matches", config_key]
        if provider:
            name_parts.append(provider)
        if resource_type:
            name_parts.append(resource_type)

        super().__init__(
            "_".join(name_parts),
            f"Assert config '{config_key}' matches expected value/pattern",
        )
        self.config_key = config_key
        self.pattern = pattern
        self.expected_value = expected_value
        self.resource_type = resource_type
        self.provider = provider

    @override
    def run(
        self,
        resources: list[ResourceConfig],
        env_config: dict[str, Any],
    ) -> InfraTestResult:
        """Check that config values match."""
        filtered = resources
        if self.resource_type:
            filtered = [r for r in filtered if r.type == self.resource_type]
        if self.provider:
            filtered = [r for r in filtered if r.provider == self.provider]

        mismatches: list[dict[str, Any]] = []
        for resource in filtered:
            value = resource.config.get(self.config_key)
            if value is None:
                continue  # AssertConfigHasKey handles missing keys

            if self.expected_value is not None:
                if value != self.expected_value:
                    mismatches.append(
                        {
                            "resource": resource.name,
                            "actual": value,
                            "expected": self.expected_value,
                        }
                    )
            elif self.pattern and (not isinstance(value, str) or not re.match(self.pattern, value)):
                mismatches.append(
                    {
                        "resource": resource.name,
                        "actual": value,
                        "pattern": self.pattern,
                    }
                )

        if mismatches:
            return self.fail_test(
                f"{len(mismatches)} resources have mismatched config values",
                details={"mismatches": mismatches},
            )

        return self.pass_test(f"All {len(filtered)} resources have matching config values")


# Convenience functions for creating assertions
def assert_resource_exists(
    resource_name: str, resource_type: str | None = None
) -> AssertResourceExists:
    """Create a resource existence assertion."""
    return AssertResourceExists(resource_name, resource_type)


def assert_resource_count(
    resource_type: str | None = None,
    provider: str | None = None,
    min_count: int | None = None,
    max_count: int | None = None,
    exact_count: int | None = None,
) -> AssertResourceCount:
    """Create a resource count assertion."""
    return AssertResourceCount(resource_type, provider, min_count, max_count, exact_count)


def assert_no_duplicate_names(
    resource_type: str | None = None, provider: str | None = None
) -> AssertNoDuplicateNames:
    """Create a no-duplicate-names assertion."""
    return AssertNoDuplicateNames(resource_type, provider)


def assert_references_exist(reference_field: str, target_type: str) -> AssertReferencesExist:
    """Create a reference existence assertion."""
    return AssertReferencesExist(reference_field, target_type)


def assert_config_has_key(
    config_key: str,
    resource_type: str | None = None,
    provider: str | None = None,
) -> AssertConfigHasKey:
    """Create a config key existence assertion."""
    return AssertConfigHasKey(config_key, resource_type, provider)


def assert_config_matches(
    config_key: str,
    pattern: str | None = None,
    expected_value: Any = None,
    resource_type: str | None = None,
    provider: str | None = None,
) -> AssertConfigMatches:
    """Create a config value matching assertion."""
    return AssertConfigMatches(config_key, pattern, expected_value, resource_type, provider)
