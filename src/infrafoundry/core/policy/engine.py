"""Policy engine for evaluating policies against resources."""

from pathlib import Path
from typing import Any

import yaml

from .evaluators import (
    AllowedProvidersEvaluator,
    NamingConventionEvaluator,
    PolicyEvaluator,
    RequiredTagsEvaluator,
    ResourceLimitEvaluator,
)
from .models import Policy, PolicyLevel, PolicyType, PolicyViolation


class PolicyEngine:
    """Evaluates policies against infrastructure configurations.

    This engine loads policies from YAML files and evaluates resources
    using pluggable evaluators for each policy type.
    """

    def __init__(self, policy_dir: Path | None = None):
        """Initialize policy engine.

        Args:
            policy_dir: Directory containing policy files (defaults to ./policies)
        """
        self.policy_dir = policy_dir or Path("policies")
        self.policies: list[Policy] = []

        # Initialize evaluator registry
        self._evaluators: dict[PolicyType, PolicyEvaluator] = {
            PolicyType.RESOURCE_LIMIT: ResourceLimitEvaluator(),
            PolicyType.NAMING_CONVENTION: NamingConventionEvaluator(),
            PolicyType.REQUIRED_TAGS: RequiredTagsEvaluator(),
            PolicyType.ALLOWED_PROVIDERS: AllowedProvidersEvaluator(),
        }

        if self.policy_dir.exists():
            self._load_policies()

    def _load_policies(self) -> None:
        """Load policies from YAML files in policy directory."""
        for policy_file in self.policy_dir.glob("*.yaml"):
            try:
                with open(policy_file) as f:
                    data = yaml.safe_load(f)
                    if not data or "policies" not in data:
                        continue

                    for policy_data in data["policies"]:
                        policy = Policy(
                            name=policy_data["name"],
                            description=policy_data.get("description", ""),
                            type=PolicyType(policy_data["type"]),
                            level=PolicyLevel(policy_data.get("level", "error")),
                            enabled=policy_data.get("enabled", True),
                            rules=policy_data.get("rules", {}),
                            environments=policy_data.get("environments"),
                        )
                        self.policies.append(policy)
            except Exception as e:
                print(f"Warning: Failed to load policy file {policy_file}: {e}")

    def register_evaluator(self, policy_type: PolicyType, evaluator: PolicyEvaluator) -> None:
        """Register a custom evaluator for a policy type.

        Args:
            policy_type: Type of policy this evaluator handles
            evaluator: Evaluator instance
        """
        self._evaluators[policy_type] = evaluator

    def evaluate_resources(self, resources: list[Any], environment: str) -> list[PolicyViolation]:
        """Evaluate resources against all applicable policies.

        Args:
            resources: List of resources to evaluate
            environment: Environment name

        Returns:
            List of policy violations
        """
        violations = []

        for policy in self.policies:
            if not policy.enabled:
                continue

            # Check if policy applies to this environment
            if policy.environments and environment not in policy.environments:
                continue

            # Get evaluator for this policy type
            evaluator = self._evaluators.get(policy.type)
            if evaluator:
                violations.extend(evaluator.evaluate(policy, resources))
            else:
                print(f"Warning: No evaluator registered for policy type {policy.type}")

        return violations

    def get_policy(self, name: str) -> Policy | None:
        """Get a specific policy by name.

        Args:
            name: Policy name

        Returns:
            Policy if found, None otherwise
        """
        for policy in self.policies:
            if policy.name == name:
                return policy
        return None

    def get_policies_for_environment(self, environment: str) -> list[Policy]:
        """Get all policies that apply to an environment.

        Args:
            environment: Environment name

        Returns:
            List of applicable policies
        """
        return [
            p
            for p in self.policies
            if p.enabled and (p.environments is None or environment in p.environments)
        ]
