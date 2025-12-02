"""Base policy evaluator abstract class."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from infrafoundry.core.policy.models import Policy, PolicyViolation


class PolicyEvaluator(ABC):
    """Base class for policy evaluators.

    Each evaluator implements logic for evaluating a specific policy type.
    """

    @abstractmethod
    def evaluate(self, policy: Policy, resources: list[Any]) -> list[PolicyViolation]:
        """Evaluate resources against a policy.

        Args:
            policy: Policy to evaluate
            resources: List of resources to check

        Returns:
            List of policy violations found
        """
        pass

    def _evaluate_resources(
        self,
        resources: list[Any],
        check_resource: Callable[[Any], PolicyViolation | list[PolicyViolation] | None],
    ) -> list[PolicyViolation]:
        """Helper method to reduce boilerplate when evaluating resources.

        This method handles the common pattern of iterating through resources,
        checking each one, and collecting violations.

        Args:
            resources: List of resources to check
            check_resource: Callable that checks a single resource and returns:
                - None if no violation
                - A single PolicyViolation
                - A list of PolicyViolations

        Returns:
            List of all policy violations found

        Example:
            >>> def check_cpu(resource):
            ...     if resource.cpu > 8:
            ...         return self._create_violation(...)
            ...     return None
            >>> violations = self._evaluate_resources(resources, check_cpu)
        """
        violations = []
        for resource in resources:
            result = check_resource(resource)
            if result is not None:
                if isinstance(result, list):
                    violations.extend(result)
                else:
                    violations.append(result)
        return violations

    def _create_violation(
        self,
        policy: Policy,
        resource: Any,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> PolicyViolation:
        """Helper to create a PolicyViolation.

        Args:
            policy: Policy that was violated
            resource: Resource that violated the policy
            message: Violation message
            details: Additional violation details

        Returns:
            PolicyViolation object
        """
        return PolicyViolation(
            policy_name=policy.name,
            policy_type=policy.type,
            level=policy.level,
            resource_name=resource.name,
            provider=resource.provider,
            message=message,
            details=details,
        )
