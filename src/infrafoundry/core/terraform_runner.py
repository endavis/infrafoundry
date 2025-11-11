"""Terraform execution and management (legacy compatibility).

This module provides backward compatibility. New code should import from:
    from infrafoundry.core.runners import TerraformRunner
"""

# Import from new location for backward compatibility
from infrafoundry.core.runners.terraform_runner import TerraformRunner  # noqa: F401

__all__ = ["TerraformRunner"]
