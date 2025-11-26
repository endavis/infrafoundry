"""Base policy evaluator abstract class."""

from abc import ABC, abstractmethod
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
