"""Policy enforcement for infrastructure deployments.

DEPRECATED: This module has been refactored into a package structure.
All imports now come from the policy package.

For backward compatibility, all public APIs are re-exported here.
New code should import from infrafoundry.core.policy directly.
"""

# Re-export all public APIs from the policy package
from .policy import Policy, PolicyEngine, PolicyLevel, PolicyType, PolicyViolation

__all__ = [
    "PolicyEngine",
    "Policy",
    "PolicyViolation",
    "PolicyLevel",
    "PolicyType",
]
