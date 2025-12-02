"""Naming convention policy evaluator."""

import logging
import re
from typing import Any

from ..models import Policy, PolicyViolation
from .base_evaluator import PolicyEvaluator

logger = logging.getLogger(__name__)


class NamingConventionEvaluator(PolicyEvaluator):
    """Evaluates naming convention policies (regex patterns)."""

    def evaluate(self, policy: Policy, resources: list[Any]) -> list[PolicyViolation]:
        """Check if resource names match required patterns.

        Args:
            policy: Policy to evaluate
            resources: List of resources to check

        Returns:
            List of policy violations
        """
        patterns = policy.rules.get("patterns", {})

        def check_naming_convention(resource: Any) -> PolicyViolation | None:
            # Check if there's a pattern for this resource type
            pattern_key = f"{resource.provider}:{resource.type}"
            if pattern_key in patterns or "*" in patterns:
                pattern_str = patterns.get(pattern_key) or patterns.get("*")
                try:
                    pattern = re.compile(pattern_str)
                    if not pattern.match(resource.name):
                        return self._create_violation(
                            policy=policy,
                            resource=resource,
                            message=f"Name does not match pattern: {pattern_str}",
                            details={"pattern": pattern_str, "name": resource.name},
                        )
                except re.error as e:
                    logger.warning(f"Invalid regex pattern {pattern_str}: {e}")
            return None

        return self._evaluate_resources(resources, check_naming_convention)
