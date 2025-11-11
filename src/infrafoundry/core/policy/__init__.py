"""Policy enforcement package for infrastructure deployments.

This package provides a pluggable policy engine for enforcing various
policies on infrastructure resources before deployment.

Main exports:
    - PolicyEngine: Main engine for policy evaluation
    - Policy: Policy definition
    - PolicyViolation: Represents a policy violation
    - PolicyLevel: Enforcement levels (ERROR, WARNING, INFO)
    - PolicyType: Types of policies (RESOURCE_LIMIT, NAMING_CONVENTION, etc.)

Example:
    >>> from infrafoundry.core.policy import PolicyEngine, PolicyLevel
    >>> engine = PolicyEngine(policy_dir=Path("policies"))
    >>> violations = engine.evaluate_resources(resources, "prod")
    >>> errors = [v for v in violations if v.level == PolicyLevel.ERROR]
"""

from .engine import PolicyEngine
from .models import Policy, PolicyLevel, PolicyType, PolicyViolation

__all__ = [
    "PolicyEngine",
    "Policy",
    "PolicyViolation",
    "PolicyLevel",
    "PolicyType",
]
