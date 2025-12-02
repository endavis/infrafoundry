"""Required tags policy evaluator."""

from typing import Any

from ..models import Policy, PolicyViolation
from .base_evaluator import PolicyEvaluator


class RequiredTagsEvaluator(PolicyEvaluator):
    """Evaluates required tags policies."""

    def evaluate(self, policy: Policy, resources: list[Any]) -> list[PolicyViolation]:
        """Check if resources have required tags.

        Args:
            policy: Policy to evaluate
            resources: List of resources to check

        Returns:
            List of policy violations
        """
        required_tags = policy.rules.get("tags", [])

        def check_tags(resource: Any) -> PolicyViolation | None:
            config = resource.config if hasattr(resource, "config") else {}
            tags_val = config.get("tags", "")

            # Parse tags (handle both string and list formats)
            if isinstance(tags_val, str):
                resource_tags = {tag.strip() for tag in tags_val.split(",") if tag.strip()}
            elif isinstance(tags_val, list):
                resource_tags = {str(tag).strip() for tag in tags_val if tag}
            else:
                resource_tags = set()

            # Check for missing required tags
            missing_tags = set(required_tags) - resource_tags
            if missing_tags:
                return self._create_violation(
                    policy=policy,
                    resource=resource,
                    message=f"Missing required tags: {', '.join(missing_tags)}",
                    details={"missing": list(missing_tags), "has": list(resource_tags)},
                )
            return None

        return self._evaluate_resources(resources, check_tags)
