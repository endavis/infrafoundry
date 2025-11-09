"""Policy enforcement for infrastructure deployments."""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class PolicyLevel(Enum):
    """Policy enforcement levels."""

    ERROR = "error"  # Block deployment
    WARNING = "warning"  # Allow but warn
    INFO = "info"  # Informational only


class PolicyType(Enum):
    """Types of policies that can be enforced."""

    RESOURCE_LIMIT = "resource_limit"  # Limit resource specs (CPU, memory, etc.)
    NAMING_CONVENTION = "naming_convention"  # Enforce naming patterns
    REQUIRED_TAGS = "required_tags"  # Require specific tags
    ALLOWED_PROVIDERS = "allowed_providers"  # Restrict which providers can be used
    ALLOWED_REGIONS = "allowed_regions"  # Restrict deployment regions


@dataclass
class PolicyViolation:
    """Represents a policy violation."""

    policy_name: str
    policy_type: PolicyType
    level: PolicyLevel
    resource_name: str
    provider: str
    message: str
    details: dict[str, Any] | None = None


@dataclass
class Policy:
    """Represents a single policy."""

    name: str
    description: str
    type: PolicyType
    level: PolicyLevel
    enabled: bool
    rules: dict[str, Any]
    environments: list[str] | None = None  # None = all environments


class PolicyEngine:
    """Evaluates policies against infrastructure configurations."""

    def __init__(self, policy_dir: Path | None = None):
        """Initialize policy engine.

        Args:
            policy_dir: Directory containing policy files (defaults to ./policies)
        """
        self.policy_dir = policy_dir or Path("policies")
        self.policies: list[Policy] = []
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

            # Evaluate based on policy type
            if policy.type == PolicyType.RESOURCE_LIMIT:
                violations.extend(self._check_resource_limits(policy, resources))
            elif policy.type == PolicyType.NAMING_CONVENTION:
                violations.extend(self._check_naming_conventions(policy, resources))
            elif policy.type == PolicyType.REQUIRED_TAGS:
                violations.extend(self._check_required_tags(policy, resources))
            elif policy.type == PolicyType.ALLOWED_PROVIDERS:
                violations.extend(self._check_allowed_providers(policy, resources))

        return violations

    def _check_resource_limits(self, policy: Policy, resources: list[Any]) -> list[PolicyViolation]:
        """Check if resources exceed defined limits."""
        violations = []
        limits = policy.rules.get("limits", {})

        for resource in resources:
            config = resource.config if hasattr(resource, "config") else {}

            # Check CPU limit
            if "max_cpu" in limits:
                cpu = config.get("cores") or config.get("cpu")
                if cpu and cpu > limits["max_cpu"]:
                    violations.append(
                        PolicyViolation(
                            policy_name=policy.name,
                            policy_type=policy.type,
                            level=policy.level,
                            resource_name=resource.name,
                            provider=resource.provider,
                            message=f"CPU cores ({cpu}) exceeds limit ({limits['max_cpu']})",
                            details={"actual": cpu, "limit": limits["max_cpu"]},
                        )
                    )

            # Check memory limit
            if "max_memory_mb" in limits:
                memory = config.get("memory")
                if memory and memory > limits["max_memory_mb"]:
                    violations.append(
                        PolicyViolation(
                            policy_name=policy.name,
                            policy_type=policy.type,
                            level=policy.level,
                            resource_name=resource.name,
                            provider=resource.provider,
                            message=(
                                f"Memory ({memory}MB) exceeds limit ({limits['max_memory_mb']}MB)"
                            ),
                            details={
                                "actual": memory,
                                "limit": limits["max_memory_mb"],
                            },
                        )
                    )

        return violations

    def _check_naming_conventions(
        self, policy: Policy, resources: list[Any]
    ) -> list[PolicyViolation]:
        """Check if resource names match required patterns."""
        violations = []
        patterns = policy.rules.get("patterns", {})

        for resource in resources:
            # Check if there's a pattern for this resource type
            pattern_key = f"{resource.provider}:{resource.type}"
            if pattern_key in patterns or "*" in patterns:
                pattern_str = patterns.get(pattern_key) or patterns.get("*")
                try:
                    pattern = re.compile(pattern_str)
                    if not pattern.match(resource.name):
                        violations.append(
                            PolicyViolation(
                                policy_name=policy.name,
                                policy_type=policy.type,
                                level=policy.level,
                                resource_name=resource.name,
                                provider=resource.provider,
                                message=f"Name does not match pattern: {pattern_str}",
                                details={"pattern": pattern_str, "name": resource.name},
                            )
                        )
                except re.error as e:
                    print(f"Warning: Invalid regex pattern {pattern_str}: {e}")

        return violations

    def _check_required_tags(self, policy: Policy, resources: list[Any]) -> list[PolicyViolation]:
        """Check if resources have required tags."""
        violations = []
        required_tags = policy.rules.get("tags", [])

        for resource in resources:
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
                violations.append(
                    PolicyViolation(
                        policy_name=policy.name,
                        policy_type=policy.type,
                        level=policy.level,
                        resource_name=resource.name,
                        provider=resource.provider,
                        message=f"Missing required tags: {', '.join(missing_tags)}",
                        details={"missing": list(missing_tags), "has": list(resource_tags)},
                    )
                )

        return violations

    def _check_allowed_providers(
        self, policy: Policy, resources: list[Any]
    ) -> list[PolicyViolation]:
        """Check if only allowed providers are used."""
        violations = []
        allowed = policy.rules.get("allowed", [])

        if not allowed:
            return violations

        for resource in resources:
            if resource.provider not in allowed:
                violations.append(
                    PolicyViolation(
                        policy_name=policy.name,
                        policy_type=policy.type,
                        level=policy.level,
                        resource_name=resource.name,
                        provider=resource.provider,
                        message=f"Provider '{resource.provider}' is not allowed",
                        details={"allowed": allowed, "actual": resource.provider},
                    )
                )

        return violations

    def get_policy(self, name: str) -> Policy | None:
        """Get a specific policy by name."""
        for policy in self.policies:
            if policy.name == name:
                return policy
        return None

    def get_policies_for_environment(self, environment: str) -> list[Policy]:
        """Get all policies that apply to an environment."""
        return [
            p
            for p in self.policies
            if p.enabled and (p.environments is None or environment in p.environments)
        ]
