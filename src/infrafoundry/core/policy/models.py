"""Policy models and data structures."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


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
