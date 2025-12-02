"""Resource limit policy evaluator."""

from typing import Any

from ..models import Policy, PolicyViolation
from .base_evaluator import PolicyEvaluator


class ResourceLimitEvaluator(PolicyEvaluator):
    """Evaluates resource limit policies (CPU, memory, etc.)."""

    def evaluate(self, policy: Policy, resources: list[Any]) -> list[PolicyViolation]:
        """Check if resources exceed defined limits.

        Args:
            policy: Policy to evaluate
            resources: List of resources to check

        Returns:
            List of policy violations
        """
        limits = policy.rules.get("limits", {})

        def check_limits(resource: Any) -> list[PolicyViolation]:
            resource_violations = []
            config = resource.config if hasattr(resource, "config") else {}

            # Check CPU limit
            if "max_cpu" in limits:
                cpu = config.get("cores") or config.get("cpu")
                if cpu and cpu > limits["max_cpu"]:
                    resource_violations.append(
                        self._create_violation(
                            policy=policy,
                            resource=resource,
                            message=f"CPU cores ({cpu}) exceeds limit ({limits['max_cpu']})",
                            details={"actual": cpu, "limit": limits["max_cpu"]},
                        )
                    )

            # Check memory limit
            if "max_memory_mb" in limits:
                memory = config.get("memory")
                if memory and memory > limits["max_memory_mb"]:
                    resource_violations.append(
                        self._create_violation(
                            policy=policy,
                            resource=resource,
                            message=(
                                f"Memory ({memory}MB) exceeds limit ({limits['max_memory_mb']}MB)"
                            ),
                            details={
                                "actual": memory,
                                "limit": limits["max_memory_mb"],
                            },
                        )
                    )

            return resource_violations

        return self._evaluate_resources(resources, check_limits)
