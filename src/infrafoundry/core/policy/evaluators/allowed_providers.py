"""Allowed providers policy evaluator."""

from typing import Any

from ..models import Policy, PolicyViolation
from .base_evaluator import PolicyEvaluator


class AllowedProvidersEvaluator(PolicyEvaluator):
    """Evaluates allowed providers policies."""

    def evaluate(self, policy: Policy, resources: list[Any]) -> list[PolicyViolation]:
        """Check if only allowed providers are used.

        Args:
            policy: Policy to evaluate
            resources: List of resources to check

        Returns:
            List of policy violations
        """
        violations = []
        allowed = policy.rules.get("allowed", [])

        if not allowed:
            return violations

        for resource in resources:
            if resource.provider not in allowed:
                violations.append(
                    self._create_violation(
                        policy=policy,
                        resource=resource,
                        message=f"Provider '{resource.provider}' is not allowed",
                        details={"allowed": allowed, "actual": resource.provider},
                    )
                )

        return violations
